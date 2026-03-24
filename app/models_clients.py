"""
顧問先管理用モデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Numeric
from datetime import datetime
from app.db import Base


class TClient(Base):
    """T_顧問先テーブル"""
    __tablename__ = 'T_顧問先'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    type = Column(String(50))  # 個人/法人
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(50))
    notes = Column(Text)
    storage_folder_path = Column(String(500))  # ストレージ内の保存先フォルダパス（例: /clients/株式会社A）

    # 士業共通追加情報
    address = Column(String(500), nullable=True)          # 住所・所在地
    industry = Column(String(100), nullable=True)         # 業種
    fiscal_year_end = Column(String(10), nullable=True)   # 決算月（後方互換用・非推奨）
    contract_start_date = Column(String(20), nullable=True)  # 契約開始日

    # 税理士固有
    tax_accountant_code = Column(String(50), nullable=True)   # 顧問先コード
    tax_id_number = Column(String(20), nullable=True)         # 法人番号 / マイナンバー

    # 税務申告基本情報
    fiscal_year_start_month = Column(Integer, nullable=True)      # 会計期間（開始月）
    fiscal_year_end_month = Column(Integer, nullable=True)        # 会計期間（終了月）
    established_date = Column(String(20), nullable=True)          # 設立年月日
    establishment_notification = Column(Integer, nullable=True, default=0)  # 設立届の有無（0=なし, 1=あり）
    blue_return = Column(Integer, nullable=True, default=0)       # 青色申告（0=白色, 1=青色）
    consumption_tax_payer = Column(Integer, nullable=True, default=0)  # 消費税課税事業者（0=免税, 1=課税）
    consumption_tax_method = Column(String(50), nullable=True)    # 課税方式（原則課税/簡易課税）
    consumption_tax_calc = Column(String(50), nullable=True)      # 原則課税の計算方式（全額控除/個別対応/一括比例配分）
    qualified_invoice_registered = Column(Integer, nullable=True, default=0)  # 適格事業者登録（0=なし, 1=あり）
    qualified_invoice_number = Column(String(50), nullable=True)  # 適格請求書発行事業者登録番号
    salary_office_notification = Column(Integer, nullable=True, default=0)  # 給与支払事務所設置届（0=なし, 1=あり）
    withholding_tax_special = Column(Integer, nullable=True, default=0)     # 納期特例（0=なし, 1=あり）
    tax_filing_extension = Column(Integer, nullable=True, default=0)        # 申告期限延長（後方互換用・非推奨）
    corp_tax_extension = Column(Integer, nullable=True, default=0)           # 法人税申告期限延長（0=なし, 1=あり）
    consumption_tax_extension = Column(Integer, nullable=True, default=0)    # 消費税申告期限延長（0=なし, 1=あり）
    local_tax_extension = Column(Integer, nullable=True, default=0)          # 法人住民税・事業税申告期限延長（後方互換用・非推奨）
    prefectural_tax_extension = Column(Integer, nullable=True, default=0)     # 法人道府県民税・事業税申告期限延長（0=なし, 1=あり）
    municipal_tax_extension = Column(Integer, nullable=True, default=0)       # 法人市町村民税申告期限延長（0=なし, 1=あり）
    has_fixed_asset_tax = Column(Integer, nullable=True, default=0)           # 固定資産税の有無（0=なし, 1=あり）
    has_depreciable_asset_tax = Column(Integer, nullable=True, default=0)     # 償却資産税の有無（0=なし, 1=あり）

    # 弁護士固有
    case_number = Column(String(100), nullable=True)      # 事件番号
    case_type = Column(String(100), nullable=True)        # 事件種別（民事・刑事・家事等）
    opposing_party = Column(String(255), nullable=True)   # 相手方

    # 公認会計士固有
    audit_type = Column(String(100), nullable=True)       # 監査種別（法定監査・任意監査等）
    listed = Column(Integer, nullable=True, default=0)    # 上場区分（0=非上場, 1=上場）

    # 社労士固有
    employee_count = Column(Integer, nullable=True)                  # 従業員数
    labor_insurance_number = Column(String(50), nullable=True)       # 労働保険番号
    social_insurance_number = Column(String(50), nullable=True)      # 社会保険番号（事業所整理記号）
    payroll_closing_day = Column(String(10), nullable=True)          # 給与締め日

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TCommissionedWork(Base):
    """T_受託業務テーブル（顧問先ごとの受託業務一覧）"""
    __tablename__ = 'T_受託業務'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    work_name = Column(String(255), nullable=False)       # 業務名
    start_date = Column(String(20), nullable=True)        # 受託開始日
    fee = Column(Integer, nullable=True)                  # 顧問料（円）
    fee_cycle = Column(String(20), nullable=True)         # 顧問料サイクル（月次/年次/スポット）
    notes = Column(Text, nullable=True)                   # 備考
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TMessage(Base):
    """T_メッセージテーブル（顧問先ごとのチャット）"""
    __tablename__ = 'T_メッセージ'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    sender = Column(String(255), nullable=False)
    sender_type = Column(String(20), default='staff')  # 'staff'=税理士側, 'client'=クライアント側
    message = Column(Text, nullable=True)  # ファイルメッセージの場合はNone可
    message_type = Column(String(20), default='text')  # 'text'=テキスト, 'file'=ファイル, 'file_notify'=ファイル共有通知
    file_url = Column(Text, nullable=True)   # ファイルメッセージの場合のファイルURL
    file_name = Column(String(255), nullable=True)  # ファイル名
    timestamp = Column(DateTime, default=datetime.utcnow)


class TMessageRead(Base):
    """T_メッセージ既読テーブル（誰がどのメッセージを既読にしたか）"""
    __tablename__ = 'T_メッセージ既読'

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey('T_メッセージ.id'), nullable=False)
    reader_type = Column(String(20), nullable=False)  # 'staff'=税理士側, 'client'=クライアント側
    reader_id = Column(String(255), nullable=False)   # ログインIDまたはユーザー識別子
    read_at = Column(DateTime, default=datetime.utcnow)


class TFile(Base):
    """T_ファイルテーブル（顧問先ごとのファイル共有）"""
    __tablename__ = 'T_ファイル'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    filename = Column(String(255), nullable=False)
    file_url = Column(Text, nullable=False)
    uploader = Column(String(255), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
