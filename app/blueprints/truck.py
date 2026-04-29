# -*- coding: utf-8 -*-
"""
トラック運行管理システム blueprint
/truck/ 配下のすべてのルートを管理します。
"""
import hmac
import hashlib
import json
import os
import uuid
import requests as http_requests
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify, Response, stream_with_context
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

from app.db import SessionLocal
from app.models_truck import Truck, TruckRoute, TruckDriver, TruckOperation, TruckAppSettings, TruckClient, TruckContract, TruckInsurance, TruckAccidentRecord, TruckInspectionRecord, TruckInvoice, TruckInvoiceItem, TruckSchedule
from app.models_login import TTenpo, TTenant, TKanrisha, TAppManagerGroup, TJugyoin, TJugyoinTenpo
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('truck', __name__, url_prefix='/truck')

MOBILE_API_KEY = os.environ.get("TRUCK_MOBILE_API_KEY", "truck-app-key")


# ─── ヘルパー ────────────────────────────────────────────

def format_status(status):
    mapping = {
        "driving": "運行中",
        "break": "休憩中",
        "loading": "荷積み中",
        "unloading": "荷下ろし中",
        "finished": "運行終了",
        "off": "未出発",
    }
    return mapping.get(status, status)


def status_color(status):
    mapping = {
        "driving": "#16a34a",
        "break": "#d97706",
        "loading": "#2563eb",
        "unloading": "#7c3aed",
        "finished": "#dc2626",
        "off": "#6b7280",
    }
    return mapping.get(status, "#6b7280")


