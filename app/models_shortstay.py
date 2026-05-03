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

# ─────────────────────────────────────────────
# 送迎管理（車両・ドライバー・ルート）
# ─────────────────────────────────────────────

class SSVehicle(Base):
    """車両管理"""
    __tablename__ = 'SS_車両'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    name = Column(String(100), nullable=False, comment='車両名')
    plate_number = Column(String(20), nullable=True, comment='ナンバー')
    vehicle_type = Column(String(50), nullable=True, comment='車種')
    capacity = Column(Integer, nullable=False, default=4, comment='定員（乗客数）')
    wheelchair_accessible = Column(Boolean, default=False, comment='車椅子対応')
    has_lift = Column(Boolean, default=False, comment='リフト有無')
    is_active = Column(Boolean, default=True, comment='稼働状況')
    inspection_date = Column(Date, nullable=True, comment='点検日')
    vehicle_inspection_expiry = Column(Date, nullable=True, comment='車検期限')
    insurance_expiry = Column(Date, nullable=True, comment='保険期限')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    drivers = relationship('SSDriver', back_populates='vehicle')
    routes = relationship('SSTransportRoute', back_populates='vehicle')


class SSDriver(Base):
    """ドライバー管理"""
    __tablename__ = 'SS_ドライバー'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    employee_id = Column(Integer, ForeignKey('T_従業員.id'), nullable=True, comment='従業員ID（紐付け）')
    name = Column(String(100), nullable=False, comment='ドライバー名')
    phone = Column(String(20), nullable=True, comment='電話番号')
    license_number = Column(String(30), nullable=True, comment='免許番号')
    license_expiry = Column(Date, nullable=True, comment='免許有効期限')
    vehicle_id = Column(Integer, ForeignKey('SS_車両.id'), nullable=True, comment='担当車両')
    is_active = Column(Boolean, default=True, comment='稼働フラグ')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    vehicle = relationship('SSVehicle', back_populates='drivers')
    ng_restrictions = relationship('SSUserDriverRestriction', back_populates='driver')
    routes = relationship('SSTransportRoute', back_populates='driver')


class SSUserTransportAddress(Base):
    """利用者ごとの送迎先管理（複数登録可）"""
    __tablename__ = 'SS_送迎先'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False, comment='利用者ID')
    name = Column(String(100), nullable=False, comment='送迎先名')
    address_type = Column(String(20), nullable=False, default='自宅',
                          comment='区分（自宅/勤務先/家族宅/病院/その他）')
    postal_code = Column(String(10), nullable=True, comment='郵便番号')
    address = Column(String(300), nullable=True, comment='住所')
    building = Column(String(100), nullable=True, comment='建物名')
    phone = Column(String(20), nullable=True, comment='電話番号')
    latitude = Column(String(20), nullable=True, comment='緯度（将来API連携用）')
    longitude = Column(String(20), nullable=True, comment='経度（将来API連携用）')
    wheelchair_required = Column(Boolean, default=False, comment='車椅子利用')
    care_notes = Column(Text, nullable=True, comment='介助注意事項')
    is_default = Column(Boolean, default=False, comment='標準送迎先フラグ')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resident = relationship('SSResident', backref='transport_addresses')


class SSUserDriverRestriction(Base):
    """NGドライバー設定（利用者ごと）"""
    __tablename__ = 'SS_NGドライバー'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False, comment='利用者ID')
    driver_id = Column(Integer, ForeignKey('SS_ドライバー.id'), nullable=False, comment='NGドライバーID')
    reason = Column(Text, nullable=True, comment='NG理由（管理者のみ閲覧）')
    start_date = Column(Date, nullable=True, comment='開始日')
    end_date = Column(Date, nullable=True, comment='終了日')
    is_active = Column(Boolean, default=True, comment='有効フラグ')
    created_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True, comment='登録者')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resident = relationship('SSResident', backref='driver_restrictions')
    driver = relationship('SSDriver', back_populates='ng_restrictions')


