"""
ショートステイ運営管理システム - データモデル定義

テナント（法人）→ 店舗（施設）→ 各種データ の階層構造に対応。
"""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Boolean,
    ForeignKey, Numeric, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from .db import Base
import enum


# ─────────────────────────────────────────────
# Enum 定義
# ─────────────────────────────────────────────

class GenderEnum(str, enum.Enum):
    male = "男性"
    female = "女性"
    other = "その他"

class CareLevel(str, enum.Enum):
    support1 = "要支援1"
    support2 = "要支援2"
    care1 = "要介護1"
    care2 = "要介護2"
    care3 = "要介護3"
    care4 = "要介護4"
    care5 = "要介護5"

class ReservationStatus(str, enum.Enum):
    tentative = "仮予約"
    confirmed = "確定"
    cancelled = "キャンセル"
    waitlisted = "キャンセル待ち"

class CheckStatus(str, enum.Enum):
    scheduled = "予定"
    checked_in = "入所中"
    checked_out = "退所済"
    cancelled = "キャンセル"

class MealType(str, enum.Enum):
    breakfast = "朝食"
    lunch = "昼食"
    dinner = "夕食"
    snack = "おやつ"

class MealAmount(str, enum.Enum):
    all = "全量"
    most = "ほぼ全量"
    half = "半量"
    little = "少量"
    none = "摂取なし"

class ExcretionType(str, enum.Enum):
    urine = "排尿"
    stool = "排便"
    both = "排尿・排便"
    none = "なし"

class ExcretionMethod(str, enum.Enum):
    toilet = "トイレ"
    portable_toilet = "ポータブルトイレ"
    diaper = "おむつ"
    pad = "パッド"

class BathType(str, enum.Enum):
    general = "一般浴"
    machine = "機械浴"
    shower = "シャワー浴"
    bed_bath = "清拭"

class BillingStatus(str, enum.Enum):
    draft = "下書き"
    issued = "発行済"
    paid = "支払済"
    overdue = "未払い"

class ShiftType(str, enum.Enum):
    early = "早番"
    day = "日勤"
    late = "遅番"
    night = "夜勤"
    holiday = "休日"
    paid_leave = "有給"


# ─────────────────────────────────────────────
# 利用者（入居者）管理
# ─────────────────────────────────────────────

