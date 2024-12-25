import asyncio
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager
import multiprocessing
from multiprocessing import current_process
import multiprocessing.resource_tracker
import multiprocessing.spawn
import multiprocessing.util
import os
import signal


# 第三方库导入
import numpy as np
import psutil
import soundfile as sf
import torch
from quart import Quart, request, Response, send_file,send_from_directory, url_for,jsonify, abort
from quart_cors import cors
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from logger import logger
from middleware.hash.hash import hash_string
from middleware.mysql import session
from middleware.mysql.models.audio_voice import VoiceSchema
from middleware.mysql.models.audio_position import PositionSchema
from middleware.redis import r
from importlib.resources import files

import torch
import dotenv
dotenv.load_dotenv()
host = os.getenv("URL", "0.0.0.0")

app = Quart(__name__)
scheduler = AsyncIOScheduler()
app = cors(app, allow_origin="*")
future_map = defaultdict(set)
task_control = Manager().dict({})

from src.f5_tts.api import F5TTS

def init_worker():
    global f5tts,infer
    f5tts = F5TTS()
    infer=f5tts.infer
    if not hasattr(f5tts, 'infer'):
        logger.error("f5tts 没有正确初始化，'infer' 方法不可用！")
    else:
        logger.info("f5tts 初始化成功")


# 初始化进程池
max_workers = 4
executor = ProcessPoolExecutor(
    max_workers=max_workers,
    initializer=init_worker,
    mp_context=multiprocessing.get_context("spawn"),
)
def dummy_workers():
    logger.info("预热所有进程...")
    dummy_futures = []

    for _ in range(max_workers):
        future = executor.submit(dummy_task)
        dummy_futures.append(future)
    for future in dummy_futures:
        future.result()
    logger.info("所有进程已完成初始化")

def dummy_task():
    logger.info("进程初始化完成")




@app.before_serving
async def startup():
    # 在app启动服务前启动scheduler
    scheduler.start()
@app.after_serving
async def shutdown():
    # 在app停止服务时关闭scheduler
    scheduler.shutdown()

@app.route('/test', methods=['GET'])
def test():
    return jsonify({"message": "Test endpoint"}), 200
@app.route('/root/upload/<voicename>', methods=['POST'])
def upload_voice(voicename):
    try:
        with session() as conn:
            voice = conn.query(VoiceSchema).filter(VoiceSchema.name == voicename).first()
            if voice:
                logger.error(f"Voice Name has already been used: {voicename}")
                return Response('{"detail": "Voice Name has already been used"}', status=409, mimetype='application/json')

            if 'files' not in request.files:
                return Response('{"detail": "No file part"}', status=400, mimetype='application/json')

            files = request.files.getlist('files')
            if not files or files[0].filename == '':
                return Response('{"detail": "No selected file"}', status=400, mimetype='application/json')

            upload_dir = f"src/f5_tts/upload_audio/{voicename}"
            os.makedirs(upload_dir, exist_ok=True)
            for file in files:
                file.save(f"src/f5_tts/upload_audio/{voicename}/{file.filename}")

            voice_data = VoiceSchema(name=voicename, position=f"upload_audio/{voicename}/{file.filename}")

            conn.add(voice_data)
            conn.commit()

        return Response('{"message": "Upload Success"}', status=200, mimetype='application/json')
    
    except Exception as e:
        logger.error(f"Error uploading voice: {str(e)}")
        return Response(f'{{"detail": "Error uploading voice: {str(e)}"}}', status=500, mimetype='application/json')

@app.route('/tts', methods=['POST'])
async def tts():
    form_data = await request.form
    voicename = form_data.get('voicename')
    content = form_data.get('content')


    res = await process_tts(content=content,voicename=voicename)


    return res

class TaskCancelledException(Exception):
    pass



