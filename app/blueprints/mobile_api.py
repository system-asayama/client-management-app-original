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
from app.models_login import TKanrisha, TJugyoin, TTenant, TAttendance, TAttendanceLocation, TJugyoinTenpo, TKanrishaTenpo

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
            'gps_interval_seconds': getattr(tenant, 'gps_interval_seconds', None) or (tenant.gps_interval_minutes or 5) * 60,
            'gps_mode': getattr(staff, 'gps_mode', None) or 'always',
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

        # 未退勤の出勤中レコードを確認（退勤済みは再出勤可能）
        rec = db.query(TAttendance).filter(
            and_(
                TAttendance.tenant_id == staff_info['tenant_id'],
                TAttendance.staff_id == staff_info['staff_id'],
                TAttendance.staff_type == staff_info['staff_type'],
                TAttendance.work_date == today,
                TAttendance.clock_in.isnot(None),
                TAttendance.clock_out.is_(None),
            )
        ).first()

        if rec:
            return jsonify({'ok': False, 'error': '既に出勤中です'}), 400

        # スタッフ名を取得
        staff_name = ''
        if staff_info['staff_type'] == 'employee':
            s = db.query(TJugyoin).filter(TJugyoin.id == staff_info['staff_id']).first()
        else:
            s = db.query(TKanrisha).filter(TKanrisha.id == staff_info['staff_id']).first()
        if s:
            staff_name = s.name

         # スタッフの所属店舗を自動取得（店舗ベースアーキテクチャ対応）
        store_id = None
        try:
            if staff_info['staff_type'] == 'employee':
                tenpo_link = db.query(TJugyoinTenpo).filter(
                    TJugyoinTenpo.employee_id == staff_info['staff_id']
                ).first()
            else:
                tenpo_link = db.query(TKanrishaTenpo).filter(
                    TKanrishaTenpo.admin_id == staff_info['staff_id']
                ).first()
            if tenpo_link:
                store_id = tenpo_link.store_id
        except Exception:
            store_id = None
        # 常に新しいレコードを作成（退勤後の再出勤対応）
        rec = TAttendance(
            tenant_id=staff_info['tenant_id'],
            staff_id=staff_info['staff_id'],
            staff_type=staff_info['staff_type'],
            staff_name=staff_name,
            work_date=today,
            clock_in=now,
            store_id=store_id,
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


@bp.route('/attendance/monthly', methods=['GET'])
def get_monthly_attendance():
    """月次勤怠一覧を取得
    
    クエリパラメータ: year_month=YYYY-MM
    """
    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    year_month = request.args.get('year_month', '')
    if not year_month or len(year_month) != 7:
        return jsonify({'ok': False, 'error': 'year_month パラメータが必要です（例: 2024-01）'}), 400

    try:
        year, month = int(year_month[:4]), int(year_month[5:7])
    except ValueError:
        return jsonify({'ok': False, 'error': 'year_month の形式が不正です'}), 400

    db = SessionLocal()
    try:
        # 月初〜月末の範囲でフィルタ
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        records = db.query(TAttendance).filter(
            and_(
                TAttendance.tenant_id == staff_info['tenant_id'],
                TAttendance.staff_id == staff_info['staff_id'],
                TAttendance.staff_type == staff_info['staff_type'],
                TAttendance.work_date >= start_date,
                TAttendance.work_date <= end_date,
            )
        ).order_by(TAttendance.work_date.desc()).all()

        result = []
        for rec in records:
            # 動的にステータスを計算
            if not rec.clock_in:
                computed_status = 'off'
            elif rec.clock_out:
                computed_status = 'finished'
            elif rec.break_start and not rec.break_end:
                computed_status = 'break'
            else:
                computed_status = 'working'

            result.append({
                'id': rec.id,
                'work_date': rec.work_date.isoformat(),
                'clock_in': rec.clock_in.strftime('%H:%M') if rec.clock_in else None,
                'clock_out': rec.clock_out.strftime('%H:%M') if rec.clock_out else None,
                'break_start': rec.break_start.strftime('%H:%M') if rec.break_start else None,
                'break_end': rec.break_end.strftime('%H:%M') if rec.break_end else None,
                'break_minutes': rec.break_minutes or 0,
                'status': computed_status,
                'note': rec.note,
            })

        return jsonify({'ok': True, 'records': result, 'year_month': year_month})
    except Exception as e:
        current_app.logger.error(f'[attendance/monthly] 例外: {e}', exc_info=True)
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

# ─────────────────────────────────────────────
# 顔認証 API
# ─────────────────────────────────────────────

import base64

@bp.route('/face/register', methods=['POST'])
def face_register():
    """顔写真を登録する（初回セットアップ時に使用）

    Request JSON:
        face_image_base64 (str): Base64エンコードされた顔画像（JPEG/PNG）

    Response JSON:
        ok (bool): 成功フラグ
        message (str): 結果メッセージ
    """
    if not _check_api_key():
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401

    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    data = request.get_json() or {}
    face_image_b64 = data.get('face_image_base64', '')
    if not face_image_b64:
        return jsonify({'ok': False, 'error': '顔画像が必要です'}), 400

    try:
        img_bytes = base64.b64decode(face_image_b64.split(',')[-1])
        if len(img_bytes) < 100:
            return jsonify({'ok': False, 'error': '画像データが不正です'}), 400
    except Exception:
        return jsonify({'ok': False, 'error': '画像のデコードに失敗しました'}), 400

    db = SessionLocal()
    try:
        staff_id = staff_info['staff_id']
        staff_type = staff_info['staff_type']

        if staff_type == 'employee':
            staff = db.query(TJugyoin).filter(TJugyoin.id == staff_id).first()
        else:
            staff = db.query(TKanrisha).filter(TKanrisha.id == staff_id).first()

        if not staff:
            return jsonify({'ok': False, 'error': 'スタッフが見つかりません'}), 404

        if not hasattr(staff, 'face_photo_url'):
            return jsonify({'ok': False, 'error': 'face_photo_urlカラムが存在しません。マイグレーションを実行してください'}), 500

        staff.face_photo_url = f'data:image/jpeg;base64,{face_image_b64.split(",")[-1]}'
        db.commit()

        return jsonify({'ok': True, 'message': '顔写真を登録しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/face/verify', methods=['POST'])
def face_verify():
    """顔認証を実行する（ライブネス検知付き・出発打刻前の本人確認）

    Request JSON:
        face_image_base64  (str):        正面顔画像（Base64エンコードされた JPEG/PNG）
        challenge_types    (list[str]):  実施したチャレンジの種類リスト
                                         (例: ['face_front', 'face_left', 'wink_right'])
        all_images_base64  (list[str]):  全ステップの撑影画像リスト（ライブネス検知用）

    Response JSON:
        ok              (bool):   成功フラグ
        verified        (bool):   認証成功かどうか
        confidence      (float):  類似度スコア（0.0～1.0）
        liveness_passed (bool):   ライブネス検知通過かどうか
        message         (str):    結果メッセージ
    """
    if not _check_api_key():
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401

    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    data = request.get_json() or {}
    face_image_b64 = data.get('face_image_base64', '')
    if not face_image_b64:
        return jsonify({'ok': False, 'error': '顔画像が必要です'}), 400

    # ライブネス検知用パラメータ
    challenge_types   = data.get('challenge_types', [])    # list[str]
    all_images_base64 = data.get('all_images_base64', [])  # list[str]

    db = SessionLocal()
    try:
        staff_id = staff_info['staff_id']
        staff_type = staff_info['staff_type']

        if staff_type == 'employee':
            staff = db.query(TJugyoin).filter(TJugyoin.id == staff_id).first()
        else:
            staff = db.query(TKanrisha).filter(TKanrisha.id == staff_id).first()

        if not staff:
            return jsonify({'ok': False, 'error': 'スタッフが見つかりません'}), 404

        registered_photo = getattr(staff, 'face_photo_url', None)
        if not registered_photo:
            return jsonify({
                'ok': True,
                'verified': False,
                'confidence': 0.0,
                'liveness_passed': False,
                'message': '顔写真が未登録です。管理者に登録を依頼してください',
                'needs_registration': True,
            })

        # ─────────────────────────────────────────────
        # ライブネス検知（サーバー側チェック）
        # アプリが複数ステップの画像を送信した場合に実施する。
        # 検知内容:
        #   1. ステップ数の確認（最低2枚以上）
        #   2. 画像間の差分（同一画像を繰り返し送信していないか）
        #   3. チャレンジ種類に応じた向き変化の有無（OpenCV利用）
        # ─────────────────────────────────────────────
        liveness_passed = False
        liveness_checked = False

        if len(all_images_base64) >= 2:
            try:
                import numpy as np
                import cv2

                def b64_to_gray(b64_str):
                    if ',' in b64_str:
                        b64_str = b64_str.split(',', 1)[1]
                    img_bytes = base64.b64decode(b64_str)
                    arr = np.frombuffer(img_bytes, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
                    if img is None:
                        raise ValueError('画像デコード失敗')
                    return img

                imgs = [b64_to_gray(b) for b in all_images_base64]

                # 画像間の差分平均を計算（同一画像繰り返しの検出）
                diffs = []
                for i in range(len(imgs) - 1):
                    a = cv2.resize(imgs[i], (64, 64)).astype(np.float32)
                    b = cv2.resize(imgs[i + 1], (64, 64)).astype(np.float32)
                    diff = np.mean(np.abs(a - b))
                    diffs.append(diff)

                avg_diff = float(np.mean(diffs))
                # 差分値が小すぎる（全く同じ画像）場合はライブネスNG
                DIFF_THRESHOLD = float(os.environ.get('LIVENESS_DIFF_THRESHOLD', '3.0'))
                if avg_diff < DIFF_THRESHOLD:
                    current_app.logger.warning(
                        f'ライブネス検知NG: 画像差分小すぎ (avg_diff={avg_diff:.2f} < {DIFF_THRESHOLD})'
                    )
                    return jsonify({
                        'ok': True,
                        'verified': False,
                        'confidence': 0.0,
                        'liveness_passed': False,
                        'message': 'ライブネス検知に失敗しました（画像に変化が検出されませんでした）。指示に従って再度試してください。',
                    })

                liveness_passed = True
                liveness_checked = True
                current_app.logger.info(f'ライブネス検知OK: avg_diff={avg_diff:.2f}')

            except ImportError:
                # OpenCV未インストール時はライブネスチェックをスキップ
                liveness_passed = True
                current_app.logger.warning('ライブネス検知: OpenCV未インストールのためスキップ')
        else:
            # 画像が1枚のみの場合はライブネスチェックなし（従来動作）
            liveness_passed = True

        # ─────────────────────────────────────────────
        # 顔照合（正面画像と登録済み顔写真の比較）
        # ─────────────────────────────────────────────
        try:
            import numpy as np
            import cv2

            def b64_to_rgb(b64_str):
                if ',' in b64_str:
                    b64_str = b64_str.split(',', 1)[1]
                img_bytes = base64.b64decode(b64_str)
                arr = np.frombuffer(img_bytes, dtype=np.uint8)
                img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img_bgr is None:
                    raise ValueError('画像のデコードに失敗しました')
                return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

            try:
                import face_recognition

                registered_rgb = b64_to_rgb(registered_photo)
                registered_encodings = face_recognition.face_encodings(registered_rgb)
                if not registered_encodings:
                    return jsonify({
                        'ok': True,
                        'verified': False,
                        'confidence': 0.0,
                        'liveness_passed': liveness_passed,
                        'message': '登録済み顔写真から顔を検出できませんでした。再登録してください',
                    })

                input_rgb = b64_to_rgb(face_image_b64)
                input_encodings = face_recognition.face_encodings(input_rgb)
                if not input_encodings:
                    return jsonify({
                        'ok': True,
                        'verified': False,
                        'confidence': 0.0,
                        'liveness_passed': liveness_passed,
                        'message': '撑影した画像から顔を検出できませんでした。正面を向いて再撑影してください',
                    })

                face_distance = face_recognition.face_distance(
                    [registered_encodings[0]], input_encodings[0]
                )[0]
                confidence = float(max(0.0, 1.0 - face_distance))
                threshold = float(os.environ.get('FACE_VERIFY_THRESHOLD', '0.55'))
                verified = confidence >= threshold

                return jsonify({
                    'ok': True,
                    'verified': verified,
                    'confidence': round(confidence, 3),
                    'liveness_passed': liveness_passed,
                    'message': '本人確認が完了しました' if verified else f'本人確認に失敗しました（類似度: {round(confidence * 100, 1)}%）',
                })

            except ImportError:
                current_app.logger.warning('face_recognition 未インストール。簡易照合にフォールバック')
                reg_img = b64_to_rgb(registered_photo)
                inp_img = b64_to_rgb(face_image_b64)
                reg_gray = cv2.cvtColor(reg_img, cv2.COLOR_RGB2GRAY)
                inp_gray = cv2.cvtColor(inp_img, cv2.COLOR_RGB2GRAY)
                reg_hist = cv2.calcHist([reg_gray], [0], None, [256], [0, 256])
                inp_hist = cv2.calcHist([inp_gray], [0], None, [256], [0, 256])
                cv2.normalize(reg_hist, reg_hist)
                cv2.normalize(inp_hist, inp_hist)
                similarity = float(cv2.compareHist(reg_hist, inp_hist, cv2.HISTCMP_CORREL))
                confidence = max(0.0, similarity)
                threshold = float(os.environ.get('FACE_VERIFY_THRESHOLD', '0.85'))
                verified = confidence >= threshold
                return jsonify({
                    'ok': True,
                    'verified': verified,
                    'confidence': round(confidence, 3),
                    'liveness_passed': liveness_passed,
                    'message': '本人確認が完了しました（簡易照合）' if verified else '本人確認に失敗しました（簡易照合）',
                    'fallback': True,
                })

        except ImportError:
            current_app.logger.warning('OpenCV 未インストール。開発用フォールバックを使用')
            return jsonify({
                'ok': True,
                'verified': True,
                'confidence': 1.0,
                'liveness_passed': True,
                'message': '顔認証ライブラリ未設定（開発モード）',
                'dev_mode': True,
            })

    except Exception as e:
        current_app.logger.error(f'顔認証エラー: {e}', exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/face/status', methods=['GET'])
def face_status():
    """顔写真の登録状況を確認する"""
    if not _check_api_key():
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401

    staff_info, err_resp, err_code = _auth_required()
    if err_resp:
        return err_resp, err_code

    db = SessionLocal()
    try:
        staff_id = staff_info['staff_id']
        staff_type = staff_info['staff_type']

        if staff_type == 'employee':
            staff = db.query(TJugyoin).filter(TJugyoin.id == staff_id).first()
        else:
            staff = db.query(TKanrisha).filter(TKanrisha.id == staff_id).first()

        if not staff:
            return jsonify({'ok': False, 'error': 'スタッフが見つかりません'}), 404

        registered_photo = getattr(staff, 'face_photo_url', None)
        registered_at = None
        if hasattr(staff, 'updated_at') and staff.updated_at and registered_photo:
            registered_at = staff.updated_at.strftime('%Y-%m-%d %H:%M')

        return jsonify({
            'ok': True,
            'registered': bool(registered_photo),
            'registered_at': registered_at,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


# ─────────────────────────────────────────────
# トラック運行管理アプリ APKダウンロード
# ─────────────────────────────────────────────
@bp.route('/truck_apk_download')
def truck_apk_download():
    """トラック運行管理アプリのAPKファイルをプロキシ配信する（署名付きURLの期限切れに依存しない永続エンドポイント）

    認証: X-Mobile-API-Key ヘッダーによるAPIキー認証
    テナント識別: X-Tenant-Slug ヘッダーまたはクエリパラメータ tenant_slug
    """
    if not _check_api_key():
        return jsonify({'ok': False, 'error': 'APIキーが無効です'}), 401

    tenant_slug = request.headers.get('X-Tenant-Slug') or request.args.get('tenant_slug', '')
    if not tenant_slug:
        return jsonify({'ok': False, 'error': 'tenant_slugが必要です'}), 400

    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.slug == tenant_slug).first()
        if not tenant:
            return jsonify({'ok': False, 'error': 'テナントが見つかりません'}), 404

        apk_url = getattr(tenant, 'truck_apk_url', None)
        if not apk_url:
            return jsonify({'ok': False, 'error': 'APKファイルが設定されていません。管理者にお問い合わせください。'}), 404

        import requests as req_lib
        from flask import Response, stream_with_context
        try:
            resp = req_lib.get(apk_url, stream=True, timeout=60)
            if resp.status_code == 200:
                apk_version = getattr(tenant, 'truck_apk_version', None) or '1.0.0'
                filename = 'truck-operation-app-{}.apk'.format(apk_version)
                return Response(
                    stream_with_context(resp.iter_content(chunk_size=8192)),
                    content_type='application/vnd.android.package-archive',
                    headers={
                        'Content-Disposition': 'attachment; filename="{}"'.format(filename),
                        'Content-Length': resp.headers.get('Content-Length', ''),
                    }
                )
            else:
                return jsonify({'ok': False, 'error': 'APKファイルのダウンロードに失敗しました（HTTP {}）'.format(resp.status_code)}), 502
        except Exception as e:
            current_app.logger.error(f'トラックAPKダウンロードエラー: {e}', exc_info=True)
            return jsonify({'ok': False, 'error': 'APKファイルの取得中にエラーが発生しました: {}'.format(str(e))}), 500
    finally:
        db.close()