class SSResident(Base):
    """ショートステイ利用者"""
    __tablename__ = 'SS_利用者'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, comment='テナントID')
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True, comment='施設ID')

    # 基本情報
    last_name = Column(String(50), nullable=False, comment='姓')
    first_name = Column(String(50), nullable=False, comment='名')
    last_name_kana = Column(String(50), nullable=True, comment='姓（フリガナ）')
    first_name_kana = Column(String(50), nullable=True, comment='名（フリガナ）')
    gender = Column(SAEnum(GenderEnum), nullable=True, comment='性別')
    birth_date = Column(Date, nullable=True, comment='生年月日')
    postal_code = Column(String(10), nullable=True, comment='郵便番号')
    address = Column(String(300), nullable=True, comment='住所')
    phone = Column(String(20), nullable=True, comment='電話番号')

    # 介護情報
    care_level = Column(SAEnum(CareLevel), nullable=True, comment='介護度')
    care_insurance_no = Column(String(20), nullable=True, comment='介護保険番号')
    care_insurance_expiry = Column(Date, nullable=True, comment='介護保険有効期限')
    insurer_no = Column(String(10), nullable=True, comment='保険者番号')
    insurer_name = Column(String(100), nullable=True, comment='保険者名')

    # 医療情報
    doctor_name = Column(String(100), nullable=True, comment='主治医名')
    hospital_name = Column(String(200), nullable=True, comment='病院名')
    hospital_phone = Column(String(20), nullable=True, comment='病院電話番号')
    allergies = Column(Text, nullable=True, comment='アレルギー')
    medical_history = Column(Text, nullable=True, comment='既往歴')
    medications = Column(Text, nullable=True, comment='服薬情報')
    special_notes = Column(Text, nullable=True, comment='特記事項')

    # 食事情報
    meal_type = Column(String(50), nullable=True, comment='食事形態')
    meal_texture = Column(String(50), nullable=True, comment='食事テクスチャ')
    thickener = Column(Boolean, default=False, comment='とろみ使用')

    # ケアマネ情報
    care_manager_name = Column(String(100), nullable=True, comment='担当ケアマネジャー名')
    care_manager_office = Column(String(200), nullable=True, comment='居宅介護支援事業所名')
    care_manager_phone = Column(String(20), nullable=True, comment='ケアマネ電話番号')

    # フェイスシート：障害・支給情報
    disability_support_category = Column(String(50), nullable=True, comment='障害支援区分')
    approved_service_amount = Column(String(50), nullable=True, comment='決定支給量（日/月）')
    certification_valid_from = Column(Date, nullable=True, comment='認定有効期間（開始）')
    certification_valid_to = Column(Date, nullable=True, comment='認定有効期間（終了）')
    service_decision_from = Column(Date, nullable=True, comment='支給決定期間（開始）')
    service_decision_to = Column(Date, nullable=True, comment='支給決定期間（終了）')
    disability_certification = Column(String(200), nullable=True, comment='障害等認定')
    consultant_name = Column(String(100), nullable=True, comment='相談員')

    # フェイスシート：食事
    meal_action = Column(String(20), nullable=True, default='自立', comment='食事動作（自立/見守り/介助）')
    disliked_food = Column(Text, nullable=True, comment='嫌いなもの')
    favorite_food = Column(Text, nullable=True, comment='好きなもの')
    meal_form = Column(String(100), nullable=True, comment='食事形態（とろみ等）')

    # フェイスシート：服薬
    medication_regular = Column(String(200), nullable=True, comment='定期薬（朝/昼/夕/眠前）')
    medication_prn = Column(String(200), nullable=True, comment='頓服')
    medication_management = Column(String(20), nullable=True, default='自己管理', comment='服薬管理（自己管理/職員管理）')
    medication_special_notes = Column(Text, nullable=True, comment='服薬特記事項')

    # フェイスシート：ADL
    toilet_action = Column(String(20), nullable=True, default='自立', comment='トイレ動作（自立/見守り/介助）')
    bath_assistance = Column(String(20), nullable=True, default='自立', comment='入浴（自立/見守り/一部介助/全介助）')
    urinary_control = Column(String(20), nullable=True, default='失禁なし', comment='排尿コントロール（失禁なし/時に失禁/介助）')
    dressing_assistance = Column(String(20), nullable=True, default='自立', comment='更衣（自立/見守り/一部介助/全介助）')
    bowel_control = Column(String(20), nullable=True, default='失禁なし', comment='排便コントロール（失禁なし/時に失禁/介助）')
    communication = Column(String(20), nullable=True, default='可能', comment='意思疎通（可能/何とか可能/不可能）')

    # 状態
    active = Column(Boolean, default=True, nullable=False, comment='有効フラグ')
    created_at = Column(DateTime, default=datetime.utcnow, comment='作成日時')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新日時')

    # リレーション
    emergency_contacts = relationship('SSEmergencyContact', back_populates='resident', cascade='all, delete-orphan')
    reservations = relationship('SSReservation', back_populates='resident')
    care_records = relationship('SSCareRecord', back_populates='resident')
    vital_records = relationship('SSVitalRecord', back_populates='resident')
    billing_records = relationship('SSBilling', back_populates='resident')
    care_plans = relationship('SSCarePlan', back_populates='resident')