class SSTransportSchedule(Base):
    """送迎スケジュール（日付・区分ごとの送迎対象リスト）"""
    __tablename__ = 'SS_送迎スケジュール'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    schedule_date = Column(Date, nullable=False, comment='送迎日')
    transport_type = Column(String(10), nullable=False, comment='区分（迎え/送り）')
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False)
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True)
    transport_address_id = Column(Integer, ForeignKey('SS_送迎先.id'), nullable=True, comment='送迎先ID')
    desired_time = Column(String(10), nullable=True, comment='希望時刻（後方互換）')
    wheelchair_required = Column(Boolean, default=False, comment='車椅子')
    care_notes = Column(Text, nullable=True, comment='注意事項')
    is_confirmed = Column(Boolean, default=False, comment='確定フラグ')

    # ── 時間条件タイプ（exact/window/before/after/preferred/none）
    time_constraint_type = Column(
        String(20), nullable=True, default='none',
        comment='時間条件タイプ（exact/window/before/after/preferred/none）'
    )
    # 時間条件の重要度（required/preferred/reference）
    time_priority = Column(
        String(20), nullable=True, default='preferred',
        comment='時間条件の重要度（required=必須/preferred=希望/reference=参考）'
    )
    # exact: 指定時刻
    target_time = Column(String(10), nullable=True, comment='指定時刻（exact用）')
    # window: 時間帯指定
    window_start_time = Column(String(10), nullable=True, comment='時間帯開始（window用）')
    window_end_time = Column(String(10), nullable=True, comment='時間帯終了（window用）')
    # before: 期限時刻
    deadline_time = Column(String(10), nullable=True, comment='期限時刻（before用）')
    # after: 開始可能時刻
    not_before_time = Column(String(10), nullable=True, comment='開始可能時刻（after用）')
    # preferred: 希望時刻
    preferred_time = Column(String(10), nullable=True, comment='希望時刻（preferred用）')
    # 乗降時間・余裕時間
    boarding_time_minutes = Column(Integer, nullable=True, default=5, comment='乗降時間（分）')
    buffer_minutes = Column(Integer, nullable=True, default=5, comment='余裕時間（分）')
    delay_tolerance_minutes = Column(Integer, nullable=True, default=0, comment='遅延許容時間（分）')
    # 制約の説明メモ
    time_constraint_note = Column(Text, nullable=True, comment='時間条件の説明メモ')
    # 予約からのコピー元フラグ（再生成時に上書きしないための管理）
    is_manually_edited = Column(Boolean, default=False, comment='手動編集済みフラグ（再生成時に上書きしない）')
    source_reservation_id = Column(
        Integer, ForeignKey('SS_予約.id'), nullable=True,
        comment='生成元予約ID（予約から生成した場合）'
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resident = relationship('SSResident', backref='transport_schedules')
    reservation = relationship('SSReservation', backref='transport_schedules')
    transport_address = relationship('SSUserTransportAddress', backref='transport_schedules')
    source_reservation = relationship(
        'SSReservation',
        foreign_keys='SSTransportSchedule.source_reservation_id',
        backref='generated_transport_schedules'
    )


class SSTransportRoute(Base):
    """送迎ルート（車両ごとの確定ルート）"""
    __tablename__ = 'SS_送迎ルート'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    route_date = Column(Date, nullable=False, comment='送迎日')
    transport_type = Column(String(10), nullable=False, default='混在', comment='区分（迎え/送り/混在）')
    vehicle_id = Column(Integer, ForeignKey('SS_車両.id'), nullable=True)
    driver_id = Column(Integer, ForeignKey('SS_ドライバー.id'), nullable=True)
    route_name = Column(String(100), nullable=True, comment='ルート名（例：1号車）')
    status = Column(String(20), default='draft', comment='状態（draft/confirmed）')
    notes = Column(Text, nullable=True, comment='備考')
    created_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)
    confirmed_by = Column(Integer, ForeignKey('T_従業員.id'), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    vehicle = relationship('SSVehicle', back_populates='routes')
    driver = relationship('SSDriver', back_populates='routes')
    stops = relationship('SSTransportRouteStop', back_populates='route',
                         order_by='SSTransportRouteStop.stop_order', cascade='all, delete-orphan')


class SSTransportTimeConstraint(Base):
    """
    送迎時刻制約
    利用者ごと・予約ごとに「何時までにどこへ」という時間制約を管理する。
    constraint_type で「必須」「希望」「参考」の優先度を区別する。
    """
    __tablename__ = 'SS_送迎時刻制約'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True)
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=False, comment='利用者ID')
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True, comment='予約ID（特定予約に紐付ける場合）')
    transport_address_id = Column(Integer, ForeignKey('SS_送迎先.id'), nullable=True, comment='送迎先ID')

    # 送迎区分
    transport_type = Column(String(10), nullable=False, default='迎え', comment='送迎区分（迎え/送り）')

    # 時刻制約の優先度
    constraint_type = Column(String(10), nullable=False, default='希望',
                             comment='制約種別（必須/希望/参考）')

    # 時刻制約の各項目
    earliest_departure_time = Column(String(10), nullable=True, comment='出発可能時刻（これ以前は出発不可）')
    desired_arrival_time = Column(String(10), nullable=True, comment='到着希望時刻')
    required_arrival_time = Column(String(10), nullable=True, comment='到着必須時刻（必須制約）')
    facility_arrival_deadline = Column(String(10), nullable=True, comment='施設到着期限')
    destination_arrival_deadline = Column(String(10), nullable=True, comment='送迎先到着期限')
    earliest_boarding_time = Column(String(10), nullable=True, comment='乗車可能開始時刻')
    latest_boarding_time = Column(String(10), nullable=True, comment='乗車可能終了時刻')
    required_destination_arrival_time = Column(String(10), nullable=True, comment='滞在先への到着必須時刻')

    # 時間加算値（分単位）
    boarding_time_minutes = Column(Integer, nullable=True, default=5, comment='乗降に必要な時間（分）')
    buffer_minutes = Column(Integer, nullable=True, default=5, comment='余裕時間（分）')
    delay_tolerance_minutes = Column(Integer, nullable=True, default=0, comment='遅延許容時間（分）')

    # 制約の説明（管理者向けメモ）
    constraint_reason = Column(Text, nullable=True, comment='制約の理由・説明（例：家族が17:00以降でないと在宅していない）')

    # 有効期間
    valid_from = Column(Date, nullable=True, comment='有効開始日（空欄=常時有効）')
    valid_to = Column(Date, nullable=True, comment='有効終了日（空欄=常時有効）')
    is_active = Column(Boolean, default=True, comment='有効フラグ')

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    resident = relationship('SSResident', backref='time_constraints')
    reservation = relationship('SSReservation', backref='time_constraints')
    transport_address = relationship('SSUserTransportAddress', backref='time_constraints')


