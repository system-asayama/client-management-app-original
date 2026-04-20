# -*- coding: utf-8 -*-
"""
勤怠管理システム blueprint

スタッフの勤怠管理・GPS位置確認機能を提供します。
/kintaikanri/ 配下のすべてのルートを管理します。
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from sqlalchemy import and_
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')


def now_jst():
    """日本時間（JST）の現在時刻をタイムゾーンなしdatetimeで返す"""
    return datetime.now(JST).replace(tzinfo=None)


def today_jst():
    """日本時間（JST）の今日の日付を返す"""
    return datetime.now(JST).date()


from app.db import SessionLocal
from app.models_login import TKanrisha, TJugyoin, TTenant, TTenpo, TKanrishaTenpo, TJugyoinTenpo, TTenantAdminTenant, TAttendance, TAttendanceLocation
from app.models_clients import TMessage, TMessageRead
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('kintaikanri', __name__, url_prefix='/kintaikanri')


def _get_unread_count(tenant_id, user_name):
    """担当顧問先の未読チャット数を取得する"""
    db = SessionLocal()
    try:
        read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'staff',
            TMessageRead.reader_id == user_name
        ).all()}
        unread = db.query(TMessage).filter(
            TMessage.sender_type == 'client'
        ).count()
        already_read = db.query(TMessage).filter(
            TMessage.sender_type == 'client',
            TMessage.id.in_(read_ids)
        ).count() if read_ids else 0
        return max(0, unread - already_read)
    except Exception:
        return 0
    finally:
        db.close()


# ─────────────────────────────────────────────
# トップページ
# ─────────────────────────────────────────────
@bp.route('/')
@bp.route('')
def index():
    """勤怠管理システム トップページ"""
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return redirect(url_for('kintaikanri.attendance'))


# ─────────────────────────────────────────────
# 勤怠管理
# ─────────────────────────────────────────────
@bp.route('/attendance', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["APP_MANAGER"])
def attendance():
    """管理者向け：全スタッフの勤怠一覧を表示する"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        today = today_jst()

        # 月パラメータ処理
        month_str = request.args.get('month', today.strftime('%Y-%m'))
        try:
            year_m, mon_m = map(int, month_str.split('-'))
        except Exception:
            year_m, mon_m = today.year, today.month

        from calendar import monthrange
        _, last_day = monthrange(year_m, mon_m)
        month_start = date(year_m, mon_m, 1)
        month_end = date(year_m, mon_m, last_day)

        # 前月・翌月の計算
        if mon_m == 1:
            prev_month = f'{year_m - 1}-12'
        else:
            prev_month = f'{year_m}-{mon_m - 1:02d}'
        if mon_m == 12:
            next_month = f'{year_m + 1}-01'
        else:
            next_month = f'{year_m}-{mon_m + 1:02d}'

        # スタッフ絞り込みフィルター
        staff_filter = request.args.get('staff_filter', '')

        # テナント内の全勤怠レコードを取得
        query = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.work_date >= month_start,
                 TAttendance.work_date <= month_end)
        )
        if staff_filter and '_' in staff_filter:
            parts = staff_filter.split('_', 1)
            filter_type = parts[0]
            try:
                filter_id = int(parts[1])
                query = query.filter(
                    and_(TAttendance.staff_type == filter_type,
                         TAttendance.staff_id == filter_id)
                )
            except (ValueError, IndexError):
                pass
        all_records = query.order_by(
            TAttendance.staff_type.asc(),
            TAttendance.staff_id.asc(),
            TAttendance.work_date.asc()
        ).all()

        # スタッフ別にグループ化
        staff_map = {}
        for r in all_records:
            key = (r.staff_type, r.staff_id)
            if key not in staff_map:
                staff_map[key] = {
                    'staff_type': r.staff_type,
                    'staff_id': r.staff_id,
                    'name': r.staff_name or f'スタッフ{r.staff_id}',
                    'records': [],
                    'work_days': 0,
                    'total_minutes': 0,
                    'is_working_now': False,
                }
            staff_map[key]['records'].append(r)

        # 各スタッフの集計
        currently_working = 0
        total_work_days = 0
        total_work_minutes_all = 0
        for key, s in staff_map.items():
            work_days = 0
            total_mins = 0
            is_working = False
            for r in s['records']:
                if r.clock_in:
                    work_days += 1
                    if r.clock_out:
                        diff = (r.clock_out - r.clock_in).total_seconds() / 60
                        total_mins += max(0, diff - (r.break_minutes or 0))
                    else:
                        is_working = True
            s['work_days'] = work_days
            s['total_minutes'] = int(total_mins)
            s['total_hours'] = int(total_mins) // 60
            s['total_minutes_rem'] = int(total_mins) % 60
            s['is_working_now'] = is_working
            if is_working:
                currently_working += 1
            total_work_days += work_days
            total_work_minutes_all += int(total_mins)

        staff_data = list(staff_map.values())

        # 従業員管理画面と同じロジックで全スタッフを取得（管理者含む・重複なし）
        all_stores = db.query(TTenpo).filter(
            TTenpo.tenant_id == tenant_id, TTenpo.有効 == 1
        ).all()
        all_store_ids = [st.id for st in all_stores]
        store_admin_rows = db.query(TKanrishaTenpo).filter(
            TKanrishaTenpo.store_id.in_(all_store_ids)
        ).all() if all_store_ids else []
        store_admin_ids = list(set(r.admin_id for r in store_admin_rows))
        tenant_admin_rows = db.query(TTenantAdminTenant).filter(
            TTenantAdminTenant.tenant_id == tenant_id
        ).all()
        tenant_admin_ids = list(set(r.admin_id for r in tenant_admin_rows))
        all_admin_ids = list(set(store_admin_ids + tenant_admin_ids))

        # 管理者リスト（全店舗の管理者＋テナント管理者）
        admins_all = db.query(TKanrisha).filter(
            TKanrisha.id.in_(all_admin_ids), TKanrisha.active == 1
        ).order_by(TKanrisha.id).all() if all_admin_ids else []

        # 従業員リスト
        employees_all = db.query(TJugyoin).filter(
            TJugyoin.tenant_id == tenant_id, TJugyoin.active == 1
        ).order_by(TJugyoin.id).all()

        # 管理者のrole情報マップ
        admin_role_map = {a.id: getattr(a, 'role', 'admin') for a in admins_all}

        # 管理者のlogin_idセット（従業員との重複排除用）
        admin_login_id_set = {a.login_id for a in admins_all}

        # ドロップダウン用：全スタッフ一覧（管理者＋従業員、重複なし）
        all_staff = []
        seen_login_ids = set()
        for a in admins_all:
            if a.login_id not in seen_login_ids:
                seen_login_ids.add(a.login_id)
                all_staff.append({
                    'staff_type': 'admin',
                    'staff_id': a.id,
                    'staff_name': a.name,
                    'role': getattr(a, 'role', 'admin')
                })
        for e in employees_all:
            if e.login_id not in seen_login_ids:
                seen_login_ids.add(e.login_id)
                all_staff.append({
                    'staff_type': 'employee',
                    'staff_id': e.id,
                    'staff_name': e.name,
                    'role': 'employee'
                })

        # 対象スタッフ数（重複なし）
        total_staff_count = len(seen_login_ids)

        # staff_dataにもrole情報を付加
        for s in staff_data:
            if s['staff_type'] == 'admin':
                s['role'] = admin_role_map.get(s['staff_id'], 'admin')
            else:
                s['role'] = 'employee'

        return render_template('kintaikanri_attendance.html',
                               staff_data=staff_data,
                               all_staff=all_staff,
                               staff_filter=staff_filter,
                               month_str=month_str,
                               year_m=year_m,
                               mon_m=mon_m,
                               prev_month=prev_month,
                               next_month=next_month,
                               total_work_days=total_work_days,
                               total_work_hours=total_work_minutes_all // 60,
                               total_work_minutes_remainder=total_work_minutes_all % 60,
                               currently_working=currently_working,
                               total_staff_count=total_staff_count)
    finally:
        db.close()