class SSEmergencyContact(Base):
    """緊急連絡先"""
    __tablename__ = 'SS_緊急連絡先'

    id = Column(Integer, primary_key=True, autoincrement=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    name = Column(String(100), nullable=False, comment='氏名')
    relation_type = Column(String(50), nullable=True, comment='続柄')
    phone = Column(String(20), nullable=True, comment='電話番号')
    phone2 = Column(String(20), nullable=True, comment='電話番号2')
    address = Column(String(300), nullable=True, comment='住所')
    sort_order = Column(Integer, default=0, comment='表示順')

    resident = relationship('SSResident', back_populates='emergency_contacts')


# ─────────────────────────────────────────────
# 予約・入退所管理
# ─────────────────────────────────────────────

class SSRoom(Base):
    """居室（ベッド）管理"""
    __tablename__ = 'SS_居室'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    room_number = Column(String(20), nullable=False, comment='居室番号')
    room_name = Column(String(100), nullable=True, comment='居室名')
    capacity = Column(Integer, default=1, comment='定員')
    floor = Column(String(10), nullable=True, comment='階')
    notes = Column(Text, nullable=True, comment='備考')
    active = Column(Boolean, default=True)

    reservations = relationship('SSReservation', back_populates='room')


class SSReservation(Base):
    """予約管理"""
    __tablename__ = 'SS_予約'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    room_id = Column(Integer, ForeignKey('SS_居室.id'), nullable=True, comment='居室ID')

    # 予約期間
    check_in_date = Column(Date, nullable=False, comment='入所予定日')
    check_out_date = Column(Date, nullable=False, comment='退所予定日')
    actual_check_in = Column(DateTime, nullable=True, comment='実際の入所日時')
    actual_check_out = Column(DateTime, nullable=True, comment='実際の退所日時')

    # 状態
    status = Column(SAEnum(ReservationStatus), default=ReservationStatus.tentative, comment='予約状態')
    check_status = Column(SAEnum(CheckStatus), default=CheckStatus.scheduled, comment='入退所状態')

    # 送迎
    pickup_required = Column(Boolean, default=False, comment='送迎（迎え）')
    dropoff_required = Column(Boolean, default=False, comment='送迎（送り）')
    pickup_address = Column(String(300), nullable=True, comment='送迎先住所')
    pickup_time = Column(String(10), nullable=True, comment='迎え時間')
    dropoff_time = Column(String(10), nullable=True, comment='送り時間')

    # 料金プラン
    service_type = Column(String(50), nullable=True, comment='サービス種別')
    notes = Column(Text, nullable=True, comment='備考')

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    resident = relationship('SSResident', back_populates='reservations')
    room = relationship('SSRoom', back_populates='reservations')
    billing = relationship('SSBilling', back_populates='reservation', uselist=False)


# ─────────────────────────────────────────────
# ケア記録
# ─────────────────────────────────────────────

class SSCareRecord(Base):
    """ケア記録（日常記録）"""
    __tablename__ = 'SS_ケア記録'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True)
    recorded_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True, comment='記録者（従業員ID）')

    record_date = Column(Date, nullable=False, comment='記録日')
    record_time = Column(String(10), nullable=True, comment='記録時刻')

    # 記録種別
    record_type = Column(String(50), nullable=False, comment='記録種別（食事/排泄/入浴/その他）')
    content = Column(Text, nullable=True, comment='記録内容')

    created_at = Column(DateTime, default=datetime.utcnow)

    resident = relationship('SSResident', back_populates='care_records')


class SSVitalRecord(Base):
    """バイタル記録"""
    __tablename__ = 'SS_バイタル記録'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True)
    recorded_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)

    record_date = Column(Date, nullable=False, comment='記録日')
    record_time = Column(String(10), nullable=True, comment='記録時刻')

    # バイタルサイン
    body_temp = Column(Numeric(4, 1), nullable=True, comment='体温（℃）')
    blood_pressure_high = Column(Integer, nullable=True, comment='血圧（収縮期）')
    blood_pressure_low = Column(Integer, nullable=True, comment='血圧（拡張期）')
    pulse = Column(Integer, nullable=True, comment='脈拍（回/分）')
    spo2 = Column(Integer, nullable=True, comment='SpO2（%）')
    respiration = Column(Integer, nullable=True, comment='呼吸数（回/分）')
    weight = Column(Numeric(5, 1), nullable=True, comment='体重（kg）')

    notes = Column(Text, nullable=True, comment='特記事項')
    created_at = Column(DateTime, default=datetime.utcnow)

    resident = relationship('SSResident', back_populates='vital_records')


