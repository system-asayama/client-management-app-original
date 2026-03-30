"""
login-system-app用のSQLAlchemyモデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Date, Float
from sqlalchemy.sql import func
from app.db import Base


class TKanrisha(Base):
    """T_管理者テーブル（system_admin / tenant_admin / admin）"""
    __tablename__ = 'T_管理者'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    login_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(50), default='admin')  # system_admin, tenant_admin, admin
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    active = Column(Integer, default=1)
    is_owner = Column(Integer, default=0)
    can_manage_admins = Column(Integer, default=0)
    can_manage_all_tenants = Column(Integer, default=0, comment='全テナント管理権限（1=全テナントにアクセス可能、0=作成/招待されたテナントのみ）')
    openai_api_key = Column(Text, nullable=True)
    phone = Column(String(50), nullable=True, comment='電話番号')
    position = Column(String(100), nullable=True, comment='役職')
    face_photo_url = Column(Text, nullable=True, comment='顔認証用写真URL（Base64またはストレージURL）')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TJugyoin(Base):
    """T_従業員テーブル（employee）"""
    __tablename__ = 'T_従業員'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    login_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(Text, nullable=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    role = Column(String(50), default='employee')
    active = Column(Integer, default=1)
    phone = Column(String(50), nullable=True, comment='電話番号')
    position = Column(String(100), nullable=True, comment='役職')
    face_photo_url = Column(Text, nullable=True, comment='顔認証用写真URL（Base64またはストレージURL）')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TTenant(Base):
    """T_テナントテーブル"""
    __tablename__ = 'T_テナント'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    名称 = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    郵便番号 = Column(String(10), nullable=True)
    住所 = Column(String(500), nullable=True)
    電話番号 = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    openai_api_key = Column(String(255), nullable=True)
    profession = Column(String(50), nullable=True, comment='士業種別: tax=税理士, legal=弁護士, accounting=公認会計士, sr=社労士')
    有効 = Column(Integer, default=1)
    created_by_admin_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=True, comment='このテナントを作成したシステム管理者のID')
    gps_enabled = Column(Integer, default=0, comment='GPS位置記録機能の有効/無効（1=有効, 0=無効）')
    gps_interval_minutes = Column(Integer, default=10, comment='GPS位置記録間隔（分）デフォルト:10')
    gps_interval_seconds = Column(Integer, nullable=True, comment='GPS位置記録間隔（秒）。設定時はgps_interval_minutesより優先される')
    gps_continuous = Column(Integer, default=0, comment='GPS常時記録モード（1=常時記録, 0=間隔記録）')
    gps_realtime_enabled = Column(Integer, default=0, comment='リアルタイム追跡モード（1=有効, 0=無効）管理者が地図画面からON/OFF')
    android_apk_url = Column(Text, nullable=True, comment='AndroidアプリのAPKダウンロードURL')
    android_apk_version = Column(String(20), nullable=True, comment='AndroidアプリのAPKバージョン（例: v1.0.2）')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class TTenpo(Base):
    """T_店舗テーブル"""
    __tablename__ = 'T_店舗'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    名称 = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    郵便番号 = Column(String(10), nullable=True)
    住所 = Column(String(500), nullable=True)
    電話番号 = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    openai_api_key = Column(String(255), nullable=True)
    有効 = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class TKanrishaTenpo(Base):
    """Ｔ_管理者_店舗（多対多）"""
    __tablename__ = 'T_管理者_店舗'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=False)
    is_owner = Column(Integer, default=0, comment='この店舗のオーナーかどうか')
    can_manage_admins = Column(Integer, default=0, comment='店舗管理者を管理する権限')
    created_at = Column(DateTime, server_default=func.now())


class TJugyoinTenpo(Base):
    """T_従業員_店舗（多対多）"""
    __tablename__ = 'T_従業員_店舗'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey('T_従業員.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class TTenantAppSetting(Base):
    """T_テナントアプリ設定"""
    __tablename__ = 'T_テナントアプリ設定'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    app_id = Column(String(255), nullable=False)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())


class TTenpoAppSetting(Base):
    """T_店舗アプリ設定"""
    __tablename__ = 'T_店舗アプリ設定'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=False)
    app_id = Column(String(255), nullable=False)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())


class TTenantAdminTenant(Base):
    """T_テナント管理者_テナント中間テーブル"""
    __tablename__ = 'T_テナント管理者_テナント'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=False)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    is_owner = Column(Integer, default=0, comment='このテナントのオーナーかどうか')
    can_manage_tenant_admins = Column(Integer, default=0, comment='テナント管理者を管理する権限')
    created_at = Column(DateTime, server_default=func.now())
    
    # ユニーク制約: 同じ管理者が同じテナントに複数回紐付けられないようにする
    __table_args__ = (
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci', 'extend_existing': True}
    )


class TSystemAdminTenant(Base):
    """T_システム管理者_テナント中間テーブル（招待されたテナントを管理）"""
    __tablename__ = 'T_システム管理者_テナント'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=False, comment='システム管理者のID')
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, comment='テナントID')
    created_at = Column(DateTime, server_default=func.now())
    
    # ユニーク制約
    __table_args__ = (
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci', 'extend_existing': True}
    )


class TNotice(Base):
    """T_お知らせテーブル（事務所内お知らせ）"""
    __tablename__ = 'T_お知らせ'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    title = Column(String(255), nullable=False, comment='タイトル')
    body = Column(Text, nullable=True, comment='本文')
    author_id = Column(Integer, nullable=True, comment='投稿者ID（T_管理者.id）')
    author_name = Column(String(255), nullable=True, comment='投稿者名')
    is_important = Column(Integer, default=0, comment='重要フラグ（0=通常, 1=重要）')
    published_at = Column(DateTime, nullable=True, comment='公開日時')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TAttendance(Base):
    """T_勤怠テーブル（出退勤記録）"""
    __tablename__ = 'T_勤怠'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    staff_id = Column(Integer, nullable=False, comment='スタッフID（T_管理者.id または T_従業員.id）')
    staff_type = Column(String(20), nullable=False, default='admin', comment='admin=管理者, employee=従業員')
    staff_name = Column(String(255), nullable=True, comment='スタッフ名（非正規化）')
    work_date = Column(Date, nullable=False, comment='勤務日')
    clock_in = Column(DateTime, nullable=True, comment='出勤時刻')
    clock_out = Column(DateTime, nullable=True, comment='退勤時刻')
    break_start = Column(DateTime, nullable=True, comment='休憩開始時刻')
    break_end = Column(DateTime, nullable=True, comment='休憩終了時刻')
    break_minutes = Column(Integer, default=0, comment='休憩時間（分）')
    note = Column(Text, nullable=True, comment='備考')
    status = Column(String(20), default='normal', comment='normal=通常, late=遅刻, early=早退, absent=欠勤, holiday=休日')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TAttendanceLocation(Base):
    """T_勤怠位置履歴テーブル（出勤中のGPS記録）"""
    __tablename__ = 'T_勤怠位置履歴'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    attendance_id = Column(Integer, ForeignKey('T_勤怠.id'), nullable=True, comment='紐付く勤怠レコードID')
    staff_id = Column(Integer, nullable=False, comment='スタッフID')
    staff_type = Column(String(20), nullable=False, default='admin', comment='admin=管理者, employee=従業員')
    latitude = Column(Float, nullable=False, comment='緯度')
    longitude = Column(Float, nullable=False, comment='経度')
    accuracy = Column(Float, nullable=True, comment='精度（メートル）')
    is_background = Column(Integer, default=0, comment='バックグラウンド取得フラグ（0=フォアグラウンド, 1=バックグラウンド）')
    recorded_at = Column(DateTime, nullable=False, comment='位置情報取得日時')
    created_at = Column(DateTime, server_default=func.now())


class TClientAssignment(Base):
    """T_顧問先担当テーブル（スタッフと顧問先の担当関係）"""
    __tablename__ = 'T_顧問先担当'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    staff_id = Column(Integer, nullable=False, comment='担当スタッフID（T_管理者.id または T_従業員.id）')
    staff_type = Column(String(20), nullable=False, default='admin', comment='admin=管理者, employee=従業員')
    is_primary = Column(Integer, default=0, comment='主担当フラグ（0=サブ, 1=主担当）')
    created_at = Column(DateTime, server_default=func.now())


class TInternalChatRoom(Base):
    """T_社内チャットルームテーブル（スタッフ間チャット）"""
    __tablename__ = 'T_社内チャットルーム'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    name = Column(String(255), nullable=True, comment='ルーム名（グループチャット用）')
    room_type = Column(String(20), default='direct', comment='direct=1対1, group=グループ')
    created_by_id = Column(Integer, nullable=True, comment='作成者ID')
    created_by_type = Column(String(20), nullable=True, comment='admin/employee')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TInternalChatMember(Base):
    """T_社内チャットメンバーテーブル"""
    __tablename__ = 'T_社内チャットメンバー'
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey('T_社内チャットルーム.id'), nullable=False)
    staff_id = Column(Integer, nullable=False)
    staff_type = Column(String(20), default='admin', comment='admin/employee')
    staff_name = Column(String(255), nullable=True)
    joined_at = Column(DateTime, server_default=func.now())


class TInternalMessage(Base):
    """T_社内メッセージテーブル（スタッフ間チャットメッセージ）"""
    __tablename__ = 'T_社内メッセージ'
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey('T_社内チャットルーム.id'), nullable=False)
    sender_id = Column(Integer, nullable=False)
    sender_type = Column(String(20), default='admin', comment='admin/employee')
    sender_name = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    message_type = Column(String(20), default='text', comment='text/file')
    file_url = Column(Text, nullable=True)
    file_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TInternalMessageRead(Base):
    """T_社内メッセージ既読テーブル"""
    __tablename__ = 'T_社内メッセージ既読'
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey('T_社内メッセージ.id'), nullable=False)
    staff_id = Column(Integer, nullable=False)
    staff_type = Column(String(20), default='admin')
    read_at = Column(DateTime, server_default=func.now())


class TNoticeRead(Base):
    """T_お知らせ既読テーブル"""
    __tablename__ = 'T_お知らせ既読'
    id = Column(Integer, primary_key=True, autoincrement=True)
    notice_id = Column(Integer, ForeignKey('T_お知らせ.id'), nullable=False)
    staff_id = Column(Integer, nullable=False)
    staff_type = Column(String(20), default='admin')
    read_at = Column(DateTime, server_default=func.now())
