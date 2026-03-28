"""
モバイルアプリ専用 API ブループリント
Expo（React Native）スタッフ勤怠GPSアプリからの接続を受け付ける。
認証: X-Mobile-API-Key ヘッダーによるAPIキー認証 + staff_token（スタッフID・テナントID）
"""
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import and_
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import os
import hmac
import hashlib

from app.db import SessionLocal
from app.models_login import TKanrisha, TJugyoin, TTenant, TAttendance, TAttendanceLocation

bp = Blueprint('mobile_api', __name__, url_prefix='/api/mobile')

JST = ZoneInfo('Asia/Tokyo')


def now_jst():
    """日本時間（JST）の現在時刻をタイムゾーンなしdatetimeで返す"""
    return datetime.now(JST).replace(tzinfo=None)


def today_jst():
    """日本時間（JST）の今日の日付を返す"""
    return datetime.now(JST).date()


def _check_api_key():
    """APIキーを検証する。無効な場合はNoneを返す"""
    api_key = request.headers.get('X-Mobile-API-Key', '')
    expected = os.environ.get('MOBILE_API_KEY', '')
    if not expected:
        return False
    return hmac.compare_digest(api_key, expected)


def _get_staff(tenant_id: int, staff_id: int, staff_type: str):
    """スタッフ情報を取得する"""
    db = SessionLocal()
    try:
        if staff_type == 'employee':
            staff = db.query(TJugyoin).filter(
                and_(TJugyoin.id == staff_id, TJugyoin.tenant_id == tenant_id)
            ).first()
        else:
            staff = db.query(TKanrisha).filter(
                TKanrisha.id == staff_id
            ).first()
        return staff
    finally:
        db.close()


# ─────────────────────────────────────────────
# 認証エンドポイント
# ─────────────────────────────────────────────

