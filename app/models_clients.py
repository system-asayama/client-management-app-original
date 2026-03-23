"""
顧問先管理用モデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
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
    storage_folder_path = Column(String(500))  # ストレージ内の保存先フォルダパス（例: /clients/株式会社A）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TMessage(Base):
    """T_メッセージテーブル（顧問先ごとのチャット）"""
    __tablename__ = 'T_メッセージ'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    sender = Column(String(255), nullable=False)
    sender_type = Column(String(20), default='staff')  # 'staff'=税理士側, 'client'=クライアント側
    message = Column(Text, nullable=True)  # ファイルメッセージの場合はNone可
    message_type = Column(String(20), default='text')  # 'text'=テキスト, 'file'=ファイル, 'file_notify'=ファイル共有通知
    file_url = Column(Text, nullable=True)   # ファイルメッセージの場合のファイルURL
    file_name = Column(String(255), nullable=True)  # ファイル名
    timestamp = Column(DateTime, default=datetime.utcnow)


class TMessageRead(Base):
    """T_メッセージ既読テーブル（誰がどのメッセージを既読にしたか）"""
    __tablename__ = 'T_メッセージ既読'

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey('T_メッセージ.id'), nullable=False)
    reader_type = Column(String(20), nullable=False)  # 'staff'=税理士側, 'client'=クライアント側
    reader_id = Column(String(255), nullable=False)   # ログインIDまたはユーザー識別子
    read_at = Column(DateTime, default=datetime.utcnow)


class TFile(Base):
    """T_ファイルテーブル（顧問先ごとのファイル共有）"""
    __tablename__ = 'T_ファイル'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    filename = Column(String(255), nullable=False)
    file_url = Column(Text, nullable=False)
    uploader = Column(String(255), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
