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


class TSchedulerConfig(Base):
    """T_スケジューラ設定テーブル（自動取得のオンオフ・間隔を画面から設定）

    アプリ全体で1行（job_name='integrations_sync'）。DB設定が最優先で、
    未設定時は環境変数→既定値にフォールバックする。変更は稼働中のスケジューラが
    次のチェック（最大60秒後）で自動反映するため、再起動不要。
    """
    __tablename__ = 'T_スケジューラ設定'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(100), nullable=False, unique=True)
    enabled = Column(Integer, nullable=False, default=1)          # 1=有効, 0=無効
    interval_minutes = Column(Integer, nullable=False, default=5)  # 巡回間隔（分）
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TSchedulerState(Base):
    """T_スケジューラ状態テーブル（アプリ内定期実行の管理・多重起動ロック用）

    複数のgunicornワーカーが同時に走っても、last_run_at への条件付きUPDATEで
    実行権を1つに絞り、重複実行を防ぐ（ai-app-studio の db_backup と同方式）。
    """
    __tablename__ = 'T_スケジューラ状態'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(100), nullable=False, unique=True)  # 例: 'integrations_sync'
    last_run_at = Column(DateTime, nullable=True)       # 前回実行を「取得」した時刻
    last_finished_at = Column(DateTime, nullable=True)  # 前回実行が完了した時刻
    last_status = Column(String(20), nullable=True)     # 'ok' / 'error'
    last_detail = Column(Text, nullable=True)           # 直近の結果サマリ（JSON文字列）
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TGmailSenderMapping(Base):
    """T_Gmail送信者マッピングテーブル（差出人メールアドレス → 顧問先の対応付け）"""
    __tablename__ = 'T_Gmail送信者マッピング'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    sender_email = Column(String(320), nullable=False)  # 差出人メールアドレス（小文字で保存）
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    subfolder = Column(String(255), nullable=True, default='Gmail受信')  # 保存先サブフォルダ
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