class SSTransportRouteStop(Base):
    """送迎ルート停車地（ルートの各停車ポイント）"""
    __tablename__ = 'SS_送迎ルート停車地'
    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey('SS_送迎ルート.id'), nullable=False)
    stop_order = Column(Integer, nullable=False, comment='停車順序')
    resident_id = Column(Integer, ForeignKey('SS_利用者.id'), nullable=True, comment='利用者ID（施設はNULL）')
    transport_address_id = Column(Integer, ForeignKey('SS_送迎先.id'), nullable=True)
    scheduled_time = Column(String(10), nullable=True, comment='予定時刻')
    address_snapshot = Column(String(300), nullable=True, comment='住所スナップショット（印刷用）')
    phone_snapshot = Column(String(20), nullable=True, comment='電話スナップショット（印刷用）')
    care_notes_snapshot = Column(Text, nullable=True, comment='注意事項スナップショット（印刷用）')
    is_facility = Column(Boolean, default=False, comment='施設フラグ（True=施設、False=利用者宅）')
    estimated_arrival = Column(String(10), nullable=True, comment='到着予定時刻（自動計算）')
    constraint_status = Column(String(20), nullable=True, comment='制約対応状態（ok/warning/violation）')
    constraint_message = Column(Text, nullable=True, comment='制約警告メッセージ')
    # 混在ルート対応カラム
    event_type = Column(String(10), nullable=True, default='facility',
                        comment='イベント種別（pickup=乗車/dropoff=降車/facility=施設）')
    reservation_id = Column(Integer, ForeignKey('SS_予約.id'), nullable=True,
                            comment='予約ID（イベントと予約を結び付ける）')
    current_passengers = Column(Integer, nullable=True, default=0,
                                comment='この停車地到着時の車内乗車人数')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    route = relationship('SSTransportRoute', back_populates='stops')
    resident = relationship('SSResident', backref='route_stops')
    transport_address = relationship('SSUserTransportAddress', backref='route_stops')
    reservation = relationship('SSReservation', backref='route_stops')