@bp.route('/auth/login', methods=['POST'])
def mobile_login():
    """モバイルアプリ用ログインエンドポイント
    
    JSONボディ: { login_id, password, tenant_slug }
    レスポンス: { ok, staff_token, staff_id, staff_type, tenant_id, name, gps_enabled, gps_interval_minutes }
    """
    if not _check_api_key():
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401

    from werkzeug.security import check_password_hash

    data = request.get_json(silent=True) or {}
    login_id = data.get('login_id', '').strip()
    password = data.get('password', '')
    tenant_slug = data.get('tenant_slug', '').strip()

    if not login_id or not password or not tenant_slug:
        return jsonify({'ok': False, 'error': 'login_id・password・tenant_slugは必須です'}), 400

    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.slug == tenant_slug).first()
        if not tenant:
            return jsonify({'ok': False, 'error': 'テナントが見つかりません'}), 404

        # 従業員テーブルを検索
        staff = db.query(TJugyoin).filter(
            and_(TJugyoin.login_id == login_id, TJugyoin.tenant_id == tenant.id, TJugyoin.active == 1)
        ).first()
        staff_type = 'employee'

        # 見つからなければ管理者テーブルを検索
        if not staff:
            staff = db.query(TKanrisha).filter(
                TKanrisha.login_id == login_id
            ).first()
            staff_type = 'admin'

        if not staff:
            return jsonify({'ok': False, 'error': 'ログインIDまたはパスワードが正しくありません'}), 401

        if not staff.password_hash or not check_password_hash(staff.password_hash, password):
            return jsonify({'ok': False, 'error': 'ログインIDまたはパスワードが正しくありません'}), 401

        # シンプルなトークン生成（staff_id:staff_type:tenant_id のHMAC署名）
        secret = os.environ.get('MOBILE_API_KEY', 'dev-secret')
        payload = f"{staff.id}:{staff_type}:{tenant.id}"
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        staff_token = f"{payload}:{sig}"

        return jsonify({
            'ok': True,
            'staff_token': staff_token,
            'staff_id': staff.id,
            'staff_type': staff_type,
            'tenant_id': tenant.id,
            'name': staff.name,
            'gps_enabled': bool(tenant.gps_enabled),
            'gps_interval_minutes': tenant.gps_interval_minutes or 5,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


def _verify_staff_token(token: str):
    """staff_tokenを検証してスタッフ情報を返す。無効な場合はNoneを返す"""
    try:
        parts = token.split(':')
        if len(parts) != 4:
            return None
        staff_id, staff_type, tenant_id, sig = parts
        secret = os.environ.get('MOBILE_API_KEY', 'dev-secret')
        payload = f"{staff_id}:{staff_type}:{tenant_id}"
        expected_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return {
            'staff_id': int(staff_id),
            'staff_type': staff_type,
            'tenant_id': int(tenant_id),
        }
    except Exception:
        return None


def _auth_required():
    """APIキーとstaff_tokenを検証してスタッフ情報を返す。失敗時はNoneを返す"""
    if not _check_api_key():
        api_key_recv = request.headers.get('X-Mobile-API-Key', '')
        current_app.logger.warning(
            f'[_auth_required] APIキー無効 path={request.path} '
            f'key_present={bool(api_key_recv)} key_len={len(api_key_recv)}'
        )
        return None, jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401
    token = request.headers.get('X-Staff-Token', '')
    staff_info = _verify_staff_token(token)
    if not staff_info:
        current_app.logger.warning(
            f'[_auth_required] staff_token無効 path={request.path} '
            f'token_present={bool(token)} token_len={len(token)}'
        )
        return None, jsonify({'ok': False, 'error': '認証トークンが無効です'}), 401
    current_app.logger.info(
        f'[_auth_required] 認証成功 path={request.path} '
        f'staff_id={staff_info["staff_id"]} staff_type={staff_info["staff_type"]} tenant_id={staff_info["tenant_id"]}'
    )
    return staff_info, None, None


# ─────────────────────────────────────────────
# 勤怠エンドポイント
# ─────────────────────────────────────────────

@bp.route('/attendance/today', methods=['GET'])
def get_today_attendance():
    """今日の勤怠状態を取得"""
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        current_app.logger.warning(f'[attendance/today] 認証失敗: {err_code}')
        return err_resp, err_code

    db = SessionLocal()
    try:
        today = today_jst()
        current_app.logger.info(f'[attendance/today] staff_id={staff_info["staff_id"]} staff_type={staff_info["staff_type"]} tenant_id={staff_info["tenant_id"]} today={today}')

        # 複数レコードがある場合は最新（clock_inが最も新しい）レコードを返す
        rec = db.query(TAttendance).filter(
            and_(
                TAttendance.tenant_id == staff_info['tenant_id'],
                TAttendance.staff_id == staff_info['staff_id'],
                TAttendance.staff_type == staff_info['staff_type'],
                TAttendance.work_date == today,
            )
        ).order_by(TAttendance.clock_in.desc().nullslast()).first()

        if not rec:
            current_app.logger.info(f'[attendance/today] レコードなし → status=off')
            return jsonify({'ok': True, 'attendance': None})

        # clock_in/clock_out/break_start/break_endから現在の出退勤状態を動的に計算
        if not rec.clock_in:
            computed_status = 'off'
        elif rec.clock_out:
            computed_status = 'finished'
        elif rec.break_start and not rec.break_end:
            computed_status = 'break'
        else:
            computed_status = 'working'

        current_app.logger.info(
            f'[attendance/today] rec.id={rec.id} clock_in={rec.clock_in} clock_out={rec.clock_out} '
            f'break_start={rec.break_start} break_end={rec.break_end} → computed_status={computed_status}'
        )

        return jsonify({
            'ok': True,
            'attendance': {
                'id': rec.id,
                'work_date': rec.work_date.isoformat(),
                'clock_in': rec.clock_in.strftime('%H:%M') if rec.clock_in else None,
                'clock_out': rec.clock_out.strftime('%H:%M') if rec.clock_out else None,
                'break_start': rec.break_start.strftime('%H:%M') if rec.break_start else None,
                'break_end': rec.break_end.strftime('%H:%M') if rec.break_end else None,
                'break_minutes': rec.break_minutes or 0,
                'status': computed_status,
                'note': rec.note,
            }
        })
    except Exception as e:
        current_app.logger.error(f'[attendance/today] 例外: {e}', exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/attendance/clock_in', methods=['POST'])
def clock_in():
    """出勤打刻"""
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    db = SessionLocal()
    try:
        today = today_jst()
        now = now_jst()

        # 既存レコード確認
        rec = db.query(TAttendance).filter(
            and_(
                TAttendance.tenant_id == staff_info['tenant_id'],
                TAttendance.staff_id == staff_info['staff_id'],
                TAttendance.staff_type == staff_info['staff_type'],
                TAttendance.work_date == today,
            )
        ).first()

        if rec and rec.clock_in:
            return jsonify({'ok': False, 'error': '既に出勤済みです'}), 400

        # スタッフ名を取得
        staff_name = ''
        if staff_info['staff_type'] == 'employee':
            s = db.query(TJugyoin).filter(TJugyoin.id == staff_info['staff_id']).first()
        else:
            s = db.query(TKanrisha).filter(TKanrisha.id == staff_info['staff_id']).first()
        if s:
            staff_name = s.name

        if rec:
            rec.clock_in = now
            rec.updated_at = now
        else:
            rec = TAttendance(
                tenant_id=staff_info['tenant_id'],
                staff_id=staff_info['staff_id'],
                staff_type=staff_info['staff_type'],
                staff_name=staff_name,
                work_date=today,
                clock_in=now,
            )
            db.add(rec)

        db.commit()
        db.refresh(rec)
        return jsonify({'ok': True, 'attendance_id': rec.id, 'clock_in': now.strftime('%H:%M')})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/attendance/clock_out', methods=['POST'])
def clock_out():
    """退勤打刻"""
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    db = SessionLocal()
    try:
        today = today_jst()
        now = now_jst()

        rec = db.query(TAttendance).filter(
            and_(
                TAttendance.tenant_id == staff_info['tenant_id'],
                TAttendance.staff_id == staff_info['staff_id'],
                TAttendance.staff_type == staff_info['staff_type'],
                TAttendance.work_date == today,
            )
        ).first()

        if not rec or not rec.clock_in:
            return jsonify({'ok': False, 'error': '出勤記録がありません'}), 400
        if rec.clock_out:
            return jsonify({'ok': False, 'error': '既に退勤済みです'}), 400

        # 休憩中なら休憩終了
        if rec.break_start and not rec.break_end:
            rec.break_end = now
            delta = (now - rec.break_start).total_seconds() / 60
            rec.break_minutes = (rec.break_minutes or 0) + int(delta)

        rec.clock_out = now
        rec.updated_at = now
        db.commit()
        return jsonify({'ok': True, 'clock_out': now.strftime('%H:%M')})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/attendance/break_start', methods=['POST'])
def break_start():
    """休憩開始"""
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    db = SessionLocal()
    try:
        today = today_jst()
        now = now_jst()

        rec = db.query(TAttendance).filter(
            and_(
                TAttendance.tenant_id == staff_info['tenant_id'],
                TAttendance.staff_id == staff_info['staff_id'],
                TAttendance.staff_type == staff_info['staff_type'],
                TAttendance.work_date == today,
            )
        ).first()

        if not rec or not rec.clock_in:
            return jsonify({'ok': False, 'error': '出勤記録がありません'}), 400
        if rec.clock_out:
            return jsonify({'ok': False, 'error': '既に退勤済みです'}), 400
        if rec.break_start and not rec.break_end:
            return jsonify({'ok': False, 'error': '既に休憩中です'}), 400

        rec.break_start = now
        rec.break_end = None
        rec.updated_at = now
        db.commit()
        return jsonify({'ok': True, 'break_start': now.strftime('%H:%M')})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/attendance/break_end', methods=['POST'])
def break_end():
    """休憩終了"""
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    db = SessionLocal()
    try:
        today = today_jst()
        now = now_jst()

        rec = db.query(TAttendance).filter(
            and_(
                TAttendance.tenant_id == staff_info['tenant_id'],
                TAttendance.staff_id == staff_info['staff_id'],
                TAttendance.staff_type == staff_info['staff_type'],
                TAttendance.work_date == today,
            )
        ).first()

        if not rec or not rec.break_start:
            return jsonify({'ok': False, 'error': '休憩記録がありません'}), 400
        if rec.break_end:
            return jsonify({'ok': False, 'error': '既に休憩終了済みです'}), 400

        rec.break_end = now
        delta = (now - rec.break_start).total_seconds() / 60
        rec.break_minutes = (rec.break_minutes or 0) + int(delta)
        rec.updated_at = now
        db.commit()
        return jsonify({'ok': True, 'break_end': now.strftime('%H:%M'), 'break_minutes': rec.break_minutes})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


# ─────────────────────────────────────────────
# GPS位置情報エンドポイント
# ─────────────────────────────────────────────

@bp.route('/location/record', methods=['POST'])
def record_location():
    """GPS位置情報を記録
    
    JSONボディ: { latitude, longitude, accuracy, attendance_id, is_background, recorded_at }
    recorded_at: 実際に位置を取得した時刻（ISO 8601形式、例: "2024-01-15T09:30:00.000Z"）
               未指定またはnullの場合は現在時刻（JST）を使用する
    """
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    data = request.get_json(silent=True) or {}
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy')
    attendance_id = data.get('attendance_id')
    is_background = 1 if data.get('is_background') else 0
    recorded_at_str = data.get('recorded_at')  # ISO 8601形式の文字列またはnull

    if latitude is None or longitude is None:
        return jsonify({'ok': False, 'error': '緯度・経度が必要です'}), 400

    # recorded_atをパースする。未指定またはパース失敗時は現在時刻を使用
    recorded_at = now_jst()
    if recorded_at_str:
        try:
            # ISO 8601形式（UTCまたはJST）をパースしてJSTの naive datetimeに変換
            dt = datetime.fromisoformat(recorded_at_str.replace('Z', '+00:00'))
            if dt.tzinfo is not None:
                # タイムゾーン付きの場合はJSTに変換してtzinfoを除去
                recorded_at = dt.astimezone(JST).replace(tzinfo=None)
            else:
                # タイムゾーンなしはそのまま使用
                recorded_at = dt
        except (ValueError, TypeError):
            # パース失敗時は現在時刻を使用（ログは出すがエラーにはしない）
            current_app.logger.warning(f'recorded_atのパース失敗: {recorded_at_str}')

    db = SessionLocal()
    try:
        # attendance_idが未指定の場合は今日の勤怠レコードを自動取得
        if not attendance_id:
            today = today_jst()
            rec = db.query(TAttendance).filter(
                and_(
                    TAttendance.tenant_id == staff_info['tenant_id'],
                    TAttendance.staff_id == staff_info['staff_id'],
                    TAttendance.staff_type == staff_info['staff_type'],
                    TAttendance.work_date == today,
                )
            ).first()
            if rec:
                attendance_id = rec.id

        loc = TAttendanceLocation(
            tenant_id=staff_info['tenant_id'],
            attendance_id=attendance_id,
            staff_id=staff_info['staff_id'],
            staff_type=staff_info['staff_type'],
            latitude=float(latitude),
            longitude=float(longitude),
            accuracy=float(accuracy) if accuracy is not None else None,
            is_background=is_background,
            recorded_at=recorded_at,  # 実際に位置を取得した時刻（オフライン時の正確な時刻を保持）
        )
        db.add(loc)
        db.commit()
        return jsonify({'ok': True, 'id': loc.id})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/location/today', methods=['GET'])
def today_locations():
    """今日のGPS位置履歴を取得"""
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    db = SessionLocal()
    try:
        today = today_jst()
        locs = db.query(TAttendanceLocation).filter(
            and_(
                TAttendanceLocation.tenant_id == staff_info['tenant_id'],
                TAttendanceLocation.staff_id == staff_info['staff_id'],
                TAttendanceLocation.staff_type == staff_info['staff_type'],
                TAttendanceLocation.recorded_at >= datetime.combine(today, datetime.min.time()),
                TAttendanceLocation.recorded_at < datetime.combine(today + timedelta(days=1), datetime.min.time()),
            )
        ).order_by(TAttendanceLocation.recorded_at.asc()).all()

        return jsonify({
            'ok': True,
            'locations': [
                {
                    'id': l.id,
                    'latitude': l.latitude,
                    'longitude': l.longitude,
                    'accuracy': l.accuracy,
                    'is_background': bool(l.is_background),
                    'recorded_at': l.recorded_at.strftime('%H:%M:%S'),
                }
                for l in locs
            ],
            'count': len(locs),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/location/realtime_mode', methods=['GET'])
def get_realtime_mode():
    """リアルタイムモードフラグを返す（Expoアプリが10秒ごとにポーリングする）
    
    管理者が地図画面でリアルタイム追跡をONにしている場合は realtime_enabled: true を返す。
    Expoアプリはこのフラグに応じて送信間隔を切り替える（通常: 5分, リアルタイム: 4秒）。
    """
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.id == staff_info['tenant_id']).first()
        if not tenant:
            return jsonify({'ok': False, 'error': 'テナントが見つかりません'}), 404
        realtime_enabled = bool(getattr(tenant, 'gps_realtime_enabled', False))
        return jsonify({'ok': True, 'realtime_enabled': realtime_enabled})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()