class SSMealRecord(Base):
    """食事記録"""
    __tablename__ = 'SS_食事記録'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True)
    recorded_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)

    record_date = Column(Date, nullable=False)
    meal_type = Column(SAEnum(MealType), nullable=False, comment='食事種別')
    meal_amount = Column(SAEnum(MealAmount), nullable=True, comment='摂取量')
    water_intake_ml = Column(Integer, nullable=True, comment='水分摂取量（ml）')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SSExcretionRecord(Base):
    """排泄記録"""
    __tablename__ = 'SS_排泄記録'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True)
    recorded_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)

    record_date = Column(Date, nullable=False)
    record_time = Column(String(10), nullable=True)
    excretion_type = Column(SAEnum(ExcretionType), nullable=True, comment='排泄種別')
    excretion_method = Column(SAEnum(ExcretionMethod), nullable=True, comment='排泄方法')
    amount = Column(String(20), nullable=True, comment='量（多/中/少）')
    stool_form = Column(String(50), nullable=True, comment='便の性状（ブリストル便形状スケール）')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SSBathRecord(Base):
    """入浴記録"""
    __tablename__ = 'SS_入浴記録'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True)
    recorded_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)

    record_date = Column(Date, nullable=False)
    bath_type = Column(SAEnum(BathType), nullable=True, comment='入浴種別')
    duration_minutes = Column(Integer, nullable=True, comment='入浴時間（分）')
    skin_condition = Column(String(100), nullable=True, comment='皮膚状態')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# ケアプラン
# ─────────────────────────────────────────────

class SSCarePlan(Base):
    """ケアプラン"""
    __tablename__ = 'SS_ケアプラン'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)

    plan_start_date = Column(Date, nullable=False, comment='計画開始日')
    plan_end_date = Column(Date, nullable=True, comment='計画終了日')
    long_term_goal = Column(Text, nullable=True, comment='長期目標')
    short_term_goal = Column(Text, nullable=True, comment='短期目標')
    service_content = Column(Text, nullable=True, comment='サービス内容')
    created_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resident = relationship('SSResident', back_populates='care_plans')


# ─────────────────────────────────────────────
# 請求管理
# ─────────────────────────────────────────────

class SSBillingItem(Base):
    """請求項目マスタ"""
    __tablename__ = 'SS_請求項目マスタ'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    item_name = Column(String(200), nullable=False, comment='項目名')
    item_code = Column(String(50), nullable=True, comment='サービスコード')
    unit_price = Column(Numeric(10, 0), nullable=False, default=0, comment='単価（円）')
    unit = Column(String(20), nullable=True, comment='単位（日/回/月等）')
    is_insurance = Column(Boolean, default=True, comment='介護保険対象')
    notes = Column(Text, nullable=True)
    active = Column(Boolean, default=True)


class SSBilling(Base):
    """請求書"""
    __tablename__ = 'SS_請求書'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True)

    billing_year = Column(Integer, nullable=False, comment='請求年')
    billing_month = Column(Integer, nullable=False, comment='請求月')
    billing_date = Column(Date, nullable=True, comment='請求日')
    due_date = Column(Date, nullable=True, comment='支払期限')

    # 金額
    subtotal = Column(Numeric(12, 0), default=0, comment='小計')
    insurance_amount = Column(Numeric(12, 0), default=0, comment='介護保険給付額')
    self_pay_amount = Column(Numeric(12, 0), default=0, comment='自己負担額')
    total_amount = Column(Numeric(12, 0), default=0, comment='合計金額')

    status = Column(SAEnum(BillingStatus), default=BillingStatus.draft, comment='請求状態')
    paid_date = Column(Date, nullable=True, comment='支払日')
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resident = relationship('SSResident', back_populates='billing_records')
    reservation = relationship('SSReservation', back_populates='billing')
    billing_details = relationship('SSBillingDetail', back_populates='billing', cascade='all, delete-orphan')