def calc_duration(start_val, end_val=None):
    if not start_val:
        return "-"
    try:
        if isinstance(start_val, str):
            start = datetime.fromisoformat(start_val)
        else:
            start = start_val
        if end_val:
            if isinstance(end_val, str):
                end = datetime.fromisoformat(end_val)
            else:
                end = end_val
        else:
            end = datetime.now()
        delta = end - start
        total_minutes = int(delta.total_seconds() // 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}時間{minutes}分"
    except Exception:
        return "-"


def format_time(dt_val):
    if not dt_val:
        return "-"
    try:
        if isinstance(dt_val, str):
            dt_val = datetime.fromisoformat(dt_val)
        return dt_val.strftime("%H:%M")
    except Exception:
        return "-"


def login_required_truck(f):
    """トラック管理者ログイン確認デコレーター"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # client-management-appのセッションでログイン済みかチェック
        if not session.get('user_id'):
            return redirect(url_for('auth.select_login'))
        return f(*args, **kwargs)
    return decorated


def driver_login_required(f):
    """ドライバーログイン確認デコレーター"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('truck_driver_id'):
            return redirect(url_for('truck.driver_login'))
        return f(*args, **kwargs)
    return decorated


def office_login_required(f):
    """内勤スタッフログイン確認デコレーター"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('truck_office_id'):
            return redirect(url_for('truck.office_login'))
        return f(*args, **kwargs)
    return decorated


# ─── テンプレートフィルター ──────────────────────────────
bp.add_app_template_global(format_status, 'truck_format_status')
bp.add_app_template_global(status_color, 'truck_status_color')
bp.add_app_template_global(calc_duration, 'truck_calc_duration')
bp.add_app_template_global(format_time, 'truck_format_time')


# ─── ダッシュボード ──────────────────────────────────────

@bp.route('/')
@login_required_truck
def dashboard():
    # 店舗管理者（role=admin かつ store_id あり）は自店舗ダッシュボードへリダイレクト
    role = session.get('role', '')
    store_id = session.get('store_id')
    if role == 'admin' and store_id:
        return redirect(url_for('truck.store_dashboard', store_id=store_id))

    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        today = date.today()
        today_str = today.strftime("%Y年%m月%d日")

        q = db.query(TruckOperation).filter(TruckOperation.operation_date == today)
        if tenant_id:
            from sqlalchemy import or_
            q = q.filter(
                or_(
                    TruckOperation.tenant_id == tenant_id,
                    TruckOperation.tenant_id == None,
                )
            )
        operations = q.order_by(TruckOperation.start_time).all()

        status_counts = {}
        for op in operations:
            status_counts[op.status] = status_counts.get(op.status, 0) + 1

        ops_data = []
        for op in operations:
            ops_data.append({
                'status': op.status,
                'driver_name': op.driver.name if op.driver else '-',
                'truck_name': op.truck.name if op.truck else '-',
                'truck_number': op.truck.number if op.truck else '-',
                'route_name': op.route.name if op.route else '-',
                'start_time': op.start_time,
                'end_time': op.end_time,
            })

        tq = db.query(Truck).filter(Truck.active == True)
        if tenant_id:
            tq = tq.filter(Truck.tenant_id == tenant_id)
        trucks = tq.all()

        dq = db.query(TruckDriver).filter(TruckDriver.active == True)
        if tenant_id:
            dq = dq.filter(TruckDriver.tenant_id == tenant_id)
        drivers = dq.all()

        return render_template(
            'truck/dashboard.html',
            today_str=today_str,
            operations=ops_data,
            status_counts=status_counts,
            trucks=trucks,
            drivers=drivers,
            error=None,
        )
    except Exception as e:
        return render_template('truck/dashboard.html',
                               today_str=date.today().strftime("%Y年%m月%d日"),
                               operations=[], status_counts={}, trucks=[], drivers=[],
                               error=str(e))
    finally:
        db.close()


# ─── 運行履歴 ────────────────────────────────────────────

@bp.route('/history')
@login_required_truck
def history():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        today = date.today()
        selected_year = request.args.get('year', str(today.year))
        selected_month = request.args.get('month', str(today.month))
        selected_driver_id = request.args.get('driver_id', '')
        selected_truck_id = request.args.get('truck_id', '')

        try:
            year = int(selected_year)
            month = int(selected_month)
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1)
            else:
                end_date = date(year, month + 1, 1)
        except Exception:
            start_date = date(today.year, today.month, 1)
            end_date = today + timedelta(days=1)

        OFFICE_STATUSES = ['office_working', 'office_break', 'office_finished']
        q = db.query(TruckOperation).filter(
            TruckOperation.operation_date >= start_date,
            TruckOperation.operation_date < end_date,
            ~TruckOperation.status.in_(OFFICE_STATUSES),
        )
        if tenant_id:
            q = q.filter(TruckOperation.tenant_id == tenant_id)
        if selected_driver_id:
            try:
                q = q.filter(TruckOperation.driver_id == int(selected_driver_id))
            except ValueError:
                pass
        if selected_truck_id:
            try:
                q = q.filter(TruckOperation.truck_id == int(selected_truck_id))
            except ValueError:
                pass
        operations = q.order_by(TruckOperation.operation_date.desc(), TruckOperation.start_time.desc()).all()

        ops_data = []
        for op in operations:
            ops_data.append({
                'operation_date': op.operation_date,
                'status': op.status,
                'driver_name': op.driver.name if op.driver else '-',
                'driver_staff_id': op.driver_id,
                'truck_name': op.truck.name if op.truck else '-',
                'truck_id': op.truck_id,
                'route_name': op.route.name if op.route else '-',
                'start_time': op.start_time,
                'end_time': op.end_time,
            })

        dq = db.query(TruckDriver).filter(TruckDriver.active == True)
        if tenant_id:
            dq = dq.filter(TruckDriver.tenant_id == tenant_id)
        drivers = dq.all()

        tq = db.query(Truck).filter(Truck.active == True)
        if tenant_id:
            tq = tq.filter(Truck.tenant_id == tenant_id)
        trucks = tq.all()

        years = list(range(today.year - 2, today.year + 1))
        months = list(range(1, 13))

        return render_template(
            'truck/history.html',
            operations=ops_data,
            drivers=drivers,
            trucks=trucks,
            years=years,
            months=months,
            selected_year=int(selected_year),
            selected_month=int(selected_month),
            selected_driver_id=selected_driver_id,
            selected_truck_id=selected_truck_id,
            error=None,
        )
    except Exception as e:
        return render_template('truck/history.html',
                               operations=[], drivers=[], trucks=[],
                               years=[], months=list(range(1, 13)),
                               selected_year=date.today().year, selected_month=date.today().month,
                               selected_driver_id='', selected_truck_id='',
                               error=str(e))
    finally:
        db.close()


# ─── トラック管理 ────────────────────────────────────────

@bp.route('/trucks')
@login_required_truck
def trucks():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        store_id = session.get('store_id')
        role = session.get('role')
        q = db.query(Truck)
        if tenant_id:
            q = q.filter(Truck.tenant_id == tenant_id)
        # 店舗管理者は自店舗のトラックのみ表示
        if role == 'admin' and store_id:
            q = q.filter((Truck.store_id == store_id) | (Truck.store_id == None))
        trucks_list = q.order_by(Truck.created_at.desc()).all()
        return render_template('truck/trucks.html', trucks=trucks_list, error=None, today=date.today())
    except Exception as e:
        return render_template('truck/trucks.html', trucks=[], error=str(e), today=date.today())
    finally:
        db.close()


def _parse_truck_form(form, files=None):
    """フォームから詳細フィールドを取得するヘルパー"""
    import re as _re
    capacity_raw = form.get('capacity', '').strip()
    capacity_num = _re.sub(r'[^0-9.]', '', capacity_raw)
    try:
        capacity_val = float(capacity_num) if capacity_num else None
    except ValueError:
        capacity_val = None

    def parse_date(val):
        if not val:
            return None
        try:
            from datetime import date as _date
            return _date.fromisoformat(val)
        except Exception:
            return None

    def parse_int(val):
        try:
            return int(val) if val else None
        except Exception:
            return None

    def parse_float(val):
        v = _re.sub(r'[^0-9.]', '', val or '')
        try:
            return float(v) if v else None
        except Exception:
            return None

    data = dict(
        number=form.get('number', '').strip(),
        name=form.get('name', '').strip(),
        capacity=capacity_val,
        note=form.get('note', '').strip(),
        owner_name=form.get('owner_name', '').strip() or None,
        user_name=form.get('user_name', '').strip() or None,
        base_location=form.get('base_location', '').strip() or None,
        vehicle_type=form.get('vehicle_type', '').strip() or None,
        year=parse_int(form.get('year', '').strip()),
        color=form.get('color', '').strip() or None,
        vin=form.get('vin', '').strip() or None,
        engine_number=form.get('engine_number', '').strip() or None,
        shaken_expiry=parse_date(form.get('shaken_expiry', '').strip()),
        shaken_number=form.get('shaken_number', '').strip() or None,
        insurance_company=form.get('insurance_company', '').strip() or None,
        insurance_policy=form.get('insurance_policy', '').strip() or None,
        insurance_expiry=parse_date(form.get('insurance_expiry', '').strip()),
        store_id=parse_int(form.get('store_id', '').strip()),
    )
    # 写真アップロード
    if files:
        photo = files.get('photo')
        if photo and photo.filename:
            result = _save_truck_file(photo, 'photos')
            if result:
                data['photo_path'] = result[0]
                data['photo_name'] = result[1]
        # 車検証アップロード
        shaken_doc = files.get('shaken_doc')
        if shaken_doc and shaken_doc.filename:
            result = _save_truck_file(shaken_doc, 'shaken_docs')
            if result:
                data['shaken_doc_path'] = result[0]
                data['shaken_doc_name'] = result[1]
        # 保険証アップロード
        insurance_doc = files.get('insurance_doc')
        if insurance_doc and insurance_doc.filename:
            result = _save_truck_file(insurance_doc, 'insurance_docs')
            if result:
                data['insurance_doc_path'] = result[0]
                data['insurance_doc_name'] = result[1]
    return data


@bp.route('/trucks/new', methods=['GET', 'POST'])
@login_required_truck
def truck_new():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id, TTenpo.有効 == 1).order_by(TTenpo.名称).all() if tenant_id else []
        if request.method == 'POST':
            data = _parse_truck_form(request.form, request.files)
            if not data['number'] or not data['name']:
                flash('車両番号と車両名称は必須です', 'error')
                return render_template('truck/truck_form.html', truck=None, action='new', stores=stores)
            truck = Truck(tenant_id=tenant_id, **data)
            db.add(truck)
            db.commit()
            flash(f'トラック「{data["name"]}」を登録しました', 'success')
            return redirect(url_for('truck.truck_detail', truck_id=truck.id))
        return render_template('truck/truck_form.html', truck=None, action='new', stores=stores)
    except Exception as e:
        import traceback
        flash(f'エラー: {str(e)} | {traceback.format_exc()[-300:]}', 'error')
        return render_template('truck/truck_form.html', truck=None, action='new', stores=[])
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>', methods=['GET'])
@login_required_truck
def truck_detail(truck_id):
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        if not truck:
            flash('トラックが見つかりません', 'error')
            return redirect(url_for('truck.trucks'))
        accidents = db.query(TruckAccidentRecord).filter_by(truck_id=truck_id).order_by(TruckAccidentRecord.accident_date.desc()).all()
        inspections = db.query(TruckInspectionRecord).filter_by(truck_id=truck_id).order_by(TruckInspectionRecord.inspection_date.desc()).all()
        return render_template('truck/truck_detail.html', truck=truck, accidents=accidents, inspections=inspections, now=datetime.utcnow())
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/photo')
@login_required_truck
def truck_photo(truck_id):
    """車両写真を返す"""
    from flask import send_file
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        if not truck or not truck.photo_path or not os.path.exists(truck.photo_path):
            from flask import abort
            abort(404)
        return send_file(truck.photo_path)
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/shaken_doc')
@login_required_truck
def truck_shaken_doc(truck_id):
    """車検証ファイルを返す"""
    from flask import send_file, abort
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        if not truck or not truck.shaken_doc_path or not os.path.exists(truck.shaken_doc_path):
            abort(404)
        return send_file(truck.shaken_doc_path, as_attachment=False,
                         download_name=truck.shaken_doc_name or 'shaken_doc')
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/insurance_doc')
@login_required_truck
def truck_insurance_doc(truck_id):
    """保険証ファイルを返す"""
    from flask import send_file, abort
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        if not truck or not truck.insurance_doc_path or not os.path.exists(truck.insurance_doc_path):
            abort(404)
        return send_file(truck.insurance_doc_path, as_attachment=False,
                         download_name=truck.insurance_doc_name or 'insurance_doc')
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def truck_edit(truck_id):
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        if not truck:
            flash('トラックが見つかりません', 'error')
            return redirect(url_for('truck.trucks'))
        tenant_id = session.get('tenant_id') or truck.tenant_id
        stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id, TTenpo.有効 == 1).order_by(TTenpo.名称).all() if tenant_id else []
        if request.method == 'POST':
            data = _parse_truck_form(request.form, request.files)
            if not data['number'] or not data['name']:
                flash('車両番号と車両名称は必須です', 'error')
                return render_template('truck/truck_form.html', truck=truck, action='edit', stores=stores)
            for k, v in data.items():
                setattr(truck, k, v)
            truck.active = request.form.get('active') == '1'
            db.commit()
            flash(f'トラック「{truck.name}」を更新しました', 'success')
            return redirect(url_for('truck.truck_detail', truck_id=truck.id))
        return render_template('truck/truck_form.html', truck=truck, action='edit', stores=stores)
    finally:
        db.close()


# ─── 事故履歴 CRUD ────────────────────────────────────────

@bp.route('/trucks/<int:truck_id>/accidents/new', methods=['GET', 'POST'])
@login_required_truck
def accident_new(truck_id):
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        if not truck:
            flash('トラックが見つかりません', 'error')
            return redirect(url_for('truck.trucks'))
        drivers = db.query(TruckDriver).filter_by(tenant_id=session.get('tenant_id'), active=True).all()
        if request.method == 'POST':
            import re as _re
            from datetime import date as _date
            def pd(v):
                try: return _date.fromisoformat(v) if v else None
                except: return None
            def pf(v):
                n = _re.sub(r'[^0-9.]', '', v or '')
                try: return float(n) if n else None
                except: return None
            def pi(v):
                try: return int(v) if v and str(v).strip() else None
                except: return None
            rec = TruckAccidentRecord(
                truck_id=truck_id,
                driver_id=pi(request.form.get('driver_id')),
                accident_date=pd(request.form.get('accident_date', '').strip()),
                location=request.form.get('location', '').strip() or None,
                description=request.form.get('description', '').strip() or None,
                damage_level=request.form.get('damage_level', '').strip() or None,
                fault_ratio=pi(request.form.get('fault_ratio')),
                repair_cost=pf(request.form.get('repair_cost', '').strip()),
                repair_completed=request.form.get('repair_completed') == '1',
                note=request.form.get('note', '').strip() or None,
                tenant_id=session.get('tenant_id'),
            )
            db.add(rec)
            db.commit()
            flash('事故履歴を登録しました', 'success')
            return redirect(url_for('truck.truck_detail', truck_id=truck_id))
        return render_template('truck/accident_form.html', truck=truck, record=None, action='new', drivers=drivers)
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/accidents/<int:record_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def accident_edit(truck_id, record_id):
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        rec = db.query(TruckAccidentRecord).get(record_id)
        if not truck or not rec:
            flash('データが見つかりません', 'error')
            return redirect(url_for('truck.trucks'))
        drivers = db.query(TruckDriver).filter_by(tenant_id=session.get('tenant_id'), active=True).all()
        if request.method == 'POST':
            import re as _re
            from datetime import date as _date
            def pd(v):
                try: return _date.fromisoformat(v) if v else None
                except: return None
            def pf(v):
                n = _re.sub(r'[^0-9.]', '', v or '')
                try: return float(n) if n else None
                except: return None
            def pi(v):
                try: return int(v) if v and str(v).strip() else None
                except: return None
            rec.driver_id = pi(request.form.get('driver_id'))
            rec.accident_date = pd(request.form.get('accident_date', '').strip())
            rec.location = request.form.get('location', '').strip() or None
            rec.description = request.form.get('description', '').strip() or None
            rec.damage_level = request.form.get('damage_level', '').strip() or None
            rec.fault_ratio = pi(request.form.get('fault_ratio'))
            rec.repair_cost = pf(request.form.get('repair_cost', '').strip())
            rec.repair_completed = request.form.get('repair_completed') == '1'
            rec.note = request.form.get('note', '').strip() or None
            db.commit()
            flash('事故履歴を更新しました', 'success')
            return redirect(url_for('truck.truck_detail', truck_id=truck_id))
        return render_template('truck/accident_form.html', truck=truck, record=rec, action='edit', drivers=drivers)
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/accidents/<int:record_id>/delete', methods=['POST'])
@login_required_truck
def accident_delete(truck_id, record_id):
    db = SessionLocal()
    try:
        rec = db.query(TruckAccidentRecord).get(record_id)
        if rec:
            db.delete(rec)
            db.commit()
            flash('事故履歴を削除しました', 'success')
        return redirect(url_for('truck.truck_detail', truck_id=truck_id))
    finally:
        db.close()


# ─── 点検履歴 CRUD ────────────────────────────────────────

@bp.route('/trucks/<int:truck_id>/inspections/new', methods=['GET', 'POST'])
@login_required_truck
def inspection_new(truck_id):
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        if not truck:
            flash('トラックが見つかりません', 'error')
            return redirect(url_for('truck.trucks'))
        if request.method == 'POST':
            import re as _re
            from datetime import date as _date
            def pd(v):
                try: return _date.fromisoformat(v) if v else None
                except: return None
            def pf(v):
                n = _re.sub(r'[^0-9.]', '', v or '')
                try: return float(n) if n else None
                except: return None
            def pi(v):
                try: return int(v) if v else None
                except: return None
            rec = TruckInspectionRecord(
                truck_id=truck_id,
                inspection_date=pd(request.form.get('inspection_date', '').strip()),
                inspection_type=request.form.get('inspection_type', '').strip() or None,
                inspector=request.form.get('inspector', '').strip() or None,
                result=request.form.get('result', '').strip() or None,
                next_inspection_date=pd(request.form.get('next_inspection_date', '').strip()),
                mileage=pi(request.form.get('mileage', '').strip()),
                description=request.form.get('description', '').strip() or None,
                cost=pf(request.form.get('cost', '').strip()),
                note=request.form.get('note', '').strip() or None,
                tenant_id=session.get('tenant_id'),
            )
            db.add(rec)
            db.commit()
            flash('点検履歴を登録しました', 'success')
            return redirect(url_for('truck.truck_detail', truck_id=truck_id))
        return render_template('truck/inspection_form.html', truck=truck, record=None, action='new')
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/inspections/<int:record_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def inspection_edit(truck_id, record_id):
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        rec = db.query(TruckInspectionRecord).get(record_id)
        if not truck or not rec:
            flash('データが見つかりません', 'error')
            return redirect(url_for('truck.trucks'))
        if request.method == 'POST':
            import re as _re
            from datetime import date as _date
            def pd(v):
                try: return _date.fromisoformat(v) if v else None
                except: return None
            def pf(v):
                n = _re.sub(r'[^0-9.]', '', v or '')
                try: return float(n) if n else None
                except: return None
            def pi(v):
                try: return int(v) if v else None
                except: return None
            rec.inspection_date = pd(request.form.get('inspection_date', '').strip())
            rec.inspection_type = request.form.get('inspection_type', '').strip() or None
            rec.inspector = request.form.get('inspector', '').strip() or None
            rec.result = request.form.get('result', '').strip() or None
            rec.next_inspection_date = pd(request.form.get('next_inspection_date', '').strip())
            rec.mileage = pi(request.form.get('mileage', '').strip())
            rec.description = request.form.get('description', '').strip() or None
            rec.cost = pf(request.form.get('cost', '').strip())
            rec.note = request.form.get('note', '').strip() or None
            db.commit()
            flash('点検履歴を更新しました', 'success')
            return redirect(url_for('truck.truck_detail', truck_id=truck_id))
        return render_template('truck/inspection_form.html', truck=truck, record=rec, action='edit')
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/inspections/<int:record_id>/delete', methods=['POST'])
@login_required_truck
def inspection_delete(truck_id, record_id):
    db = SessionLocal()
    try:
        rec = db.query(TruckInspectionRecord).get(record_id)
        if rec:
            db.delete(rec)
            db.commit()
            flash('点検履歴を削除しました', 'success')
        return redirect(url_for('truck.truck_detail', truck_id=truck_id))
    finally:
        db.close()


@bp.route('/trucks/<int:truck_id>/delete', methods=['POST'])
@login_required_truck
def truck_delete(truck_id):
    db = SessionLocal()
    try:
        truck = db.query(Truck).get(truck_id)
        if truck:
            truck.active = False
            db.commit()
            flash(f'トラック「{truck.name}」を無効化しました', 'success')
        return redirect(url_for('truck.trucks'))
    finally:
        db.close()


# ─── ルート管理 ──────────────────────────────────────────

@bp.route('/routes')
@login_required_truck
def routes():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        store_id = session.get('store_id')
        role = session.get('role')
        q = db.query(TruckRoute)
        if tenant_id:
            q = q.filter(TruckRoute.tenant_id == tenant_id)
        # 店舗管理者は自店舗のルートのみ表示
        if role == 'admin' and store_id:
            q = q.filter((TruckRoute.store_id == store_id) | (TruckRoute.store_id == None))
        routes_list = q.order_by(TruckRoute.created_at.desc()).all()
        return render_template('truck/routes.html', routes=routes_list, error=None)
    except Exception as e:
        return render_template('truck/routes.html', routes=[], error=str(e))
    finally:
        db.close()


@bp.route('/routes/new', methods=['GET', 'POST'])
@login_required_truck
def route_new():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        clients = db.query(TruckClient).filter_by(active=True, tenant_id=tenant_id).order_by(TruckClient.name).all()
        stores = db.query(TTenpo).filter_by(tenant_id=tenant_id).order_by(TTenpo.id).all() if tenant_id else []
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            origin = request.form.get('origin', '').strip()
            destination = request.form.get('destination', '').strip()
            distance_km = request.form.get('distance_km', '').strip()
            client_id_str = request.form.get('client_id', '').strip()
            contract_amount = request.form.get('contract_amount', '').strip()
            note = request.form.get('note', '').strip()
            if not name:
                flash('ルート名は必須です', 'error')
                return render_template('truck/route_form.html', route=None, action='new', clients=clients, stores=stores)
            form_store_id = request.form.get('store_id', '').strip()
            try:
                form_store_id = int(form_store_id) if form_store_id else None
            except Exception:
                form_store_id = None
            route = TruckRoute(
                name=name,
                origin=origin,
                destination=destination,
                distance_km=float(distance_km) if distance_km else None,
                client_id=int(client_id_str) if client_id_str else None,
                contract_amount=int(contract_amount) if contract_amount else None,
                note=note,
                tenant_id=tenant_id,
                store_id=form_store_id,
            )
            db.add(route)
            db.commit()
            flash(f'ルート「{name}」を登録しました', 'success')
            return redirect(url_for('truck.routes'))
        return render_template('truck/route_form.html', route=None, action='new', clients=clients, stores=stores)
    finally:
        db.close()
@bp.route('/routes/<int:route_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def route_edit(route_id):
    db = SessionLocal()
    try:
        route = db.query(TruckRoute).get(route_id)
        if not route:
            flash('ルートが見つかりません', 'error')
            return redirect(url_for('truck.routes'))
        tenant_id = session.get('tenant_id')
        clients = db.query(TruckClient).filter_by(active=True, tenant_id=tenant_id).order_by(TruckClient.name).all()
        stores = db.query(TTenpo).filter_by(tenant_id=tenant_id).order_by(TTenpo.id).all() if tenant_id else []
        if request.method == 'POST':
            route.name = request.form.get('name', '').strip()
            route.origin = request.form.get('origin', '').strip()
            route.destination = request.form.get('destination', '').strip()
            distance_km = request.form.get('distance_km', '').strip()
            route.distance_km = float(distance_km) if distance_km else None
            client_id_str = request.form.get('client_id', '').strip()
            route.client_id = int(client_id_str) if client_id_str else None
            contract_amount_edit = request.form.get('contract_amount', '').strip()
            route.contract_amount = int(contract_amount_edit) if contract_amount_edit else None
            route.note = request.form.get('note', '').strip()
            route.active = request.form.get('active') == '1'
            form_store_id = request.form.get('store_id', '').strip()
            try:
                route.store_id = int(form_store_id) if form_store_id else None
            except Exception:
                route.store_id = None
            if not route.name:
                flash('ルート名は必須です', 'error')
                return render_template('truck/route_form.html', route=route, action='edit', clients=clients, stores=stores)
            db.commit()
            flash(f'ルート「{route.name}」を更新しました', 'success')
            return redirect(url_for('truck.routes'))
        return render_template('truck/route_form.html', route=route, action='edit', clients=clients, stores=stores)
    finally:
        db.close()


@bp.route('/routes/<int:route_id>/delete', methods=['POST'])
@login_required_truck
def route_delete(route_id):
    db = SessionLocal()
    try:
        route = db.query(TruckRoute).get(route_id)
        if route:
            route.active = False
            db.commit()
            flash(f'ルート「{route.name}」を無効化しました', 'success')
        return redirect(url_for('truck.routes'))
    finally:
        db.close()


# ─── ドライバー管理 ──────────────────────────────────────

@bp.route('/drivers')
@login_required_truck
def drivers():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        store_id = session.get('store_id')
        role = session.get('role')
        q = db.query(TruckDriver)
        if tenant_id:
            q = q.filter(TruckDriver.tenant_id == tenant_id)
        # 店舗管理者は自店舗のドライバーのみ表示
        if role == 'admin' and store_id:
            q = q.filter((TruckDriver.store_id == store_id) | (TruckDriver.store_id == None))
        drivers_list = q.order_by(TruckDriver.created_at.desc()).all()
        return render_template('truck/drivers.html', drivers=drivers_list, error=None)
    except Exception as e:
        return render_template('truck/drivers.html', drivers=[], error=str(e))
    finally:
        db.close()


@bp.route('/drivers/new', methods=['GET', 'POST'])
@login_required_truck
def driver_new():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            password = request.form.get('password', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            position = request.form.get('position', 'ドライバー').strip()
            license_number = request.form.get('license_number', '').strip()
            note = request.form.get('note', '').strip()
            stores_list = db.query(TTenpo).filter_by(tenant_id=tenant_id).order_by(TTenpo.id).all() if tenant_id else []
            if not login_id or not password or not name or not email:
                flash('ログインID・パスワード・氏名・メールアドレスは必須です', 'error')
                return render_template('truck/driver_form.html', driver=None, action='new', stores=stores_list)
            existing = db.query(TruckDriver).filter_by(login_id=login_id).first()
            if existing:
                flash('そのログインIDはすでに登録されています', 'error')
                return render_template('truck/driver_form.html', driver=None, action='new', stores=stores_list)
            # 従業員テーブルのlogin_id / email 重複チェック
            existing_emp = db.query(TJugyoin).filter(
                (TJugyoin.login_id == login_id) | (TJugyoin.email == email)
            ).first()
            if existing_emp:
                flash('そのログインIDまたはメールアドレスは従業員としてすでに登録されています', 'error')
                return render_template('truck/driver_form.html', driver=None, action='new')
            form_store_id = request.form.get('store_id', '').strip()
            try:
                form_store_id = int(form_store_id) if form_store_id else None
            except Exception:
                form_store_id = None
            driver = TruckDriver(
                login_id=login_id,
                password_hash=generate_password_hash(password),
                name=name,
                phone=phone,
                license_number=license_number,
                note=note,
                tenant_id=tenant_id,
                store_id=form_store_id,
            )
            db.add(driver)
            db.flush()
            # 従業員テーブルに自動登録
            employee = TJugyoin(
                login_id=login_id,
                email=email,
                name=name,
                phone=phone,
                password_hash=generate_password_hash(password),
                tenant_id=tenant_id,
                role='employee',
                active=1,
                position=position,
            )
            db.add(employee)
            db.flush()
            # 店舗に紐付け（セッションのstore_id、なければテナントの最初の店舗）
            store_id = session.get('store_id')
            if not store_id and tenant_id:
                first_store = db.query(TTenpo).filter_by(tenant_id=tenant_id).order_by(TTenpo.id).first()
                if first_store:
                    store_id = first_store.id
            if store_id:
                db.add(TJugyoinTenpo(employee_id=employee.id, store_id=store_id))
            db.commit()
            flash(f'ドライバー「{name}」を登録しました（従業員にも自動登録しました）', 'success')
            return redirect(url_for('truck.drivers'))
        stores_list = db.query(TTenpo).filter_by(tenant_id=tenant_id).order_by(TTenpo.id).all() if tenant_id else []
        return render_template('truck/driver_form.html', driver=None, action='new', stores=stores_list)
    finally:
        db.close()
@bp.route('/drivers/<int:driver_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def driver_edit(driver_id):
    db = SessionLocal()
    try:
        driver = db.query(TruckDriver).get(driver_id)
        if not driver:
            flash('ドライバーが見つかりません', 'error')
            return redirect(url_for('truck.drivers'))
        if request.method == 'POST':
            driver.login_id = request.form.get('login_id', '').strip()
            driver.name = request.form.get('name', '').strip()
            driver.phone = request.form.get('phone', '').strip()
            driver.license_number = request.form.get('license_number', '').strip()
            driver.note = request.form.get('note', '').strip()
            driver.active = request.form.get('active') == '1'
            new_password = request.form.get('password', '').strip()
            if new_password:
                driver.password_hash = generate_password_hash(new_password)
            form_store_id = request.form.get('store_id', '').strip()
            try:
                driver.store_id = int(form_store_id) if form_store_id else None
            except Exception:
                driver.store_id = None
            if not driver.login_id or not driver.name:
                flash('ログインIDと氏名は必須です', 'error')
                tenant_id = session.get('tenant_id')
                stores_list = db.query(TTenpo).filter_by(tenant_id=tenant_id).order_by(TTenpo.id).all() if tenant_id else []
                return render_template('truck/driver_form.html', driver=driver, action='edit', stores=stores_list)
            db.commit()
            flash(f'ドライバー「{driver.name}」を更新しました', 'success')
            return redirect(url_for('truck.drivers'))
        tenant_id = session.get('tenant_id')
        stores_list = db.query(TTenpo).filter_by(tenant_id=tenant_id).order_by(TTenpo.id).all() if tenant_id else []
        return render_template('truck/driver_form.html', driver=driver, action='edit', stores=stores_list)
    finally:
        db.close()


@bp.route('/drivers/<int:driver_id>/delete', methods=['POST'])
@login_required_truck
def driver_delete(driver_id):
    db = SessionLocal()
    try:
        driver = db.query(TruckDriver).get(driver_id)
        if driver:
            driver.active = False
            db.commit()
            flash(f'ドライバー「{driver.name}」を無効化しました', 'success')
        return redirect(url_for('truck.drivers'))
    finally:
        db.close()


@bp.route('/drivers/<int:driver_id>/destroy', methods=['POST'])
@login_required_truck
def driver_destroy(driver_id):
    db = SessionLocal()
    try:
        driver = db.query(TruckDriver).get(driver_id)
        if driver:
            name = driver.name
            db.delete(driver)
            db.commit()
            flash(f'ドライバー「{name}」を削除しました', 'success')
        return redirect(url_for('truck.drivers'))
    finally:
        db.close()


@bp.route('/drivers/from_employee', methods=['GET', 'POST'])
@login_required_truck
def driver_from_employee():
    """従業員をドライバーとして登録する"""
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        store_id = session.get('store_id')

        def _get_employees():
            """店舗に紐づく従業員を取得（store_idがあれば店舗絞り込み、なければテナント全体）"""
            registered_driver_names = set(
                d.name for d in db.query(TruckDriver).filter_by(tenant_id=tenant_id, active=True).all()
            )
            if store_id:
                # T_従業員_店舗 を JOIN して対象店舗の従業員のみ取得
                emps = db.query(TJugyoin).join(
                    TJugyoinTenpo, TJugyoin.id == TJugyoinTenpo.employee_id
                ).filter(
                    TJugyoinTenpo.store_id == store_id,
                    TJugyoin.active == 1,
                ).order_by(TJugyoin.name).all() if store_id else []
            else:
                emps = db.query(TJugyoin).filter(
                    TJugyoin.tenant_id == tenant_id,
                    TJugyoin.active == 1,
                ).order_by(TJugyoin.name).all() if tenant_id else []
            return emps, registered_driver_names

        if request.method == 'POST':
            employee_id = request.form.get('employee_id', '').strip()
            login_id = request.form.get('login_id', '').strip()
            password = request.form.get('password', '').strip()
            license_number = request.form.get('license_number', '').strip()
            note = request.form.get('note', '').strip()
            if not employee_id or not login_id or not password:
                flash('従業員・ログインID・パスワードは必須です', 'error')
                emps, registered_names = _get_employees()
                return render_template('truck/driver_from_employee.html',
                                       employees=emps, registered_names=registered_names)
            employee = db.query(TJugyoin).get(int(employee_id))
            if not employee:
                flash('従業員が見つかりません', 'error')
                return redirect(url_for('truck.drivers'))
            existing = db.query(TruckDriver).filter_by(login_id=login_id).first()
            if existing:
                flash('そのログインIDはすでに登録されています', 'error')
                emps, registered_names = _get_employees()
                return render_template('truck/driver_from_employee.html',
                                       employees=emps, registered_names=registered_names)
            driver = TruckDriver(
                login_id=login_id,
                password_hash=generate_password_hash(password),
                name=employee.name,
                phone=employee.phone or '',
                license_number=license_number,
                note=note,
                tenant_id=tenant_id,
                store_id=store_id,
            )
            db.add(driver)
            # 従業員から登録の場合、従業員は既存。ドライバー用パスワードで従業員パスワードを更新する
            employee.password_hash = generate_password_hash(password)
            db.commit()
            flash(f'従業員「{employee.name}」をドライバーとして登録しました', 'success')
            return redirect(url_for('truck.drivers'))
        emps, registered_names = _get_employees()
        return render_template('truck/driver_from_employee.html',
                               employees=emps,
                               registered_names=registered_names)
    finally:
        db.close()


# ─── GPS位置確認 ─────────────────────────────────────────

@bp.route('/gps_map')
@login_required_truck
def gps_map():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            target_date = date.today()
        driver_id_param = request.args.get('driver_id')

        dq = db.query(TruckDriver).filter(TruckDriver.active == True)
        if tenant_id:
            dq = dq.filter(TruckDriver.tenant_id == tenant_id)
        drivers = dq.all()

        driver_list = []
        for d in drivers:
            driver_list.append({
                'id': d.id,
                'name': d.name,
                'login_id': d.login_id,
            })

        if driver_id_param:
            try:
                sel_id = int(driver_id_param)
                target_drivers = [dl for dl in driver_list if dl['id'] == sel_id]
            except ValueError:
                target_drivers = driver_list
        else:
            target_drivers = driver_list

        driver_ids = [dl['id'] for dl in target_drivers]
        driver_tracks = {}
        if driver_ids:
            ids_str = ','.join(str(did) for did in driver_ids)
            dt_start = datetime.combine(target_date, datetime.min.time())
            dt_end = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            try:
                locs = db.execute(text(f"""
                    SELECT driver_id, latitude, longitude, recorded_at, speed
                    FROM "T_トラック運行位置履歴"
                    WHERE driver_id IN ({ids_str})
                      AND recorded_at >= :dt_start
                      AND recorded_at < :dt_end
                    ORDER BY driver_id ASC, recorded_at ASC
                """), {'dt_start': dt_start, 'dt_end': dt_end}).fetchall()
                for loc in locs:
                    key = loc[0]
                    if key not in driver_tracks:
                        driver_tracks[key] = []
                    driver_tracks[key].append({
                        'lat': float(loc[1]),
                        'lng': float(loc[2]),
                        'time': loc[3].strftime('%H:%M:%S') if loc[3] else '',
                        'speed': float(loc[4]) if loc[4] is not None else None,
                    })
            except Exception:
                pass

        tracks = []
        for dl in target_drivers:
            pts = driver_tracks.get(dl['id'], [])
            if not pts:
                continue
            tracks.append({
                'driver_id': dl['id'],
                'staff_id': dl['id'],
                'staff_name': dl['name'],
                'points': pts,
            })

        return render_template(
            'truck/gps_map.html',
            tracks_data=tracks,
            drivers=driver_list,
            selected_date=date_str,
            selected_driver_id=driver_id_param or '',
            error=None,
        )
    except Exception as e:
        return render_template('truck/gps_map.html',
                               tracks_data=[], drivers=[],
                               selected_date=date.today().strftime('%Y-%m-%d'),
                               selected_driver_id='',
                               error=str(e))
    finally:
        db.close()


@bp.route('/gps_map/realtime_data')
@login_required_truck
def gps_map_realtime_data():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            target_date = date.today()
        driver_id_param = request.args.get('driver_id')

        dq = db.query(TruckDriver).filter(TruckDriver.active == True)
        if tenant_id:
            dq = dq.filter(TruckDriver.tenant_id == tenant_id)
        drivers = dq.all()

        driver_list = []
        for d in drivers:
            driver_list.append({
                'id': d.id,
                'name': d.name,
                'login_id': d.login_id,
            })

        if driver_id_param:
            try:
                sel_id = int(driver_id_param)
                target_drivers = [dl for dl in driver_list if dl['id'] == sel_id]
            except ValueError:
                target_drivers = driver_list
        else:
            target_drivers = driver_list

        driver_ids = [dl['id'] for dl in target_drivers]
        driver_tracks = {}
        if driver_ids:
            ids_str = ','.join(str(did) for did in driver_ids)
            dt_start = datetime.combine(target_date, datetime.min.time())
            dt_end = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            try:
                locs = db.execute(text(f"""
                    SELECT driver_id, latitude, longitude, recorded_at
                    FROM "T_トラック運行位置履歴"
                    WHERE driver_id IN ({ids_str})
                      AND recorded_at >= :dt_start
                      AND recorded_at < :dt_end
                    ORDER BY driver_id ASC, recorded_at ASC
                """), {'dt_start': dt_start, 'dt_end': dt_end}).fetchall()
                for loc in locs:
                    key = loc[0]
                    if key not in driver_tracks:
                        driver_tracks[key] = []
                    driver_tracks[key].append({
                        'lat': float(loc[1]),
                        'lng': float(loc[2]),
                        'time': loc[3].strftime('%H:%M:%S') if loc[3] else ''
                    })
            except Exception:
                pass

        # 各ドライバーの運行情報（運行開始・荷積み・荷下ろし時刻）を取得
        op_times = {}
        if driver_ids:
            ops = db.execute(text(f"""
                SELECT driver_id, loading_start_time, unloading_start_time, start_time, status, break_start_time, break_end_time
                FROM truck_operations
                WHERE driver_id IN ({ids_str})
                  AND operation_date = :op_date
                ORDER BY driver_id ASC, start_time ASC
            """), {'op_date': target_date}).fetchall()
            for op in ops:
                did = op[0]
                if did not in op_times:
                    op_times[did] = {
                        'loading': op[1],
                        'unloading': op[2],
                        'start_times': [],
                        'is_finished': False,
                        'break_start': op[5],
                        'break_end': op[6],
                    }
                # 複数運行の開始時刻をすべて記録
                if op[3]:
                    op_times[did]['start_times'].append(op[3])
                # 荷積み・荷下ろしは最新の値で上書き（最後の運行を優先）
                if op[1]:
                    op_times[did]['loading'] = op[1]
                if op[2]:
                    op_times[did]['unloading'] = op[2]
                # 休憩開始・終了は最新の値で上書き
                if op[5]:
                    op_times[did]['break_start'] = op[5]
                if op[6]:
                    op_times[did]['break_end'] = op[6]
                # 退勤済みかどうか（最後の運行のstatusで判定）
                if op[4] == 'finished':
                    op_times[did]['is_finished'] = True
        drivers_out = []
        for dl in target_drivers:
            pts = driver_tracks.get(dl['id'], [])
            if not pts:
                continue
            # 荷積み・荷下ろし時刻に最も近いGPS点のインデックスを特定
            op_info = op_times.get(dl['id'], {})
            loading_time = op_info.get('loading')
            unloading_time = op_info.get('unloading')
            def find_nearest_idx(target_time, pts_list):
                if not target_time:
                    return None
                target_str = target_time.strftime('%H:%M:%S')
                best_idx = None
                best_diff = None
                for idx, p in enumerate(pts_list):
                    try:
                        from datetime import datetime as dt2
                        t = dt2.strptime(p['time'], '%H:%M:%S')
                        tgt = dt2.strptime(target_str, '%H:%M:%S')
                        diff = abs((t - tgt).total_seconds())
                        if best_diff is None or diff < best_diff:
                            best_diff = diff
                            best_idx = idx
                    except Exception:
                        pass
                return best_idx
            loading_idx = find_nearest_idx(loading_time, pts)
            unloading_idx = find_nearest_idx(unloading_time, pts)
            break_start_time = op_info.get('break_start')
            break_end_time = op_info.get('break_end')
            break_start_idx = find_nearest_idx(break_start_time, pts)
            break_end_idx = find_nearest_idx(break_end_time, pts)
            # 各運行のstart_timeに最も近いGPS点を出発地点(clock_in)として特定
            start_times = op_info.get('start_times', [])
            clock_in_indices = set()
            for st in start_times:
                idx = find_nearest_idx(st, pts)
                if idx is not None:
                    clock_in_indices.add(idx)
            # start_timesがない場合は最初の点を出発地点にする
            if not clock_in_indices:
                clock_in_indices.add(0)
            # locationsにtypeフィールドを追加
            SPEED_LIMIT_KMH = 80  # 速度超過の閾値
            locations = []
            for i, p in enumerate(pts):
                if i in clock_in_indices:
                    loc_type = 'clock_in'
                elif i == loading_idx:
                    loc_type = 'loading'
                elif i == unloading_idx:
                    loc_type = 'unloading'
                elif i == break_start_idx:
                    loc_type = 'break_start'
                elif i == break_end_idx:
                    loc_type = 'break_end'
                elif p.get('speed') is not None and p['speed'] > SPEED_LIMIT_KMH:
                    loc_type = 'speeding'
                else:
                    loc_type = 'location'
                locations.append({
                    'lat': p['lat'],
                    'lng': p['lng'],
                    'time': p['time'],
                    'type': loc_type,
                    'speed': p.get('speed'),
                })
            drivers_out.append({
                'driver_id': dl['id'],
                'staff_id': dl['id'],
                'staff_name': dl['name'],
                'locations': locations,
                'is_finished': op_info.get('is_finished', False),
            })

        return jsonify({'ok': True, 'drivers': drivers_out})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


# ─── 取引先・荷主管理 ──────────────────────────────────────

@bp.route('/clients')
@login_required_truck
def clients():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckClient).filter_by(active=True)
        if tenant_id:
            q = q.filter(TruckClient.tenant_id == tenant_id)
        rows = q.order_by(TruckClient.kana, TruckClient.name).all()
        return render_template('truck/clients.html', clients=rows)
    finally:
        db.close()


@bp.route('/clients/new', methods=['GET', 'POST'])
@login_required_truck
def client_new():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if not name:
                flash('会社名は必須です', 'error')
                return render_template('truck/client_form.html', client=None)
            c = TruckClient(
                name=name,
                kana=request.form.get('kana', '').strip(),
                contact_name=request.form.get('contact_name', '').strip(),
                phone=request.form.get('phone', '').strip(),
                email=request.form.get('email', '').strip(),
                address=request.form.get('address', '').strip(),
                client_type=request.form.get('client_type', 'both'),
                note=request.form.get('note', '').strip(),
                tenant_id=session.get('tenant_id'),
            )
            db.add(c)
            db.commit()
            flash(f'取引先「{name}」を登録しました', 'success')
            return redirect(url_for('truck.clients'))
        return render_template('truck/client_form.html', client=None)
    finally:
        db.close()


@bp.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def client_edit(client_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckClient).filter_by(id=client_id, active=True)
        if tenant_id:
            q = q.filter(TruckClient.tenant_id == tenant_id)
        c = q.first()
        if not c:
            flash('取引先が見つかりません', 'error')
            return redirect(url_for('truck.clients'))
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if not name:
                flash('会社名は必須です', 'error')
                return render_template('truck/client_form.html', client=c)
            c.name = name
            c.kana = request.form.get('kana', '').strip()
            c.contact_name = request.form.get('contact_name', '').strip()
            c.phone = request.form.get('phone', '').strip()
            c.email = request.form.get('email', '').strip()
            c.address = request.form.get('address', '').strip()
            c.client_type = request.form.get('client_type', 'both')
            c.note = request.form.get('note', '').strip()
            db.commit()
            flash(f'取引先「{c.name}」を更新しました', 'success')
            return redirect(url_for('truck.clients'))
        return render_template('truck/client_form.html', client=c)
    finally:
        db.close()


@bp.route('/clients/<int:client_id>/delete', methods=['POST'])
@login_required_truck
def client_delete(client_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckClient).filter_by(id=client_id)
        if tenant_id:
            q = q.filter(TruckClient.tenant_id == tenant_id)
        c = q.first()
        if c:
            c.active = False
            db.commit()
            flash(f'取引先「{c.name}」を削除しました', 'success')
        return redirect(url_for('truck.clients'))
    finally:
        db.close()


## ─── 契約書管理 ──────────────────────────────────────────

@bp.route('/contracts')
@login_required_truck
def contracts():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckContract).filter_by(active=True)
        if tenant_id:
            q = q.filter(TruckContract.tenant_id == tenant_id)
        rows = q.order_by(TruckContract.created_at.desc()).all()
        return render_template('truck/contracts.html', contracts=rows)
    finally:
        db.close()


@bp.route('/contracts/new', methods=['GET', 'POST'])
@login_required_truck
def contract_new():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            if not title:
                flash('契約書名は必須です', 'error')
                return render_template('truck/contract_form.html', contract=None)
            c = TruckContract(
                title=title,
                contract_type=request.form.get('contract_type', 'other'),
                counterparty=request.form.get('counterparty', '').strip(),
                start_date=_parse_date(request.form.get('start_date', '')),
                end_date=_parse_date(request.form.get('end_date', '')),
                amount=_parse_float(request.form.get('amount', '')),
                note=request.form.get('note', '').strip(),
                tenant_id=session.get('tenant_id'),
            )
            # ファイルアップロード（複数ファイル + 撮影写真）
            saved = _save_truck_files_multi(request, 'contracts')
            if saved:
                c.file_path, c.file_name = saved
            db.add(c)
            db.commit()
            # AI自動読み取り
            if request.form.get('ocr_mode') == 'auto' and c.file_path:
                _api_keys = _get_truck_api_keys(db, session.get('tenant_id'))
                api_key = _api_keys.get('openai_api_key')
                google_vision_key = _api_keys.get('google_vision_api_key')
                if api_key:
                    try:
                        result = _run_truck_ocr(c.file_path, api_key, 'contract', google_vision_key=google_vision_key)
                        c.ocr_status = 'done'
                        c.ocr_title = result.get('title', '')
                        c.ocr_counterparty = result.get('counterparty', '')
                        c.ocr_start_date = result.get('start_date', '')
                        c.ocr_end_date = result.get('end_date', '')
                        c.ocr_amount = result.get('amount', '')
                        c.ocr_summary = result.get('summary', '')
                        c.ocr_raw = json.dumps(result, ensure_ascii=False)
                        db.commit()
                        flash(f'契約書「{title}」を登録し、AI読み取りを完了しました', 'success')
                    except Exception as e:
                        flash(f'契約書「{title}」を登録しました（AI読み取り失敗: {str(e)[:50]}）', 'warning')
                else:
                    flash(f'契約書「{title}」を登録しました（APIキー未設定のためAI読み取りをスキップ）', 'warning')
            else:
                flash(f'契約書「{title}」を登録しました', 'success')
            return redirect(url_for('truck.contracts'))
        return render_template('truck/contract_form.html', contract=None)
    finally:
        db.close()


@bp.route('/contracts/<int:contract_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def contract_edit(contract_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckContract).filter_by(id=contract_id, active=True)
        if tenant_id:
            q = q.filter(TruckContract.tenant_id == tenant_id)
        c = q.first()
        if not c:
            flash('契約書が見つかりません', 'error')
            return redirect(url_for('truck.contracts'))
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            if not title:
                flash('契約書名は必須です', 'error')
                return render_template('truck/contract_form.html', contract=c)
            c.title = title
            c.contract_type = request.form.get('contract_type', 'other')
            c.counterparty = request.form.get('counterparty', '').strip()
            c.start_date = _parse_date(request.form.get('start_date', ''))
            c.end_date = _parse_date(request.form.get('end_date', ''))
            c.amount = _parse_float(request.form.get('amount', ''))
            c.note = request.form.get('note', '').strip()
            saved = _save_truck_files_multi(request, 'contracts')
            if saved:
                c.file_path, c.file_name = saved
            db.commit()
            flash(f'契約書「{c.title}」を更新しました', 'success')
            return redirect(url_for('truck.contracts'))
        return render_template('truck/contract_form.html', contract=c)
    finally:
        db.close()


@bp.route('/contracts/<int:contract_id>/delete', methods=['POST'])
@login_required_truck
def contract_delete(contract_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckContract).filter_by(id=contract_id)
        if tenant_id:
            q = q.filter(TruckContract.tenant_id == tenant_id)
        c = q.first()
        if c:
            c.active = False
            db.commit()
            flash(f'契約書「{c.title}」を削除しました', 'success')
        return redirect(url_for('truck.contracts'))
    finally:
        db.close()


@bp.route('/contracts/<int:contract_id>/ocr', methods=['POST'])
@login_required_truck
def contract_ocr(contract_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckContract).filter_by(id=contract_id, active=True)
        if tenant_id:
            q = q.filter(TruckContract.tenant_id == tenant_id)
        c = q.first()
        if not c or not c.file_path:
            return jsonify({'error': 'ファイルがありません'}), 400
        api_keys = _get_truck_api_keys(db, tenant_id)
        api_key = api_keys.get('openai_api_key')
        google_vision_key = api_keys.get('google_vision_api_key')
        if not api_key and not google_vision_key:
            return jsonify({'error': 'APIキーが設定されていません。テナント管理者のAPIキー設定でOpenAI APIキーまたはGoogle Vision APIキーを登録してください'}), 400
        result = _run_truck_ocr(c.file_path, api_key, 'contract', google_vision_key=google_vision_key)
        c.ocr_status = 'done'
        c.ocr_title = result.get('title', '')
        c.ocr_counterparty = result.get('counterparty', '')
        c.ocr_start_date = result.get('start_date', '')
        c.ocr_end_date = result.get('end_date', '')
        c.ocr_amount = result.get('amount', '')
        c.ocr_summary = result.get('summary', '')
        c.ocr_raw = json.dumps(result, ensure_ascii=False)
        db.commit()
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ─── 保険情報管理 ──────────────────────────────────────────

@bp.route('/insurances')
@login_required_truck
def insurances():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckInsurance).filter_by(active=True)
        if tenant_id:
            q = q.filter(TruckInsurance.tenant_id == tenant_id)
        rows = q.order_by(TruckInsurance.end_date).all()
        trucks_list = db.query(Truck).filter_by(active=True).filter(Truck.tenant_id == tenant_id).all() if tenant_id else []
        drivers_list = db.query(TruckDriver).filter_by(active=True).filter(TruckDriver.tenant_id == tenant_id).all() if tenant_id else []
        return render_template('truck/insurances.html', insurances=rows, trucks=trucks_list, drivers=drivers_list, today_iso=date.today().isoformat())
    finally:
        db.close()


@bp.route('/insurances/new', methods=['GET', 'POST'])
@login_required_truck
def insurance_new():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        trucks_list = db.query(Truck).filter_by(active=True).filter(Truck.tenant_id == tenant_id).all() if tenant_id else []
        drivers_list = db.query(TruckDriver).filter_by(active=True).filter(TruckDriver.tenant_id == tenant_id).all() if tenant_id else []
        if request.method == 'POST':
            ins = TruckInsurance(
                insurance_type=request.form.get('insurance_type', 'other'),
                insurer=request.form.get('insurer', '').strip(),
                policy_number=request.form.get('policy_number', '').strip(),
                truck_id=_parse_int(request.form.get('truck_id', '')),
                driver_id=_parse_int(request.form.get('driver_id', '')),
                start_date=_parse_date(request.form.get('start_date', '')),
                end_date=_parse_date(request.form.get('end_date', '')),
                premium=_parse_float(request.form.get('premium', '')),
                coverage_amount=_parse_float(request.form.get('coverage_amount', '')),
                note=request.form.get('note', '').strip(),
                tenant_id=tenant_id,
            )
            saved = _save_truck_files_multi(request, 'insurances')
            if saved:
                ins.file_path, ins.file_name = saved
            db.add(ins)
            db.commit()
            # AI自動読み取り
            if request.form.get('ocr_mode') == 'auto' and ins.file_path:
                _api_keys2 = _get_truck_api_keys(db, tenant_id)
                api_key = _api_keys2.get('openai_api_key')
                google_vision_key = _api_keys2.get('google_vision_api_key')
                if api_key:
                    try:
                        result = _run_truck_ocr(ins.file_path, api_key, 'insurance', google_vision_key=google_vision_key)
                        ins.ocr_status = 'done'
                        ins.ocr_insurer = result.get('insurer', '')
                        ins.ocr_policy_number = result.get('policy_number', '')
                        ins.ocr_start_date = result.get('start_date', '')
                        ins.ocr_end_date = result.get('end_date', '')
                        ins.ocr_premium = result.get('premium', '')
                        ins.ocr_summary = result.get('summary', '')
                        ins.ocr_raw = json.dumps(result, ensure_ascii=False)
                        db.commit()
                        flash('保険情報を登録し、AI読み取りを完了しました', 'success')
                    except Exception as e:
                        flash(f'保険情報を登録しました（AI読み取り失敗: {str(e)[:50]}）', 'warning')
                else:
                    flash('保険情報を登録しました（APIキー未設定のためAI読み取りをスキップ）', 'warning')
            else:
                flash('保険情報を登録しました', 'success')
            return redirect(url_for('truck.insurances'))
        return render_template('truck/insurance_form.html', insurance=None, trucks=trucks_list, drivers=drivers_list)
    finally:
        db.close()


@bp.route('/insurances/<int:ins_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def insurance_edit(ins_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckInsurance).filter_by(id=ins_id, active=True)
        if tenant_id:
            q = q.filter(TruckInsurance.tenant_id == tenant_id)
        ins = q.first()
        if not ins:
            flash('保険情報が見つかりません', 'error')
            return redirect(url_for('truck.insurances'))
        trucks_list = db.query(Truck).filter_by(active=True).filter(Truck.tenant_id == tenant_id).all() if tenant_id else []
        drivers_list = db.query(TruckDriver).filter_by(active=True).filter(TruckDriver.tenant_id == tenant_id).all() if tenant_id else []
        if request.method == 'POST':
            ins.insurance_type = request.form.get('insurance_type', 'other')
            ins.insurer = request.form.get('insurer', '').strip()
            ins.policy_number = request.form.get('policy_number', '').strip()
            ins.truck_id = _parse_int(request.form.get('truck_id', ''))
            ins.driver_id = _parse_int(request.form.get('driver_id', ''))
            ins.start_date = _parse_date(request.form.get('start_date', ''))
            ins.end_date = _parse_date(request.form.get('end_date', ''))
            ins.premium = _parse_float(request.form.get('premium', ''))
            ins.coverage_amount = _parse_float(request.form.get('coverage_amount', ''))
            ins.note = request.form.get('note', '').strip()
            saved = _save_truck_files_multi(request, 'insurances')
            if saved:
                ins.file_path, ins.file_name = saved
            db.commit()
            flash('保険情報を更新しました', 'success')
            return redirect(url_for('truck.insurances'))
        return render_template('truck/insurance_form.html', insurance=ins, trucks=trucks_list, drivers=drivers_list)
    finally:
        db.close()


@bp.route('/insurances/<int:ins_id>/delete', methods=['POST'])
@login_required_truck
def insurance_delete(ins_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckInsurance).filter_by(id=ins_id)
        if tenant_id:
            q = q.filter(TruckInsurance.tenant_id == tenant_id)
        ins = q.first()
        if ins:
            ins.active = False
            db.commit()
            flash('保険情報を削除しました', 'success')
        return redirect(url_for('truck.insurances'))
    finally:
        db.close()


@bp.route('/insurances/<int:ins_id>/ocr', methods=['POST'])
@login_required_truck
def insurance_ocr(ins_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        q = db.query(TruckInsurance).filter_by(id=ins_id, active=True)
        if tenant_id:
            q = q.filter(TruckInsurance.tenant_id == tenant_id)
        ins = q.first()
        if not ins or not ins.file_path:
            return jsonify({'error': 'ファイルがありません'}), 400
        api_keys = _get_truck_api_keys(db, tenant_id)
        api_key = api_keys.get('openai_api_key')
        google_vision_key = api_keys.get('google_vision_api_key')
        if not api_key and not google_vision_key:
            return jsonify({'error': 'APIキーが設定されていません。テナント管理者のAPIキー設定でOpenAI APIキーまたはGoogle Vision APIキーを登録してください'}), 400
        result = _run_truck_ocr(ins.file_path, api_key, 'insurance', google_vision_key=google_vision_key)
        ins.ocr_status = 'done'
        ins.ocr_insurer = result.get('insurer', '')
        ins.ocr_policy_number = result.get('policy_number', '')
        ins.ocr_start_date = result.get('start_date', '')
        ins.ocr_end_date = result.get('end_date', '')
        ins.ocr_premium = result.get('premium', '')
        ins.ocr_summary = result.get('summary', '')
        ins.ocr_raw = json.dumps(result, ensure_ascii=False)
        db.commit()
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ─── AI-OCRヘルパー関数 ────────────────────────────────────

def _get_truck_api_keys(db, tenant_id):
    """アプリ固有(TruckAppSettings) → テナント(TTenant) → アプリ管理者(TAppManagerGroup) → システム管理者の順でAPIキーを取得"""
    result = {'openai_api_key': None, 'google_vision_api_key': None}
    # 1. アプリ固有設定（最優先）
    if tenant_id:
        app_openai = TruckAppSettings.get(db, 'openai_api_key', tenant_id=tenant_id)
        app_vision = TruckAppSettings.get(db, 'google_vision_api_key', tenant_id=tenant_id)
        if app_openai:
            result['openai_api_key'] = app_openai
        if app_vision:
            result['google_vision_api_key'] = app_vision
    # 2. テナント共通設定
    if (not result['openai_api_key'] or not result['google_vision_api_key']) and tenant_id:
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        if tenant:
            if not result['openai_api_key'] and getattr(tenant, 'openai_api_key', None):
                result['openai_api_key'] = tenant.openai_api_key
            if not result['google_vision_api_key'] and getattr(tenant, 'google_vision_api_key', None):
                result['google_vision_api_key'] = tenant.google_vision_api_key
    # 3. アプリ管理グループ
    if not result['openai_api_key'] or not result['google_vision_api_key']:
        try:
            app_managers = db.query(TKanrisha).filter(
                TKanrisha.role == 'app_manager',
                TKanrisha.app_manager_group_id.isnot(None)
            ).all()
            for am in app_managers:
                grp = db.query(TAppManagerGroup).filter(TAppManagerGroup.id == am.app_manager_group_id).first()
                if grp:
                    if not result['openai_api_key'] and getattr(grp, 'openai_api_key', None):
                        result['openai_api_key'] = grp.openai_api_key
                    if not result['google_vision_api_key'] and getattr(grp, 'google_vision_api_key', None):
                        result['google_vision_api_key'] = grp.google_vision_api_key
                    break
        except Exception:
            pass
    # 4. システム管理者
    if not result['openai_api_key'] or not result['google_vision_api_key']:
        sys_admins = db.query(TKanrisha).filter(TKanrisha.role == 'system_admin').all()
        for sa in sys_admins:
            if not result['openai_api_key'] and getattr(sa, 'openai_api_key', None):
                result['openai_api_key'] = sa.openai_api_key
            if not result['google_vision_api_key'] and getattr(sa, 'google_vision_api_key', None):
                result['google_vision_api_key'] = sa.google_vision_api_key
            if result['openai_api_key'] and result['google_vision_api_key']:
                break
    return result


def _parse_date(s):
    if not s:
        return None
    try:
        from datetime import date as _date
        return _date.fromisoformat(s)
    except Exception:
        return None


def _parse_float(s):
    if not s:
        return None
    try:
        return float(str(s).replace(',', ''))
    except Exception:
        return None


def _parse_int(s):
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _save_truck_files_multi(req, subdir):
    """複数ファイル選択 + カメラ撮影写真（Base64）をまとめて保存し、最初のファイルのパスを返す"""
    import uuid, base64 as _b64
    from urllib.parse import unquote as _unquote
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads', 'truck', subdir)
    os.makedirs(upload_dir, exist_ok=True)
    saved_first = None
    # 通常ファイル（複数）
    files = req.files.getlist('files')
    for f in files:
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp']:
                continue
            fname = f"{uuid.uuid4().hex}{ext}"
            fpath = os.path.join(upload_dir, fname)
            f.save(fpath)
            if saved_first is None:
                saved_first = (fpath, f.filename)
    # 撮影写真（Base64）
    captured = req.form.getlist('captured_photos')
    for i, data_url in enumerate(captured):
        try:
            data_url = _unquote(data_url)
            header, b64data = data_url.split(',', 1)
            img_bytes = _b64.b64decode(b64data)
            fname = f"{uuid.uuid4().hex}.jpg"
            fpath = os.path.join(upload_dir, fname)
            with open(fpath, 'wb') as fp:
                fp.write(img_bytes)
            display_name = f'撮影写真{i+1}.jpg'
            if saved_first is None:
                saved_first = (fpath, display_name)
        except Exception:
            continue
    return saved_first


def _save_truck_file(file_obj, subdir):
    """PDF/画像をアップロードしてパスを返す"""
    import uuid
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads', 'truck', subdir)
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file_obj.filename)[1].lower()
    if ext not in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return None
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = os.path.join(upload_dir, fname)
    file_obj.save(fpath)
    return fpath, file_obj.filename


def _run_truck_ocr(file_path, api_key, doc_type, google_vision_key=None):
    """契約書・保険証券を読み取る。証桯データ化アプリと同じロジック：
    1. Google Vision API（OCR）+ GPT-4o（構造化）: 最高精度
    2. GPT-4o Vision単体: 標準精度
    """
    import base64
    import requests as _req
    import fitz  # PyMuPDF

    def encode_image(path):
        with open(path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    # PDFは先頭2ページまで画像化
    ext = os.path.splitext(file_path)[1].lower()
    image_paths = []
    if ext == '.pdf':
        try:
            doc = fitz.open(file_path)
            for i in range(min(2, len(doc))):
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(200/72, 200/72))
                tmp = file_path + f'_p{i}.jpg'
                pix.save(tmp)
                image_paths.append(tmp)
            doc.close()
        except Exception:
            image_paths = []
    else:
        image_paths = [file_path]

    if not image_paths:
        return {'error': '画像変換失敗'}

    if doc_type == 'contract':
        json_schema = '{"title": "契約書名・契約の種類", "counterparty": "相手方会社名", "start_date": "YYYY-MM-DD形式", "end_date": "YYYY-MM-DD形式", "amount": "契約金額（数字のみ）", "summary": "契約内容の要約（200字以内）"}'
        image_prompt = f"以下の契約書画像から情報を抽出してJSONで返してください。\n{json_schema}"
        text_prompt_template = f"以下の契約書OCRテキストから情報を抽出してJSONで返してください。\n{json_schema}\nOCRテキスト:\n{{OCR_TEXT}}"
    elif doc_type == 'shaken':
        json_schema = '{"shaken_number": "車検証番号・登録番号", "expiry_date": "車検有効期限 YYYY-MM-DD形式", "vehicle_number": "車両番号", "vin": "車台番号", "owner_name": "所有者名", "user_name": "使用者名", "vehicle_type": "車種・型式", "year": "初年度登録年（数字のみ）", "summary": "車検証の要約（100字以内）"}'
        image_prompt = f"以下の車検証画像から情報を抽出してJSONで返してください。\n{json_schema}"
        text_prompt_template = f"以下の車検証OCRテキストから情報を抽出してJSONで返してください。\n{json_schema}\nOCRテキスト:\n{{OCR_TEXT}}"
    elif doc_type == 'insurance_doc':
        json_schema = '{"insurer": "保険会社名", "policy_number": "証券番号", "insurance_type": "保険種類（自賞責/任意/貨物/その他）", "start_date": "YYYY-MM-DD形式", "end_date": "YYYY-MM-DD形式", "premium": "保険料（数字のみ）", "vehicle_number": "車両番号", "summary": "保険内容の要約（200字以内）"}'
        image_prompt = f"以下の保険証画像から情報を抽出してJSONで返してください。\n{json_schema}"
        text_prompt_template = f"以下の保険証OCRテキストから情報を抽出してJSONで返してください。\n{json_schema}\nOCRテキスト:\n{{OCR_TEXT}}"
    else:
        json_schema = '{"insurer": "保険会社名", "policy_number": "証券番号", "insurance_type": "保険種類（自賞責/任意/貨物/その他）", "start_date": "YYYY-MM-DD形式", "end_date": "YYYY-MM-DD形式", "premium": "保険料（数字のみ）", "coverage_amount": "保険金額（数字のみ）", "summary": "保険内容の要約（200字以内）"}'
        image_prompt = f"以下の保険証券画像から情報を抽出してJSONで返してください。\n{json_schema}"
        text_prompt_template = f"以下の保険証券OCRテキストから情報を抽出してJSONで返してください。\n{json_schema}\nOCRテキスト:\n{{OCR_TEXT}}"

    # 方式1: Google Vision API（OCR）+ GPT-4o（構造化）: 最高精度
    if google_vision_key and api_key:
        try:
            from app.utils.voucher.ocr import extract_text_with_google_vision_api_key
            ocr_text = ''
            for p in image_paths:
                ocr_text += extract_text_with_google_vision_api_key(p, google_vision_key) + '\n'
            if ocr_text.strip():
                prompt_text = text_prompt_template.replace('{OCR_TEXT}', ocr_text)
                headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
                payload = {
                    'model': 'gpt-4o',
                    'messages': [
                        {'role': 'system', 'content': 'あなたは日本語文書のOCR専門家です。必ずJSON形式のみで返してください。'},
                        {'role': 'user', 'content': prompt_text}
                    ],
                    'max_tokens': 2000,
                    'response_format': {'type': 'json_object'}
                }
                resp = _req.post('https://api.openai.com/v1/chat/completions', headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                return json.loads(resp.json()['choices'][0]['message']['content'])
        except Exception as e:
            print(f'[TruckOCR] Google Vision + GPT-4oエラー: {e}、GPT-4o Visionにフォールバック')

    # 方式2: GPT-4o Vision単体
    if not api_key:
        return {'error': 'APIキーが設定されていません'}
    content = [{'type': 'text', 'text': image_prompt}]
    for p in image_paths:
        img_data = encode_image(p)
        content.append({'type': 'image_url', 'image_url': {
            'url': f'data:image/jpeg;base64,{img_data}',
            'detail': 'high'
        }})
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'gpt-4o',
        'messages': [
            {'role': 'system', 'content': 'あなたは日本語文書のOCR専門家です。必ずJSON形式のみで返してください。'},
            {'role': 'user', 'content': content}
        ],
        'max_tokens': 2000,
        'response_format': {'type': 'json_object'}
    }
    resp = _req.post('https://api.openai.com/v1/chat/completions', headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return json.loads(resp.json()['choices'][0]['message']['content'])


## ─── OCRプレビュー（AJAX: フォーム上でファイルをアップロードしてOCR結果を返す）──────
@bp.route('/ocr/preview', methods=['POST'])
@login_required_truck
def ocr_preview():
    """フォーム上でAI読み取りボタンを押したときにOCR結果をJSONで返すAJAXエンドポイント"""
    import tempfile
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        doc_type = request.form.get('doc_type', 'contract')  # 'contract' or 'insurance'
        file = request.files.get('file')
        if not file or file.filename == '':
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.pdf', '.jpg', '.jpeg', '.png']:
            return jsonify({'error': 'PDF・JPG・PNGのみ対応しています'}), 400
        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        try:
            _ocr_keys = _get_truck_api_keys(db, tenant_id)
            api_key = _ocr_keys.get('openai_api_key')
            google_vision_key = _ocr_keys.get('google_vision_api_key')
            if not api_key:
                return jsonify({'error': 'APIキーが設定されていません。システム設定 > APIキー設定 で登録してください。'}), 400
            result = _run_truck_ocr(tmp_path, api_key, doc_type, google_vision_key=google_vision_key)
            return jsonify({'success': True, 'data': result})
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception as e:
        return jsonify({'error': f'読み取りエラー: {str(e)[:100]}'}), 500
    finally:
        db.close()

# ─── # ─── APIキー設定 ──────────────────────────────────────
@bp.route('/settings/api', methods=['GET', 'POST'])
@login_required_truck
def api_settings():
    """AIサービスAPIキー設定（アプリ固有・最優先）"""
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        if request.method == 'POST':
            openai_key = request.form.get('openai_api_key', '').strip()
            google_vision_key = request.form.get('google_vision_api_key', '').strip()
            if openai_key:
                TruckAppSettings.set(db, 'openai_api_key', openai_key, tenant_id=tenant_id)
            if google_vision_key:
                TruckAppSettings.set(db, 'google_vision_api_key', google_vision_key, tenant_id=tenant_id)
            flash('APIキーを保存しました', 'success')
            return redirect(url_for('truck.api_settings'))
        app_openai_key = TruckAppSettings.get(db, 'openai_api_key', tenant_id=tenant_id)
        app_google_vision_key = TruckAppSettings.get(db, 'google_vision_api_key', tenant_id=tenant_id)
        return render_template('truck/api_settings.html',
                               app_openai_key=app_openai_key,
                               app_google_vision_key=app_google_vision_key)
    finally:
        db.close()


# ─── APK設定 ──────────────────────────────────────

@bp.route('/settings/apk', methods=['GET', 'POST'])
@login_required_truck
def apk_settings():
    db = SessionLocal()
    try:
        # APK設定はテナント共通（tenant_id=None）
        if request.method == 'POST':
            apk_url = request.form.get('apk_url', '').strip()
            apk_version = request.form.get('apk_version', '').strip()
            gps_interval_raw = request.form.get('gps_interval_seconds', '30').strip()
            try:
                gps_interval_sec = max(1, int(gps_interval_raw))
            except (ValueError, TypeError):
                gps_interval_sec = 30
            TruckAppSettings.set(db, 'android_apk_url', apk_url, None)
            TruckAppSettings.set(db, 'android_apk_version', apk_version, None)
            TruckAppSettings.set(db, 'gps_interval_seconds', str(gps_interval_sec), None)
            flash('APK設定を保存しました', 'success')
            return redirect(url_for('truck.apk_settings'))
        apk_url = TruckAppSettings.get(db, 'android_apk_url', None, '')
        apk_version = TruckAppSettings.get(db, 'android_apk_version', None, '')
        gps_interval_seconds = int(TruckAppSettings.get(db, 'gps_interval_seconds', None, '30') or '30')
        return render_template('truck/apk_settings.html', apk_url=apk_url, apk_version=apk_version, gps_interval_seconds=gps_interval_seconds)
    finally:
        db.close()


# ─── モバイルAPI（ドライバーアプリ向け）────────────────────

@bp.route('/api/mobile/auth/login', methods=['POST'])
def mobile_login():
    data = request.get_json(silent=True) or {}
    login_id = data.get('login_id', '').strip()
    password = data.get('password', '')
    tenant_slug = data.get('tenant_slug', '').strip()
    db = SessionLocal()
    try:
        # tenant_slugからtenant_idを解決（見つからなければ全テナントから検索）
        tenant_id = None
        if tenant_slug:
            from app.models_login import TTenant
            tenant = db.query(TTenant).filter_by(slug=tenant_slug).first()
            if tenant:
                tenant_id = tenant.id
        q = db.query(TruckDriver).filter_by(login_id=login_id, active=True)
        if tenant_id is not None:
            q = q.filter_by(tenant_id=tenant_id)
        driver = q.first()
        if driver and check_password_hash(driver.password_hash, password):
            secret = MOBILE_API_KEY
            payload = f"{driver.id}:driver:{tenant_id or 'local'}"
            sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            token = f"{driver.id}:{sig}"
            gps_interval_seconds = int(TruckAppSettings.get(db, 'gps_interval_seconds', driver.tenant_id, '30') or '30')
            return jsonify({
                'ok': True,
                'staff_id': driver.id,
                'staff_type': 'driver',
                'tenant_id': driver.tenant_id,
                'name': driver.name,
                'staff_token': token,
                'gps_interval_seconds': gps_interval_seconds,
                # 後方互換
                'driver_id': driver.id,
                'token': token,
            })
        return jsonify({'ok': False, 'error': 'ログインIDまたはパスワードが正しくありません'}), 401
    finally:
        db.close()


@bp.route('/api/mobile/config', methods=['GET'])
def mobile_config():
    """モバイルアプリ向け設定取得API（GPS間隔など）"""
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    # X-Staff-Tokenからtenant_idを取得
    staff_token = request.headers.get('X-Staff-Token', '')
    tenant_id = None
    if staff_token and ':' in staff_token:
        try:
            driver_id_str = staff_token.split(':')[0]
            db_tmp = SessionLocal()
            try:
                d = db_tmp.query(TruckDriver).filter_by(id=int(driver_id_str), active=True).first()
                if d:
                    tenant_id = d.tenant_id
            finally:
                db_tmp.close()
        except Exception:
            pass
    db = SessionLocal()
    try:
        gps_interval_seconds = int(TruckAppSettings.get(db, 'gps_interval_seconds', tenant_id, '30') or '30')
        return jsonify({
            'ok': True,
            'gps_interval_seconds': gps_interval_seconds,
        })
    finally:
        db.close()


@bp.route('/api/mobile/trucks', methods=['GET'])
def mobile_trucks():
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    # X-Staff-Tokenからdriver_idとtenant_idを取得
    staff_token = request.headers.get('X-Staff-Token', '')
    tenant_id = None
    if staff_token and ':' in staff_token:
        try:
            driver_id_str = staff_token.split(':')[0]
            db_tmp = SessionLocal()
            try:
                d = db_tmp.query(TruckDriver).filter_by(id=int(driver_id_str), active=True).first()
                if d:
                    tenant_id = d.tenant_id
            finally:
                db_tmp.close()
        except Exception:
            pass
    db = SessionLocal()
    try:
        q = db.query(Truck).filter_by(active=True)
        if tenant_id:
            q = q.filter_by(tenant_id=tenant_id)
        trucks_list = q.all()
        trucks_data = [{
            'id': t.id,
            'truck_number': t.number,
            'truck_name': t.name,
            'capacity': str(t.capacity) if t.capacity else None,
            'status': 'available',
        } for t in trucks_list]
        return jsonify({'ok': True, 'trucks': trucks_data})
    finally:
        db.close()


@bp.route('/api/mobile/routes', methods=['GET'])
def mobile_routes():
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    # X-Staff-Tokenからtenant_idを取得
    staff_token = request.headers.get('X-Staff-Token', '')
    tenant_id = None
    if staff_token and ':' in staff_token:
        try:
            driver_id_str = staff_token.split(':')[0]
            db_tmp = SessionLocal()
            try:
                d = db_tmp.query(TruckDriver).filter_by(id=int(driver_id_str), active=True).first()
                if d:
                    tenant_id = d.tenant_id
            finally:
                db_tmp.close()
        except Exception:
            pass
    db = SessionLocal()
    try:
        q = db.query(TruckRoute).filter_by(active=True)
        if tenant_id:
            q = q.filter_by(tenant_id=tenant_id)
        routes_list = q.all()
        routes_data = [{
            'id': r.id,
            'route_name': r.name,
            'description': r.note,
            'estimated_minutes': None,
        } for r in routes_list]
        return jsonify({'ok': True, 'routes': routes_data})
    finally:
        db.close()


@bp.route('/api/mobile/operation/start', methods=['POST'])
def mobile_operation_start():
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    data = request.get_json(silent=True) or {}
    # driver_idはX-Staff-Tokenから自動取得（アプリ側が送らない場合のフォールバック）
    driver_id = data.get('driver_id')
    if not driver_id:
        staff_token = request.headers.get('X-Staff-Token', '')
        if staff_token and ':' in staff_token:
            try:
                driver_id = int(staff_token.split(':')[0])
            except (ValueError, IndexError):
                pass
    truck_id = data.get('truck_id')
    route_id = data.get('route_id')
    if not driver_id or not truck_id:
        return jsonify({'ok': False, 'error': 'driver_idとtruck_idは必須です'}), 400
    db = SessionLocal()
    try:
        # ドライバーのtenant_idを自動取得
        driver = db.query(TruckDriver).get(driver_id)
        tenant_id = driver.tenant_id if driver else None
        op = TruckOperation(
            driver_id=driver_id,
            truck_id=truck_id,
            route_id=route_id,
            status='driving',
            start_time=datetime.now(),
            operation_date=date.today(),
            tenant_id=tenant_id,
        )
        db.add(op)
        db.commit()
        return jsonify({'ok': True, 'operation_id': op.id})
    finally:
        db.close()
@bp.route('/api/mobile/operation/today', methods=['GET'])
def mobile_operation_today():
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    # X-Staff-Tokenからdriver_idを取得
    driver_id = None
    staff_token = request.headers.get('X-Staff-Token', '')
    if staff_token and ':' in staff_token:
        try:
            driver_id = int(staff_token.split(':')[0])
        except (ValueError, IndexError):
            pass
    if not driver_id:
        return jsonify({'ok': False, 'error': '認証情報がありません'}), 401
    db = SessionLocal()
    try:
        today = date.today()
        op = db.query(TruckOperation).filter(
            TruckOperation.driver_id == driver_id,
            TruckOperation.operation_date == today,
            TruckOperation.status != 'finished',
            ~TruckOperation.status.in_([
                'office_working', 'office_break', 'office_finished'
            ])
        ).order_by(TruckOperation.id.desc()).first()
        if not op:
            return jsonify({'ok': True, 'operation': None})
        truck = db.query(Truck).get(op.truck_id) if op.truck_id else None
        route = db.query(TruckRoute).get(op.route_id) if op.route_id else None
        return jsonify({'ok': True, 'operation': {
            'id': op.id,
            'driver_id': op.driver_id,
            'truck_id': op.truck_id,
            'route_id': op.route_id,
            'status': op.status,
            'start_time': op.start_time.isoformat() if op.start_time else None,
            'end_time': op.end_time.isoformat() if op.end_time else None,
            'operation_date': op.operation_date.isoformat() if op.operation_date else None,
            'truck_number': truck.number if truck else None,
            'truck_name': truck.name if truck else None,
            'route_name': route.name if route else None,
        }})
    finally:
        db.close()


@bp.route('/api/mobile/operation/status', methods=['POST'])
def mobile_operation_status():
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    data = request.get_json(silent=True) or {}
    operation_id = data.get('operation_id')
    status = data.get('status')
    if not operation_id or not status:
        return jsonify({'ok': False, 'error': 'operation_idとstatusは必須です'}), 400
    db = SessionLocal()
    try:
        op = db.query(TruckOperation).get(operation_id)
        if not op:
            return jsonify({'ok': False, 'error': '運行記録が見つかりません'}), 404
        op.status = status
        now = datetime.now()
        if status == 'finished':
            op.end_time = now
        elif status == 'loading':
            op.loading_start_time = now
        elif status == 'unloading':
            op.unloading_start_time = now
        elif status == 'break':
            op.break_start_time = now
        elif status == 'driving' and op.status == 'break':
            # 休憩終了（breakからdrivingに戻る時）
            op.break_end_time = now
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@bp.route('/api/mobile/location/record', methods=['POST'])
def mobile_location_record():
    """GPS位置情報をT_トラック運行位置履歴に記録
    JSONボディ: { latitude, longitude, accuracy, operation_id, is_background, recorded_at }
    """
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    data = request.get_json(silent=True) or {}
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    if latitude is None or longitude is None:
        return jsonify({'ok': False, 'error': 'latitude と longitude は必須です'}), 400
    operation_id = data.get('operation_id')
    accuracy = data.get('accuracy')
    speed = data.get('speed')  # km/h
    recorded_at_str = data.get('recorded_at')
    if recorded_at_str:
        try:
            recorded_at = datetime.strptime(recorded_at_str[:19], '%Y-%m-%dT%H:%M:%S')
        except Exception:
            recorded_at = datetime.now()
    else:
        recorded_at = datetime.now()
    # ドライバー情報をX-Staff-Tokenから取得、またはoperation_idから取得
    staff_token = request.headers.get('X-Staff-Token', '')
    db = SessionLocal()
    try:
        driver_id = None
        tenant_id = None
        if operation_id:
            op = db.query(TruckOperation).get(int(operation_id))
            if op:
                driver_id = op.driver_id
                tenant_id = op.tenant_id
        db.execute(text("""
            INSERT INTO "T_トラック運行位置履歴"
                (operation_id, driver_id, tenant_id, latitude, longitude, accuracy, speed, recorded_at)
            VALUES
                (:operation_id, :driver_id, :tenant_id, :latitude, :longitude, :accuracy, :speed, :recorded_at)
        """), {
            'operation_id': int(operation_id) if operation_id else None,
            'driver_id': driver_id,
            'tenant_id': tenant_id,
            'latitude': float(latitude),
            'longitude': float(longitude),
            'accuracy': float(accuracy) if accuracy is not None else None,
            'speed': float(speed) if speed is not None else None,
            'recorded_at': recorded_at,
        })
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


# ─── ドライバーマイページ ──────────────────────────────────

@bp.route('/api/mobile/location/count', methods=['GET'])
def mobile_location_count():
    """運行開始時間以降のGPS送信件数を返す
    クエリパラメータ: operation_id (必須)
    """
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    operation_id = request.args.get('operation_id')
    if not operation_id:
        return jsonify({'ok': False, 'error': 'operation_id は必須です'}), 400
    db = SessionLocal()
    try:
        op = db.query(TruckOperation).get(int(operation_id))
        if not op:
            return jsonify({'ok': False, 'error': '運行が見つかりません'}), 404
        # 運行開始時間以降の送信件数をカウント
        start_time = op.start_time
        result = db.execute(text("""
            SELECT COUNT(*) as cnt
            FROM "T_トラック運行位置履歴"
            WHERE operation_id = :operation_id
              AND recorded_at >= :start_time
        """), {'operation_id': int(operation_id), 'start_time': start_time})
        row = result.fetchone()
        count = row[0] if row else 0
        return jsonify({'ok': True, 'count': count, 'operation_id': int(operation_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()

@bp.route('/api/mobile/photo/upload', methods=['POST'])
def mobile_photo_upload():
    """運行写真アップロードAPI
    multipart/form-data: file=<画像>, operation_id=<int>, comment=<str>
    """
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401

    operation_id = request.form.get('operation_id')
    comment = request.form.get('comment', '').strip()
    file = request.files.get('file')

    if not operation_id:
        return jsonify({'ok': False, 'error': 'operation_id は必須です'}), 400
    if not file:
        return jsonify({'ok': False, 'error': '画像ファイルは必須です'}), 400

    # 保存先ディレクトリ
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              'static', 'uploads', 'operation_photos')
    os.makedirs(upload_dir, exist_ok=True)

    # ファイル名をUUIDで生成
    ext = os.path.splitext(secure_filename(file.filename))[1].lower() or '.jpg'
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(upload_dir, filename)
    file.save(save_path)

    # 相対URLパス
    photo_url = f"/truck/static/operation_photos/{filename}"

    # DBに記録
    db = SessionLocal()
    try:
        op = db.query(TruckOperation).get(int(operation_id))
        tenant_id = op.tenant_id if op else None
        driver_id = op.driver_id if op else None
        db.execute(text("""
            INSERT INTO truck_operation_photos
                (operation_id, driver_id, tenant_id, photo_path, comment, taken_at)
            VALUES
                (:operation_id, :driver_id, :tenant_id, :photo_path, :comment, :taken_at)
        """), {
            'operation_id': int(operation_id),
            'driver_id': driver_id,
            'tenant_id': tenant_id,
            'photo_path': photo_url,
            'comment': comment if comment else None,
            'taken_at': datetime.now(),
        })
        db.commit()
        return jsonify({'ok': True, 'photo_url': photo_url})
    except Exception as e:
        db.rollback()
        # DBエラー時はファイルも削除
        try:
            os.remove(save_path)
        except Exception:
            pass
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/api/mobile/photo/list', methods=['GET'])
def mobile_photo_list():
    """運行写真一覧取得API
    クエリパラメータ: operation_id (必須)
    """
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401

    operation_id = request.args.get('operation_id')
    if not operation_id:
        return jsonify({'ok': False, 'error': 'operation_id は必須です'}), 400

    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT id, photo_path, comment, taken_at
            FROM truck_operation_photos
            WHERE operation_id = :operation_id
            ORDER BY taken_at ASC
        """), {'operation_id': int(operation_id)}).fetchall()
        photos = []
        for row in rows:
            photos.append({
                'id': row[0],
                'photo_url': row[1],
                'comment': row[2],
                'taken_at': row[3].isoformat() if row[3] else None,
            })
        return jsonify({'ok': True, 'photos': photos})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/api/mobile/operation/history', methods=['GET'])
