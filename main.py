from flask import Flask, request, jsonify, send_file, send_from_directory,url_for
import os

from logger import logger
from middleware.mysql import session
from middleware.mysql.models.audio_voice import VoiceSchema
from middleware.mysql.models.audio_position import PositionSchema
from importlib.resources import files

app = Flask(__name__)


from src.f5_tts.api import F5TTS
f5tts = F5TTS()


@app.route('/test', methods=['GET'])
def test():
    return jsonify({"message": "Test endpoint"}), 200

@app.route('/root/upload/<voicename>', methods=['POST'])
def upload_voice(voicename):
    with session() as conn:

        voice = conn.query(VoiceSchema).filter(VoiceSchema.name ==voicename).first()
        if voice:
            logger.error(f"Voice Name has already been used: {voicename}")
            return jsonify({"detail": "Voice Name has already been used"}), 409

        if 'files' not in request.files:
            return jsonify({"detail": "No file part"}), 400

        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({"detail": "No selected file"}), 400

        
        upload_dir = f"src/f5_tts/upload_audio/{voicename}"
        os.makedirs(upload_dir, exist_ok=True)
        for file in files:
            file.save(f"src/f5_tts/upload_audio/{voicename}/{file.filename}")

        voice_data= VoiceSchema(name=voicename,position=f"upload_audio/{voicename}/{file.filename}")

        conn.add(voice_data)
        conn.commit()

    return jsonify({"message": "Upload Success"}), 200
@app.route('/tts', methods=['POST'])
async def tts():
    voicename = request.form.get('voicename')
    content = request.form.get('content')

    with session() as conn:
        voice = conn.query(VoiceSchema).filter(VoiceSchema.name ==voicename).first()
        if not voice:
            return jsonify({"detail": "Voice not found"}), 404
        position = voice.position

        if not voicename or not content:
            return jsonify({"detail": "Missing 'voicename' or 'content'"}), 400
        
        position_data= conn.query(PositionSchema).filter(PositionSchema.content ==voicename+content).first()
        if position_data:
            return jsonify({"url": position_data.content_position}), 200
    

    import random
    name=voicename+content[0:5]+str(random.random())
    generated_audio_path = f"output_dir/{name}/"
    os.makedirs("src/f5_tts/"+generated_audio_path, exist_ok=True)

    logger.info(f"Generating audio for: {content}")

    try:
        f5tts.infer(
            ref_file=str(files("f5_tts").joinpath(position)),
            ref_text="",
            gen_text=content,
            file_wave=str(files("f5_tts").joinpath(f"{generated_audio_path}{name}.wav")),
            file_spect=str(files("f5_tts").joinpath(f"{generated_audio_path}{name}.png")),
            seed=-1  
        )

        logger.info(f"Generated audio saved to: {generated_audio_path}{name}.wav")
        audio_url = url_for('static_files', filename=f"{name}.wav", _external=True)

        with session() as conn:
            position_data = PositionSchema(content=voicename+content, content_position=audio_url)
            conn.add(position_data)
            conn.commit()

        return jsonify({"url": audio_url}), 200

    except Exception as e:
        return jsonify({"detail": f"Error generating audio: {str(e)}"}), 500
    
@app.route('/static/<filename>')
def static_files(filename):
    name, ext = os.path.splitext(filename)
    directory = f'src/f5_tts/output_dir/{name}'
    try:
        return send_from_directory(directory, filename)
    except FileNotFoundError:
        return jsonify({"detail": f"File not found: {directory,filename}"}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8175, debug=True)