class SSBillingDetail(Base):
    """請求明細"""
    __tablename__ = 'SS_請求明細'

    id = Column(Integer, primary_key=True, autoincrement=True)
    billing_id = Column(Integer, ForeignKey('SS_請求書.id'), nullable=False)
    item_id = Column(Integer, ForeignKey('SS_請求項目マスタ.id'), nullable=True)
    item_name = Column(String(200), nullable=False, comment='項目名')
    quantity = Column(Numeric(8, 1), default=1, comment='数量')
    unit_price = Column(Numeric(10, 0), default=0, comment='単価')
    amount = Column(Numeric(12, 0), default=0, comment='金額')
    is_insurance = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)

    billing = relationship('SSBilling', back_populates='billing_details')


# ─────────────────────────────────────────────
# スタッフ・シフト管理
# ─────────────────────────────────────────────

class SSShift(Base):
    """シフト管理"""
    __tablename__ = 'SS_シフト'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    employee_id = Column(Integer, ForeignKey('T_従業員.id'), nullable=False, comment='従業員ID')

    shift_date = Column(Date, nullable=False, comment='勤務日')
    shift_type = Column(SAEnum(ShiftType), nullable=False, comment='シフト種別')
    start_time = Column(String(10), nullable=True, comment='開始時刻')
    end_time = Column(String(10), nullable=True, comment='終了時刻')
    break_minutes = Column(Integer, default=0, comment='休憩時間（分）')
    actual_start = Column(String(10), nullable=True, comment='実際の開始時刻')
    actual_end = Column(String(10), nullable=True, comment='実際の終了時刻')
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SSStaffNote(Base):
    """申し送り（スタッフ間連絡）"""
    __tablename__ = 'SS_申し送り'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    written_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True, comment='記載者')

    note_date = Column(Date, nullable=False, comment='申し送り日')
    note_time = Column(String(10), nullable=True, comment='時刻')
    category = Column(String(50), nullable=True, comment='カテゴリ（緊急/通常等）')
    priority = Column(String(20), nullable=True, default='通常', comment='優先度（緊急/重要/通常）')
    target_shift = Column(String(20), nullable=True, comment='対象シフト')
    content = Column(Text, nullable=False, comment='内容')
    is_urgent = Column(Boolean, default=False, comment='緊急フラグ')
    is_resolved = Column(Boolean, default=False, comment='対応済みフラグ')
    author_name = Column(String(100), nullable=True, comment='記載者氏名')

    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# 報告書・書類
# ─────────────────────────────────────────────

class SSReport(Base):
    """報告書"""
    __tablename__ = 'SS_報告書'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=True)
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True)
    created_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)

    report_type = Column(String(50), nullable=False, comment='報告書種別（サービス提供記録/事故報告等）')
    report_date = Column(Date, nullable=False, comment='報告日')
    title = Column(String(200), nullable=True, comment='タイトル')
    content = Column(Text, nullable=True, comment='内容')
    file_path = Column(String(500), nullable=True, comment='添付ファイルパス')
    file_name = Column(String(200), nullable=True, comment='添付ファイル名')
    author_name = Column(String(100), nullable=True, comment='作成者氏名')

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SSIncidentReport(Base):
    """事故・ヒヤリハット報告"""
    __tablename__ = 'SS_事故報告'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=True)
    reported_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)

    incident_date = Column(Date, nullable=False, comment='発生日')
    incident_time = Column(String(10), nullable=True, comment='発生時刻')
    incident_type = Column(String(50), nullable=True, comment='種別（転倒/誤薬/ヒヤリハット等）')
    location = Column(String(100), nullable=True, comment='発生場所')
    description = Column(Text, nullable=True, comment='状況説明')
    injury = Column(Text, nullable=True, comment='受傷状況')
    action_taken = Column(Text, nullable=True, comment='対応内容')
    prevention = Column(Text, nullable=True, comment='再発防止策')
    is_near_miss = Column(Boolean, default=False, comment='ヒヤリハットフラグ')
    severity = Column(String(20), nullable=True, comment='重症度（なし/軽傷/中等度/重傷）')
    response = Column(Text, nullable=True, comment='対応内容')
    reporter_name = Column(String(100), nullable=True, comment='報告者氏名')
    family_notified = Column(Boolean, default=False, comment='家族への報告済み')
    authority_notified = Column(Boolean, default=False, comment='行政への報告済み')

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