def mobile_operation_history():
    """運行履歴取得API
    クエリパラメータ: year, month
    """
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    driver_id = None
    staff_token = request.headers.get('X-Staff-Token', '')
    if staff_token and ':' in staff_token:
        try:
            driver_id = int(staff_token.split(':')[0])
        except (ValueError, IndexError):
            pass
    if not driver_id:
        return jsonify({'ok': False, 'error': '認証情報がありません'}), 401
    today = date.today()
    try:
        year = int(request.args.get('year', today.year))
        month = int(request.args.get('month', today.month))
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
    except Exception:
        start_date = date(today.year, today.month, 1)
        end_date = today
    db = SessionLocal()
    try:
        ops = db.query(TruckOperation).filter(
            TruckOperation.driver_id == driver_id,
            TruckOperation.operation_date >= start_date,
            TruckOperation.operation_date < end_date,
            ~TruckOperation.status.in_([
                'office_working', 'office_break', 'office_finished'
            ])
        ).order_by(TruckOperation.operation_date.desc(), TruckOperation.start_time.desc()).all()
        result = []
        for op in ops:
            truck = db.query(Truck).get(op.truck_id) if op.truck_id else None
            route = db.query(TruckRoute).get(op.route_id) if op.route_id else None
            result.append({
                'id': op.id,
                'driver_id': op.driver_id,
                'truck_id': op.truck_id,
                'route_id': op.route_id,
                'status': op.status,
                'operation_date': op.operation_date.isoformat() if op.operation_date else None,
                'start_time': op.start_time.isoformat() if op.start_time else None,
                'end_time': op.end_time.isoformat() if op.end_time else None,
                'truck_number': truck.number if truck else None,
                'truck_name': truck.name if truck else None,
                'route_name': route.name if route else None,
            })
        return jsonify({'ok': True, 'operations': result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/static/operation_photos/<path:filename>')
def serve_operation_photo(filename):
    """運行写真の静的ファイル配信"""
    from flask import send_from_directory
    photo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'static', 'uploads', 'operation_photos')
    return send_from_directory(photo_dir, filename)


@bp.route('/driver/login', methods=['GET', 'POST'])
def driver_login():
    error = None
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        password = request.form.get('password', '')
        db = SessionLocal()
        try:
            driver = db.query(TruckDriver).filter_by(login_id=login_id, active=True).first()
            if driver and check_password_hash(driver.password_hash, password):
                session['truck_driver_id'] = driver.id
                session['truck_driver_name'] = driver.name
                return redirect(url_for('truck.driver_dashboard'))
            else:
                error = 'ログインIDまたはパスワードが正しくありません'
        finally:
            db.close()
    return render_template('truck/driver_login.html', error=error)


@bp.route('/driver/logout')
def driver_logout():
    session.pop('truck_driver_id', None)
    session.pop('truck_driver_name', None)
    return redirect(url_for('truck.driver_login'))


@bp.route('/driver/dashboard')
@driver_login_required
def driver_dashboard():
    driver_id = session['truck_driver_id']
    db = SessionLocal()
    try:
        driver = db.query(TruckDriver).get(driver_id)
        today = date.today()
        today_str = today.strftime('%Y年%m月%d日')
        operations = db.query(TruckOperation).filter(
            TruckOperation.driver_id == driver_id,
            TruckOperation.operation_date == today,
            ~TruckOperation.status.in_([
                'office_working', 'office_break', 'office_finished'
            ])
        ).order_by(TruckOperation.start_time).all()
        # /truck/settings/apkで設定したTruckAppSettingsのandroid_apk_urlを使用
        # APK設定はテナント共通（tenant_id=None）
        apk_url = TruckAppSettings.get(db, 'android_apk_url', None, '')
        apk_version = TruckAppSettings.get(db, 'android_apk_version', None, '')
        return render_template(
            'truck/driver_dashboard.html',
            driver=driver,
            today_str=today_str,
            operations=operations,
            apk_url=apk_url,
            apk_version=apk_version,
        )
    finally:
        db.close()


@bp.route('/driver/history')
@driver_login_required
def driver_history():
    driver_id = session['truck_driver_id']
    db = SessionLocal()
    try:
        today = date.today()
        try:
            hist_year = int(request.args.get('hist_year', today.year))
            hist_month = int(request.args.get('hist_month', today.month))
        except (ValueError, TypeError):
            hist_year = today.year
            hist_month = today.month
        hist_start = date(hist_year, hist_month, 1)
        hist_end = date(hist_year + 1, 1, 1) if hist_month == 12 else date(hist_year, hist_month + 1, 1)
        history_ops = db.query(TruckOperation).filter(
            TruckOperation.driver_id == driver_id,
            TruckOperation.operation_date >= hist_start,
            TruckOperation.operation_date < hist_end,
            ~TruckOperation.status.in_([
                'office_working', 'office_break', 'office_finished'
            ])
        ).order_by(TruckOperation.operation_date.desc(), TruckOperation.start_time.desc()).all()
        return render_template(
            'truck/driver_history.html',
            history_ops=history_ops,
            hist_year=hist_year,
            hist_month=hist_month,
        )
    finally:
        db.close()


@bp.route('/driver/apk_download')
@driver_login_required
def driver_apk_download():
    driver_id = session['truck_driver_id']
    db = SessionLocal()
    try:
        driver = db.query(TruckDriver).get(driver_id)
        # APK設定はテナント共通（tenant_id=None）
        apk_url = TruckAppSettings.get(db, 'android_apk_url', None, '')
        if not apk_url:
            return 'APKが設定されていません', 404
        resp = http_requests.get(apk_url, stream=True, timeout=30)
        def generate():
            for chunk in resp.iter_content(chunk_size=8192):
                yield chunk
        filename = 'truck-operation-app.apk'
        return Response(
            generate(),
            content_type='application/vnd.android.package-archive',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return f'ダウンロードエラー: {e}', 500
    finally:
        db.close()


# ─── ドライバー内勤モード ────────────────────────────────────────

@bp.route('/driver/office')
@driver_login_required
def driver_office():
    """ドライバー内勤モード画面（出勤・休憩・退勤）"""
    driver_id = session['truck_driver_id']
    db = SessionLocal()
    try:
        driver = db.query(TruckDriver).get(driver_id)
        today = date.today()
        today_str = today.strftime('%Y年%m月%d日')
        # 本日の内勤レコードを取得
        office_op = db.query(TruckOperation).filter_by(
            driver_id=driver_id,
            operation_date=today,
            operation_type='office',
        ).order_by(TruckOperation.id.desc()).first()
        return render_template(
            'truck/driver_office.html',
            driver=driver,
            today_str=today_str,
            office_op=office_op,
        )
    finally:
        db.close()


@bp.route('/driver/office/action', methods=['POST'])
@driver_login_required
def driver_office_action():
    """ドライバー内勤モードのアクション（出勤・休憩開始・休憩終了・退勤）"""
    driver_id = session['truck_driver_id']
    action = request.form.get('action')
    db = SessionLocal()
    try:
        today = date.today()
        now = datetime.now()
        office_op = db.query(TruckOperation).filter_by(
            driver_id=driver_id,
            operation_date=today,
            operation_type='office',
        ).order_by(TruckOperation.id.desc()).first()

        if action == 'checkin':
            # 出勤：新規レコード作成
            # truck_idはNOT NULLなのでそのドライバーのテナントの最初のトラックを使用、なけれ〇1
            from app.models_truck import Truck as TruckModel
            driver = db.query(TruckDriver).get(driver_id)
            truck = db.query(TruckModel).filter_by(
                tenant_id=driver.tenant_id, active=True
            ).first() if driver else None
            truck_id = truck.id if truck else 1
            new_op = TruckOperation(
                driver_id=driver_id,
                truck_id=truck_id,
                route_id=None,
                status='office_working',
                operation_type='office',
                start_time=now,
                operation_date=today,
                tenant_id=driver.tenant_id if driver else None,
            )
            db.add(new_op)
            db.commit()

        elif action == 'break_start' and office_op:
            office_op.status = 'office_break'
            office_op.break_start_time = now
            db.commit()

        elif action == 'break_end' and office_op:
            office_op.status = 'office_working'
            office_op.break_end_time = now
            db.commit()

        elif action == 'checkout' and office_op:
            office_op.status = 'office_finished'
            office_op.end_time = now
            db.commit()

        return redirect(url_for('truck.driver_office'))
    finally:
        db.close()


# ─── 内勤スタッフ（TruckAdmin）マイページ ────────────────────────────────────────

@bp.route('/office/login', methods=['GET', 'POST'])
def office_login():
    error = None
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        password = request.form.get('password', '')
        db = SessionLocal()
        try:
            from app.models_truck import TruckAdmin
            admin = db.query(TruckAdmin).filter_by(login_id=login_id, active=True).first()
            if admin and check_password_hash(admin.password_hash, password):
                session['truck_office_id'] = admin.id
                session['truck_office_name'] = admin.name
                session['truck_office_tenant_id'] = admin.tenant_id
                return redirect(url_for('truck.office_dashboard'))
            else:
                error = 'ログインIDまたはパスワードが正しくありません'
        finally:
            db.close()
    return render_template('truck/office_login.html', error=error)


@bp.route('/office/logout')
def office_logout():
    session.pop('truck_office_id', None)
    session.pop('truck_office_name', None)
    session.pop('truck_office_tenant_id', None)
    return redirect(url_for('truck.office_login'))


@bp.route('/office/dashboard')
@office_login_required
def office_dashboard():
    from app.models_truck import TruckAdmin
    admin_id = session['truck_office_id']
    tenant_id = session.get('truck_office_tenant_id')
    db = SessionLocal()
    try:
        admin = db.query(TruckAdmin).get(admin_id)
        today = date.today()
        today_str = today.strftime('%Y年%m月%d日')
        q = db.query(TruckOperation).filter_by(operation_date=today)
        if tenant_id:
            driver_ids = [d.id for d in db.query(TruckDriver).filter_by(tenant_id=tenant_id, active=True).all()]
            if driver_ids:
                q = q.filter(TruckOperation.driver_id.in_(driver_ids))
        operations = q.order_by(TruckOperation.start_time.desc()).all()
        status_counts = {}
        for op in operations:
            status_counts[op.status] = status_counts.get(op.status, 0) + 1
        return render_template(
            'truck/office_dashboard.html',
            admin=admin,
            today_str=today_str,
            operations=operations,
            status_counts=status_counts,
        )
    finally:
        db.close()


# ─── テナント集計 ────────────────────────────────────────
@bp.route("/tenant_summary")
@login_required_truck
def tenant_summary():
    """テナント集計ページ（テナント管理者・システム管理者用）"""
    from app.models_login import TTenpo, TTenant
    db = SessionLocal()
    try:
        user_role = session.get("user_role", "")
        tenant_id = session.get("tenant_id")
        today = date.today()
        today_str = today.strftime("%Y年%m月%d日")

        # 対象テナントの店舗一覧を取得
        sq = db.query(TTenpo)
        if tenant_id:
            sq = sq.filter(TTenpo.tenant_id == tenant_id)
        stores = sq.order_by(TTenpo.id).all()

        total_status_counts = {}
        total_trucks = 0
        total_drivers = 0
        store_summaries = []

        for store in stores:
            ops = db.query(TruckOperation).filter(
                TruckOperation.operation_date == today,
                TruckOperation.tenant_id == store.tenant_id,
            ).all()
            sc = {}
            for op in ops:
                sc[op.status] = sc.get(op.status, 0) + 1
                total_status_counts[op.status] = total_status_counts.get(op.status, 0) + 1
            t_count = db.query(Truck).filter(Truck.tenant_id == store.tenant_id, Truck.active == True).count()
            d_count = db.query(TruckDriver).filter(TruckDriver.tenant_id == store.tenant_id, TruckDriver.active == True).count()
            total_trucks += t_count
            total_drivers += d_count
            store_summaries.append({
                "store": store,
                "status_counts": sc,
                "truck_count": t_count,
                "driver_count": d_count,
            })

        return render_template(
            "truck/tenant_summary.html",
            today_str=today_str,
            store_summaries=store_summaries,
            total_status_counts=total_status_counts,
            total_trucks=total_trucks,
            total_drivers=total_drivers,
            error=None,
        )
    except Exception as e:
        return render_template("truck/tenant_summary.html",
                               today_str=date.today().strftime("%Y年%m月%d日"),
                               store_summaries=[], total_status_counts={},
                               total_trucks=0, total_drivers=0, error=str(e))
    finally:
        db.close()


# ─── 店舗別ダッシュボード ────────────────────────────────
@bp.route("/store/<int:store_id>/")
@login_required_truck
def store_dashboard(store_id):
    """店舗別ダッシュボード"""
    from app.models_login import TTenpo
    db = SessionLocal()
    try:
        tenant_id = session.get("tenant_id")
        today = date.today()
        today_str = today.strftime("%Y年%m月%d日")

        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        if not store:
            return render_template("truck/store_dashboard.html",
                                   store=None, today_str=today_str,
                                   operations=[], status_counts={},
                                   trucks=[], drivers=[], error="店舗が見つかりません")

        OFFICE_STATUSES = ['office_working', 'office_break', 'office_finished']
        ops = db.query(TruckOperation).filter(
            TruckOperation.operation_date == today,
            TruckOperation.tenant_id == store.tenant_id,
            ~TruckOperation.status.in_(OFFICE_STATUSES),
        ).order_by(TruckOperation.start_time).all()

        status_counts = {}
        ops_data = []
        for op in ops:
            status_counts[op.status] = status_counts.get(op.status, 0) + 1
            ops_data.append({
                "status": op.status,
                "driver_name": op.driver.name if op.driver else "-",
                "truck_name": op.truck.name if op.truck else "-",
                "truck_number": op.truck.number if op.truck else "-",
                "route_name": op.route.name if op.route else "-",
                "start_time": op.start_time,
                "end_time": op.end_time,
            })

        trucks = db.query(Truck).filter(Truck.tenant_id == store.tenant_id, Truck.active == True).all()
        drivers = db.query(TruckDriver).filter(TruckDriver.tenant_id == store.tenant_id, TruckDriver.active == True).all()

        return render_template(
            "truck/store_dashboard.html",
            store=store,
            today_str=today_str,
            operations=ops_data,
            status_counts=status_counts,
            trucks=trucks,
            drivers=drivers,
            error=None,
        )
    except Exception as e:
        return render_template("truck/store_dashboard.html",
                               store=None, today_str=date.today().strftime("%Y年%m月%d日"),
                               operations=[], status_counts={},
                               trucks=[], drivers=[], error=str(e))
    finally:
        db.close()

# ─── 財務管理 ──────────────────────────────────────
@bp.route('/finance/accounting')
@login_required_truck
def finance_accounting():
    return render_template('truck/finance_accounting.html')

@bp.route('/finance/payroll')
@login_required_truck
def finance_payroll():
    return render_template('truck/finance_payroll.html')

@bp.route('/finance/attendance')
@login_required_truck
def finance_attendance():
    return render_template('truck/finance_attendance.html')

# ─── 請求書管理 ──────────────────────────────────────
@bp.route('/finance/invoice')
@login_required_truck
def finance_invoice():
    db = SessionLocal()
    try:
        invoices = db.query(TruckInvoice).order_by(TruckInvoice.issue_date.desc()).all()
        return render_template('truck/finance_invoice.html', invoices=invoices)
    finally:
        db.close()


@bp.route('/finance/invoice/new', methods=['GET', 'POST'])
@login_required_truck
def finance_invoice_new():
    db = SessionLocal()
    try:
        clients = db.query(TruckClient).filter_by(active=True).order_by(TruckClient.name).all()
        if request.method == 'POST':
            mode = request.form.get('mode', 'manual')
            # 請求書番号の自動生成
            today = date.today()
            count = db.query(TruckInvoice).filter(
                TruckInvoice.issue_date >= date(today.year, today.month, 1)
            ).count()
            invoice_number = f"INV-{today.strftime('%Y%m')}-{count+1:03d}"

            client_id = request.form.get('client_id') or None
            if client_id:
                client_id = int(client_id)
                c = db.query(TruckClient).get(client_id)
                client_name = c.name if c else ''
                client_address = c.address if c else ''
            else:
                client_name = request.form.get('client_name', '')
                client_address = request.form.get('client_address', '')

            issue_date = datetime.strptime(request.form['issue_date'], '%Y-%m-%d').date()
            due_date_str = request.form.get('due_date')
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
            period_from_str = request.form.get('period_from')
            period_to_str = request.form.get('period_to')
            period_from = datetime.strptime(period_from_str, '%Y-%m-%d').date() if period_from_str else None
            period_to = datetime.strptime(period_to_str, '%Y-%m-%d').date() if period_to_str else None
            tax_rate = float(request.form.get('tax_rate', 0.10))
            note = request.form.get('note', '')

            invoice = TruckInvoice(
                invoice_number=invoice_number,
                client_id=client_id,
                client_name=client_name,
                client_address=client_address,
                issue_date=issue_date,
                due_date=due_date,
                period_from=period_from,
                period_to=period_to,
                tax_rate=tax_rate,
                note=note,
                status='draft',
            )
            db.add(invoice)
            db.flush()

            items = []
            if mode == 'auto' and period_from and period_to:
                # 運行履歴から自動集計
                ops = db.query(TruckOperation).filter(
                    TruckOperation.operation_date >= period_from,
                    TruckOperation.operation_date <= period_to,
                    TruckOperation.status == 'finished',
                ).order_by(TruckOperation.operation_date).all()
                if client_id:
                    ops = [o for o in ops if o.route and o.route.client_id == client_id]
                for op in ops:
                    route = op.route
                    unit_price = route.contract_amount if route and route.contract_amount else 0
                    desc = f"{op.operation_date.strftime('%m/%d')} {route.name if route else '運行'}"
                    item = TruckInvoiceItem(
                        invoice_id=invoice.id,
                        description=desc,
                        operation_date=op.operation_date,
                        route_name=route.name if route else '',
                        quantity=1,
                        unit_price=unit_price,
                        amount=unit_price,
                    )
                    db.add(item)
                    items.append(item)
            else:
                # 手動明細
                descriptions = request.form.getlist('item_description[]')
                quantities = request.form.getlist('item_quantity[]')
                unit_prices = request.form.getlist('item_unit_price[]')
                for i, desc in enumerate(descriptions):
                    if not desc.strip():
                        continue
                    qty = int(quantities[i]) if i < len(quantities) else 1
                    up = int(unit_prices[i]) if i < len(unit_prices) else 0
                    item = TruckInvoiceItem(
                        invoice_id=invoice.id,
                        description=desc,
                        quantity=qty,
                        unit_price=up,
                        amount=qty * up,
                    )
                    db.add(item)
                    items.append(item)

            # 合計計算
            subtotal = sum(int(it.amount) for it in items)
            tax_amount = int(subtotal * tax_rate)
            invoice.subtotal = subtotal
            invoice.tax_amount = tax_amount
            invoice.total_amount = subtotal + tax_amount
            db.commit()
            flash('請求書を作成しました', 'success')
            return redirect(url_for('truck.finance_invoice_detail', invoice_id=invoice.id))

        # GET
        today = date.today()
        default_period_from = date(today.year, today.month, 1)
        default_period_to = today
        return render_template('truck/finance_invoice_new.html',
                               clients=clients,
                               today=today,
                               default_period_from=default_period_from,
                               default_period_to=default_period_to)
    finally:
        db.close()


@bp.route('/finance/invoice/<int:invoice_id>')
@login_required_truck
def finance_invoice_detail(invoice_id):
    db = SessionLocal()
    try:
        invoice = db.query(TruckInvoice).get(invoice_id)
        if not invoice:
            flash('請求書が見つかりません', 'error')
            return redirect(url_for('truck.finance_invoice'))
        return render_template('truck/finance_invoice_detail.html', invoice=invoice)
    finally:
        db.close()


@bp.route('/finance/invoice/<int:invoice_id>/print')
@login_required_truck
def finance_invoice_print(invoice_id):
    db = SessionLocal()
    try:
        invoice = db.query(TruckInvoice).get(invoice_id)
        if not invoice:
            return '請求書が見つかりません', 404
        return render_template('truck/finance_invoice_print.html', invoice=invoice)
    finally:
        db.close()


@bp.route('/finance/invoice/<int:invoice_id>/status', methods=['POST'])
@login_required_truck
def finance_invoice_status(invoice_id):
    db = SessionLocal()
    try:
        invoice = db.query(TruckInvoice).get(invoice_id)
        if invoice:
            invoice.status = request.form.get('status', invoice.status)
            db.commit()
            flash('ステータスを更新しました', 'success')
        return redirect(url_for('truck.finance_invoice_detail', invoice_id=invoice_id))
    finally:
        db.close()


@bp.route('/finance/invoice/<int:invoice_id>/delete', methods=['POST'])
@login_required_truck
def finance_invoice_delete(invoice_id):
    db = SessionLocal()
    try:
        invoice = db.query(TruckInvoice).get(invoice_id)
        if invoice:
            db.delete(invoice)
            db.commit()
            flash('請求書を削除しました', 'success')
        return redirect(url_for('truck.finance_invoice'))
    finally:
        db.close()


# ─── 運行スケジュール ────────────────────────────────────

@bp.route('/schedule')
@login_required_truck
def schedule_list():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        today = date.today()
        selected_year = request.args.get('year', str(today.year))
        selected_month = request.args.get('month', str(today.month))

        try:
            year = int(selected_year)
            month = int(selected_month)
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1)
            else:
                end_date = date(year, month + 1, 1)
        except Exception:
            year = today.year
            month = today.month
            start_date = date(year, month, 1)
            end_date = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)

        q = db.query(TruckSchedule).filter(
            TruckSchedule.schedule_date >= start_date,
            TruckSchedule.schedule_date < end_date,
        )
        if tenant_id:
            from sqlalchemy import or_
            q = q.filter(or_(TruckSchedule.tenant_id == tenant_id, TruckSchedule.tenant_id == None))
        schedules = q.order_by(TruckSchedule.schedule_date, TruckSchedule.start_time).all()

        dq = db.query(TruckDriver).filter(TruckDriver.active == True)
        if tenant_id:
            dq = dq.filter(TruckDriver.tenant_id == tenant_id)
        drivers = dq.all()

        tq = db.query(Truck).filter(Truck.active == True)
        if tenant_id:
            tq = tq.filter(Truck.tenant_id == tenant_id)
        trucks = tq.all()

        rq = db.query(TruckRoute).filter(TruckRoute.active == True)
        if tenant_id:
            rq = rq.filter(TruckRoute.tenant_id == tenant_id)
        routes = rq.all()

        years = list(range(today.year - 1, today.year + 3))
        months = list(range(1, 13))

        return render_template(
            'truck/schedule_list.html',
            schedules=schedules,
            drivers=drivers,
            trucks=trucks,
            routes=routes,
            years=years,
            months=months,
            selected_year=year,
            selected_month=month,
            error=None,
        )
    except Exception as e:
        return render_template('truck/schedule_list.html',
                               schedules=[], drivers=[], trucks=[], routes=[],
                               years=[], months=list(range(1, 13)),
                               selected_year=date.today().year, selected_month=date.today().month,
                               error=str(e))
    finally:
        db.close()


