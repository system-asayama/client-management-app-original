"""
外部サービス連携用モデル（ChatWork / Gmail 等）

顧客からもらった資料を、選択したストレージ（Dropbox/GCS/Cloudinary 等）へ
自動保存するための連携設定・ルーティング・受信ログを管理する。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
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
    """T_ChatWork連携ルームテーブル（ルーム → 顧問先の対応付け）

    staff_account_id が NULL の行は「事務所（テナント）共通トークン」で巡回する
    従来方式。値がある行は、その担当スタッフの ChatWork アカウント
    （T_担当ChatWork連携）のトークンで巡回する担当ごと方式。
    """
    __tablename__ = 'T_ChatWork連携ルーム'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    staff_account_id = Column(Integer, nullable=True)  # T_担当ChatWork連携.id（NULL=テナント共通）
    room_id = Column(String(50), nullable=False)       # ChatWorkのルームID
    room_name = Column(String(255), nullable=True)     # 表示用ルーム名（キャッシュ）
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    subfolder = Column(String(255), nullable=True, default='ChatWork受信')  # 保存先サブフォルダ
    status = Column(String(20), nullable=False, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TStaffChatworkAccount(Base):
    """T_担当ChatWork連携テーブル（担当スタッフごとの ChatWork アカウント）

    ChatWork のAPIトークンはアカウント（個人）ごとに発行されるため、
    顧問先とやり取りしている担当者本人のトークンを担当単位で登録する。
    （メールの T_担当メール連携 と同じ考え方）
    ※api_token は既存踏襲で平文（将来暗号化）。
    """
    __tablename__ = 'T_担当ChatWork連携'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    staff_id = Column(Integer, nullable=False)        # T_管理者.id または T_従業員.id
    staff_type = Column(String(20), nullable=False, default='admin')  # 'admin' / 'employee'

    api_token = Column(Text, nullable=False)          # ChatWork APIトークン（アカウントごと）
    account_name = Column(String(255), nullable=True)  # 表示用（get_me の name をキャッシュ）
    chatwork_account_id = Column(String(50), nullable=True)  # ChatWork の account_id（任意）

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


class TStaffMailAccount(Base):
    """T_担当メール連携テーブル（担当スタッフごとのメール受信アカウント）

    メールは担当者本人の受信箱に届くため、担当（スタッフ）単位で登録する。
    Gmail / Outlook(M365) / Yahoo / iCloud / その他 を、接続先(IMAP)の違いだけで
    同一の仕組みで扱う。※app_password は既存踏襲で平文（将来暗号化）。
    """
    __tablename__ = 'T_担当メール連携'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    staff_id = Column(Integer, nullable=False)        # T_管理者.id または T_従業員.id
    staff_type = Column(String(20), nullable=False, default='admin')  # 'admin' / 'employee'

    provider = Column(String(30), nullable=False, default='gmail')  # gmail/outlook/yahoo/icloud/other
    email = Column(String(320), nullable=False)
    imap_host = Column(String(255), nullable=False)
    imap_port = Column(Integer, nullable=False, default=993)
    app_password = Column(Text, nullable=True)        # アプリパスワード等

    since_uid = Column(Integer, nullable=False, default=0)  # 処理済み管理
    status = Column(String(20), nullable=False, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
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


class TMailOAuthConfig(Base):
    """T_テナントメールOAuth設定（テナントごとのメールOAuthアプリ認証情報）

    Google Workspace / Microsoft 365 のメールを OAuth（IMAP XOAUTH2）で連携する
    ために、各事務所（テナント）が自分で登録した「自前のOAuthアプリ」の
    Client ID / Secret を保持する。会計ソフト連携（T_テナント会計ソフトアプリ設定）
    と同じ考え方で、テナント管理者が画面から設定する。
    自社ドメイン限定（内部アプリ／単一テナント）で登録すればプロバイダの審査は不要。
    ※将来的に client_secret は暗号化列へ移行。
    """
    __tablename__ = 'T_テナントメールOAuth設定'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'provider', name='uq_tenant_provider_mail_oauth'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    provider = Column(String(30), nullable=False)      # 'google' / 'microsoft'
    client_id = Column(Text, nullable=True)
    client_secret = Column(Text, nullable=True)
    ms_tenant_id = Column(String(255), nullable=True)  # Microsoft のディレクトリ(テナント)ID
    status = Column(String(20), nullable=False, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TStorageConnection(Base):
    """T_外部ストレージ連携（＝ストレージ接続プール）のORMマッピング。

    既存テーブルをそのまま「接続プール」として使う。1テナントに複数の接続を
    保持でき、store_id は「登録元（本部=NULL / 店舗=ID）」を表す。実際にどの店舗が
    どの接続を使うかは T_店舗ストレージ割当（TStoreStorageAssignment）で管理する。
    """
    __tablename__ = 'T_外部ストレージ連携'
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False)
    store_id = Column(Integer, nullable=True)          # 登録元（NULL=本部）
    name = Column(String(255), nullable=True)          # 接続の表示名
    provider = Column(String(50), nullable=True)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    bucket_name = Column(Text, nullable=True)
    service_account_json = Column(Text, nullable=True)
    base_folder_path = Column(Text, nullable=True)
    status = Column(String(20), nullable=True, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TStoreStorageAssignment(Base):
    """T_店舗ストレージ割当（店舗 → 接続 の割り当て）

    どの店舗（or 本部既定）が、プール内のどの接続を使うかを管理する。
    store_id が NULL の行は「テナント（本部）既定」。将来はミラー/振り分け用に
    is_primary=0 の行を足すことで拡張できる（現状は各店舗 is_primary=1 が1つ）。
    """
    __tablename__ = 'T_店舗ストレージ割当'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, nullable=True)          # NULL=本部（テナント）既定
    connection_id = Column(Integer, nullable=False)    # T_外部ストレージ連携.id
    is_primary = Column(Integer, nullable=False, default=1)   # 1=主に使用
    status = Column(String(20), nullable=False, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TStorageAppConfig(Base):
    """T_テナントストレージアプリ設定（テナントごとのストレージOAuthアプリ認証情報）

    Dropbox 等のOAuthアプリ（App Key / App Secret）を、各事務所（テナント）が自分で
    登録した「自前アプリ」の情報として保持する。共有アプリの接続ユーザー上限を
    回避するための仕組み。未設定時はプラットフォーム共通の既定値にフォールバックする。
    ※将来的に app_secret は暗号化列へ移行。
    """
    __tablename__ = 'T_テナントストレージアプリ設定'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'provider', name='uq_tenant_provider_storage_app'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    provider = Column(String(30), nullable=False)      # 'dropbox'
    app_key = Column(Text, nullable=True)
    app_secret = Column(Text, nullable=True)
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
