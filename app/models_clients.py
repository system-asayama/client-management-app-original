"""
顧問先管理用モデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class TClient(Base):
    """T_顧問先テーブル"""
    __tablename__ = 'T_顧問先'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    type = Column(String(50))  # 個人/法人
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(50))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
