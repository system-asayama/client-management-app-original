"""
会計ソフト連携用モデル（freee / マネーフォワード 等）

ストレージに保存済みの受信資料を、顧問先ごとに紐づく会計ソフトの
ファイルボックス（証憑）へアップロードするための連携情報とログを管理する。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime
from app.db import Base


class TAccountingConnection(Base):
    """T_会計ソフト連携テーブル（顧問先 × 会計ソフト の接続情報）"""
    __tablename__ = 'T_会計ソフト連携'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    provider = Column(String(30), nullable=False, default='freee')  # 'freee' / 'moneyforward'

    company_id = Column(String(50), nullable=True)     # freee事業所ID（アップロード先）
    company_name = Column(String(255), nullable=True)  # 表示用事業所名

    # OAuth2 トークン（※将来的に暗号化列へ移行）
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    status = Column(String(20), nullable=False, default='active')  # 'active' / 'disabled'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TAccountingUploadLog(Base):
    """T_会計ソフトアップロードテーブル（アップロード履歴・重複防止）"""
    __tablename__ = 'T_会計ソフトアップロード'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=True)
    provider = Column(String(30), nullable=False, default='freee')

    source_type = Column(String(30), nullable=False, default='received_file')  # 元データ種別
    source_id = Column(Integer, nullable=False)        # T_受信ファイル.id 等
    external_id = Column(String(100), nullable=True)   # freee receipt.id
    filename = Column(String(500), nullable=True)

    status = Column(String(20), nullable=False, default='uploaded')  # 'uploaded' / 'error' / 'skipped'
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
