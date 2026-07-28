"""
外部サービス連携用モデル（ChatWork / Gmail 等）

顧客からもらった資料を、選択したストレージ（Dropbox/GCS/Cloudinary 等）へ
自動保存するための連携設定・ルーティング・受信ログを管理する。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime
from app.db import Base


class TIntegrationSetting(Base):
    """T_連携設定テーブル（テナントごとの外部サービス連携設定）"""
    __tablename__ = 'T_連携設定'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    provider = Column(String(50), nullable=False)      # 'chatwork' / 'gmail' など
    api_token = Column(Text, nullable=True)            # APIトークン（ChatWork）。※将来的に暗号化列へ移行
    webhook_secret = Column(String(255), nullable=True)  # Webhook署名検証用シークレット（任意）
    extra = Column(Text, nullable=True)                # プロバイダ固有設定（JSON文字列）
    status = Column(String(20), nullable=False, default='active')  # 'active' / 'disabled'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TChatworkRoomMapping(Base):
    """T_ChatWork連携ルームテーブル（ルーム → 顧問先の対応付け）"""
    __tablename__ = 'T_ChatWork連携ルーム'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    room_id = Column(String(50), nullable=False)       # ChatWorkのルームID
    room_name = Column(String(255), nullable=True)     # 表示用ルーム名（キャッシュ）
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    subfolder = Column(String(255), nullable=True, default='ChatWork受信')  # 保存先サブフォルダ
    status = Column(String(20), nullable=False, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TReceivedFile(Base):
    """T_受信ファイルテーブル（外部連携で受信・保存したファイルのログ／重複防止）"""
    __tablename__ = 'T_受信ファイル'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    provider = Column(String(50), nullable=False)          # 'chatwork' / 'gmail'
    external_id = Column(String(255), nullable=False)      # 受信元での一意ID（ChatWork file_id 等）
    room_id = Column(String(50), nullable=True)            # 受信元ルーム/メールボックス識別子
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=True)
    filename = Column(String(500), nullable=True)
    storage_url = Column(Text, nullable=True)              # 保存先ストレージのURL
    status = Column(String(20), nullable=False, default='saved')  # 'saved' / 'error' / 'skipped'
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
