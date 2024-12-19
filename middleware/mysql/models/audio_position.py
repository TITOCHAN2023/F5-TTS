from .base import BaseSchema
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

class PositionSchema(BaseSchema):
    __tablename__ = "f5tts_position"
    position_id: int = Column(Integer, primary_key=True, autoincrement=True)
    create_at: datetime = Column(DateTime, default=datetime.now)
    content: str = Column(String(255), nullable=False)
    content_position: str = Column(String(255), nullable=True)
