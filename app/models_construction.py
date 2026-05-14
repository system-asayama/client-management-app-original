# -*- coding: utf-8 -*-
"""
建設業運営アプリ用モデル定義
login-system-app の認証基盤の上に追加する業務テーブル群
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, Date, ForeignKey, Enum
from sqlalchemy.sql import func
from app.db import Base


class TKokyaku(Base):
    """T_建設顧客 - 建設業顧客・取引先マスタ"""
    __tablename__ = 'T_建設顧客'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    company_name = Column(String(255), nullable=False, comment='会社名')
    contact_name = Column(String(255), nullable=True, comment='担当者名')
    phone = Column(String(64), nullable=True, comment='電話番号')
    email = Column(String(320), nullable=True, comment='メールアドレス')
    address = Column(Text, nullable=True, comment='住所')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TAnken(Base):
    """T_案件 - 案件管理"""
    __tablename__ = 'T_案件'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    name = Column(String(255), nullable=False, comment='案件名')
    customer_id = Column(Integer, ForeignKey('T_建設顧客.id'), nullable=True)
    status = Column(
        Enum('見積中', '受注', '施工中', '完了', '請求済', name='anken_status'),
        default='見積中', nullable=False, comment='ステータス'
    )
    start_date = Column(Date, nullable=True, comment='着工日')
    end_date = Column(Date, nullable=True, comment='完工予定日')
    assigned_to = Column(String(255), nullable=True, comment='担当者名')
    description = Column(Text, nullable=True, comment='案件概要')
    contract_amount = Column(Numeric(15, 2), nullable=True, comment='契約金額')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TNippo(Base):
    """T_日報 - 作業日報"""
    __tablename__ = 'T_日報'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    employee_id = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)
    report_date = Column(Date, nullable=False, comment='作業日')
    work_content = Column(Text, nullable=False, comment='作業内容')
    work_hours = Column(Numeric(5, 2), nullable=True, comment='作業時間（h）')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TSchedule(Base):
    """T_スケジュール - 現場・個人予定"""
    __tablename__ = 'T_スケジュール'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    employee_id = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)
    title = Column(String(255), nullable=False, comment='予定タイトル')
    start_at = Column(DateTime, nullable=False, comment='開始日時')
    end_at = Column(DateTime, nullable=True, comment='終了日時')
    all_day = Column(Integer, default=0, comment='終日フラグ（1=終日）')
    description = Column(Text, nullable=True, comment='詳細')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TMitsumori(Base):
    """T_見積 - 見積書・請求書"""
    __tablename__ = 'T_見積'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=True)
    doc_type = Column(
        Enum('estimate', 'invoice', name='doc_type'),
        default='estimate', nullable=False, comment='種別: estimate=見積書 / invoice=請求書'
    )
    status = Column(
        Enum('draft', 'sent', 'accepted', 'paid', name='mitsumori_status'),
        default='draft', nullable=False, comment='ステータス'
    )
    issue_date = Column(Date, nullable=True, comment='発行日')
    due_date = Column(Date, nullable=True, comment='支払期限')
    total_amount = Column(Numeric(15, 2), nullable=True, comment='合計金額')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TMitsumoriMeisai(Base):
    """T_見積明細 - 見積書・請求書の明細行"""
    __tablename__ = 'T_見積明細'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mitsumori_id = Column(Integer, ForeignKey('T_見積.id'), nullable=False)
    description = Column(String(500), nullable=False, comment='品名・作業内容')
    quantity = Column(Numeric(10, 2), nullable=True, comment='数量')
    unit_price = Column(Numeric(15, 2), nullable=True, comment='単価')
    amount = Column(Numeric(15, 2), nullable=True, comment='金額')
    sort_order = Column(Integer, default=0, comment='表示順')


class TAnkenFile(Base):
    """T_案件ファイル - 案件添付ファイル（S3）"""
    __tablename__ = 'T_案件ファイル'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=False)
    uploaded_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    file_name = Column(String(500), nullable=False, comment='ファイル名')
    file_key = Column(String(1000), nullable=False, comment='S3キー')
    file_url = Column(String(2000), nullable=False, comment='アクセスURL')
    mime_type = Column(String(255), nullable=True, comment='MIMEタイプ')
    file_size = Column(Integer, nullable=True, comment='ファイルサイズ（bytes）')
    created_at = Column(DateTime, server_default=func.now())