# ─────────────────────────────────────────────
# GPS位置記録 API（勤怠画面からのAjaxリクエスト用）
# ─────────────────────────────────────────────
@bp.route('/attendance/location', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"], ROLES["APP_MANAGER"])
def record_location():
    """勤怠中のGPS位置を記録するAPIエンドポイント

    JSONボディ: { latitude, longitude, accuracy, is_background }
    """
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    role = session.get('role', '')
    staff_type = 'employee' if role == ROLES['EMPLOYEE'] else 'admin'

    data = request.get_json(silent=True) or {}
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy')
    is_background = 1 if data.get('is_background') else 0

    if latitude is None or longitude is None:
        return jsonify({'ok': False, 'error': '緯度・経度が必要です'}), 400

    db = SessionLocal()
    try:
        today = today_jst()
        # 今日の勤怠レコードを取得（attendance_idの紐付け用）
        today_record = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.staff_id == user_id,
                 TAttendance.staff_type == staff_type,
                 TAttendance.work_date == today)
        ).first()

        loc = TAttendanceLocation(
            tenant_id=tenant_id,
            attendance_id=today_record.id if today_record else None,
            staff_id=user_id,
            staff_type=staff_type,
            latitude=float(latitude),
            longitude=float(longitude),
            accuracy=float(accuracy) if accuracy is not None else None,
            is_background=is_background,
            recorded_at=now_jst()
        )
        db.add(loc)
        db.commit()
        return jsonify({'ok': True, 'id': loc.id})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/attendance/location/today')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"], ROLES["APP_MANAGER"])
