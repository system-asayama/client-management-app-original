# -*- coding: utf-8 -*-
"""
ショートステイ運営管理システム - メインBlueprint

機能:
  - ダッシュボード（稼働状況サマリー）
  - 利用者管理
  - 予約・空き状況管理
  - 入退所管理
  - ケア記録（バイタル・食事・排泄・入浴）
  - ケアプラン管理
  - 請求管理
  - スタッフ・シフト管理
  - 申し送り
  - 報告書・事故報告
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from sqlalchemy import and_, or_, func
from ..db import SessionLocal
from ..models_login import TTenant, TTenpo, TJugyoin
from ..models_shortstay import (
    SSResident, SSEmergencyContact, SSRoom, SSReservation,
    SSCareRecord, SSVitalRecord, SSMealRecord, SSExcretionRecord, SSBathRecord,
    SSCarePlan, SSBillingItem, SSBilling, SSBillingDetail,
    SSShift, SSStaffNote, SSReport, SSIncidentReport,
    SSVehicle, SSDriver, SSUserTransportAddress, SSUserDriverRestriction,
    SSTransportSchedule, SSTransportRoute, SSTransportRouteStop, SSTransportTimeConstraint,
    ReservationStatus, CheckStatus, BillingStatus, ShiftType,
    GenderEnum, CareLevel, MealType, MealAmount, ExcretionType, ExcretionMethod, BathType
)
from ..utils.decorators import ROLES, require_roles

bp = Blueprint('shortstay', __name__, url_prefix='/shortstay')


def _get_store_tenant():
    """セッションから store_id / tenant_id を取得するヘルパー"""
    return session.get('store_id'), session.get('tenant_id')


# ─────────────────────────────────────────────
# ダッシュボード
# ─────────────────────────────────────────────

@bp.route('/')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def dashboard():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        today = date.today()

        # 基本フィルタ
        def base_filter(q, model):
            if store_id:
                return q.filter(model.store_id == store_id)
            elif tenant_id:
                return q.filter(model.tenant_id == tenant_id)
            return q

        # 本日の入所者数
        today_checkins = base_filter(
            db.query(func.count(SSReservation.id)).filter(
                SSReservation.check_in_date == today,
                SSReservation.status == ReservationStatus.confirmed
            ), SSReservation
        ).scalar() or 0

        # 本日の退所者数
        today_checkouts = base_filter(
            db.query(func.count(SSReservation.id)).filter(
                SSReservation.check_out_date == today,
                SSReservation.status == ReservationStatus.confirmed
            ), SSReservation
        ).scalar() or 0

        # 現在入所中の利用者数
        current_residents = base_filter(
            db.query(func.count(SSReservation.id)).filter(
                SSReservation.check_status == CheckStatus.checked_in
            ), SSReservation
        ).scalar() or 0

        # 今後7日間の予約数
        week_later = today + timedelta(days=7)
        upcoming_reservations = base_filter(
            db.query(SSReservation).filter(
                SSReservation.check_in_date.between(today, week_later),
                SSReservation.status.in_([ReservationStatus.confirmed, ReservationStatus.tentative])
            ).order_by(SSReservation.check_in_date), SSReservation
        ).limit(10).all()

        # 未対応の申し送り
        urgent_notes = base_filter(
            db.query(SSStaffNote).filter(
                SSStaffNote.is_resolved == False,
                SSStaffNote.is_urgent == True
            ).order_by(SSStaffNote.note_date.desc()), SSStaffNote
        ).limit(5).all()

        # 利用者総数
        total_residents = base_filter(
            db.query(func.count(SSResident.id)).filter(SSResident.active == True),
            SSResident
        ).scalar() or 0

        # 居室稼働率
        total_rooms = base_filter(
            db.query(func.count(SSRoom.id)).filter(SSRoom.active == True),
            SSRoom
        ).scalar() or 0
        occupancy_rate = round(current_residents / total_rooms * 100, 1) if total_rooms > 0 else 0

        return render_template('shortstay/dashboard.html',
            today=today,
            today_checkins=today_checkins,
            today_checkouts=today_checkouts,
            current_residents=current_residents,
            total_residents=total_residents,
            total_rooms=total_rooms,
            occupancy_rate=occupancy_rate,
            upcoming_reservations=upcoming_reservations,
            urgent_notes=urgent_notes,
        )
    finally:
        db.close()


# ─────────────────────────────────────────────
# 利用者管理
# ─────────────────────────────────────────────

@bp.route('/residents')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def residents():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSResident).filter(SSResident.active == True)
        if store_id:
            q = q.filter(SSResident.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSResident.tenant_id == tenant_id)

        search = request.args.get('search', '').strip()
        if search:
            q = q.filter(or_(
                SSResident.last_name.contains(search),
                SSResident.first_name.contains(search),
                SSResident.last_name_kana.contains(search),
                SSResident.first_name_kana.contains(search),
            ))

        residents_list = q.order_by(SSResident.last_name_kana).all()
        return render_template('shortstay/residents.html',
            residents=residents_list, search=search)
    finally:
        db.close()


@bp.route('/residents/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def resident_new():
    store_id, tenant_id = _get_store_tenant()
    if request.method == 'POST':
        db = SessionLocal()
        try:
            r = SSResident(
                tenant_id=tenant_id,
                store_id=store_id,
                last_name=request.form.get('last_name', ''),
                first_name=request.form.get('first_name', ''),
                last_name_kana=request.form.get('last_name_kana'),
                first_name_kana=request.form.get('first_name_kana'),
                gender=request.form.get('gender') or None,
                birth_date=_parse_date(request.form.get('birth_date')),
                postal_code=request.form.get('postal_code'),
                address=request.form.get('address'),
                phone=request.form.get('phone'),
                care_level=request.form.get('care_level') or None,
                care_insurance_no=request.form.get('care_insurance_no'),
                care_insurance_expiry=_parse_date(request.form.get('care_insurance_expiry')),
                insurer_no=request.form.get('insurer_no'),
                insurer_name=request.form.get('insurer_name'),
                doctor_name=request.form.get('doctor_name'),
                hospital_name=request.form.get('hospital_name'),
                hospital_phone=request.form.get('hospital_phone'),
                allergies=request.form.get('allergies'),
                medical_history=request.form.get('medical_history'),
                medications=request.form.get('medications'),
                special_notes=request.form.get('special_notes'),
                meal_type=request.form.get('meal_type'),
                meal_texture=request.form.get('meal_texture'),
                thickener=bool(request.form.get('thickener')),
                care_manager_name=request.form.get('care_manager_name'),
                care_manager_office=request.form.get('care_manager_office'),
                care_manager_phone=request.form.get('care_manager_phone'),
                # フェイスシート対応フィールド
                consultant_name=request.form.get('consultant_name'),
                disability_support_category=request.form.get('disability_support_category'),
                approved_service_amount=request.form.get('approved_service_amount'),
                certification_valid_from=_parse_date(request.form.get('certification_valid_from')),
                certification_valid_to=_parse_date(request.form.get('certification_valid_to')),
                service_decision_from=_parse_date(request.form.get('service_decision_from')),
                service_decision_to=_parse_date(request.form.get('service_decision_to')),
                disability_certification=request.form.get('disability_certification'),
                meal_action=request.form.get('meal_action'),
                disliked_food=request.form.get('disliked_food'),
                meal_form=request.form.get('meal_form'),
                favorite_food=request.form.get('favorite_food'),
                medication_regular=request.form.get('medication_regular'),
                medication_prn=request.form.get('medication_prn'),
                medication_management=request.form.get('medication_management'),
                medication_special_notes=request.form.get('medication_special_notes'),
                toilet_action=request.form.get('toilet_action'),
                bath_assistance=request.form.get('bath_assistance'),
                urinary_control=request.form.get('urinary_control'),
                bowel_control=request.form.get('bowel_control'),
                dressing_assistance=request.form.get('dressing_assistance'),
                communication=request.form.get('communication'),
            )
            db.add(r)
            db.flush()

            # 緊急連絡先
            ec_names = request.form.getlist('ec_name[]')
            ec_rels = request.form.getlist('ec_relation_type[]')
            ec_phones = request.form.getlist('ec_phone[]')
            for i, name in enumerate(ec_names):
                if name.strip():
                    ec = SSEmergencyContact(
                        resident_id=r.id,
                        name=name.strip(),
                        relation_type=ec_rels[i] if i < len(ec_rels) else None,
                        phone=ec_phones[i] if i < len(ec_phones) else None,
                        sort_order=i,
                    )
                    db.add(ec)

            db.commit()
            flash('利用者を登録しました。', 'success')
            return redirect(url_for('shortstay.resident_detail', resident_id=r.id))
        except Exception as e:
            db.rollback()
            flash(f'登録に失敗しました: {e}', 'error')
        finally:
            db.close()

    return render_template('shortstay/resident_form.html',
        resident=None,
        care_levels=list(CareLevel),
        genders=list(GenderEnum),
    )


@bp.route('/residents/<int:resident_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def resident_detail(resident_id):
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        if not resident:
            flash('利用者が見つかりません。', 'error')
            return redirect(url_for('shortstay.residents'))

        # 最新の予約
        reservations = db.query(SSReservation).filter(
            SSReservation.resident_id == resident_id
        ).order_by(SSReservation.check_in_date.desc()).limit(10).all()

        # 最新のバイタル
        vitals = db.query(SSVitalRecord).filter(
            SSVitalRecord.resident_id == resident_id
        ).order_by(SSVitalRecord.record_date.desc(), SSVitalRecord.record_time.desc()).limit(5).all()

        # 緊急連絡先
        emergency_contacts = db.query(SSEmergencyContact).filter(
            SSEmergencyContact.resident_id == resident_id
        ).order_by(SSEmergencyContact.sort_order).all()

        # ケアプラン（最新）
        care_plan = db.query(SSCarePlan).filter(
            SSCarePlan.resident_id == resident_id
        ).order_by(SSCarePlan.plan_start_date.desc()).first()

        # 年齢計算
        age = None
        if resident.birth_date:
            today = date.today()
            age = today.year - resident.birth_date.year - (
                (today.month, today.day) < (resident.birth_date.month, resident.birth_date.day)
            )

        return render_template('shortstay/resident_detail.html',
            resident=resident,
            reservations=reservations,
            vitals=vitals,
            emergency_contacts=emergency_contacts,
            care_plan=care_plan,
            age=age,
        )
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def resident_edit(resident_id):
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        if not resident:
            flash('利用者が見つかりません。', 'error')
            return redirect(url_for('shortstay.residents'))

        if request.method == 'POST':
            resident.last_name = request.form.get('last_name', '')
            resident.first_name = request.form.get('first_name', '')
            resident.last_name_kana = request.form.get('last_name_kana')
            resident.first_name_kana = request.form.get('first_name_kana')
            resident.gender = request.form.get('gender') or None
            resident.birth_date = _parse_date(request.form.get('birth_date'))
            resident.postal_code = request.form.get('postal_code')
            resident.address = request.form.get('address')
            resident.phone = request.form.get('phone')
            resident.care_level = request.form.get('care_level') or None
            resident.care_insurance_no = request.form.get('care_insurance_no')
            resident.care_insurance_expiry = _parse_date(request.form.get('care_insurance_expiry'))
            resident.insurer_no = request.form.get('insurer_no')
            resident.insurer_name = request.form.get('insurer_name')
            resident.doctor_name = request.form.get('doctor_name')
            resident.hospital_name = request.form.get('hospital_name')
            resident.hospital_phone = request.form.get('hospital_phone')
            resident.allergies = request.form.get('allergies')
            resident.medical_history = request.form.get('medical_history')
            resident.medications = request.form.get('medications')
            resident.special_notes = request.form.get('special_notes')
            resident.meal_type = request.form.get('meal_type')
            resident.meal_texture = request.form.get('meal_texture')
            resident.thickener = bool(request.form.get('thickener'))
            resident.care_manager_name = request.form.get('care_manager_name')
            resident.care_manager_office = request.form.get('care_manager_office')
            resident.care_manager_phone = request.form.get('care_manager_phone')
            # フェイスシート対応フィールド
            resident.consultant_name = request.form.get('consultant_name')
            resident.disability_support_category = request.form.get('disability_support_category')
            resident.approved_service_amount = request.form.get('approved_service_amount')
            resident.certification_valid_from = _parse_date(request.form.get('certification_valid_from'))
            resident.certification_valid_to = _parse_date(request.form.get('certification_valid_to'))
            resident.service_decision_from = _parse_date(request.form.get('service_decision_from'))
            resident.service_decision_to = _parse_date(request.form.get('service_decision_to'))
            resident.disability_certification = request.form.get('disability_certification')
            resident.meal_action = request.form.get('meal_action')
            resident.disliked_food = request.form.get('disliked_food')
            resident.meal_form = request.form.get('meal_form')
            resident.favorite_food = request.form.get('favorite_food')
            resident.medication_regular = request.form.get('medication_regular')
            resident.medication_prn = request.form.get('medication_prn')
            resident.medication_management = request.form.get('medication_management')
            resident.medication_special_notes = request.form.get('medication_special_notes')
            resident.toilet_action = request.form.get('toilet_action')
            resident.bath_assistance = request.form.get('bath_assistance')
            resident.urinary_control = request.form.get('urinary_control')
            resident.bowel_control = request.form.get('bowel_control')
            resident.dressing_assistance = request.form.get('dressing_assistance')
            resident.communication = request.form.get('communication')
            resident.updated_at = datetime.utcnow()

            # 緊急連絡先を更新
            db.query(SSEmergencyContact).filter(SSEmergencyContact.resident_id == resident_id).delete()
            ec_names = request.form.getlist('ec_name[]')
            ec_rels = request.form.getlist('ec_relation_type[]')
            ec_phones = request.form.getlist('ec_phone[]')
            for i, name in enumerate(ec_names):
                if name.strip():
                    ec = SSEmergencyContact(
                        resident_id=resident_id,
                        name=name.strip(),
                        relation_type=ec_rels[i] if i < len(ec_rels) else None,
                        phone=ec_phones[i] if i < len(ec_phones) else None,
                        sort_order=i,
                    )
                    db.add(ec)

            db.commit()
            flash('利用者情報を更新しました。', 'success')
            return redirect(url_for('shortstay.resident_detail', resident_id=resident_id))

        emergency_contacts = db.query(SSEmergencyContact).filter(
            SSEmergencyContact.resident_id == resident_id
        ).order_by(SSEmergencyContact.sort_order).all()

        return render_template('shortstay/resident_form.html',
            resident=resident,
            emergency_contacts=emergency_contacts,
            care_levels=list(CareLevel),
            genders=list(GenderEnum),
        )
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def resident_delete(resident_id):
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        if resident:
            resident.active = False
            db.commit()
            flash('利用者を削除しました。', 'success')
    finally:
        db.close()
    return redirect(url_for('shortstay.residents'))


# ─────────────────────────────────────────────
# 予約管理
# ─────────────────────────────────────────────

@bp.route('/reservations')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def reservations():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSReservation)
        if store_id:
            q = q.filter(SSReservation.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSReservation.tenant_id == tenant_id)

        # フィルタ
        status_filter = request.args.get('status', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')

        if status_filter:
            q = q.filter(SSReservation.status == status_filter)
        if date_from:
            q = q.filter(SSReservation.check_in_date >= _parse_date(date_from))
        if date_to:
            q = q.filter(SSReservation.check_in_date <= _parse_date(date_to))

        reservations_list = q.order_by(SSReservation.check_in_date.desc()).limit(100).all()

        # 利用者情報を付加
        resident_ids = list({r.resident_id for r in reservations_list})
        residents_map = {r.id: r for r in db.query(SSResident).filter(SSResident.id.in_(resident_ids)).all()} if resident_ids else {}

        return render_template('shortstay/reservations.html',
            reservations=reservations_list,
            residents_map=residents_map,
            status_filter=status_filter,
            date_from=date_from,
            date_to=date_to,
            ReservationStatus=ReservationStatus,
        )
    finally:
        db.close()


@bp.route('/reservations/calendar')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def reservation_calendar():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        today = date.today()
        year = int(request.args.get('year', today.year))
        month = int(request.args.get('month', today.month))

        import calendar
        cal = calendar.monthcalendar(year, month)
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])

        q = db.query(SSReservation).filter(
            SSReservation.check_in_date <= last_day,
            SSReservation.check_out_date >= first_day,
            SSReservation.status.in_([ReservationStatus.confirmed, ReservationStatus.tentative])
        )
        if store_id:
            q = q.filter(SSReservation.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSReservation.tenant_id == tenant_id)

        month_reservations = q.all()
        resident_ids = list({r.resident_id for r in month_reservations})
        residents_map = {r.id: r for r in db.query(SSResident).filter(SSResident.id.in_(resident_ids)).all()} if resident_ids else {}

        # 居室一覧
        rooms_q = db.query(SSRoom).filter(SSRoom.active == True)
        if store_id:
            rooms_q = rooms_q.filter(SSRoom.store_id == store_id)
        elif tenant_id:
            rooms_q = rooms_q.filter(SSRoom.tenant_id == tenant_id)
        rooms = rooms_q.order_by(SSRoom.room_number).all()

        return render_template('shortstay/reservation_calendar.html',
            year=year, month=month, cal=cal,
            first_day=first_day, last_day=last_day,
            month_reservations=month_reservations,
            residents_map=residents_map,
            rooms=rooms,
            today=today,
        )
    finally:
        db.close()


@bp.route('/reservations/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def reservation_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            resident_id = int(request.form.get('resident_id', 0))
            check_in = _parse_date(request.form.get('check_in_date'))
            check_out = _parse_date(request.form.get('check_out_date'))

            if not resident_id or not check_in or not check_out:
                flash('必須項目を入力してください。', 'error')
            elif check_in > check_out:
                flash('入所日は退所日より前に設定してください。', 'error')
            else:
                rsv = SSReservation(
                    tenant_id=tenant_id,
                    store_id=store_id,
                    resident_id=resident_id,
                    room_id=int(request.form.get('room_id')) if request.form.get('room_id') else None,
                    check_in_date=check_in,
                    check_out_date=check_out,
                    status=request.form.get('status', ReservationStatus.tentative.value),
                    pickup_required=bool(request.form.get('pickup_required')),
                    dropoff_required=bool(request.form.get('dropoff_required')),
                    pickup_address=request.form.get('pickup_address'),
                    pickup_time=request.form.get('pickup_time'),
                    dropoff_time=request.form.get('dropoff_time'),
                    service_type=request.form.get('service_type'),
                    notes=request.form.get('notes'),
                )
                db.add(rsv)
                db.commit()
                flash('予約を登録しました。', 'success')
                return redirect(url_for('shortstay.reservation_detail', reservation_id=rsv.id))

        # 利用者一覧
        residents_q = db.query(SSResident).filter(SSResident.active == True)
        if store_id:
            residents_q = residents_q.filter(SSResident.store_id == store_id)
        elif tenant_id:
            residents_q = residents_q.filter(SSResident.tenant_id == tenant_id)
        residents_list = residents_q.order_by(SSResident.last_name_kana).all()

        # 居室一覧
        rooms_q = db.query(SSRoom).filter(SSRoom.active == True)
        if store_id:
            rooms_q = rooms_q.filter(SSRoom.store_id == store_id)
        elif tenant_id:
            rooms_q = rooms_q.filter(SSRoom.tenant_id == tenant_id)
        rooms = rooms_q.order_by(SSRoom.room_number).all()

        prefill_resident = request.args.get('resident_id', '')

        return render_template('shortstay/reservation_form.html',
            reservation=None,
            residents=residents_list,
            rooms=rooms,
            ReservationStatus=ReservationStatus,
            prefill_resident=prefill_resident,
        )
    finally:
        db.close()


@bp.route('/reservations/<int:reservation_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def reservation_detail(reservation_id):
    db = SessionLocal()
    try:
        rsv = db.query(SSReservation).filter(SSReservation.id == reservation_id).first()
        if not rsv:
            flash('予約が見つかりません。', 'error')
            return redirect(url_for('shortstay.reservations'))

        resident = db.query(SSResident).filter(SSResident.id == rsv.resident_id).first()
        room = db.query(SSRoom).filter(SSRoom.id == rsv.room_id).first() if rsv.room_id else None
        billing = db.query(SSBilling).filter(SSBilling.reservation_id == reservation_id).first()

        # ケア記録（この予約に紐づく）
        care_records = db.query(SSCareRecord).filter(
            SSCareRecord.reservation_id == reservation_id
        ).order_by(SSCareRecord.record_date.desc(), SSCareRecord.record_time.desc()).limit(20).all()

        return render_template('shortstay/reservation_detail.html',
            reservation=rsv,
            resident=resident,
            room=room,
            billing=billing,
            care_records=care_records,
            ReservationStatus=ReservationStatus,
            CheckStatus=CheckStatus,
        )
    finally:
        db.close()


@bp.route('/reservations/<int:reservation_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def reservation_edit(reservation_id):
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        rsv = db.query(SSReservation).filter(SSReservation.id == reservation_id).first()
        if not rsv:
            flash('予約が見つかりません。', 'error')
            return redirect(url_for('shortstay.reservations'))

        if request.method == 'POST':
            rsv.resident_id = int(request.form.get('resident_id', rsv.resident_id))
            rsv.room_id = int(request.form.get('room_id')) if request.form.get('room_id') else None
            rsv.check_in_date = _parse_date(request.form.get('check_in_date')) or rsv.check_in_date
            rsv.check_out_date = _parse_date(request.form.get('check_out_date')) or rsv.check_out_date
            rsv.status = request.form.get('status', rsv.status)
            rsv.check_status = request.form.get('check_status', rsv.check_status)
            rsv.pickup_required = bool(request.form.get('pickup_required'))
            rsv.dropoff_required = bool(request.form.get('dropoff_required'))
            rsv.pickup_address = request.form.get('pickup_address')
            rsv.pickup_time = request.form.get('pickup_time')
            rsv.dropoff_time = request.form.get('dropoff_time')
            rsv.service_type = request.form.get('service_type')
            rsv.notes = request.form.get('notes')
            rsv.updated_at = datetime.utcnow()

            # 入退所日時の更新
            if rsv.check_status == CheckStatus.checked_in.value and not rsv.actual_check_in:
                rsv.actual_check_in = datetime.utcnow()
            elif rsv.check_status == CheckStatus.checked_out.value and not rsv.actual_check_out:
                rsv.actual_check_out = datetime.utcnow()

            db.commit()
            flash('予約を更新しました。', 'success')
            return redirect(url_for('shortstay.reservation_detail', reservation_id=reservation_id))

        residents_q = db.query(SSResident).filter(SSResident.active == True)
        if store_id:
            residents_q = residents_q.filter(SSResident.store_id == store_id)
        elif tenant_id:
            residents_q = residents_q.filter(SSResident.tenant_id == tenant_id)
        residents_list = residents_q.order_by(SSResident.last_name_kana).all()

        rooms_q = db.query(SSRoom).filter(SSRoom.active == True)
        if store_id:
            rooms_q = rooms_q.filter(SSRoom.store_id == store_id)
        elif tenant_id:
            rooms_q = rooms_q.filter(SSRoom.tenant_id == tenant_id)
        rooms = rooms_q.order_by(SSRoom.room_number).all()

        return render_template('shortstay/reservation_form.html',
            reservation=rsv,
            residents=residents_list,
            rooms=rooms,
            ReservationStatus=ReservationStatus,
            CheckStatus=CheckStatus,
        )
    finally:
        db.close()


# ─────────────────────────────────────────────
# ケア記録
# ─────────────────────────────────────────────

@bp.route('/care_records')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def care_records():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        today = date.today()
        record_date = _parse_date(request.args.get('date', '')) or today
        resident_id = request.args.get('resident_id', '')

        # バイタル記録
        vq = db.query(SSVitalRecord).filter(SSVitalRecord.record_date == record_date)
        if store_id:
            vq = vq.filter(SSVitalRecord.store_id == store_id)
        elif tenant_id:
            vq = vq.filter(SSVitalRecord.tenant_id == tenant_id)
        if resident_id:
            vq = vq.filter(SSVitalRecord.resident_id == int(resident_id))
        vitals = vq.order_by(SSVitalRecord.record_time).all()

        # 食事記録
        mq = db.query(SSMealRecord).filter(SSMealRecord.record_date == record_date)
        if store_id:
            mq = mq.filter(SSMealRecord.store_id == store_id)
        elif tenant_id:
            mq = mq.filter(SSMealRecord.tenant_id == tenant_id)
        if resident_id:
            mq = mq.filter(SSMealRecord.resident_id == int(resident_id))
        meals = mq.all()

        # 排泄記録
        eq = db.query(SSExcretionRecord).filter(SSExcretionRecord.record_date == record_date)
        if store_id:
            eq = eq.filter(SSExcretionRecord.store_id == store_id)
        elif tenant_id:
            eq = eq.filter(SSExcretionRecord.tenant_id == tenant_id)
        if resident_id:
            eq = eq.filter(SSExcretionRecord.resident_id == int(resident_id))
        excretions = eq.order_by(SSExcretionRecord.record_time).all()

        # 入浴記録
        bq = db.query(SSBathRecord).filter(SSBathRecord.record_date == record_date)
        if store_id:
            bq = bq.filter(SSBathRecord.store_id == store_id)
        elif tenant_id:
            bq = bq.filter(SSBathRecord.tenant_id == tenant_id)
        if resident_id:
            bq = bq.filter(SSBathRecord.resident_id == int(resident_id))
        baths = bq.all()

        # 現在入所中の利用者
        current_q = db.query(SSReservation).filter(
            SSReservation.check_status == CheckStatus.checked_in
        )
        if store_id:
            current_q = current_q.filter(SSReservation.store_id == store_id)
        elif tenant_id:
            current_q = current_q.filter(SSReservation.tenant_id == tenant_id)
        current_reservations = current_q.all()
        current_resident_ids = [r.resident_id for r in current_reservations]
        current_residents = db.query(SSResident).filter(SSResident.id.in_(current_resident_ids)).all() if current_resident_ids else []

        # 全利用者（フィルタ用）
        all_residents_q = db.query(SSResident).filter(SSResident.active == True)
        if store_id:
            all_residents_q = all_residents_q.filter(SSResident.store_id == store_id)
        elif tenant_id:
            all_residents_q = all_residents_q.filter(SSResident.tenant_id == tenant_id)
        all_residents = all_residents_q.order_by(SSResident.last_name_kana).all()
        residents_map = {r.id: r for r in all_residents}

        return render_template('shortstay/care_records.html',
            record_date=record_date,
            resident_id=resident_id,
            vitals=vitals,
            meals=meals,
            excretions=excretions,
            baths=baths,
            current_residents=current_residents,
            all_residents=all_residents,
            residents_map=residents_map,
        )
    finally:
        db.close()


@bp.route('/care_records/vital/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def vital_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            v = SSVitalRecord(
                tenant_id=tenant_id,
                store_id=store_id,
                resident_id=int(request.form.get('resident_id', 0)),
                reservation_id=int(request.form.get('reservation_id')) if request.form.get('reservation_id') else None,
                record_date=_parse_date(request.form.get('record_date')) or date.today(),
                record_time=request.form.get('record_time'),
                body_temp=_parse_decimal(request.form.get('body_temp')),
                blood_pressure_high=_parse_int(request.form.get('blood_pressure_high')),
                blood_pressure_low=_parse_int(request.form.get('blood_pressure_low')),
                pulse=_parse_int(request.form.get('pulse')),
                spo2=_parse_int(request.form.get('spo2')),
                respiration=_parse_int(request.form.get('respiration')),
                weight=_parse_decimal(request.form.get('weight')),
                notes=request.form.get('notes'),
            )
            db.add(v)
            db.commit()
            flash('バイタル記録を登録しました。', 'success')
            return redirect(url_for('shortstay.care_records', date=v.record_date))

        residents_list = _get_residents(db, store_id, tenant_id)
        return render_template('shortstay/vital_form.html',
            residents=residents_list, today=date.today())
    finally:
        db.close()


@bp.route('/care_records/meal/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def meal_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            m = SSMealRecord(
                tenant_id=tenant_id,
                store_id=store_id,
                resident_id=int(request.form.get('resident_id', 0)),
                reservation_id=int(request.form.get('reservation_id')) if request.form.get('reservation_id') else None,
                record_date=_parse_date(request.form.get('record_date')) or date.today(),
                meal_type=request.form.get('meal_type'),
                meal_amount=request.form.get('meal_amount') or None,
                water_intake_ml=_parse_int(request.form.get('water_intake_ml')),
                notes=request.form.get('notes'),
            )
            db.add(m)
            db.commit()
            flash('食事記録を登録しました。', 'success')
            return redirect(url_for('shortstay.care_records', date=m.record_date))

        residents_list = _get_residents(db, store_id, tenant_id)
        return render_template('shortstay/meal_form.html',
            residents=residents_list, today=date.today(),
            MealType=MealType, MealAmount=MealAmount)
    finally:
        db.close()


@bp.route('/care_records/excretion/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def excretion_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            e = SSExcretionRecord(
                tenant_id=tenant_id,
                store_id=store_id,
                resident_id=int(request.form.get('resident_id', 0)),
                reservation_id=int(request.form.get('reservation_id')) if request.form.get('reservation_id') else None,
                record_date=_parse_date(request.form.get('record_date')) or date.today(),
                record_time=request.form.get('record_time'),
                excretion_type=request.form.get('excretion_type') or None,
                excretion_method=request.form.get('excretion_method') or None,
                amount=request.form.get('amount'),
                stool_form=request.form.get('stool_form'),
                notes=request.form.get('notes'),
            )
            db.add(e)
            db.commit()
            flash('排泄記録を登録しました。', 'success')
            return redirect(url_for('shortstay.care_records', date=e.record_date))

        residents_list = _get_residents(db, store_id, tenant_id)
        return render_template('shortstay/excretion_form.html',
            residents=residents_list, today=date.today(),
            ExcretionType=ExcretionType, ExcretionMethod=ExcretionMethod)
    finally:
        db.close()


@bp.route('/care_records/bath/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def bath_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            b = SSBathRecord(
                tenant_id=tenant_id,
                store_id=store_id,
                resident_id=int(request.form.get('resident_id', 0)),
                reservation_id=int(request.form.get('reservation_id')) if request.form.get('reservation_id') else None,
                record_date=_parse_date(request.form.get('record_date')) or date.today(),
                bath_type=request.form.get('bath_type') or None,
                duration_minutes=_parse_int(request.form.get('duration_minutes')),
                skin_condition=request.form.get('skin_condition'),
                notes=request.form.get('notes'),
            )
            db.add(b)
            db.commit()
            flash('入浴記録を登録しました。', 'success')
            return redirect(url_for('shortstay.care_records', date=b.record_date))

        residents_list = _get_residents(db, store_id, tenant_id)
        return render_template('shortstay/bath_form.html',
            residents=residents_list, today=date.today(), BathType=BathType)
    finally:
        db.close()


# ─────────────────────────────────────────────
# ケアプラン
# ─────────────────────────────────────────────

@bp.route('/care_plans')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def care_plans():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSCarePlan)
        if store_id:
            q = q.filter(SSCarePlan.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSCarePlan.tenant_id == tenant_id)
        plans = q.order_by(SSCarePlan.plan_start_date.desc()).all()
        resident_ids = list({p.resident_id for p in plans})
        residents_map = {r.id: r for r in db.query(SSResident).filter(SSResident.id.in_(resident_ids)).all()} if resident_ids else {}
        return render_template('shortstay/care_plans.html', plans=plans, residents_map=residents_map)
    finally:
        db.close()


@bp.route('/care_plans/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def care_plan_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            plan = SSCarePlan(
                tenant_id=tenant_id,
                store_id=store_id,
                resident_id=int(request.form.get('resident_id', 0)),
                plan_start_date=_parse_date(request.form.get('plan_start_date')) or date.today(),
                plan_end_date=_parse_date(request.form.get('plan_end_date')),
                long_term_goal=request.form.get('long_term_goal'),
                short_term_goal=request.form.get('short_term_goal'),
                service_content=request.form.get('service_content'),
                notes=request.form.get('notes'),
            )
            db.add(plan)
            db.commit()
            flash('ケアプランを登録しました。', 'success')
            return redirect(url_for('shortstay.care_plans'))

        residents_list = _get_residents(db, store_id, tenant_id)
        prefill_resident = request.args.get('resident_id', '')
        return render_template('shortstay/care_plan_form.html',
            plan=None, residents=residents_list, prefill_resident=prefill_resident)
    finally:
        db.close()


@bp.route('/care_plans/<int:plan_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def care_plan_edit(plan_id):
    db = SessionLocal()
    try:
        plan = db.query(SSCarePlan).filter(SSCarePlan.id == plan_id).first()
        if not plan:
            flash('ケアプランが見つかりません。', 'error')
            return redirect(url_for('shortstay.care_plans'))

        if request.method == 'POST':
            plan.plan_start_date = _parse_date(request.form.get('plan_start_date')) or plan.plan_start_date
            plan.plan_end_date = _parse_date(request.form.get('plan_end_date'))
            plan.long_term_goal = request.form.get('long_term_goal')
            plan.short_term_goal = request.form.get('short_term_goal')
            plan.service_content = request.form.get('service_content')
            plan.notes = request.form.get('notes')
            plan.updated_at = datetime.utcnow()
            db.commit()
            flash('ケアプランを更新しました。', 'success')
            return redirect(url_for('shortstay.care_plans'))

        store_id, tenant_id = _get_store_tenant()
        residents_list = _get_residents(db, store_id, tenant_id)
        return render_template('shortstay/care_plan_form.html',
            plan=plan, residents=residents_list)
    finally:
        db.close()


# ─────────────────────────────────────────────
# 居室管理
# ─────────────────────────────────────────────

@bp.route('/rooms')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def rooms():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSRoom).filter(SSRoom.active == True)
        if store_id:
            q = q.filter(SSRoom.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSRoom.tenant_id == tenant_id)
        rooms_list = q.order_by(SSRoom.room_number).all()
        return render_template('shortstay/rooms.html', rooms=rooms_list)
    finally:
        db.close()


@bp.route('/rooms/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def room_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            room = SSRoom(
                tenant_id=tenant_id,
                store_id=store_id,
                room_number=request.form.get('room_number', ''),
                room_name=request.form.get('room_name'),
                capacity=_parse_int(request.form.get('capacity')) or 1,
                floor=request.form.get('floor'),
                notes=request.form.get('notes'),
            )
            db.add(room)
            db.commit()
            flash('居室を登録しました。', 'success')
            return redirect(url_for('shortstay.rooms'))

        return render_template('shortstay/room_form.html', room=None)
    finally:
        db.close()


@bp.route('/rooms/<int:room_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def room_edit(room_id):
    db = SessionLocal()
    try:
        room = db.query(SSRoom).filter(SSRoom.id == room_id).first()
        if not room:
            flash('居室が見つかりません。', 'error')
            return redirect(url_for('shortstay.rooms'))

        if request.method == 'POST':
            room.room_number = request.form.get('room_number', room.room_number)
            room.room_name = request.form.get('room_name')
            room.capacity = _parse_int(request.form.get('capacity')) or room.capacity
            room.floor = request.form.get('floor')
            room.notes = request.form.get('notes')
            db.commit()
            flash('居室を更新しました。', 'success')
            return redirect(url_for('shortstay.rooms'))

        return render_template('shortstay/room_form.html', room=room)
    finally:
        db.close()


# ─────────────────────────────────────────────
# 請求管理
# ─────────────────────────────────────────────

@bp.route('/billing')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def billing_list():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSBilling)
        if store_id:
            q = q.filter(SSBilling.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSBilling.tenant_id == tenant_id)

        status_filter = request.args.get('status', '')
        if status_filter:
            q = q.filter(SSBilling.status == status_filter)

        billings = q.order_by(SSBilling.billing_year.desc(), SSBilling.billing_month.desc()).all()
        resident_ids = list({b.resident_id for b in billings})
        residents_map = {r.id: r for r in db.query(SSResident).filter(SSResident.id.in_(resident_ids)).all()} if resident_ids else {}

        return render_template('shortstay/billing_list.html',
            billings=billings,
            residents_map=residents_map,
            status_filter=status_filter,
            BillingStatus=BillingStatus,
        )
    finally:
        db.close()


@bp.route('/billing/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def billing_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            billing = SSBilling(
                tenant_id=tenant_id,
                store_id=store_id,
                resident_id=int(request.form.get('resident_id', 0)),
                reservation_id=int(request.form.get('reservation_id')) if request.form.get('reservation_id') else None,
                billing_year=int(request.form.get('billing_year', date.today().year)),
                billing_month=int(request.form.get('billing_month', date.today().month)),
                billing_date=_parse_date(request.form.get('billing_date')),
                due_date=_parse_date(request.form.get('due_date')),
                notes=request.form.get('notes'),
                status=BillingStatus.draft,
            )
            db.add(billing)
            db.flush()

            # 明細
            item_names = request.form.getlist('item_name[]')
            quantities = request.form.getlist('quantity[]')
            unit_prices = request.form.getlist('unit_price[]')
            is_insurances = request.form.getlist('is_insurance[]')

            total = 0
            insurance_total = 0
            for i, name in enumerate(item_names):
                if not name.strip():
                    continue
                qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1
                price = int(unit_prices[i]) if i < len(unit_prices) and unit_prices[i] else 0
                amount = int(qty * price)
                is_ins = str(i) in is_insurances or (i < len(is_insurances) and is_insurances[i])
                detail = SSBillingDetail(
                    billing_id=billing.id,
                    item_name=name.strip(),
                    quantity=qty,
                    unit_price=price,
                    amount=amount,
                    is_insurance=bool(is_ins),
                )
                db.add(detail)
                total += amount
                if is_ins:
                    insurance_total += amount

            # 自己負担は1割（簡易計算）
            self_pay = int(total * 0.1)
            billing.subtotal = total
            billing.insurance_amount = total - self_pay
            billing.self_pay_amount = self_pay
            billing.total_amount = total

            db.commit()
            flash('請求書を作成しました。', 'success')
            return redirect(url_for('shortstay.billing_detail', billing_id=billing.id))

        residents_list = _get_residents(db, store_id, tenant_id)

        # 請求項目マスタ
        items_q = db.query(SSBillingItem).filter(SSBillingItem.active == True)
        if store_id:
            items_q = items_q.filter(SSBillingItem.store_id == store_id)
        elif tenant_id:
            items_q = items_q.filter(SSBillingItem.tenant_id == tenant_id)
        billing_items = items_q.all()

        today = date.today()
        return render_template('shortstay/billing_form.html',
            billing=None,
            residents=residents_list,
            billing_items=billing_items,
            today=today,
        )
    finally:
        db.close()


@bp.route('/billing/<int:billing_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def billing_detail(billing_id):
    db = SessionLocal()
    try:
        billing = db.query(SSBilling).filter(SSBilling.id == billing_id).first()
        if not billing:
            flash('請求書が見つかりません。', 'error')
            return redirect(url_for('shortstay.billing_list'))

        resident = db.query(SSResident).filter(SSResident.id == billing.resident_id).first()
        details = db.query(SSBillingDetail).filter(SSBillingDetail.billing_id == billing_id).all()

        return render_template('shortstay/billing_detail.html',
            billing=billing,
            resident=resident,
            details=details,
            BillingStatus=BillingStatus,
        )
    finally:
        db.close()


@bp.route('/billing/<int:billing_id>/update_status', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def billing_update_status(billing_id):
    db = SessionLocal()
    try:
        billing = db.query(SSBilling).filter(SSBilling.id == billing_id).first()
        if billing:
            new_status = request.form.get('status')
            billing.status = new_status
            if new_status == BillingStatus.paid.value:
                billing.paid_date = _parse_date(request.form.get('paid_date')) or date.today()
            billing.updated_at = datetime.utcnow()
            db.commit()
            flash('請求状態を更新しました。', 'success')
    finally:
        db.close()
    return redirect(url_for('shortstay.billing_detail', billing_id=billing_id))


# 請求項目マスタ管理
@bp.route('/billing_items')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def billing_items():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSBillingItem).filter(SSBillingItem.active == True)
        if store_id:
            q = q.filter(SSBillingItem.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSBillingItem.tenant_id == tenant_id)
        items = q.order_by(SSBillingItem.item_name).all()
        return render_template('shortstay/billing_items.html', items=items)
    finally:
        db.close()


@bp.route('/billing_items/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def billing_item_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            item = SSBillingItem(
                tenant_id=tenant_id,
                store_id=store_id,
                item_name=request.form.get('item_name', ''),
                item_code=request.form.get('item_code'),
                unit_price=_parse_int(request.form.get('unit_price')) or 0,
                unit=request.form.get('unit'),
                is_insurance=bool(request.form.get('is_insurance')),
                notes=request.form.get('notes'),
            )
            db.add(item)
            db.commit()
            flash('請求項目を登録しました。', 'success')
            return redirect(url_for('shortstay.billing_items'))

        return render_template('shortstay/billing_item_form.html', item=None)
    finally:
        db.close()


# ─────────────────────────────────────────────
# シフト管理
# ─────────────────────────────────────────────

@bp.route('/shifts')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def shifts():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        today = date.today()
        year = int(request.args.get('year', today.year))
        month = int(request.args.get('month', today.month))

        import calendar
        _, days_in_month = calendar.monthrange(year, month)
        first_day = date(year, month, 1)
        last_day = date(year, month, days_in_month)

        q = db.query(SSShift).filter(
            SSShift.shift_date.between(first_day, last_day)
        )
        if store_id:
            q = q.filter(SSShift.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSShift.tenant_id == tenant_id)
        shifts_list = q.order_by(SSShift.shift_date, SSShift.employee_id).all()

        # 従業員一覧
        emp_q = db.query(TJugyoin).filter(TJugyoin.active == True)
        if store_id:
            emp_q = emp_q.filter(TJugyoin.store_id == store_id)
        elif tenant_id:
            emp_q = emp_q.filter(TJugyoin.tenant_id == tenant_id)
        employees = emp_q.order_by(TJugyoin.name).all()

        # シフトをマップ化 {employee_id: {date: shift}}
        shift_map = {}
        for s in shifts_list:
            if s.employee_id not in shift_map:
                shift_map[s.employee_id] = {}
            shift_map[s.employee_id][s.shift_date] = s

        return render_template('shortstay/shifts.html',
            year=year, month=month,
            first_day=first_day, last_day=last_day,
            days_in_month=days_in_month,
            shifts=shifts_list,
            shift_map=shift_map,
            employees=employees,
            ShiftType=ShiftType,
            today=today,
        )
    finally:
        db.close()


@bp.route('/shifts/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def shift_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            shift = SSShift(
                tenant_id=tenant_id,
                store_id=store_id,
                employee_id=int(request.form.get('employee_id', 0)),
                shift_date=_parse_date(request.form.get('shift_date')) or date.today(),
                shift_type=request.form.get('shift_type', ShiftType.day.value),
                start_time=request.form.get('start_time'),
                end_time=request.form.get('end_time'),
                break_minutes=_parse_int(request.form.get('break_minutes')) or 0,
                notes=request.form.get('notes'),
            )
            db.add(shift)
            db.commit()
            flash('シフトを登録しました。', 'success')
            return redirect(url_for('shortstay.shifts'))

        emp_q = db.query(TJugyoin).filter(TJugyoin.active == True)
        if store_id:
            emp_q = emp_q.filter(TJugyoin.store_id == store_id)
        elif tenant_id:
            emp_q = emp_q.filter(TJugyoin.tenant_id == tenant_id)
        employees = emp_q.order_by(TJugyoin.name).all()

        return render_template('shortstay/shift_form.html',
            shift=None, employees=employees, ShiftType=ShiftType, today=date.today())
    finally:
        db.close()


# ─────────────────────────────────────────────
# 申し送り
# ─────────────────────────────────────────────

@bp.route('/staff_notes')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def staff_notes():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSStaffNote)
        if store_id:
            q = q.filter(SSStaffNote.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSStaffNote.tenant_id == tenant_id)

        show_resolved = request.args.get('show_resolved', '0') == '1'
        if not show_resolved:
            q = q.filter(SSStaffNote.is_resolved == False)

        notes = q.order_by(SSStaffNote.is_urgent.desc(), SSStaffNote.note_date.desc()).limit(50).all()
        return render_template('shortstay/staff_notes.html',
            notes=notes, show_resolved=show_resolved)
    finally:
        db.close()


@bp.route('/staff_notes/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def staff_note_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            note = SSStaffNote(
                tenant_id=tenant_id,
                store_id=store_id,
                written_by=session.get('user_id'),
                note_date=_parse_date(request.form.get('note_date')) or date.today(),
                note_time=request.form.get('note_time'),
                category=request.form.get('category'),
                content=request.form.get('content', ''),
                is_urgent=bool(request.form.get('is_urgent')),
            )
            db.add(note)
            db.commit()
            flash('申し送りを登録しました。', 'success')
            return redirect(url_for('shortstay.staff_notes'))

        return render_template('shortstay/staff_note_form.html', note=None, today=date.today())
    finally:
        db.close()


@bp.route('/staff_notes/<int:note_id>/resolve', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def staff_note_resolve(note_id):
    db = SessionLocal()
    try:
        note = db.query(SSStaffNote).filter(SSStaffNote.id == note_id).first()
        if note:
            note.is_resolved = True
            db.commit()
            flash('申し送りを対応済みにしました。', 'success')
    finally:
        db.close()
    return redirect(url_for('shortstay.staff_notes'))


# ─────────────────────────────────────────────
# 報告書・事故報告
# ─────────────────────────────────────────────

@bp.route('/reports')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def reports():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSReport)
        if store_id:
            q = q.filter(SSReport.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSReport.tenant_id == tenant_id)

        report_type = request.args.get('type', '')
        if report_type:
            q = q.filter(SSReport.report_type == report_type)

        reports_list = q.order_by(SSReport.report_date.desc()).limit(50).all()
        resident_ids = list({r.resident_id for r in reports_list if r.resident_id})
        residents_map = {r.id: r for r in db.query(SSResident).filter(SSResident.id.in_(resident_ids)).all()} if resident_ids else {}

        return render_template('shortstay/reports.html',
            reports=reports_list, residents_map=residents_map, report_type=report_type)
    finally:
        db.close()


@bp.route('/reports/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def report_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            report = SSReport(
                tenant_id=tenant_id,
                store_id=store_id,
                resident_id=int(request.form.get('resident_id')) if request.form.get('resident_id') else None,
                created_by=session.get('user_id'),
                report_type=request.form.get('report_type', 'サービス提供記録'),
                report_date=_parse_date(request.form.get('report_date')) or date.today(),
                title=request.form.get('title'),
                content=request.form.get('content'),
            )
            db.add(report)
            db.commit()
            flash('報告書を登録しました。', 'success')
            return redirect(url_for('shortstay.reports'))

        residents_list = _get_residents(db, store_id, tenant_id)
        return render_template('shortstay/report_form.html',
            report=None, residents=residents_list, today=date.today())
    finally:
        db.close()


@bp.route('/incidents')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def incidents():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSIncidentReport)
        if store_id:
            q = q.filter(SSIncidentReport.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSIncidentReport.tenant_id == tenant_id)

        incidents_list = q.order_by(SSIncidentReport.incident_date.desc()).limit(50).all()
        resident_ids = list({i.resident_id for i in incidents_list if i.resident_id})
        residents_map = {r.id: r for r in db.query(SSResident).filter(SSResident.id.in_(resident_ids)).all()} if resident_ids else {}

        return render_template('shortstay/incidents.html',
            incidents=incidents_list, residents_map=residents_map)
    finally:
        db.close()


@bp.route('/incidents/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def incident_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            incident = SSIncidentReport(
                tenant_id=tenant_id,
                store_id=store_id,
                resident_id=int(request.form.get('resident_id')) if request.form.get('resident_id') else None,
                reported_by=session.get('user_id'),
                incident_date=_parse_date(request.form.get('incident_date')) or date.today(),
                incident_time=request.form.get('incident_time'),
                incident_type=request.form.get('incident_type'),
                location=request.form.get('location'),
                description=request.form.get('description'),
                injury=request.form.get('injury'),
                action_taken=request.form.get('action_taken'),
                prevention=request.form.get('prevention'),
                is_near_miss=bool(request.form.get('is_near_miss')),
            )
            db.add(incident)
            db.commit()
            flash('事故・ヒヤリハット報告を登録しました。', 'success')
            return redirect(url_for('shortstay.incidents'))

        residents_list = _get_residents(db, store_id, tenant_id)
        return render_template('shortstay/incident_form.html',
            incident=None, residents=residents_list, today=date.today())
    finally:
        db.close()


@bp.route('/incidents/<int:incident_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def incident_detail(incident_id):
    db = SessionLocal()
    try:
        incident = db.query(SSIncidentReport).filter(SSIncidentReport.id == incident_id).first()
        if not incident:
            flash('報告書が見つかりません。', 'error')
            return redirect(url_for('shortstay.incidents'))
        resident = db.query(SSResident).filter(SSResident.id == incident.resident_id).first() if incident.resident_id else None
        return render_template('shortstay/incident_detail.html',
            incident=incident, resident=resident)
    finally:
        db.close()


# ─────────────────────────────────────────────
# ヘルパー関数
# ─────────────────────────────────────────────

def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _parse_int(s):
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _parse_decimal(s):
    if not s:
        return None
    try:
        from decimal import Decimal
        return Decimal(s)
    except Exception:
        return None


def _get_residents(db, store_id, tenant_id):
    q = db.query(SSResident).filter(SSResident.active == True)
    if store_id:
        q = q.filter(SSResident.store_id == store_id)
    elif tenant_id:
        q = q.filter(SSResident.tenant_id == tenant_id)
    return q.order_by(SSResident.last_name_kana).all()

# ─────────────────────────────────────────────
# 追加ルート（編集・詳細）
# ─────────────────────────────────────────────

@bp.route('/billing/<int:billing_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def billing_edit(billing_id):
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        billing = db.query(SSBilling).filter(SSBilling.id == billing_id).first()
        if not billing:
            flash('請求書が見つかりません。', 'error')
            return redirect(url_for('shortstay.billing_list'))
        if request.method == 'POST':
            billing.resident_id = _parse_int(request.form.get('resident_id'))
            billing.reservation_id = _parse_int(request.form.get('reservation_id'))
            billing.billing_year = _parse_int(request.form.get('billing_year'))
            billing.billing_month = _parse_int(request.form.get('billing_month'))
            billing.total_amount = _parse_decimal(request.form.get('total_amount')) or 0
            billing.insurance_amount = _parse_decimal(request.form.get('insurance_amount')) or 0
            billing.self_pay_amount = _parse_decimal(request.form.get('self_pay_amount')) or 0
            billing.meal_fee = _parse_decimal(request.form.get('meal_fee')) or 0
            billing.accommodation_fee = _parse_decimal(request.form.get('accommodation_fee')) or 0
            billing.other_fee = _parse_decimal(request.form.get('other_fee')) or 0
            billing.status = BillingStatus(request.form.get('status', '未発行'))
            billing.payment_date = _parse_date(request.form.get('payment_date'))
            billing.payment_method = request.form.get('payment_method')
            billing.notes = request.form.get('notes')
            db.commit()
            flash('請求書を更新しました。', 'success')
            return redirect(url_for('shortstay.billing_detail', billing_id=billing.id))
        residents_list = _get_residents(db, store_id, tenant_id)
        reservations_list = db.query(SSReservation).all()
        residents_map = {r.id: r for r in residents_list}
        from datetime import datetime as dt
        return render_template('shortstay/billing_form.html',
            billing=billing, residents=residents_list,
            reservations=reservations_list, residents_map=residents_map,
            current_year=dt.now().year, current_month=dt.now().month)
    finally:
        db.close()

@bp.route('/billing/<int:billing_id>/mark_paid', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def billing_mark_paid(billing_id):
    db = SessionLocal()
    try:
        billing = db.query(SSBilling).filter(SSBilling.id == billing_id).first()
        if billing:
            billing.status = BillingStatus.paid
            billing.payment_date = date.today()
            db.commit()
            flash('支払済みに更新しました。', 'success')
        return redirect(url_for('shortstay.billing_detail', billing_id=billing_id))
    finally:
        db.close()

@bp.route('/shifts/<int:shift_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def shift_edit(shift_id):
    db = SessionLocal()
    try:
        shift = db.query(SSShift).filter(SSShift.id == shift_id).first()
        if not shift:
            flash('シフトが見つかりません。', 'error')
            return redirect(url_for('shortstay.shifts'))
        if request.method == 'POST':
            shift.staff_name = request.form.get('staff_name')
            shift.shift_date = _parse_date(request.form.get('shift_date'))
            shift.shift_type = request.form.get('shift_type')
            shift.start_time = request.form.get('start_time') or None
            shift.end_time = request.form.get('end_time') or None
            shift.break_minutes = _parse_int(request.form.get('break_minutes'))
            shift.notes = request.form.get('notes')
            db.commit()
            flash('シフトを更新しました。', 'success')
            return redirect(url_for('shortstay.shifts'))
        return render_template('shortstay/shift_form.html', shift=shift, today=date.today().isoformat())
    finally:
        db.close()

@bp.route('/staff_notes/<int:note_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def staff_note_edit(note_id):
    db = SessionLocal()
    try:
        note = db.query(SSStaffNote).filter(SSStaffNote.id == note_id).first()
        if not note:
            flash('申し送りが見つかりません。', 'error')
            return redirect(url_for('shortstay.staff_notes'))
        if request.method == 'POST':
            note.note_date = _parse_date(request.form.get('note_date'))
            note.priority = request.form.get('priority', '通常')
            note.target_shift = request.form.get('target_shift') or None
            note.content = request.form.get('content')
            note.author_name = request.form.get('author_name')
            db.commit()
            flash('申し送りを更新しました。', 'success')
            return redirect(url_for('shortstay.staff_notes'))
        return render_template('shortstay/staff_note_form.html',
            note=note, today=date.today().isoformat(), current_user_name=session.get('user_name', ''))
    finally:
        db.close()

@bp.route('/reports/<int:report_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def report_detail(report_id):
    db = SessionLocal()
    try:
        report = db.query(SSReport).filter(SSReport.id == report_id).first()
        if not report:
            flash('報告書が見つかりません。', 'error')
            return redirect(url_for('shortstay.reports'))
        resident = db.query(SSResident).filter(SSResident.id == report.resident_id).first() if report.resident_id else None
        return render_template('shortstay/report_detail.html', report=report, resident=resident)
    finally:
        db.close()

@bp.route('/reports/<int:report_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def report_edit(report_id):
    db = SessionLocal()
    try:
        report = db.query(SSReport).filter(SSReport.id == report_id).first()
        if not report:
            flash('報告書が見つかりません。', 'error')
            return redirect(url_for('shortstay.reports'))
        if request.method == 'POST':
            report.resident_id = _parse_int(request.form.get('resident_id'))
            report.report_type = request.form.get('report_type')
            report.report_date = _parse_date(request.form.get('report_date'))
            report.title = request.form.get('title')
            report.content = request.form.get('content')
            report.author_name = request.form.get('author_name')
            db.commit()
            flash('報告書を更新しました。', 'success')
            return redirect(url_for('shortstay.report_detail', report_id=report.id))
        residents_list = _get_residents(db, *_get_store_tenant())
        return render_template('shortstay/report_form.html',
            report=report, residents=residents_list,
            today=date.today().isoformat(), current_user_name=session.get('user_name', ''))
    finally:
        db.close()

@bp.route('/incidents/<int:incident_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def incident_edit(incident_id):
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        incident = db.query(SSIncidentReport).filter(SSIncidentReport.id == incident_id).first()
        if not incident:
            flash('報告書が見つかりません。', 'error')
            return redirect(url_for('shortstay.incidents'))
        if request.method == 'POST':
            incident.resident_id = _parse_int(request.form.get('resident_id'))
            incident.incident_type = request.form.get('incident_type')
            incident.incident_date = _parse_date(request.form.get('incident_date'))
            incident.incident_time = request.form.get('incident_time') or None
            incident.location = request.form.get('location')
            incident.description = request.form.get('description')
            incident.response = request.form.get('response')
            incident.prevention = request.form.get('prevention')
            incident.severity = request.form.get('severity') or None
            incident.reporter_name = request.form.get('reporter_name')
            incident.family_notified = bool(request.form.get('family_notified'))
            incident.authority_notified = bool(request.form.get('authority_notified'))
            db.commit()
            flash('報告書を更新しました。', 'success')
            return redirect(url_for('shortstay.incident_detail', incident_id=incident.id))
        residents_list = _get_residents(db, store_id, tenant_id)
        return render_template('shortstay/incident_form.html',
            incident=incident, residents=residents_list, today=date.today().isoformat())
    finally:
        db.close()

@bp.route('/care_plans/<int:plan_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def care_plan_detail(plan_id):
    db = SessionLocal()
    try:
        plan = db.query(SSCarePlan).filter(SSCarePlan.id == plan_id).first()
        if not plan:
            flash('ケアプランが見つかりません。', 'error')
            return redirect(url_for('shortstay.care_plans'))
        resident = db.query(SSResident).filter(SSResident.id == plan.resident_id).first() if plan.resident_id else None
        return render_template('shortstay/care_plan_detail.html', plan=plan, resident=resident)
    finally:
        db.close()



# ─────────────────────────────────────────────
# 送迎管理：車両管理
# ─────────────────────────────────────────────

@bp.route('/vehicles')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def vehicles():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSVehicle)
        if store_id:
            q = q.filter(SSVehicle.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSVehicle.tenant_id == tenant_id)
        vehicle_list = q.order_by(SSVehicle.name).all()
        today = date.today()
        soon = today + timedelta(days=30)
        # 期限アラート（30日以内に期限切れ）
        alerts = []
        for v in vehicle_list:
            if v.vehicle_inspection_expiry and v.vehicle_inspection_expiry <= soon:
                days = (v.vehicle_inspection_expiry - today).days
                alerts.append({'vehicle': v, 'type': '車検', 'days': days, 'expired': days < 0})
            if v.insurance_expiry and v.insurance_expiry <= soon:
                days = (v.insurance_expiry - today).days
                alerts.append({'vehicle': v, 'type': '保険', 'days': days, 'expired': days < 0})
        return render_template('shortstay/vehicles.html',
            vehicles=vehicle_list, alerts=alerts, today=today)
    finally:
        db.close()


@bp.route('/vehicles/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def vehicle_new():
    store_id, tenant_id = _get_store_tenant()
    if request.method == 'POST':
        db = SessionLocal()
        try:
            v = SSVehicle(
                tenant_id=tenant_id, store_id=store_id,
                name=request.form.get('name', ''),
                plate_number=request.form.get('plate_number'),
                vehicle_type=request.form.get('vehicle_type'),
                capacity=int(request.form.get('capacity') or 4),
                wheelchair_accessible=bool(request.form.get('wheelchair_accessible')),
                has_lift=bool(request.form.get('has_lift')),
                is_active=bool(request.form.get('is_active', True)),
                inspection_date=_parse_date(request.form.get('inspection_date')),
                vehicle_inspection_expiry=_parse_date(request.form.get('vehicle_inspection_expiry')),
                insurance_expiry=_parse_date(request.form.get('insurance_expiry')),
                notes=request.form.get('notes'),
            )
            db.add(v)
            db.commit()
            flash('車両を登録しました。', 'success')
            return redirect(url_for('shortstay.vehicles'))
        except Exception as e:
            db.rollback()
            flash(f'登録に失敗しました: {e}', 'error')
        finally:
            db.close()
    return render_template('shortstay/vehicle_form.html', vehicle=None)


@bp.route('/vehicles/<int:vehicle_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def vehicle_edit(vehicle_id):
    db = SessionLocal()
    try:
        v = db.query(SSVehicle).filter(SSVehicle.id == vehicle_id).first()
        if not v:
            flash('車両が見つかりません。', 'error')
            return redirect(url_for('shortstay.vehicles'))
        if request.method == 'POST':
            v.name = request.form.get('name', '')
            v.plate_number = request.form.get('plate_number')
            v.vehicle_type = request.form.get('vehicle_type')
            v.capacity = int(request.form.get('capacity') or 4)
            v.wheelchair_accessible = bool(request.form.get('wheelchair_accessible'))
            v.has_lift = bool(request.form.get('has_lift'))
            v.is_active = bool(request.form.get('is_active'))
            v.inspection_date = _parse_date(request.form.get('inspection_date'))
            v.vehicle_inspection_expiry = _parse_date(request.form.get('vehicle_inspection_expiry'))
            v.insurance_expiry = _parse_date(request.form.get('insurance_expiry'))
            v.notes = request.form.get('notes')
            db.commit()
            flash('車両情報を更新しました。', 'success')
            return redirect(url_for('shortstay.vehicles'))
        return render_template('shortstay/vehicle_form.html', vehicle=v)
    finally:
        db.close()


@bp.route('/vehicles/<int:vehicle_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def vehicle_delete(vehicle_id):
    db = SessionLocal()
    try:
        v = db.query(SSVehicle).filter(SSVehicle.id == vehicle_id).first()
        if v:
            db.delete(v)
            db.commit()
            flash('車両を削除しました。', 'success')
        return redirect(url_for('shortstay.vehicles'))
    finally:
        db.close()


# ─────────────────────────────────────────────
# 送迎管理：ドライバー管理
# ─────────────────────────────────────────────

@bp.route('/drivers')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def drivers():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        q = db.query(SSDriver)
        if store_id:
            q = q.filter(SSDriver.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSDriver.tenant_id == tenant_id)
        driver_list = q.order_by(SSDriver.name).all()
        today = date.today()
        soon = today + timedelta(days=30)
        alerts = []
        for d in driver_list:
            if d.license_expiry and d.license_expiry <= soon:
                days = (d.license_expiry - today).days
                alerts.append({'driver': d, 'type': '免許', 'days': days, 'expired': days < 0})
        # 車両リスト（ドロップダウン用）
        vq = db.query(SSVehicle).filter(SSVehicle.is_active == True)
        if store_id:
            vq = vq.filter(SSVehicle.store_id == store_id)
        elif tenant_id:
            vq = vq.filter(SSVehicle.tenant_id == tenant_id)
        vehicle_list = vq.order_by(SSVehicle.name).all()
        return render_template('shortstay/drivers.html',
            drivers=driver_list, alerts=alerts, vehicles=vehicle_list, today=today)
    finally:
        db.close()


@bp.route('/drivers/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def driver_new():
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            d = SSDriver(
                tenant_id=tenant_id, store_id=store_id,
                name=request.form.get('name', ''),
                phone=request.form.get('phone'),
                license_number=request.form.get('license_number'),
                license_expiry=_parse_date(request.form.get('license_expiry')),
                vehicle_id=_parse_int(request.form.get('vehicle_id')),
                is_active=bool(request.form.get('is_active', True)),
                notes=request.form.get('notes'),
            )
            db.add(d)
            db.commit()
            flash('ドライバーを登録しました。', 'success')
            return redirect(url_for('shortstay.drivers'))
        vq = db.query(SSVehicle).filter(SSVehicle.is_active == True)
        if store_id:
            vq = vq.filter(SSVehicle.store_id == store_id)
        elif tenant_id:
            vq = vq.filter(SSVehicle.tenant_id == tenant_id)
        vehicle_list = vq.order_by(SSVehicle.name).all()
        return render_template('shortstay/driver_form.html', driver=None, vehicles=vehicle_list)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'error')
        return redirect(url_for('shortstay.drivers'))
    finally:
        db.close()


@bp.route('/drivers/<int:driver_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def driver_edit(driver_id):
    db = SessionLocal()
    try:
        d = db.query(SSDriver).filter(SSDriver.id == driver_id).first()
        if not d:
            flash('ドライバーが見つかりません。', 'error')
            return redirect(url_for('shortstay.drivers'))
        if request.method == 'POST':
            d.name = request.form.get('name', '')
            d.phone = request.form.get('phone')
            d.license_number = request.form.get('license_number')
            d.license_expiry = _parse_date(request.form.get('license_expiry'))
            d.vehicle_id = _parse_int(request.form.get('vehicle_id'))
            d.is_active = bool(request.form.get('is_active'))
            d.notes = request.form.get('notes')
            db.commit()
            flash('ドライバー情報を更新しました。', 'success')
            return redirect(url_for('shortstay.drivers'))
        vq = db.query(SSVehicle).filter(SSVehicle.is_active == True)
        store_id, tenant_id = _get_store_tenant()
        if store_id:
            vq = vq.filter(SSVehicle.store_id == store_id)
        elif tenant_id:
            vq = vq.filter(SSVehicle.tenant_id == tenant_id)
        vehicle_list = vq.order_by(SSVehicle.name).all()
        return render_template('shortstay/driver_form.html', driver=d, vehicles=vehicle_list)
    finally:
        db.close()


@bp.route('/drivers/<int:driver_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def driver_delete(driver_id):
    db = SessionLocal()
    try:
        d = db.query(SSDriver).filter(SSDriver.id == driver_id).first()
        if d:
            db.delete(d)
            db.commit()
            flash('ドライバーを削除しました。', 'success')
        return redirect(url_for('shortstay.drivers'))
    finally:
        db.close()


# ─────────────────────────────────────────────
# 送迎管理：送迎先管理・NGドライバー設定
# ─────────────────────────────────────────────

@bp.route('/residents/<int:resident_id>/transport_addresses')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def transport_addresses(resident_id):
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        if not resident:
            flash('利用者が見つかりません。', 'error')
            return redirect(url_for('shortstay.residents'))
        addresses = db.query(SSUserTransportAddress).filter(
            SSUserTransportAddress.resident_id == resident_id,
            SSUserTransportAddress.is_active == True
        ).order_by(SSUserTransportAddress.is_default.desc(), SSUserTransportAddress.id).all()
        # NGドライバー一覧
        ng_list = db.query(SSUserDriverRestriction).filter(
            SSUserDriverRestriction.resident_id == resident_id,
            SSUserDriverRestriction.is_active == True
        ).all()
        # ドライバー一覧（NGドライバー設定用）
        dq = db.query(SSDriver).filter(SSDriver.is_active == True)
        if store_id:
            dq = dq.filter(SSDriver.store_id == store_id)
        elif tenant_id:
            dq = dq.filter(SSDriver.tenant_id == tenant_id)
        driver_list = dq.order_by(SSDriver.name).all()
        ng_driver_ids = {ng.driver_id for ng in ng_list}
        return render_template('shortstay/transport_addresses.html',
            resident=resident, addresses=addresses, ng_list=ng_list,
            drivers=driver_list, ng_driver_ids=ng_driver_ids)
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/transport_addresses/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def transport_address_new(resident_id):
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        if not resident:
            flash('利用者が見つかりません。', 'error')
            return redirect(url_for('shortstay.residents'))
        if request.method == 'POST':
            is_default = bool(request.form.get('is_default'))
            if is_default:
                # 既存のデフォルトを解除
                db.query(SSUserTransportAddress).filter(
                    SSUserTransportAddress.resident_id == resident_id
                ).update({'is_default': False})
            addr = SSUserTransportAddress(
                tenant_id=tenant_id, store_id=store_id,
                resident_id=resident_id,
                name=request.form.get('name', ''),
                address_type=request.form.get('address_type', '自宅'),
                postal_code=request.form.get('postal_code'),
                address=request.form.get('address'),
                building=request.form.get('building'),
                phone=request.form.get('phone'),
                wheelchair_required=bool(request.form.get('wheelchair_required')),
                care_notes=request.form.get('care_notes'),
                is_default=is_default,
            )
            db.add(addr)
            db.commit()
            flash('送迎先を登録しました。', 'success')
            return redirect(url_for('shortstay.transport_addresses', resident_id=resident_id))
        return render_template('shortstay/transport_address_form.html',
            resident=resident, address=None)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'error')
        return redirect(url_for('shortstay.transport_addresses', resident_id=resident_id))
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/transport_addresses/<int:addr_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def transport_address_edit(resident_id, addr_id):
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        addr = db.query(SSUserTransportAddress).filter(SSUserTransportAddress.id == addr_id).first()
        if not addr:
            flash('送迎先が見つかりません。', 'error')
            return redirect(url_for('shortstay.transport_addresses', resident_id=resident_id))
        if request.method == 'POST':
            is_default = bool(request.form.get('is_default'))
            if is_default:
                db.query(SSUserTransportAddress).filter(
                    SSUserTransportAddress.resident_id == resident_id
                ).update({'is_default': False})
            addr.name = request.form.get('name', '')
            addr.address_type = request.form.get('address_type', '自宅')
            addr.postal_code = request.form.get('postal_code')
            addr.address = request.form.get('address')
            addr.building = request.form.get('building')
            addr.phone = request.form.get('phone')
            addr.wheelchair_required = bool(request.form.get('wheelchair_required'))
            addr.care_notes = request.form.get('care_notes')
            addr.is_default = is_default
            db.commit()
            flash('送迎先を更新しました。', 'success')
            return redirect(url_for('shortstay.transport_addresses', resident_id=resident_id))
        return render_template('shortstay/transport_address_form.html',
            resident=resident, address=addr)
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/transport_addresses/<int:addr_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def transport_address_delete(resident_id, addr_id):
    db = SessionLocal()
    try:
        addr = db.query(SSUserTransportAddress).filter(SSUserTransportAddress.id == addr_id).first()
        if addr:
            addr.is_active = False
            db.commit()
            flash('送迎先を削除しました。', 'success')
        return redirect(url_for('shortstay.transport_addresses', resident_id=resident_id))
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/ng_drivers/add', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def ng_driver_add(resident_id):
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        driver_id = _parse_int(request.form.get('driver_id'))
        if driver_id:
            # 既存チェック
            existing = db.query(SSUserDriverRestriction).filter(
                SSUserDriverRestriction.resident_id == resident_id,
                SSUserDriverRestriction.driver_id == driver_id,
                SSUserDriverRestriction.is_active == True
            ).first()
            if not existing:
                ng = SSUserDriverRestriction(
                    tenant_id=tenant_id, store_id=store_id,
                    resident_id=resident_id,
                    driver_id=driver_id,
                    reason=request.form.get('reason'),
                    start_date=_parse_date(request.form.get('start_date')),
                    end_date=_parse_date(request.form.get('end_date')),
                )
                db.add(ng)
                db.commit()
                flash('NGドライバーを設定しました。', 'success')
            else:
                flash('既に設定済みです。', 'warning')
        return redirect(url_for('shortstay.transport_addresses', resident_id=resident_id))
    except Exception as e:
        db.rollback()
        flash(f'設定に失敗しました: {e}', 'error')
        return redirect(url_for('shortstay.transport_addresses', resident_id=resident_id))
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/ng_drivers/<int:ng_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def ng_driver_delete(resident_id, ng_id):
    db = SessionLocal()
    try:
        ng = db.query(SSUserDriverRestriction).filter(SSUserDriverRestriction.id == ng_id).first()
        if ng:
            ng.is_active = False
            db.commit()
            flash('NGドライバー設定を解除しました。', 'success')
        return redirect(url_for('shortstay.transport_addresses', resident_id=resident_id))
    finally:
        db.close()


# ─────────────────────────────────────────────
# 送迎管理：ルート管理（一覧・自動生成・編集・印刷）
# ─────────────────────────────────────────────

def _get_transport_base_query(db, store_id, tenant_id, model):
    q = db.query(model)
    if store_id:
        q = q.filter(model.store_id == store_id)
    elif tenant_id:
        q = q.filter(model.tenant_id == tenant_id)
    return q


@bp.route('/transport')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def transport_index():
    """送迎管理トップ：日付選択 → 送迎対象者一覧"""
    store_id, tenant_id = _get_store_tenant()
    target_date_str = request.args.get('date', date.today().isoformat())
    try:
        target_date = date.fromisoformat(target_date_str)
    except ValueError:
        target_date = date.today()

    db = SessionLocal()
    try:
        # 当日の予約から送迎対象者を抽出
        q = db.query(SSReservation).filter(
            SSReservation.check_in_date == target_date,
            SSReservation.status.in_([ReservationStatus.confirmed, ReservationStatus.tentative])
        )
        if store_id:
            q = q.filter(SSReservation.store_id == store_id)
        elif tenant_id:
            q = q.filter(SSReservation.tenant_id == tenant_id)
        reservations = q.all()

        pickup_targets = [r for r in reservations if r.pickup_required]
        dropoff_targets = [r for r in reservations if r.dropoff_required]

        # 既存ルート
        rq = db.query(SSTransportRoute).filter(SSTransportRoute.route_date == target_date)
        if store_id:
            rq = rq.filter(SSTransportRoute.store_id == store_id)
        elif tenant_id:
            rq = rq.filter(SSTransportRoute.tenant_id == tenant_id)
        existing_routes = rq.order_by(SSTransportRoute.transport_type, SSTransportRoute.route_name).all()

        # 車両・ドライバー一覧
        vq = _get_transport_base_query(db, store_id, tenant_id, SSVehicle).filter(SSVehicle.is_active == True)
        vehicle_list = vq.order_by(SSVehicle.name).all()
        dq = _get_transport_base_query(db, store_id, tenant_id, SSDriver).filter(SSDriver.is_active == True)
        driver_list = dq.order_by(SSDriver.name).all()

        return render_template('shortstay/transport_index.html',
            target_date=target_date,
            today=date.today(),
            pickup_count=len(pickup_targets),
            dropoff_count=len(dropoff_targets),
            existing_routes=existing_routes,
            vehicles=vehicle_list,
            drivers=driver_list,
        )
    finally:
        db.close()


# ─────────────────────────────────────────────
# 混在ルート自動生成ユーティリティ
# ─────────────────────────────────────────────

def _time_str_to_minutes(t: str | None) -> int | None:
    """時刻文字列（HH:MM）を分単位整数に変換する。失敗時はNoneを返す。"""
    if not t:
        return None
    try:
        h, m = map(int, t.strip().split(':'))
        return h * 60 + m
    except Exception:
        return None


def _minutes_to_time_str(minutes: int) -> str:
    """分単位整数をHH:MM文字列に変換する。"""
    minutes = max(0, minutes)
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def _build_mixed_route_events(db, reservations, target_date, transport_type, constraints_map):
    """
    予約リストから送迎イベントリストを生成する。

    各予約に対して以下のイベントを生成する:
      - pickup: 自宅等での乗車イベント
      - dropoff: 目的地（施設または別送迎先）での降車イベント

    返り値: list of dict {
        'event_type': 'pickup' | 'dropoff',
        'resident_id': int,
        'reservation_id': int,
        'address': str,
        'phone': str | None,
        'care_notes': str | None,
        'resident_name': str,
        'requires_wheelchair': bool,
        'boarding_time': int,  # 分
        'constraint': SSTransportTimeConstraint | None,
        'deadline_minutes': int | None,  # 期限時刻（分）ソート用
        'priority': int,  # 0=必須 1=希望 2=参考 3=なし
    }
    """
    events = []
    for res in reservations:
        resident = res.resident
        resident_name = f'{resident.last_name}{resident.first_name}'
        tc = constraints_map.get(res.resident_id)

        # 送迎先アドレスを取得
        default_addr = db.query(SSUserTransportAddress).filter(
            SSUserTransportAddress.resident_id == res.resident_id,
            SSUserTransportAddress.is_default == True,
            SSUserTransportAddress.is_active == True
        ).first()
        if not default_addr:
            default_addr = db.query(SSUserTransportAddress).filter(
                SSUserTransportAddress.resident_id == res.resident_id,
                SSUserTransportAddress.is_active == True
            ).first()

        addr_text = default_addr.address if default_addr else (res.pickup_address or '住所未登録')
        phone_text = default_addr.phone if default_addr else None
        care_notes = default_addr.care_notes if default_addr else None
        boarding_time = (tc.boarding_time_minutes or 5) if tc else 5
        requires_wc = res.resident.wheelchair_required if hasattr(res.resident, 'wheelchair_required') else False

        # 制約優先度と期限時刻
        if tc:
            priority = 0 if tc.constraint_type == '必須' else (1 if tc.constraint_type == '希望' else 2)
        else:
            priority = 3

        # 迈えイベント（pickup: 自宅で乗車、dropoff: 施設で降車）
        if transport_type in ('迈え', '混在') and res.pickup_required:
            # pickupの期限：施設到着期限または到着必須時刻
            deadlines = [_time_str_to_minutes(t) for t in [
                tc.facility_arrival_deadline if tc else None,
                tc.required_arrival_time if tc else None,
                res.pickup_time,
            ] if t]
            deadline_m = min(deadlines) if deadlines else None
            events.append({
                'event_type': 'pickup',
                'resident_id': res.resident_id,
                'reservation_id': res.id,
                'address': addr_text,
                'phone': phone_text,
                'care_notes': care_notes,
                'resident_name': resident_name,
                'requires_wheelchair': requires_wc,
                'boarding_time': boarding_time,
                'constraint': tc,
                'deadline_minutes': deadline_m,
                'priority': priority,
                'scheduled_time': res.pickup_time,
            })

        # 送りイベント（pickup: 施設で乗車、dropoff: 送迎先で降車）
        if transport_type in ('送り', '混在') and res.dropoff_required:
            # dropoffの期限：送迎先到着期限または到着必須時刻
            deadlines = [_time_str_to_minutes(t) for t in [
                tc.destination_arrival_deadline if tc else None,
                tc.required_arrival_time if tc else None,
                res.dropoff_time,
            ] if t]
            deadline_m = min(deadlines) if deadlines else None
            events.append({
                'event_type': 'dropoff',
                'resident_id': res.resident_id,
                'reservation_id': res.id,
                'address': addr_text,
                'phone': phone_text,
                'care_notes': care_notes,
                'resident_name': resident_name,
                'requires_wheelchair': requires_wc,
                'boarding_time': boarding_time,
                'constraint': tc,
                'deadline_minutes': deadline_m,
                'priority': priority,
                'scheduled_time': res.dropoff_time,
            })
    return events


def _sort_events_mixed(events: list[dict]) -> list[dict]:
    """
    混在ルートのイベントを最適順にソートする。

    ルール:
    1. pickup -> dropoff の順序は必ず守る（同一利用者）
    2. 必須制約ありを優先
    3. 期限が早い順（EDF: Earliest Deadline First）
    4. pickupは同一利用者のdropoffより必ず前
    """
    # 同一利用者のpickupとdropoffをペア化
    pickup_map = {e['resident_id']: e for e in events if e['event_type'] == 'pickup'}
    dropoff_map = {e['resident_id']: e for e in events if e['event_type'] == 'dropoff'}

    # ソートキー: (優先度, 期限分, イベント種別オーダー)
    def sort_key(ev):
        priority = ev['priority']
        deadline = ev['deadline_minutes'] if ev['deadline_minutes'] is not None else 9999
        # pickupは同一利用者のdropoffより必ず前
        event_order = 0 if ev['event_type'] == 'pickup' else 1
        return (priority, deadline, event_order)

    sorted_events = sorted(events, key=sort_key)

    # pickup -> dropoff 順序を強制（同一利用者のpickupがdropoffより必ず前）
    result = []
    processed_residents = set()
    for ev in sorted_events:
        rid = ev['resident_id']
        if ev['event_type'] == 'pickup':
            if rid not in processed_residents:
                result.append(ev)
                # 対応するdropoffが存在する場合、後で追加するためマーク
                processed_residents.add(rid)
        elif ev['event_type'] == 'dropoff':
            # pickupが存在する場合、pickupが先に処理済みか確認
            if rid in pickup_map:
                # pickupがまだresultにない場合は先にpickupを挿入
                if not any(r['resident_id'] == rid and r['event_type'] == 'pickup' for r in result):
                    result.append(pickup_map[rid])
            result.append(ev)

    return result


def _check_event_constraints(ev: dict, estimated_arrival_str: str) -> tuple[str, str | None]:
    """
    イベントの時刻制約をチェックする。
    返り値: (constraint_status, constraint_message)
    """
    tc = ev['constraint']
    if not tc or not estimated_arrival_str:
        return 'ok', None

    resident_name = ev['resident_name']
    status = 'ok'
    message = None

    # 到着必須時刻チェック
    if tc.required_arrival_time and estimated_arrival_str > tc.required_arrival_time:
        tolerance = tc.delay_tolerance_minutes or 0
        if tolerance > 0:
            deadline_m = _time_str_to_minutes(tc.required_arrival_time) + tolerance
            deadline_str = _minutes_to_time_str(deadline_m)
            if estimated_arrival_str > deadline_str:
                status = 'violation'
                message = (f'{resident_name}さんは{tc.required_arrival_time}到着必須ですが、'
                           f'現在のルートでは{estimated_arrival_str}到着見込みです（許容遅延{tolerance}分超過）。')
            else:
                status = 'warning'
                message = (f'{resident_name}さんは{tc.required_arrival_time}到着必須ですが、'
                           f'現在のルートでは{estimated_arrival_str}到着見込みです（許容遅延内）。')
        else:
            status = 'violation'
            message = (f'{resident_name}さんは{tc.required_arrival_time}到着必須ですが、'
                       f'現在のルートでは{estimated_arrival_str}到着見込みです。')
    # 到着希望時刻チェック
    elif tc.desired_arrival_time and estimated_arrival_str > tc.desired_arrival_time and status == 'ok':
        status = 'warning'
        message = (f'{resident_name}さんの到着希望時刻は{tc.desired_arrival_time}ですが、'
                   f'現在のルートでは{estimated_arrival_str}到着見込みです。')

    # 乗車可能時間チェック（pickupイベントのみ）
    if ev['event_type'] == 'pickup':
        if tc.earliest_boarding_time and estimated_arrival_str < tc.earliest_boarding_time:
            msg = (f'{resident_name}さんの乗車可能開始時刻は{tc.earliest_boarding_time}ですが、'
                   f'{estimated_arrival_str}に到着見込みです。')
            if status == 'ok':
                status = 'warning'
                message = msg
        if tc.latest_boarding_time and estimated_arrival_str > tc.latest_boarding_time:
            msg = (f'{resident_name}さんの乗車可能終了時刻は{tc.latest_boarding_time}ですが、'
                   f'{estimated_arrival_str}に到着見込みです。')
            if tc.constraint_type == '必須':
                status = 'violation'
                message = (message or '') + ' ' + msg
            elif status == 'ok':
                status = 'warning'
                message = msg

    return status, message


@bp.route('/transport/generate', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def transport_generate():
    """送迎ルート自動生成（混在ルート対応・時刻制約対応版）"""
    store_id, tenant_id = _get_store_tenant()
    target_date_str = request.form.get('date', date.today().isoformat())
    transport_type = request.form.get('transport_type', '迎え')
    vehicle_id = _parse_int(request.form.get('vehicle_id'))
    driver_id = _parse_int(request.form.get('driver_id'))
    departure_time_str = request.form.get('departure_time', '')  # 施設出発時刻
    avg_travel_minutes = _parse_int(request.form.get('avg_travel_minutes')) or 10  # 停車間平均移動時間（分）

    try:
        target_date = date.fromisoformat(target_date_str)
    except ValueError:
        target_date = date.today()

    db = SessionLocal()
    try:
        # 混在ルートの場合、迈え・送り両方の予約を取得
        if transport_type == '迈え':
            q = db.query(SSReservation).filter(
                SSReservation.check_in_date == target_date,
                SSReservation.pickup_required == True,
                SSReservation.status.in_([ReservationStatus.confirmed, ReservationStatus.tentative])
            )
        elif transport_type == '送り':
            q = db.query(SSReservation).filter(
                SSReservation.check_out_date == target_date,
                SSReservation.dropoff_required == True,
                SSReservation.status.in_([ReservationStatus.confirmed, ReservationStatus.tentative])
            )
        else:  # 混在
            # 迈え対象（入所日）と送り対象（退所日）の両方を取得
            q_pickup = db.query(SSReservation).filter(
                SSReservation.check_in_date == target_date,
                SSReservation.pickup_required == True,
                SSReservation.status.in_([ReservationStatus.confirmed, ReservationStatus.tentative])
            )
            q_dropoff = db.query(SSReservation).filter(
                SSReservation.check_out_date == target_date,
                SSReservation.dropoff_required == True,
                SSReservation.status.in_([ReservationStatus.confirmed, ReservationStatus.tentative])
            )
            if store_id:
                q_pickup = q_pickup.filter(SSReservation.store_id == store_id)
                q_dropoff = q_dropoff.filter(SSReservation.store_id == store_id)
            elif tenant_id:
                q_pickup = q_pickup.filter(SSReservation.tenant_id == tenant_id)
                q_dropoff = q_dropoff.filter(SSReservation.tenant_id == tenant_id)
            # 重複を除いてマージ
            pickup_ids = {r.id for r in q_pickup.all()}
            all_res = {r.id: r for r in q_pickup.all()}
            for r in q_dropoff.all():
                all_res[r.id] = r
            reservations = list(all_res.values())

        if transport_type != '混在':
            if store_id:
                q = q.filter(SSReservation.store_id == store_id)
            elif tenant_id:
                q = q.filter(SSReservation.tenant_id == tenant_id)
            reservations = q.all()

        if not reservations:
            flash('送迎対象者がいません。', 'warning')
            return redirect(url_for('shortstay.transport_index', date=target_date_str))

        # 車両定員・車椅子対応台数を取得
        vehicle = db.query(SSVehicle).filter(SSVehicle.id == vehicle_id).first() if vehicle_id else None
        capacity = vehicle.capacity if vehicle else 99
        wc_capacity = vehicle.wheelchair_capacity if vehicle and hasattr(vehicle, 'wheelchair_capacity') else capacity

        # NGドライバーを考慮して対象者を絞り込み
        valid_reservations = []
        for res in reservations:
            if driver_id:
                ng = db.query(SSUserDriverRestriction).filter(
                    SSUserDriverRestriction.resident_id == res.resident_id,
                    SSUserDriverRestriction.driver_id == driver_id,
                    SSUserDriverRestriction.is_active == True
                ).first()
                if ng:
                    flash(f'利用者「{res.resident.last_name}{res.resident.first_name}」はこのドライバーのNGです。スキップしました。', 'warning')
                    continue
            valid_reservations.append(res)

        # 定員超過チェック（混在ルートは「同時乗車最大人数」で判定）
        if len(valid_reservations) > capacity:
            flash(f'対象者数（{len(valid_reservations)}名）が車両定員（{capacity}名）を超えています。複数ルートに分割してください。', 'warning')
            valid_reservations = valid_reservations[:capacity]

        # 利用者ごとの時刻制約を取得（対象日に有効なもの）
        constraints_map = {}  # resident_id -> SSTransportTimeConstraint
        for res in valid_reservations:
            # 混在の場合は迈え・送り両方の制約を取得し、必須制約を優先
            tc_query = db.query(SSTransportTimeConstraint).filter(
                SSTransportTimeConstraint.resident_id == res.resident_id,
                SSTransportTimeConstraint.is_active == True,
                or_(
                    SSTransportTimeConstraint.valid_from == None,
                    SSTransportTimeConstraint.valid_from <= target_date
                ),
                or_(
                    SSTransportTimeConstraint.valid_to == None,
                    SSTransportTimeConstraint.valid_to >= target_date
                )
            )
            if transport_type != '混在':
                tc_query = tc_query.filter(SSTransportTimeConstraint.transport_type == transport_type)
            tc = tc_query.order_by(SSTransportTimeConstraint.constraint_type).first()
            if tc:
                constraints_map[res.resident_id] = tc

        # 施設出発時刻のパース
        departure_minutes = _time_str_to_minutes(departure_time_str)

        # ルート名を自動生成
        existing_count = db.query(SSTransportRoute).filter(
            SSTransportRoute.route_date == target_date,
            SSTransportRoute.tenant_id == tenant_id
        ).count()
        route_name = f'送迎ルート {existing_count + 1}号車'

        # ルート作成
        route = SSTransportRoute(
            tenant_id=tenant_id, store_id=store_id,
            route_date=target_date,
            transport_type=transport_type,
            vehicle_id=vehicle_id,
            driver_id=driver_id,
            route_name=route_name,
            status='draft',
        )
        db.add(route)
        db.flush()

        # ─────────────────────────────────────────────
        # 混在ルートイベント化・ソート・停車地生成
        # ─────────────────────────────────────────────
        # 各予約をイベント（pickup/dropoff）に分解する
        events = _build_mixed_route_events(db, valid_reservations, target_date, transport_type, constraints_map)
        # EDF方式でソート（pickup->dropoff順序を必ず守る）
        sorted_events = _sort_events_mixed(events)

        stops = []
        route_has_violation = False
        route_warnings = []

        # 施設出発イベント（常に先頭）
        stops.append(SSTransportRouteStop(
            route_id=route.id, stop_order=1,
            is_facility=True, event_type='facility',
            address_snapshot='施設（出発）',
            scheduled_time=departure_time_str or None,
            estimated_arrival=departure_time_str or None,
            current_passengers=0,
        ))

        # 車内乗車人数を追跡（定員監視）
        current_minutes = departure_minutes
        current_passengers = 0  # 施設出発時は0名
        passenger_set = set()  # 現在車内の利用者IDセット

        for seq_idx, ev in enumerate(sorted_events):
            # 到着予定時刻を計算
            estimated_arrival_str = None
            if current_minutes is not None:
                current_minutes += avg_travel_minutes
                estimated_arrival_str = _minutes_to_time_str(current_minutes)
                current_minutes += ev['boarding_time']  # 乗降時間を加算

            # 乗車人数を更新
            if ev['event_type'] == 'pickup':
                passenger_set.add(ev['resident_id'])
                current_passengers = len(passenger_set)
            elif ev['event_type'] == 'dropoff':
                passenger_set.discard(ev['resident_id'])
                current_passengers = len(passenger_set)

            # 定員超過チェック（pickup時）
            constraint_status = 'ok'
            constraint_message = None

            if ev['event_type'] == 'pickup' and current_passengers > capacity:
                constraint_status = 'violation'
                constraint_message = (
                    f'定員超過：{ev["resident_name"]}さんを乗車させると{current_passengers}名になり、'
                    f'車両定員（{capacity}名）を超えます。'
                )
                route_has_violation = True

            # 時刻制約チェック
            if constraint_status == 'ok':
                constraint_status, constraint_message = _check_event_constraints(ev, estimated_arrival_str)
                if constraint_status == 'violation':
                    route_has_violation = True

            if constraint_message:
                route_warnings.append({
                    'name': ev['resident_name'],
                    'status': constraint_status,
                    'message': constraint_message
                })

            # 停車地イベントのラベル
            event_label = '【乗車】' if ev['event_type'] == 'pickup' else '【降車】'

            stops.append(SSTransportRouteStop(
                route_id=route.id,
                stop_order=seq_idx + 2,  # 1は施設出発
                resident_id=ev['resident_id'],
                reservation_id=ev['reservation_id'],
                event_type=ev['event_type'],
                scheduled_time=ev.get('scheduled_time'),
                estimated_arrival=estimated_arrival_str,
                address_snapshot=ev['address'],
                phone_snapshot=ev['phone'],
                care_notes_snapshot=ev['care_notes'],
                is_facility=False,
                constraint_status=constraint_status,
                constraint_message=constraint_message,
                current_passengers=current_passengers,
            ))

        # 混在・迈えの場合、最後に施設到着イベントを追加
        if transport_type in ('迈え', '混在'):
            facility_arrival_str = None
            if current_minutes is not None:
                current_minutes += avg_travel_minutes
                facility_arrival_str = _minutes_to_time_str(current_minutes)
            stops.append(SSTransportRouteStop(
                route_id=route.id,
                stop_order=len(sorted_events) + 2,
                is_facility=True, event_type='facility',
                address_snapshot='施設（到着）',
                estimated_arrival=facility_arrival_str,
                current_passengers=0,
            ))

        for stop in stops:
            db.add(stop)

        # 必須制約違反がある場合は自動確定しない（draftのまま）
        if route_has_violation:
            route.status = 'draft'
            db.commit()
            flash(
                f'送迎ルート「{route_name}」を作成しましたが、'
                f'必須制約違反または定員超過があるため自動確定されませんでした。'
                f'内容を確認してください。',
                'error'
            )
        else:
            db.commit()
            if route_warnings:
                flash(
                    f'送迎ルート「{route_name}」を作成しました（{len(valid_reservations)}名・{len(sorted_events)}イベント）。'
                    f'時刻希望に関する警告があります。',
                    'warning'
                )
            else:
                flash(
                    f'送迎ルート「{route_name}」を作成しました（{len(valid_reservations)}名・{len(sorted_events)}イベント）。',
                    'success'
                )

        return redirect(url_for('shortstay.transport_route_detail', route_id=route.id))
    except Exception as e:
        db.rollback()
        flash(f'ルート生成に失敗しました: {e}', 'error')
        return redirect(url_for('shortstay.transport_index', date=target_date_str))
    finally:
        db.close()


@bp.route('/transport/routes/<int:route_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def transport_route_detail(route_id):
    db = SessionLocal()
    try:
        route = db.query(SSTransportRoute).filter(SSTransportRoute.id == route_id).first()
        if not route:
            flash('ルートが見つかりません。', 'error')
            return redirect(url_for('shortstay.transport_index'))
        stops = db.query(SSTransportRouteStop).filter(
            SSTransportRouteStop.route_id == route_id
        ).order_by(SSTransportRouteStop.stop_order).all()
        # 利用者情報を付加
        stop_data = []
        for stop in stops:
            resident = db.query(SSResident).filter(SSResident.id == stop.resident_id).first() if stop.resident_id else None
            stop_data.append({'stop': stop, 'resident': resident})
        vehicle = db.query(SSVehicle).filter(SSVehicle.id == route.vehicle_id).first() if route.vehicle_id else None
        driver = db.query(SSDriver).filter(SSDriver.id == route.driver_id).first() if route.driver_id else None
        return render_template('shortstay/transport_route_detail.html',
            route=route, stop_data=stop_data, vehicle=vehicle, driver=driver)
    finally:
        db.close()


@bp.route('/transport/routes/<int:route_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def transport_route_edit(route_id):
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        route = db.query(SSTransportRoute).filter(SSTransportRoute.id == route_id).first()
        if not route:
            flash('ルートが見つかりません。', 'error')
            return redirect(url_for('shortstay.transport_index'))
        if request.method == 'POST':
            route.route_name = request.form.get('route_name', route.route_name)
            route.vehicle_id = _parse_int(request.form.get('vehicle_id'))
            route.driver_id = _parse_int(request.form.get('driver_id'))
            route.notes = request.form.get('notes')
            # 停車地の時刻更新
            stop_ids = request.form.getlist('stop_id[]')
            stop_times = request.form.getlist('scheduled_time[]')
            stop_notes = request.form.getlist('care_notes[]')
            for i, sid in enumerate(stop_ids):
                stop = db.query(SSTransportRouteStop).filter(SSTransportRouteStop.id == int(sid)).first()
                if stop:
                    stop.scheduled_time = stop_times[i] if i < len(stop_times) else None
                    stop.care_notes_snapshot = stop_notes[i] if i < len(stop_notes) else stop.care_notes_snapshot
            db.commit()
            flash('ルートを更新しました。', 'success')
            return redirect(url_for('shortstay.transport_route_detail', route_id=route_id))
        stops = db.query(SSTransportRouteStop).filter(
            SSTransportRouteStop.route_id == route_id
        ).order_by(SSTransportRouteStop.stop_order).all()
        stop_data = []
        for stop in stops:
            resident = db.query(SSResident).filter(SSResident.id == stop.resident_id).first() if stop.resident_id else None
            stop_data.append({'stop': stop, 'resident': resident})
        vq = _get_transport_base_query(db, store_id, tenant_id, SSVehicle).filter(SSVehicle.is_active == True)
        vehicle_list = vq.order_by(SSVehicle.name).all()
        dq = _get_transport_base_query(db, store_id, tenant_id, SSDriver).filter(SSDriver.is_active == True)
        driver_list = dq.order_by(SSDriver.name).all()
        return render_template('shortstay/transport_route_edit.html',
            route=route, stop_data=stop_data, vehicles=vehicle_list, drivers=driver_list)
    finally:
        db.close()


@bp.route('/transport/routes/<int:route_id>/confirm', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def transport_route_confirm(route_id):
    db = SessionLocal()
    try:
        route = db.query(SSTransportRoute).filter(SSTransportRoute.id == route_id).first()
        if route:
            route.status = 'confirmed'
            route.confirmed_at = datetime.utcnow()
            db.commit()
            flash('ルートを確定しました。', 'success')
        return redirect(url_for('shortstay.transport_route_detail', route_id=route_id))
    finally:
        db.close()


@bp.route('/transport/routes/<int:route_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def transport_route_delete(route_id):
    db = SessionLocal()
    try:
        route = db.query(SSTransportRoute).filter(SSTransportRoute.id == route_id).first()
        if route:
            target_date = route.route_date.isoformat()
            db.delete(route)
            db.commit()
            flash('ルートを削除しました。', 'success')
            return redirect(url_for('shortstay.transport_index', date=target_date))
        return redirect(url_for('shortstay.transport_index'))
    finally:
        db.close()


@bp.route('/transport/routes/<int:route_id>/print')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["EMPLOYEE"])
def transport_route_print(route_id):
    """印刷用ルートシート"""
    db = SessionLocal()
    try:
        route = db.query(SSTransportRoute).filter(SSTransportRoute.id == route_id).first()
        if not route:
            flash('ルートが見つかりません。', 'error')
            return redirect(url_for('shortstay.transport_index'))
        stops = db.query(SSTransportRouteStop).filter(
            SSTransportRouteStop.route_id == route_id
        ).order_by(SSTransportRouteStop.stop_order).all()
        stop_data = []
        for stop in stops:
            resident = db.query(SSResident).filter(SSResident.id == stop.resident_id).first() if stop.resident_id else None
            stop_data.append({'stop': stop, 'resident': resident})
        vehicle = db.query(SSVehicle).filter(SSVehicle.id == route.vehicle_id).first() if route.vehicle_id else None
        driver = db.query(SSDriver).filter(SSDriver.id == route.driver_id).first() if route.driver_id else None
        return render_template('shortstay/transport_route_print.html',
            route=route, stop_data=stop_data, vehicle=vehicle, driver=driver)
    finally:
        db.close()


# ─────────────────────────────────────────────
# 送迎管理：時刻制約管理（CRUD）
# ─────────────────────────────────────────────

@bp.route('/residents/<int:resident_id>/time_constraints')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def time_constraints(resident_id):
    """利用者の時刻制約一覧"""
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        if not resident:
            flash('利用者が見つかりません。', 'error')
            return redirect(url_for('shortstay.residents'))
        constraints = db.query(SSTransportTimeConstraint).filter(
            SSTransportTimeConstraint.resident_id == resident_id,
            SSTransportTimeConstraint.is_active == True
        ).order_by(
            SSTransportTimeConstraint.transport_type,
            SSTransportTimeConstraint.constraint_type
        ).all()
        # 送迎先一覧（制約と紐付けるため）
        addresses = db.query(SSUserTransportAddress).filter(
            SSUserTransportAddress.resident_id == resident_id,
            SSUserTransportAddress.is_active == True
        ).all()
        return render_template('shortstay/time_constraints.html',
            resident=resident, constraints=constraints, addresses=addresses)
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/time_constraints/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def time_constraint_new(resident_id):
    """時刻制約の新規登録"""
    store_id, tenant_id = _get_store_tenant()
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        if not resident:
            flash('利用者が見つかりません。', 'error')
            return redirect(url_for('shortstay.residents'))
        addresses = db.query(SSUserTransportAddress).filter(
            SSUserTransportAddress.resident_id == resident_id,
            SSUserTransportAddress.is_active == True
        ).all()
        if request.method == 'POST':
            tc = SSTransportTimeConstraint(
                tenant_id=tenant_id, store_id=store_id,
                resident_id=resident_id,
                reservation_id=_parse_int(request.form.get('reservation_id')),
                transport_address_id=_parse_int(request.form.get('transport_address_id')),
                transport_type=request.form.get('transport_type', '迎え'),
                constraint_type=request.form.get('constraint_type', '希望'),
                earliest_departure_time=request.form.get('earliest_departure_time') or None,
                desired_arrival_time=request.form.get('desired_arrival_time') or None,
                required_arrival_time=request.form.get('required_arrival_time') or None,
                facility_arrival_deadline=request.form.get('facility_arrival_deadline') or None,
                destination_arrival_deadline=request.form.get('destination_arrival_deadline') or None,
                earliest_boarding_time=request.form.get('earliest_boarding_time') or None,
                latest_boarding_time=request.form.get('latest_boarding_time') or None,
                required_destination_arrival_time=request.form.get('required_destination_arrival_time') or None,
                boarding_time_minutes=_parse_int(request.form.get('boarding_time_minutes')) or 5,
                buffer_minutes=_parse_int(request.form.get('buffer_minutes')) or 5,
                delay_tolerance_minutes=_parse_int(request.form.get('delay_tolerance_minutes')) or 0,
                constraint_reason=request.form.get('constraint_reason') or None,
                valid_from=_parse_date(request.form.get('valid_from')),
                valid_to=_parse_date(request.form.get('valid_to')),
            )
            db.add(tc)
            db.commit()
            flash('時刻制約を登録しました。', 'success')
            return redirect(url_for('shortstay.time_constraints', resident_id=resident_id))
        return render_template('shortstay/time_constraint_form.html',
            resident=resident, constraint=None, addresses=addresses)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'error')
        return redirect(url_for('shortstay.time_constraints', resident_id=resident_id))
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/time_constraints/<int:tc_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def time_constraint_edit(resident_id, tc_id):
    """時刻制約の編集"""
    db = SessionLocal()
    try:
        resident = db.query(SSResident).filter(SSResident.id == resident_id).first()
        tc = db.query(SSTransportTimeConstraint).filter(SSTransportTimeConstraint.id == tc_id).first()
        if not tc:
            flash('時刻制約が見つかりません。', 'error')
            return redirect(url_for('shortstay.time_constraints', resident_id=resident_id))
        addresses = db.query(SSUserTransportAddress).filter(
            SSUserTransportAddress.resident_id == resident_id,
            SSUserTransportAddress.is_active == True
        ).all()
        if request.method == 'POST':
            tc.transport_address_id = _parse_int(request.form.get('transport_address_id'))
            tc.transport_type = request.form.get('transport_type', '迎え')
            tc.constraint_type = request.form.get('constraint_type', '希望')
            tc.earliest_departure_time = request.form.get('earliest_departure_time') or None
            tc.desired_arrival_time = request.form.get('desired_arrival_time') or None
            tc.required_arrival_time = request.form.get('required_arrival_time') or None
            tc.facility_arrival_deadline = request.form.get('facility_arrival_deadline') or None
            tc.destination_arrival_deadline = request.form.get('destination_arrival_deadline') or None
            tc.earliest_boarding_time = request.form.get('earliest_boarding_time') or None
            tc.latest_boarding_time = request.form.get('latest_boarding_time') or None
            tc.required_destination_arrival_time = request.form.get('required_destination_arrival_time') or None
            tc.boarding_time_minutes = _parse_int(request.form.get('boarding_time_minutes')) or 5
            tc.buffer_minutes = _parse_int(request.form.get('buffer_minutes')) or 5
            tc.delay_tolerance_minutes = _parse_int(request.form.get('delay_tolerance_minutes')) or 0
            tc.constraint_reason = request.form.get('constraint_reason') or None
            tc.valid_from = _parse_date(request.form.get('valid_from'))
            tc.valid_to = _parse_date(request.form.get('valid_to'))
            db.commit()
            flash('時刻制約を更新しました。', 'success')
            return redirect(url_for('shortstay.time_constraints', resident_id=resident_id))
        return render_template('shortstay/time_constraint_form.html',
            resident=resident, constraint=tc, addresses=addresses)
    finally:
        db.close()


@bp.route('/residents/<int:resident_id>/time_constraints/<int:tc_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def time_constraint_delete(resident_id, tc_id):
    """時刻制約の削除（論理削除）"""
    db = SessionLocal()
    try:
        tc = db.query(SSTransportTimeConstraint).filter(SSTransportTimeConstraint.id == tc_id).first()
        if tc:
            tc.is_active = False
            db.commit()
            flash('時刻制約を削除しました。', 'success')
        return redirect(url_for('shortstay.time_constraints', resident_id=resident_id))
    finally:
        db.close()
