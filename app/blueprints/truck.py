# -*- coding: utf-8 -*-
"""
トラック運行管理システム blueprint
/truck/ 配下のすべてのルートを管理します。
"""
import hmac
import hashlib
import os
import requests as http_requests
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify, Response, stream_with_context
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

from app.db import SessionLocal
from app.models_truck import Truck, TruckRoute, TruckDriver, TruckOperation, TruckAppSettings
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
            return redirect(url_for('auth.login'))
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


# ─── テンプレートフィルター ──────────────────────────────
bp.add_app_template_global(format_status, 'truck_format_status')
bp.add_app_template_global(status_color, 'truck_status_color')
bp.add_app_template_global(calc_duration, 'truck_calc_duration')
bp.add_app_template_global(format_time, 'truck_format_time')


# ─── ダッシュボード ──────────────────────────────────────

@bp.route('/')
@login_required_truck
def dashboard():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        today = date.today()
        today_str = today.strftime("%Y年%m月%d日")

        q = db.query(TruckOperation).filter(TruckOperation.operation_date == today)
        if tenant_id:
            q = q.filter(TruckOperation.tenant_id == tenant_id)
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

        q = db.query(TruckOperation).filter(
            TruckOperation.operation_date >= start_date,
            TruckOperation.operation_date < end_date,
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
        q = db.query(Truck)
        if tenant_id:
            q = q.filter(Truck.tenant_id == tenant_id)
        trucks_list = q.order_by(Truck.created_at.desc()).all()
        return render_template('truck/trucks.html', trucks=trucks_list, error=None)
    except Exception as e:
        return render_template('truck/trucks.html', trucks=[], error=str(e))
    finally:
        db.close()


@bp.route('/trucks/new', methods=['GET', 'POST'])
@login_required_truck
def truck_new():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        if request.method == 'POST':
            number = request.form.get('number', '').strip()
            name = request.form.get('name', '').strip()
            capacity = request.form.get('capacity', '').strip()
            note = request.form.get('note', '').strip()
            if not number or not name:
                flash('車両番号と車両名称は必須です', 'error')
                return render_template('truck/truck_form.html', truck=None, action='new')
            truck = Truck(
                number=number,
                name=name,
                capacity=float(capacity) if capacity else None,
                note=note,
                tenant_id=tenant_id,
            )
            db.add(truck)
            db.commit()
            flash(f'トラック「{name}」を登録しました', 'success')
            return redirect(url_for('truck.trucks'))
        return render_template('truck/truck_form.html', truck=None, action='new')
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
        if request.method == 'POST':
            truck.number = request.form.get('number', '').strip()
            truck.name = request.form.get('name', '').strip()
            capacity = request.form.get('capacity', '').strip()
            truck.capacity = float(capacity) if capacity else None
            truck.note = request.form.get('note', '').strip()
            truck.active = request.form.get('active') == '1'
            if not truck.number or not truck.name:
                flash('車両番号と車両名称は必須です', 'error')
                return render_template('truck/truck_form.html', truck=truck, action='edit')
            db.commit()
            flash(f'トラック「{truck.name}」を更新しました', 'success')
            return redirect(url_for('truck.trucks'))
        return render_template('truck/truck_form.html', truck=truck, action='edit')
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
        q = db.query(TruckRoute)
        if tenant_id:
            q = q.filter(TruckRoute.tenant_id == tenant_id)
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
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            origin = request.form.get('origin', '').strip()
            destination = request.form.get('destination', '').strip()
            distance_km = request.form.get('distance_km', '').strip()
            note = request.form.get('note', '').strip()
            if not name:
                flash('ルート名は必須です', 'error')
                return render_template('truck/route_form.html', route=None, action='new')
            route = TruckRoute(
                name=name,
                origin=origin,
                destination=destination,
                distance_km=float(distance_km) if distance_km else None,
                note=note,
                tenant_id=tenant_id,
            )
            db.add(route)
            db.commit()
            flash(f'ルート「{name}」を登録しました', 'success')
            return redirect(url_for('truck.routes'))
        return render_template('truck/route_form.html', route=None, action='new')
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
        if request.method == 'POST':
            route.name = request.form.get('name', '').strip()
            route.origin = request.form.get('origin', '').strip()
            route.destination = request.form.get('destination', '').strip()
            distance_km = request.form.get('distance_km', '').strip()
            route.distance_km = float(distance_km) if distance_km else None
            route.note = request.form.get('note', '').strip()
            route.active = request.form.get('active') == '1'
            if not route.name:
                flash('ルート名は必須です', 'error')
                return render_template('truck/route_form.html', route=route, action='edit')
            db.commit()
            flash(f'ルート「{route.name}」を更新しました', 'success')
            return redirect(url_for('truck.routes'))
        return render_template('truck/route_form.html', route=route, action='edit')
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
        q = db.query(TruckDriver)
        if tenant_id:
            q = q.filter(TruckDriver.tenant_id == tenant_id)
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
            phone = request.form.get('phone', '').strip()
            license_number = request.form.get('license_number', '').strip()
            note = request.form.get('note', '').strip()
            if not login_id or not password or not name:
                flash('ログインID・パスワード・氏名は必須です', 'error')
                return render_template('truck/driver_form.html', driver=None, action='new')
            existing = db.query(TruckDriver).filter_by(login_id=login_id).first()
            if existing:
                flash('そのログインIDはすでに登録されています', 'error')
                return render_template('truck/driver_form.html', driver=None, action='new')
            driver = TruckDriver(
                login_id=login_id,
                password_hash=generate_password_hash(password),
                name=name,
                phone=phone,
                license_number=license_number,
                note=note,
                tenant_id=tenant_id,
            )
            db.add(driver)
            db.commit()
            flash(f'ドライバー「{name}」を登録しました', 'success')
            return redirect(url_for('truck.drivers'))
        return render_template('truck/driver_form.html', driver=None, action='new')
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
            if not driver.login_id or not driver.name:
                flash('ログインIDと氏名は必須です', 'error')
                return render_template('truck/driver_form.html', driver=driver, action='edit')
            db.commit()
            flash(f'ドライバー「{driver.name}」を更新しました', 'success')
            return redirect(url_for('truck.drivers'))
        return render_template('truck/driver_form.html', driver=driver, action='edit')
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

        # ドライバーのlogin_idからsamurai-hub DBのstaff_idを取得
        driver_login_ids = [d.login_id for d in drivers]
        driver_staff_map = {}
        if driver_login_ids:
            placeholders = ','.join([f"'{lid}'" for lid in driver_login_ids])
            try:
                rows = db.execute(text(f"""
                    SELECT id, login_id, name, tenant_id
                    FROM "T_従業員"
                    WHERE login_id IN ({placeholders}) AND active = 1
                """)).fetchall()
                for row in rows:
                    driver_staff_map[row[1]] = {'staff_id': row[0], 'name': row[2], 'tenant_id': row[3]}
            except Exception:
                pass

        driver_list = []
        for d in drivers:
            info = driver_staff_map.get(d.login_id)
            driver_list.append({
                'id': d.id,
                'name': d.name,
                'login_id': d.login_id,
                'staff_id': info['staff_id'] if info else None,
            })

        if driver_id_param:
            try:
                sel_id = int(driver_id_param)
                target_drivers = [dl for dl in driver_list if dl['id'] == sel_id]
            except ValueError:
                target_drivers = driver_list
        else:
            target_drivers = driver_list

        staff_ids = [dl['staff_id'] for dl in target_drivers if dl['staff_id'] is not None]
        staff_tracks = {}
        if staff_ids:
            ids_str = ','.join(str(sid) for sid in staff_ids)
            dt_start = datetime.combine(target_date, datetime.min.time())
            dt_end = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            try:
                locs = db.execute(text(f"""
                    SELECT staff_id, latitude, longitude, recorded_at
                    FROM "T_勤怠位置履歴"
                    WHERE staff_id IN ({ids_str})
                      AND recorded_at >= :dt_start
                      AND recorded_at < :dt_end
                    ORDER BY staff_id ASC, recorded_at ASC
                """), {'dt_start': dt_start, 'dt_end': dt_end}).fetchall()
                for loc in locs:
                    key = loc[0]
                    if key not in staff_tracks:
                        staff_tracks[key] = []
                    staff_tracks[key].append({
                        'lat': float(loc[1]),
                        'lng': float(loc[2]),
                        'time': loc[3].strftime('%H:%M:%S') if loc[3] else ''
                    })
            except Exception:
                pass

        tracks = []
        for dl in target_drivers:
            if dl['staff_id'] is None:
                continue
            pts = staff_tracks.get(dl['staff_id'], [])
            if not pts:
                continue
            tracks.append({
                'driver_id': dl['id'],
                'staff_id': dl['staff_id'],
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

        driver_login_ids = [d.login_id for d in drivers]
        driver_staff_map = {}
        if driver_login_ids:
            placeholders = ','.join([f"'{lid}'" for lid in driver_login_ids])
            try:
                rows = db.execute(text(f"""
                    SELECT id, login_id, name, tenant_id
                    FROM "T_従業員"
                    WHERE login_id IN ({placeholders}) AND active = 1
                """)).fetchall()
                for row in rows:
                    driver_staff_map[row[1]] = {'staff_id': row[0], 'name': row[2], 'tenant_id': row[3]}
            except Exception:
                pass

        driver_list = []
        for d in drivers:
            info = driver_staff_map.get(d.login_id)
            driver_list.append({
                'id': d.id,
                'name': d.name,
                'login_id': d.login_id,
                'staff_id': info['staff_id'] if info else None,
            })

        if driver_id_param:
            try:
                sel_id = int(driver_id_param)
                target_drivers = [dl for dl in driver_list if dl['id'] == sel_id]
            except ValueError:
                target_drivers = driver_list
        else:
            target_drivers = driver_list

        staff_ids = [dl['staff_id'] for dl in target_drivers if dl['staff_id'] is not None]
        staff_tracks = {}
        if staff_ids:
            ids_str = ','.join(str(sid) for sid in staff_ids)
            dt_start = datetime.combine(target_date, datetime.min.time())
            dt_end = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            try:
                locs = db.execute(text(f"""
                    SELECT staff_id, latitude, longitude, recorded_at
                    FROM "T_勤怠位置履歴"
                    WHERE staff_id IN ({ids_str})
                      AND recorded_at >= :dt_start
                      AND recorded_at < :dt_end
                    ORDER BY staff_id ASC, recorded_at ASC
                """), {'dt_start': dt_start, 'dt_end': dt_end}).fetchall()
                for loc in locs:
                    key = loc[0]
                    if key not in staff_tracks:
                        staff_tracks[key] = []
                    staff_tracks[key].append({
                        'lat': float(loc[1]),
                        'lng': float(loc[2]),
                        'time': loc[3].strftime('%H:%M:%S') if loc[3] else ''
                    })
            except Exception:
                pass

        tracks = []
        for dl in target_drivers:
            if dl['staff_id'] is None:
                continue
            pts = staff_tracks.get(dl['staff_id'], [])
            if not pts:
                continue
            tracks.append({
                'driver_id': dl['id'],
                'staff_id': dl['staff_id'],
                'staff_name': dl['name'],
                'points': pts,
            })

        return jsonify({'ok': True, 'tracks': tracks})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


# ─── APK設定 ─────────────────────────────────────────────

@bp.route('/settings/apk', methods=['GET', 'POST'])
@login_required_truck
def apk_settings():
    db = SessionLocal()
    try:
        tenant_id = session.get('tenant_id')
        if request.method == 'POST':
            apk_url = request.form.get('apk_url', '').strip()
            apk_version = request.form.get('apk_version', '').strip()
            TruckAppSettings.set(db, 'android_apk_url', apk_url, tenant_id)
            TruckAppSettings.set(db, 'android_apk_version', apk_version, tenant_id)
            flash('APK設定を保存しました', 'success')
            return redirect(url_for('truck.apk_settings'))
        apk_url = TruckAppSettings.get(db, 'android_apk_url', tenant_id, '')
        apk_version = TruckAppSettings.get(db, 'android_apk_version', tenant_id, '')
        return render_template('truck/apk_settings.html', apk_url=apk_url, apk_version=apk_version)
    finally:
        db.close()


# ─── モバイルAPI（ドライバーアプリ向け）────────────────────

@bp.route('/api/mobile/auth/login', methods=['POST'])
def mobile_login():
    data = request.get_json(silent=True) or {}
    login_id = data.get('login_id', '').strip()
    password = data.get('password', '')
    db = SessionLocal()
    try:
        driver = db.query(TruckDriver).filter_by(login_id=login_id, active=True).first()
        if driver and check_password_hash(driver.password_hash, password):
            secret = MOBILE_API_KEY
            payload = f"{driver.id}:driver:local"
            sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            token = f"{driver.id}:{sig}"
            return jsonify({
                'ok': True,
                'driver_id': driver.id,
                'name': driver.name,
                'token': token,
            })
        return jsonify({'ok': False, 'error': 'ログインIDまたはパスワードが正しくありません'}), 401
    finally:
        db.close()


@bp.route('/api/mobile/trucks', methods=['GET'])
def mobile_trucks():
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    db = SessionLocal()
    try:
        trucks_list = db.query(Truck).filter_by(active=True).all()
        return jsonify({'ok': True, 'trucks': [t.to_dict() for t in trucks_list]})
    finally:
        db.close()


@bp.route('/api/mobile/routes', methods=['GET'])
def mobile_routes():
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    db = SessionLocal()
    try:
        routes_list = db.query(TruckRoute).filter_by(active=True).all()
        return jsonify({'ok': True, 'routes': [r.to_dict() for r in routes_list]})
    finally:
        db.close()


@bp.route('/api/mobile/operation/start', methods=['POST'])
def mobile_operation_start():
    api_key = request.headers.get('X-Mobile-API-Key', '')
    if not hmac.compare_digest(api_key, MOBILE_API_KEY):
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    data = request.get_json(silent=True) or {}
    driver_id = data.get('driver_id')
    truck_id = data.get('truck_id')
    route_id = data.get('route_id')
    if not driver_id or not truck_id:
        return jsonify({'ok': False, 'error': 'driver_idとtruck_idは必須です'}), 400
    db = SessionLocal()
    try:
        op = TruckOperation(
            driver_id=driver_id,
            truck_id=truck_id,
            route_id=route_id,
            status='driving',
            start_time=datetime.now(),
            operation_date=date.today(),
        )
        db.add(op)
        db.commit()
        return jsonify({'ok': True, 'operation_id': op.id})
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
        if status == 'finished':
            op.end_time = datetime.now()
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


# ─── ドライバーマイページ ──────────────────────────────────

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
        operations = db.query(TruckOperation).filter_by(
            driver_id=driver_id,
            operation_date=today,
        ).order_by(TruckOperation.start_time).all()
        apk_url = TruckAppSettings.get(db, 'android_apk_url', driver.tenant_id if driver else None, '')
        apk_version = TruckAppSettings.get(db, 'android_apk_version', driver.tenant_id if driver else None, '')
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


@bp.route('/driver/apk_download')
@driver_login_required
def driver_apk_download():
    driver_id = session['truck_driver_id']
    db = SessionLocal()
    try:
        driver = db.query(TruckDriver).get(driver_id)
        apk_url = TruckAppSettings.get(db, 'android_apk_url', driver.tenant_id if driver else None, '')
        if not apk_url:
            return 'APKが設定されていません', 404
        resp = http_requests.get(apk_url, stream=True, timeout=30)
        def generate():
            for chunk in resp.iter_content(chunk_size=8192):
                yield chunk
        filename = 'truck-operation-app.apk'
        return Response(
            stream_with_context(generate()),
            content_type='application/vnd.android.package-archive',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return f'ダウンロードエラー: {e}', 500
    finally:
        db.close()