def today_locations():
    """今日のGPS位置履歴を返すAPIエンドポイント"""
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    role = session.get('role', '')
    staff_type = 'employee' if role == ROLES['EMPLOYEE'] else 'admin'

    db = SessionLocal()
    try:
        today = today_jst()
        today_record = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.staff_id == user_id,
                 TAttendance.staff_type == staff_type,
                 TAttendance.work_date == today)
        ).first()

        if not today_record:
            return jsonify({'locations': [], 'count': 0})

        locs = db.query(TAttendanceLocation).filter(
            and_(TAttendanceLocation.attendance_id == today_record.id,
                 TAttendanceLocation.tenant_id == tenant_id)
        ).order_by(TAttendanceLocation.recorded_at.asc()).all()

        result = [{
            'id': l.id,
            'latitude': l.latitude,
            'longitude': l.longitude,
            'accuracy': l.accuracy,
            'is_background': l.is_background,
            'recorded_at': l.recorded_at.strftime('%H:%M:%S')
        } for l in locs]

        return jsonify({'locations': result, 'count': len(result)})
    finally:
        db.close()


# ─────────────────────────────────────────────
# 管理者向け：スタッフ位置確認画面
# ─────────────────────────────────────────────
@bp.route('/attendance/map')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["APP_MANAGER"])
def attendance_map():
    """管理者向け：スタッフの当日移動ルートを地図で確認する画面"""
    tenant_id = session.get('tenant_id')
    user_name = session.get('user_name', '')
    db = SessionLocal()
    try:
        unread_count = _get_unread_count(tenant_id, user_name)
        today = today_jst()

        # 対象日（クエリパラメータで変更可能）
        date_str = request.args.get('date', today.strftime('%Y-%m-%d'))
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            target_date = today

        # 対象スタッフID（未指定なら全スタッフ）
        staff_id_param = request.args.get('staff_id')

        # テナント内の全スタッフ（管理者 + 従業員）を重複なしで取得
        all_stores_m = db.query(TTenpo).filter(
            TTenpo.tenant_id == tenant_id, TTenpo.有効 == 1
        ).all()
        all_store_ids_m = [st.id for st in all_stores_m]
        store_admin_rows_m = db.query(TKanrishaTenpo).filter(
            TKanrishaTenpo.store_id.in_(all_store_ids_m)
        ).all() if all_store_ids_m else []
        store_admin_ids_m = list(set(r.admin_id for r in store_admin_rows_m))
        tenant_admin_rows_m = db.query(TTenantAdminTenant).filter(
            TTenantAdminTenant.tenant_id == tenant_id
        ).all()
        tenant_admin_ids_m = list(set(r.admin_id for r in tenant_admin_rows_m))
        all_admin_ids_m = list(set(store_admin_ids_m + tenant_admin_ids_m))
        admins = db.query(TKanrisha).filter(
            TKanrisha.id.in_(all_admin_ids_m), TKanrisha.active == 1
        ).order_by(TKanrisha.id).all() if all_admin_ids_m else []
        employees = db.query(TJugyoin).filter(
            and_(TJugyoin.tenant_id == tenant_id, TJugyoin.active == 1)
        ).order_by(TJugyoin.id).all()

        # login_idで重複排除しながらstaff_listを構築
        seen_login_ids_m = set()
        staff_list = []
        for a in admins:
            if a.login_id not in seen_login_ids_m:
                seen_login_ids_m.add(a.login_id)
                staff_list.append({'id': a.id, 'name': a.name, 'type': 'admin', 'role': getattr(a, 'role', 'admin'), 'gps_mode': getattr(a, 'gps_mode', None) or 'always'})
        for e in employees:
            if e.login_id not in seen_login_ids_m:
                seen_login_ids_m.add(e.login_id)
                staff_list.append({'id': e.id, 'name': e.name, 'type': 'employee', 'role': 'employee', 'gps_mode': getattr(e, 'gps_mode', None) or 'always'})

        # 位置データに含まれるがスタッフ一覧にないスタッフを追加（tenant_id=NULLのシステム管理者など）
        staff_id_set = {(s['id'], s['type']) for s in staff_list}

        # tenant_id=NULLのシステム管理者も取得し、同名のスタッフがいれば「IDの別名マップ」を作成
        null_admins = db.query(TKanrisha).filter(TKanrisha.tenant_id == None).all()
        def normalize_name(n): return n.replace('\u3000', ' ').strip() if n else ''
        name_to_tenant_staff = {normalize_name(s['name']): s['id'] for s in staff_list if s['type'] == 'admin'}
        null_id_to_tenant_id = {}
        for na in null_admins:
            normalized = normalize_name(na.name)
            if normalized in name_to_tenant_staff:
                null_id_to_tenant_id[na.id] = name_to_tenant_staff[normalized]

        # 対象日の勤怠レコードを取得
        attendances = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.work_date == target_date)
        ).order_by(TAttendance.clock_in.asc()).all()
        # 1日に複数レコードがある場合も対応：同一スタッフの全レコードを集約して代表値を作る
        attendance_agg = {}
        for a in attendances:
            k = (a.staff_id, a.staff_type)
            if k not in attendance_agg:
                attendance_agg[k] = {
                    'clock_in': a.clock_in,
                    'clock_out': a.clock_out,
                    'break_start': a.break_start,
                    'break_end': a.break_end
                }
            else:
                if a.clock_in and not attendance_agg[k]['clock_in']:
                    attendance_agg[k]['clock_in'] = a.clock_in
                if a.clock_out:
                    attendance_agg[k]['clock_out'] = a.clock_out
                if a.break_start:
                    attendance_agg[k]['break_start'] = a.break_start
                if a.break_end:
                    attendance_agg[k]['break_end'] = a.break_end
        attendance_map_by_key = attendance_agg

        # GPS位置履歴を取得
        loc_query = db.query(TAttendanceLocation).filter(
            and_(TAttendanceLocation.tenant_id == tenant_id,
                 TAttendanceLocation.recorded_at >= datetime.combine(target_date, datetime.min.time()),
                 TAttendanceLocation.recorded_at < datetime.combine(target_date + timedelta(days=1), datetime.min.time()))
        )
        if staff_id_param:
            try:
                sid = int(staff_id_param)
                null_ids_for_sid = [nid for nid, tid in null_id_to_tenant_id.items() if tid == sid]
                if null_ids_for_sid:
                    from sqlalchemy import or_ as sa_or
                    loc_query = loc_query.filter(sa_or(
                        TAttendanceLocation.staff_id == sid,
                        TAttendanceLocation.staff_id.in_(null_ids_for_sid)
                    ))
                else:
                    loc_query = loc_query.filter(TAttendanceLocation.staff_id == sid)
            except ValueError:
                pass

        locations = loc_query.order_by(
            TAttendanceLocation.staff_id.asc(),
            TAttendanceLocation.recorded_at.asc()
        ).all()

        # スタッフごとに位置データをまとめる
        staff_tracks = {}
        for loc in locations:
            effective_sid = null_id_to_tenant_id.get(loc.staff_id, loc.staff_id)
            key = (effective_sid, loc.staff_type)
            if key not in staff_tracks:
                staff_tracks[key] = []
            staff_tracks[key].append({
                'lat': loc.latitude,
                'lng': loc.longitude,
                'accuracy': loc.accuracy,
                'is_background': loc.is_background,
                'time': loc.recorded_at.strftime('%H:%M:%S')
            })

        # テンプレートに渡すデータを整形
        tracks_data = []
        for s in staff_list:
            key = (s['id'], s['type'])
            att = attendance_map_by_key.get(key)
            pts = staff_tracks.get(key, [])
            def _fmt(val):
                if val is None: return None
                if hasattr(val, 'strftime'): return val.strftime('%H:%M:%S')
                return str(val)
            tracks_data.append({
                'staff_id': s['id'],
                'staff_name': s['name'],
                'staff_type': s['type'],
                'gps_mode': s.get('gps_mode', 'always'),
                'clock_in': _fmt(att['clock_in']) if att else None,
                'clock_out': _fmt(att['clock_out']) if att else None,
                'break_start': _fmt(att['break_start']) if att else None,
                'break_end': _fmt(att['break_end']) if att else None,
                'points': pts,
                'point_count': len(pts)
            })

        # 位置データがあるスタッフを先頭に
        tracks_data.sort(key=lambda x: -x['point_count'])

        # テナントのリアルタイムモード設定を取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        gps_realtime_enabled = getattr(tenant_obj, 'gps_realtime_enabled', 0) or 0

        return render_template('staff_attendance_map.html',
                               tracks_data=tracks_data,
                               staff_list=staff_list,
                               target_date=target_date,
                               date_str=date_str,
                               selected_staff_id=staff_id_param,
                               unread_count=unread_count,
                               gps_realtime_enabled=gps_realtime_enabled)
    finally:
        db.close()


