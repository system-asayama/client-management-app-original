"""
クライアント（顧問先）ユーザー管理用モデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db import Base


class TClientUser(Base):
    """T_クライアントユーザーテーブル（顧問先側のユーザー）"""
    __tablename__ = 'T_クライアントユーザー'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    login_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(Text, nullable=True)
    role = Column(String(50), default='client_employee')  # client_admin / client_employee
    active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TClientInvitation(Base):
    """T_クライアント招待テーブル（招待リンク管理）"""
    __tablename__ = 'T_クライアント招待'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), nullable=True)
    role = Column(String(50), default='client_employee')  # client_admin / client_employee
    invited_by_role = Column(String(50), nullable=True)  # 招待者のロール
    invited_by_id = Column(Integer, nullable=True)        # 招待者のID
    used = Column(Integer, default=0)                     # 0=未使用, 1=使用済み
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
