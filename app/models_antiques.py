# -*- coding: utf-8 -*-
"""
骨董品店経営アプリ用モデル定義
login-system-app の認証基盤の上に追加する業務テーブル群
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, Date, ForeignKey, Enum
from sqlalchemy.sql import func
from app.db import Base


class TAntiqueTorihikisaki(Base):
    """T_骨董取引先 - 顧客・仕入先マスタ"""
    __tablename__ = 'T_骨董取引先'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    name = Column(String(255), nullable=False, comment='氏名・会社名')
    partner_type = Column(
        Enum('顧客', '仕入先', '両方', name='antique_partner_type'),
        default='顧客', nullable=False, comment='取引先区分'
    )
    contact_name = Column(String(255), nullable=True, comment='担当者名')
    phone = Column(String(64), nullable=True, comment='電話番号')
    email = Column(String(320), nullable=True, comment='メールアドレス')
    address = Column(Text, nullable=True, comment='住所')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TAntiqueShohin(Base):
    """T_骨董品 - 骨董品・在庫管理"""
    __tablename__ = 'T_骨董品'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    management_no = Column(String(64), nullable=True, comment='管理番号')
    name = Column(String(255), nullable=False, comment='品名')
    category = Column(String(64), nullable=True, comment='分類')
    era = Column(String(128), nullable=True, comment='時代・年代')
    condition = Column(
        Enum('美品', '良好', '並', '難あり', name='antique_condition'),
        default='良好', nullable=True, comment='状態'
    )
    status = Column(
        Enum('在庫', '委託中', '売約済', '販売済', name='antique_status'),
        default='在庫', nullable=False, comment='ステータス'
    )
    supplier_id = Column(Integer, ForeignKey('T_骨董取引先.id'), nullable=True)
    acquisition_cost = Column(Numeric(15, 2), nullable=True, comment='仕入価格')
    asking_price = Column(Numeric(15, 2), nullable=True, comment='販売希望価格')
    description = Column(Text, nullable=True, comment='説明・来歴')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TAntiqueKaitori(Base):
    """T_骨董買取 - 買取・仕入記録"""
    __tablename__ = 'T_骨董買取'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    shohin_id = Column(Integer, ForeignKey('T_骨董品.id'), nullable=True)
    supplier_id = Column(Integer, ForeignKey('T_骨董取引先.id'), nullable=True)
    purchase_date = Column(Date, nullable=False, comment='買取日')
    amount = Column(Numeric(15, 2), nullable=True, comment='買取金額')
    payment_method = Column(String(64), nullable=True, comment='支払方法')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TAntiqueHanbai(Base):
    """T_骨董販売 - 販売記録"""
    __tablename__ = 'T_骨董販売'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    shohin_id = Column(Integer, ForeignKey('T_骨董品.id'), nullable=True)
    customer_id = Column(Integer, ForeignKey('T_骨董取引先.id'), nullable=True)
    sale_date = Column(Date, nullable=False, comment='販売日')
    amount = Column(Numeric(15, 2), nullable=True, comment='販売金額')
    payment_method = Column(String(64), nullable=True, comment='支払方法')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TAntiqueKantei(Base):
    """T_骨董鑑定 - 鑑定・査定記録"""
    __tablename__ = 'T_骨董鑑定'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    shohin_id = Column(Integer, ForeignKey('T_骨董品.id'), nullable=True)
    target_name = Column(String(255), nullable=True, comment='鑑定品名（未登録品用）')
    appraiser = Column(String(255), nullable=True, comment='鑑定士')
    appraisal_date = Column(Date, nullable=False, comment='鑑定日')
    appraised_value = Column(Numeric(15, 2), nullable=True, comment='鑑定評価額')
    result = Column(
        Enum('真作', '模写・複製', '時代相応', '要再鑑定', '不明', name='antique_kantei_result'),
        default='不明', nullable=True, comment='鑑定結果'
    )
    comment = Column(Text, nullable=True, comment='所見・コメント')
    created_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TAntiqueFile(Base):
    """T_骨董品ファイル - 商品写真・添付ファイル（S3）"""
    __tablename__ = 'T_骨董品ファイル'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    shohin_id = Column(Integer, ForeignKey('T_骨董品.id'), nullable=False)
    uploaded_by = Column(Integer, ForeignKey('T_管理者.id'), nullable=True)
    file_name = Column(String(500), nullable=False, comment='ファイル名')
    file_key = Column(String(1000), nullable=False, comment='S3キー')
    file_url = Column(String(2000), nullable=False, comment='アクセスURL')
    mime_type = Column(String(255), nullable=True, comment='MIMEタイプ')
    file_size = Column(Integer, nullable=True, comment='ファイルサイズ（bytes）')
    created_at = Column(DateTime, server_default=func.now())
