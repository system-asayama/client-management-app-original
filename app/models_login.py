"""
login-system-app用のSQLAlchemyモデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
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
    accounting_method = Column(String(20), default='tax_inclusive', nullable=False, comment='経理方式: tax_inclusive=税込経理, tax_exclusive=税抜経理')
    tax_filing_method = Column(String(30), default='exempt', nullable=True, comment='課税方式: exempt=免税, simplified=簡易課税, general_individual=一般課税(個別対応), general_lump_sum=一般課税(一括比例配分), general_full=一般課税(全額控除)')
    tax_rounding = Column(String(20), default='cut_off', nullable=True, comment='端数処理: cut_off=切り捨て, round=四捨五入, round_up=切り上げ')
    simplified_tax_category = Column(String(20), default='category1', nullable=True, comment='簡易課税の事業区分: category1-6')
    tax_calculation_method = Column(String(50), default='sales_discount_purchase_discount', nullable=True, comment='計算方式')
    有効 = Column(Integer, default=1)
    created_by_admin_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=True, comment='このテナントを作成したシステム管理者のID')
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