@bp.route('/schedule/new', methods=['GET', 'POST'])
@login_required_truck
def schedule_new():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')

        dq = db.query(TruckDriver).filter(TruckDriver.active == True)
        if tenant_id:
            dq = dq.filter(TruckDriver.tenant_id == tenant_id)
        drivers = dq.all()

        tq = db.query(Truck).filter(Truck.active == True)
        if tenant_id:
            tq = tq.filter(Truck.tenant_id == tenant_id)
        trucks = tq.all()

        rq = db.query(TruckRoute).filter(TruckRoute.active == True)
        if tenant_id:
            rq = rq.filter(TruckRoute.tenant_id == tenant_id)
        routes = rq.all()

        if request.method == 'POST':
            schedule_date_str = request.form.get('schedule_date', '')
            driver_id = request.form.get('driver_id') or None
            truck_id = request.form.get('truck_id') or None
            route_id = request.form.get('route_id') or None
            start_time = request.form.get('start_time', '').strip() or None
            end_time = request.form.get('end_time', '').strip() or None
            note = request.form.get('note', '').strip() or None

            try:
                schedule_date = date.fromisoformat(schedule_date_str)
            except Exception:
                flash('日付の形式が正しくありません', 'error')
                return render_template('truck/schedule_form.html',
                                       schedule=None, drivers=drivers, trucks=trucks, routes=routes,
                                       action_url=url_for('truck.schedule_new'), form_title='スケジュール新規登録')

            sched = TruckSchedule(
                schedule_date=schedule_date,
                driver_id=int(driver_id) if driver_id else None,
                truck_id=int(truck_id) if truck_id else None,
                route_id=int(route_id) if route_id else None,
                start_time=start_time,
                end_time=end_time,
                note=note,
                tenant_id=tenant_id,
            )
            db.add(sched)
            db.commit()
            flash('スケジュールを登録しました', 'success')
            return redirect(url_for('truck.schedule_list',
                                    year=schedule_date.year, month=schedule_date.month))

        return render_template('truck/schedule_form.html',
                               schedule=None, drivers=drivers, trucks=trucks, routes=routes,
                               action_url=url_for('truck.schedule_new'), form_title='スケジュール新規登録')
    finally:
        db.close()


