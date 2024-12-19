from .base import BaseSchema
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

class VoiceSchema(BaseSchema):
    __tablename__ = "f5tts_voice"
    voice_id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), nullable=False)
    position: str = Column(String(255), nullable=False)
    create_at: datetime = Column(DateTime, default=datetime.now)