# リアルタイム追跡モード ON/OFF API
@bp.route('/attendance/realtime_mode', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["APP_MANAGER"])
def toggle_realtime_mode():
    """管理者が地図画面からリアルタイム追跡モードをON/OFFするAPI"""
    tenant_id = session.get('tenant_id')
    data = request.get_json(silent=True) or {}
    enabled = 1 if data.get('enabled') else 0
    db = SessionLocal()
    try:
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        if not tenant_obj:
            return jsonify({'ok': False, 'error': 'テナントが見つかりません'}), 404
        tenant_obj.gps_realtime_enabled = enabled
        db.commit()
        return jsonify({'ok': True, 'enabled': enabled})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


# リアルタイムモード状態確認API（Expoアプリからポーリング用）
@bp.route('/attendance/realtime_mode', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"], ROLES["APP_MANAGER"])
def get_realtime_mode():
    """現在のリアルタイムモードの状態を返すAPI（Expoアプリがポーリングする）"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        gps_realtime_enabled = getattr(tenant_obj, 'gps_realtime_enabled', 0) or 0
        gps_interval_minutes = getattr(tenant_obj, 'gps_interval_minutes', 5) or 5
        return jsonify({
            'ok': True,
            'realtime_enabled': bool(gps_realtime_enabled),
            'interval_seconds': 3 if gps_realtime_enabled else gps_interval_minutes * 60
        })
    finally:
        db.close()


# リアルタイム地図データAPI（地図画面がポーリングする）
@bp.route('/attendance/map/realtime_data')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["APP_MANAGER"])
def attendance_map_realtime_data():
    """リアルタイム追跡時に地図画面がポーリングする位置データAPI"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        date_str = request.args.get('date', today_jst().strftime('%Y-%m-%d'))
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            target_date = today_jst()

        staff_id_param = request.args.get('staff_id')

        all_stores_rt = db.query(TTenpo).filter(
            TTenpo.tenant_id == tenant_id, TTenpo.有効 == 1
        ).all()
        all_store_ids_rt = [st.id for st in all_stores_rt]
        store_admin_rows_rt = db.query(TKanrishaTenpo).filter(
            TKanrishaTenpo.store_id.in_(all_store_ids_rt)
        ).all() if all_store_ids_rt else []
        store_admin_ids_rt = list(set(r.admin_id for r in store_admin_rows_rt))
        tenant_admin_rows_rt = db.query(TTenantAdminTenant).filter(
            TTenantAdminTenant.tenant_id == tenant_id
        ).all()
        tenant_admin_ids_rt = list(set(r.admin_id for r in tenant_admin_rows_rt))
        all_admin_ids_rt = list(set(store_admin_ids_rt + tenant_admin_ids_rt))
        admins = db.query(TKanrisha).filter(
            TKanrisha.id.in_(all_admin_ids_rt), TKanrisha.active == 1
        ).order_by(TKanrisha.id).all() if all_admin_ids_rt else []
        employees = db.query(TJugyoin).filter(
            and_(TJugyoin.tenant_id == tenant_id, TJugyoin.active == 1)
        ).order_by(TJugyoin.id).all()
        # login_idで重複排除
        seen_rt = set()
        admins_dedup = []
        for a in admins:
            if a.login_id not in seen_rt:
                seen_rt.add(a.login_id)
                admins_dedup.append(a)
        employees_dedup = []
        for e in employees:
            if e.login_id not in seen_rt:
                seen_rt.add(e.login_id)
                employees_dedup.append(e)
        admins = admins_dedup
        employees = employees_dedup
        name_map = {(a.id, 'admin'): a.name for a in admins}
        name_map.update({(e.id, 'employee'): e.name for e in employees})
        gps_mode_map = {(a.id, 'admin'): getattr(a, 'gps_mode', None) or 'always' for a in admins}
        gps_mode_map.update({(e.id, 'employee'): getattr(e, 'gps_mode', None) or 'always' for e in employees})
        def normalize_name(n): return n.replace('　', ' ').strip() if n else ''
        name_to_tenant_id = {normalize_name(a.name): a.id for a in admins}
        null_admins = db.query(TKanrisha).filter(TKanrisha.tenant_id == None).all()
        null_id_to_tenant_id = {}
        for na in null_admins:
            normalized = normalize_name(na.name)
            if normalized in name_to_tenant_id:
                null_id_to_tenant_id[na.id] = name_to_tenant_id[normalized]

        # 勤怠データを取得
        attendances_rt = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.work_date == target_date)
        ).order_by(TAttendance.clock_in.asc()).all()
        attendance_map_rt = {}
        for a in attendances_rt:
            k = (a.staff_id, a.staff_type)
            if k not in attendance_map_rt:
                attendance_map_rt[k] = {
                    'clock_in': a.clock_in,
                    'clock_out': a.clock_out,
                    'break_start': a.break_start,
                    'break_end': a.break_end
                }
            else:
                if a.clock_in and not attendance_map_rt[k]['clock_in']:
                    attendance_map_rt[k]['clock_in'] = a.clock_in
                if a.clock_out:
                    attendance_map_rt[k]['clock_out'] = a.clock_out
                if a.break_start:
                    attendance_map_rt[k]['break_start'] = a.break_start
                if a.break_end:
                    attendance_map_rt[k]['break_end'] = a.break_end

        # GPS位置履歴を取得
        loc_query = db.query(TAttendanceLocation).filter(
            and_(TAttendanceLocation.tenant_id == tenant_id,
                 TAttendanceLocation.recorded_at >= datetime.combine(target_date, datetime.min.time()),
                 TAttendanceLocation.recorded_at < datetime.combine(target_date + timedelta(days=1), datetime.min.time()))
        )
        if staff_id_param:
            try:
                sid = int(staff_id_param)
                null_ids_for_sid = [nid for nid, tid in null_id_to_tenant_id.items() if tid == sid]
                if null_ids_for_sid:
                    from sqlalchemy import or_ as sa_or
                    loc_query = loc_query.filter(sa_or(
                        TAttendanceLocation.staff_id == sid,
                        TAttendanceLocation.staff_id.in_(null_ids_for_sid)
                    ))
                else:
                    loc_query = loc_query.filter(TAttendanceLocation.staff_id == sid)
            except ValueError:
                pass

        locations = loc_query.order_by(
            TAttendanceLocation.staff_id.asc(),
            TAttendanceLocation.recorded_at.asc()
        ).all()

        # スタッフごとにまとめる
        staff_tracks = {}
        for loc in locations:
            effective_sid = null_id_to_tenant_id.get(loc.staff_id, loc.staff_id)
            key = (effective_sid, loc.staff_type)
            if key not in staff_tracks:
                staff_tracks[key] = []
            staff_tracks[key].append({
                'lat': loc.latitude,
                'lng': loc.longitude,
                'time': loc.recorded_at.strftime('%H:%M:%S')
            })

        tracks = []
        for (sid, stype), pts in staff_tracks.items():
            staff_name = name_map.get((sid, stype))
            if not staff_name:
                extra = db.query(TKanrisha).filter(TKanrisha.id == sid).first()
                staff_name = extra.name if extra else '不明'
            att_rt = attendance_map_rt.get((sid, stype))
            def _fmt_rt(val):
                if val is None: return None
                if hasattr(val, 'strftime'): return val.strftime('%H:%M:%S')
                return str(val)
            tracks.append({
                'staff_id': sid,
                'staff_type': stype,
                'staff_name': staff_name,
                'gps_mode': gps_mode_map.get((sid, stype), 'always'),
                'clock_in': _fmt_rt(att_rt['clock_in']) if att_rt else None,
                'clock_out': _fmt_rt(att_rt['clock_out']) if att_rt else None,
                'break_start': _fmt_rt(att_rt['break_start']) if att_rt else None,
                'break_end': _fmt_rt(att_rt['break_end']) if att_rt else None,
                'points': pts
            })

        return jsonify({'ok': True, 'tracks': tracks})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()
