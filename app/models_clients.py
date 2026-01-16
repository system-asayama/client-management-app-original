"""
顧問先管理用モデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime
from app.db import Base


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


class TMessage(Base):
    """T_メッセージテーブル（顧問先ごとのチャット）"""
    __tablename__ = 'T_メッセージ'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    sender = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class TFile(Base):
    """T_ファイルテーブル（顧問先ごとのファイル共有）"""
    __tablename__ = 'T_ファイル'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    filename = Column(String(255), nullable=False)
    file_url = Column(Text, nullable=False)
    uploader = Column(String(255), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
