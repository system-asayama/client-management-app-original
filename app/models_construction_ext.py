# -*- coding: utf-8 -*-
"""
建設業運営アプリ - 拡張モデル定義 (サクミル相当機能)

既存の models_construction.py には手を加えず、追加機能のテーブルのみここに定義する。
既存テーブル(T_案件 / T_顧客 / T_見積 等)への外部キーで連携する。

【追加機能】
  1. 写真管理        : TPhotoAlbum / TPhoto
  2. 実行予算管理    : TJikkouYosan
  3. 原価管理        : TGenka
  4. 出面管理        : TDemen
  5. 仕入先マスタ    : TShiiresaki
  6. 発注管理        : THacchu / THacchuMeisai
  7. 入金管理        : TNyukin

【工事台帳について】
  専用テーブルは作成しない。
  T_案件 / T_実行予算 / T_原価 / T_見積 / T_入金 を集計して算出する。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, Date, ForeignKey, Enum
from sqlalchemy.sql import func
from app.db import Base


# ─── 1. 写真管理 ──────────────────────────────────────────────────────────────

class TPhotoAlbum(Base):
    """T_写真台帳 - 案件ごとの写真台帳(アルバム)"""
    __tablename__ = 'T_写真台帳'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=False, comment='紐づく案件')
    title = Column(String(255), nullable=False, comment='台帳タイトル')
    description = Column(Text, nullable=True, comment='説明')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TPhoto(Base):
    """T_写真 - 個別写真レコード"""
    __tablename__ = 'T_写真'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    album_id = Column(Integer, ForeignKey('T_写真台帳.id'), nullable=True, comment='所属台帳')
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=False, comment='案件')
    taken_at = Column(Date, nullable=True, comment='撮影日')
    work_type = Column(String(255), nullable=True, comment='工種')
    location = Column(String(255), nullable=True, comment='撮影場所')
    comment = Column(Text, nullable=True, comment='コメント')
    file_name = Column(String(500), nullable=False, comment='ファイル名')
    file_key = Column(String(1000), nullable=False, comment='S3キー')
    file_url = Column(String(2000), nullable=False, comment='アクセスURL')
    thumbnail_url = Column(String(2000), nullable=True, comment='サムネイルURL')
    mime_type = Column(String(255), nullable=True, comment='MIMEタイプ')
    file_size = Column(Integer, nullable=True, comment='ファイルサイズ(bytes)')
    sort_order = Column(Integer, default=0, comment='表示順')
    uploaded_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ─── 2. 実行予算管理 ─────────────────────────────────────────────────────────

class TJikkouYosan(Base):
    """T_実行予算 - 案件ごとの実行予算(費目別)"""
    __tablename__ = 'T_実行予算'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=False, comment='紐づく案件')
    category = Column(
        Enum('資材費', '労務費', '外注費', '経費', 'その他', name='yosan_category'),
        nullable=False, comment='費目'
    )
    item_name = Column(String(255), nullable=True, comment='品目・内訳名')
    budget_amount = Column(Numeric(15, 2), nullable=False, default=0, comment='予算金額')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─── 3. 原価管理 ─────────────────────────────────────────────────────────────

class TGenka(Base):
    """T_原価 - 案件ごとの原価実績(費目別)"""
    __tablename__ = 'T_原価'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=False, comment='紐づく案件')
    category = Column(
        Enum('資材費', '労務費', '外注費', '経費', 'その他', name='genka_category'),
        nullable=False, comment='費目'
    )
    item_name = Column(String(255), nullable=True, comment='品目・内訳名')
    cost_date = Column(Date, nullable=False, comment='発生日')
    amount = Column(Numeric(15, 2), nullable=False, comment='金額')
    vendor_name = Column(String(255), nullable=True, comment='取引先(自由入力)')
    shiiresaki_id = Column(Integer, ForeignKey('T_仕入先.id'), nullable=True, comment='仕入先(マスタ)')
    hacchu_id = Column(Integer, ForeignKey('T_発注.id'), nullable=True, comment='紐づく発注')
    nippo_id = Column(Integer, ForeignKey('T_日報.id'), nullable=True, comment='紐づく日報(労務費の自動計上)')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─── 4. 出面管理 ─────────────────────────────────────────────────────────────

class TDemen(Base):
    """T_出面 - 日別・案件別の作業員出面(人工管理)"""
    __tablename__ = 'T_出面'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=False, comment='現場(案件)')
    work_date = Column(Date, nullable=False, comment='作業日')
    employee_id = Column(Integer, ForeignKey('T_従業員.id'), nullable=True, comment='自社従業員')
    worker_name = Column(String(255), nullable=True, comment='作業員名(外注/自由入力)')
    worker_type = Column(
        Enum('自社', '応援', '外注', name='worker_type'),
        default='自社', nullable=False, comment='区分'
    )
    ninku = Column(Numeric(5, 2), nullable=False, default=1.0, comment='人工(にんく)')
    unit_price = Column(Numeric(15, 2), nullable=True, comment='単価(日当)')
    amount = Column(Numeric(15, 2), nullable=True, comment='金額(人工×単価)')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─── 5. 仕入先マスタ ─────────────────────────────────────────────────────────

class TShiiresaki(Base):
    """T_仕入先 - 仕入先・外注先マスタ"""
    __tablename__ = 'T_仕入先'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    company_name = Column(String(255), nullable=False, comment='会社名')
    contact_name = Column(String(255), nullable=True, comment='担当者名')
    phone = Column(String(64), nullable=True, comment='電話番号')
    email = Column(String(320), nullable=True, comment='メールアドレス')
    address = Column(Text, nullable=True, comment='住所')
    category = Column(
        Enum('資材', '外注', '労務', 'その他', name='shiiresaki_category'),
        default='資材', nullable=False, comment='区分'
    )
    payment_terms = Column(String(255), nullable=True, comment='支払条件')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─── 6. 発注管理 ─────────────────────────────────────────────────────────────

class THacchu(Base):
    """T_発注 - 発注書ヘッダ"""
    __tablename__ = 'T_発注'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=False, comment='紐づく案件')
    shiiresaki_id = Column(Integer, ForeignKey('T_仕入先.id'), nullable=True, comment='発注先')
    order_no = Column(String(64), nullable=True, comment='発注番号')
    order_date = Column(Date, nullable=True, comment='発注日')
    delivery_date = Column(Date, nullable=True, comment='納期')
    status = Column(
        Enum('draft', 'sent', 'received', 'paid', 'cancelled', name='hacchu_status'),
        default='draft', nullable=False, comment='ステータス: 下書/発注済/納品済/支払済/取消'
    )
    total_amount = Column(Numeric(15, 2), nullable=True, comment='合計金額')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class THacchuMeisai(Base):
    """T_発注明細 - 発注書の明細行"""
    __tablename__ = 'T_発注明細'

    id = Column(Integer, primary_key=True, autoincrement=True)
    hacchu_id = Column(Integer, ForeignKey('T_発注.id'), nullable=False)
    description = Column(String(500), nullable=False, comment='品名・内容')
    quantity = Column(Numeric(10, 2), nullable=True, comment='数量')
    unit = Column(String(32), nullable=True, comment='単位(個/m/kg等)')
    unit_price = Column(Numeric(15, 2), nullable=True, comment='単価')
    amount = Column(Numeric(15, 2), nullable=True, comment='金額')
    sort_order = Column(Integer, default=0, comment='表示順')


# ─── 7. 入金管理 ─────────────────────────────────────────────────────────────

class TNyukin(Base):
    """T_入金 - 請求書(T_見積 doc_type=invoice)に紐づく入金記録"""
    __tablename__ = 'T_入金'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    mitsumori_id = Column(Integer, ForeignKey('T_見積.id'), nullable=False, comment='紐づく請求書')
    anken_id = Column(Integer, ForeignKey('T_案件.id'), nullable=True, comment='紐づく案件(任意・冗長)')
    payment_date = Column(Date, nullable=False, comment='入金日')
    amount = Column(Numeric(15, 2), nullable=False, comment='入金金額')
    method = Column(
        Enum('振込', '現金', '小切手', '手形', 'その他', name='nyukin_method'),
        default='振込', nullable=False, comment='入金方法'
    )
    bank_name = Column(String(255), nullable=True, comment='振込元銀行名')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