async def process_tts(content, voicename):

    with session() as conn:
        voice = conn.query(VoiceSchema).filter(VoiceSchema.name == voicename).first()
        if not voice:
            return Response('{"detail": "Voice not found"}', status=404, mimetype='application/json')
        position = voice.position

        if not voicename or not content:
            return Response('{"detail": "Missing \'voicename\' or \'content\'}', status=400, mimetype='application/json')
        
        position_data = conn.query(PositionSchema).filter(PositionSchema.content == voicename + content).first()
        if position_data:
            return Response(f'{{"url": "{position_data.content_position}"}}', status=200, mimetype='application/json')
    
    import random
    name = voicename + content#+str(random.random())
    name = hash_string(name)
    generated_audio_path = f"output_dir/{name}/"
    os.makedirs("src/f5_tts/" + generated_audio_path, exist_ok=True)

    logger.info(f"Generating audio for: {content}")

    

    try:
        logger.info(f"tts_worker,id:{name} 开始推理...")

        loop = asyncio.get_event_loop()
        future = executor.submit(
            tts_run,
            ref_file=str(files("f5_tts").joinpath(position)),
            ref_text="",
            gen_text=content,
            file_wave=str(files("f5_tts").joinpath(f"{generated_audio_path}{name}.wav")),
            file_spect=str(files("f5_tts").joinpath(f"{generated_audio_path}{name}.png")),
            seed=-1 ,
            index=name,
            request_id=name,
            task_control_dict=task_control,
        )

        idx = await loop.run_in_executor(
            None, future.result
        )

        logger.info(f"Generated audio saved to: {generated_audio_path}{name}.wav")
        audio_url = f"http://{host}/static/{name}.wav"

        with session() as conn:
            position_data = PositionSchema(content=voicename + content, content_position=audio_url)
            conn.add(position_data)
            conn.commit()

        return {
            "url": audio_url
        }

    except Exception as e:
        raise abort(500, f"Error generating audio: {str(e)}")
    




def tts_run(
            ref_file:str,
            ref_text:str,
            gen_text:str,
            file_wave:str,
            file_spect:str,
            seed ,
            index:str,
            request_id:str,
            task_control_dict: dict = None
        ):


    logger.info(f"运行任务 {index},request_id {request_id}")

    try:
        pid = os.getpid()
        if task_control_dict[request_id]:
            logger.info(f"Worker {pid} ，任务{request_id}_{index}在执行前被取消")
            return index
    except Exception as e:
        logger.warning(f"failed to read task_control")


    try:
        logger.info(f"tts_worker,id:{index} 开始推理...")

        f5tts.infer(
            ref_file=ref_file,
            ref_text=ref_text,
            gen_text=gen_text,
            file_wave=file_wave,
            file_spect=file_spect,
            seed=seed 
        )

    except TaskCancelledException:
        logger.info(f"tts_worker,id:{index} 任务被取消")
        return index
    except Exception as e:
        logger.info(f"tts_worker,id:{index} 任务执行失败 {e}")
        raise





@app.route('/static/<filename>')
async def static_files(filename):
    name, ext = os.path.splitext(filename)
    directory = f'src/f5_tts/output_dir/{name}'
    try:
        return await send_from_directory(directory, filename)
    except FileNotFoundError:
        return Response(f'{{"detail": f"File not found: {directory,filename}"}}', status=404, mimetype='application/json')


def clean_up():
    logger.info("清理资源...")

    # 原有的清理代码...
    if "executor" in globals():
        executor.shutdown(wait=False, cancel_futures=True)

    # 获取当前进程及其所有子进程
    current_process = psutil.Process()
    children = current_process.children(recursive=True)

    # 终止所有子进程
    for child in children:
        try:
            logger.info(f"终止子进程 {child.pid}")
            child.terminate()
        except psutil.NoSuchProcess:
            continue

    # 等待子进程终止
    psutil.wait_procs(children, timeout=3)

    # 强制结束残留进程
    for child in children:
        try:
            if child.is_running():
                logger.info(f"强制终止子进程 {child.pid}")
                child.kill()
        except psutil.NoSuchProcess:
            continue

    # 清理资源追踪器
    multiprocessing.resource_tracker.getfd()
    multiprocessing.resource_tracker._resource_tracker = None

    # 清理全局资源
    multiprocessing.util._exit_function()

if __name__ == '__main__':
    dummy_workers()
    try:
        app.run(host='0.0.0.0', port=8175,debug=False)
    finally:
        clean_up()
        logger.info("tts服务器已关闭")
    