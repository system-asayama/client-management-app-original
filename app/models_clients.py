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
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)  # 担当店舗ID（店舗ベースアーキテクチャ対応）

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


class TTaxRecord(Base):
    """T_納税実績テーブル（決算期ごとの国税実績）"""
    __tablename__ = 'T_納税実績'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    fiscal_year = Column(Integer, nullable=False)        # 決算年度（例：2025 = 2025年3月期）
    fiscal_end_month = Column(Integer, nullable=False)   # 決算月（例：3）

    # 国税（税務署）
    corporate_tax = Column(Integer, nullable=True)       # 法人税
    local_corporate_tax = Column(Integer, nullable=True) # 地方法人税
    consumption_tax = Column(Integer, nullable=True)     # 消費税（国税分）
    local_consumption_tax = Column(Integer, nullable=True) # 地方消費税

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TTaxRecordPrefecture(Base):
    """T_納税実績_都道府県テーブル（都道府県ごとの地方税実績）"""
    __tablename__ = 'T_納税実績_都道府県'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tax_record_id = Column(Integer, ForeignKey('T_納税実績.id'), nullable=False)
    prefecture_name = Column(String(100), nullable=False)  # 都道府県名

    # 都道府県税の内訳
    equal_levy = Column(Integer, nullable=True)            # 均等割
    income_levy = Column(Integer, nullable=True)           # 所得割
    business_tax = Column(Integer, nullable=True)          # 事業税
    special_business_tax = Column(Integer, nullable=True)  # 特別法人事業税


class TTaxRecordMunicipality(Base):
    """T_納税実績_市区町村テーブル（市区町村ごとの地方税実績）"""
    __tablename__ = 'T_納税実績_市区町村'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tax_record_id = Column(Integer, ForeignKey('T_納税実績.id'), nullable=False)
    municipality_name = Column(String(100), nullable=False)  # 市区町村名

    # 市区町村税の内訳
    equal_levy = Column(Integer, nullable=True)              # 均等割
    corporate_tax_levy = Column(Integer, nullable=True)      # 法人税割


class TFilingOfficeTaxOffice(Base):
    """T_申告先_税務署テーブル"""
    __tablename__ = 'T_申告先_税務署'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    tax_office_name = Column(String(100), nullable=False)   # 税務署名
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TFilingOfficePrefecture(Base):
    """T_申告先_都道府県テーブル"""
    __tablename__ = 'T_申告先_都道府県'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    prefecture_name = Column(String(100), nullable=False)   # 都道府県名
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TFilingOfficeMunicipality(Base):
    """T_申告先_市区町村テーブル"""
    __tablename__ = 'T_申告先_市区町村'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=False)
    municipality_name = Column(String(100), nullable=False)  # 市区町村名
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TVideoCallSession(Base):
    """T_ビデオ通話セッションテーブル"""
    __tablename__ = 'T_ビデオ通話セッション'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('T_顧問先.id'), nullable=True)
    room_name = Column(String(255), nullable=False, comment='Daily.coのルーム名')
    room_url = Column(String(500), nullable=True, comment='Daily.coのルームURL')
    started_at = Column(DateTime, nullable=True, comment='通話開始時刻')
    ended_at = Column(DateTime, nullable=True, comment='通話終了時刻')
    duration_minutes = Column(Integer, nullable=True, comment='通話時間（分）')
    status = Column(String(20), default='created', comment='created/active/ended')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TVideoCallUsage(Base):
    """T_ビデオ通話利用量テーブル（月次集計）"""
    __tablename__ = 'T_ビデオ通話利用量'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    year_month = Column(String(7), nullable=False, comment='対象年月 例: 2026-03')
    used_minutes = Column(Integer, default=0, comment='当月使用分数')
    extra_charge = Column(Integer, default=0, comment='超過課金額（円）')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