@bp.route('/schedule/<int:schedule_id>/edit', methods=['GET', 'POST'])
@login_required_truck
def schedule_edit(schedule_id):
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        sched = db.query(TruckSchedule).get(schedule_id)
        if not sched:
            flash('スケジュールが見つかりません', 'error')
            return redirect(url_for('truck.schedule_list'))

        dq = db.query(TruckDriver).filter(TruckDriver.active == True)
        if tenant_id:
            dq = dq.filter(TruckDriver.tenant_id == tenant_id)
        drivers = dq.all()

        tq = db.query(Truck).filter(Truck.active == True)
        if tenant_id:
            tq = tq.filter(Truck.tenant_id == tenant_id)
        trucks = tq.all()

        rq = db.query(TruckRoute).filter(TruckRoute.active == True)
        if tenant_id:
            rq = rq.filter(TruckRoute.tenant_id == tenant_id)
        routes = rq.all()

        if request.method == 'POST':
            schedule_date_str = request.form.get('schedule_date', '')
            try:
                sched.schedule_date = date.fromisoformat(schedule_date_str)
            except Exception:
                flash('日付の形式が正しくありません', 'error')
                return render_template('truck/schedule_form.html',
                                       schedule=sched, drivers=drivers, trucks=trucks, routes=routes,
                                       action_url=url_for('truck.schedule_edit', schedule_id=schedule_id),
                                       form_title='スケジュール編集')
            sched.driver_id = int(request.form.get('driver_id')) if request.form.get('driver_id') else None
            sched.truck_id = int(request.form.get('truck_id')) if request.form.get('truck_id') else None
            sched.route_id = int(request.form.get('route_id')) if request.form.get('route_id') else None
            sched.start_time = request.form.get('start_time', '').strip() or None
            sched.end_time = request.form.get('end_time', '').strip() or None
            sched.note = request.form.get('note', '').strip() or None
            db.commit()
            flash('スケジュールを更新しました', 'success')
            return redirect(url_for('truck.schedule_list',
                                    year=sched.schedule_date.year, month=sched.schedule_date.month))

        return render_template('truck/schedule_form.html',
                               schedule=sched, drivers=drivers, trucks=trucks, routes=routes,
                               action_url=url_for('truck.schedule_edit', schedule_id=schedule_id),
                               form_title='スケジュール編集')
    finally:
        db.close()


@bp.route('/schedule/<int:schedule_id>/delete', methods=['POST'])
@login_required_truck
def schedule_delete(schedule_id):
    db = SessionLocal()
    try:
        sched = db.query(TruckSchedule).get(schedule_id)
        if sched:
            year = sched.schedule_date.year
            month = sched.schedule_date.month
            db.delete(sched)
            db.commit()
            flash('スケジュールを削除しました', 'success')
            return redirect(url_for('truck.schedule_list', year=year, month=month))
        flash('スケジュールが見つかりません', 'error')
        return redirect(url_for('truck.schedule_list'))
    finally:
        db.close()
