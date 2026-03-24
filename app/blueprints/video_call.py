"""
ビデオ通話ブループリント（Daily.co API使用）

プランごとの無料通話時間と超過課金：
- フリープラン: 無料時間なし、60分ごとに30円
- スタンダードプラン（3,000円）: 月3,000分無料、超過60分ごとに20円
- プロプラン（5,000円）: 月5,000分無料、超過60分ごとに15円
"""
import os
import uuid
import requests
from datetime import datetime, timezone
from flask import Blueprint, jsonify, session, request, render_template, redirect, url_for, flash
from sqlalchemy import and_
from app.db import SessionLocal
from app.models_clients import TClient, TVideoCallSession, TVideoCallUsage
from app.models_login import TTenant
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('video_call', __name__, url_prefix='/video_call')

DAILY_API_KEY = os.environ.get('DAILY_API_KEY', '')
DAILY_API_BASE = 'https://api.daily.co/v1'

# プランごとの設定
PLAN_CONFIG = {
    'free': {
        'free_minutes': 0,
        'charge_per_60min': 30,
    },
    'standard': {
        'free_minutes': 3000,
        'charge_per_60min': 20,
    },
    'pro': {
        'free_minutes': 5000,
        'charge_per_60min': 15,
    },
}


def get_tenant_plan(tenant_id):
    """テナントのプランを取得（現状はprofessionから判定、将来的にはplan列を追加）"""
    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        if not tenant:
            return 'free'
        # 将来的にはtenantのplanカラムを参照する
        # 現状はデフォルトでfreeを返す
        plan = getattr(tenant, 'plan', None) or 'free'
        return plan
    finally:
        db.close()


def get_or_create_usage(db, tenant_id, year_month):
    """月次利用量レコードを取得または作成"""
    usage = db.query(TVideoCallUsage).filter(
        and_(
            TVideoCallUsage.tenant_id == tenant_id,
            TVideoCallUsage.year_month == year_month
        )
    ).first()
    if not usage:
        usage = TVideoCallUsage(
            tenant_id=tenant_id,
            year_month=year_month,
            used_minutes=0,
            extra_charge=0
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)
    return usage


def calculate_extra_charge(plan, used_minutes, free_minutes, charge_per_60min):
    """超過課金を計算"""
    if used_minutes <= free_minutes:
        return 0
    extra_minutes = used_minutes - free_minutes
    # 60分ごとに課金（端数切り上げ）
    import math
    extra_blocks = math.ceil(extra_minutes / 60)
    return extra_blocks * charge_per_60min


def create_daily_room(room_name, expire_minutes=120):
    """Daily.coにルームを作成"""
    import time
    exp = int(time.time()) + expire_minutes * 60
    headers = {
        'Authorization': f'Bearer {DAILY_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        'name': room_name,
        'properties': {
            'exp': exp,
            'enable_chat': True,
            'enable_screenshare': True,
            'start_video_off': False,
            'start_audio_off': False,
        }
    }
    resp = requests.post(f'{DAILY_API_BASE}/rooms', json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def delete_daily_room(room_name):
    """Daily.coのルームを削除"""
    headers = {
        'Authorization': f'Bearer {DAILY_API_KEY}',
    }
    try:
        requests.delete(f'{DAILY_API_BASE}/rooms/{room_name}', headers=headers, timeout=10)
    except Exception:
        pass


def create_meeting_token(room_name, is_owner=True):
    """Daily.coのミーティングトークンを生成"""
    import time
    exp = int(time.time()) + 3 * 60 * 60  # 3時間有効
    headers = {
        'Authorization': f'Bearer {DAILY_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        'properties': {
            'room_name': room_name,
            'is_owner': is_owner,
            'exp': exp,
        }
    }
    resp = requests.post(f'{DAILY_API_BASE}/meeting-tokens', json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get('token')


@bp.route('/start/<int:client_id>', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def start_call(client_id):
    """ビデオ通話を開始（Daily.coルームを作成してトークンを返す）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    db = SessionLocal()
    try:
        # 顧問先の確認
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            return jsonify({'error': '顧問先が見つかりません'}), 404

        # ルーム名を生成（ユニーク）
        room_name = f"samurai-{tenant_id}-{client_id}-{uuid.uuid4().hex[:8]}"

        # Daily.coにルームを作成
        room_data = create_daily_room(room_name)
        room_url = room_data.get('url')

        # 事務所側のトークン（オーナー権限）
        host_token = create_meeting_token(room_name, is_owner=True)
        # 顧問先側のトークン（参加者権限）
        guest_token = create_meeting_token(room_name, is_owner=False)

        # DBにセッションを記録
        call_session = TVideoCallSession(
            tenant_id=tenant_id,
            client_id=client_id,
            room_name=room_name,
            room_url=room_url,
            started_at=datetime.now(timezone.utc),
            status='active'
        )
        db.add(call_session)
        db.commit()
        db.refresh(call_session)

        # 顧問先への招待URL（トークン付き）
        guest_url = f"{room_url}?t={guest_token}"

        return jsonify({
            'success': True,
            'session_id': call_session.id,
            'room_url': room_url,
            'host_token': host_token,
            'guest_url': guest_url,
            'client_name': client.name,
        })

    except requests.HTTPError as e:
        db.rollback()
        return jsonify({'error': f'Daily.co APIエラー: {str(e)}'}), 500
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/end/<int:session_id>', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def end_call(session_id):
    """ビデオ通話を終了（通話時間を記録して課金計算）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    db = SessionLocal()
    try:
        call_session = db.query(TVideoCallSession).filter(
            and_(
                TVideoCallSession.id == session_id,
                TVideoCallSession.tenant_id == tenant_id
            )
        ).first()
        if not call_session:
            return jsonify({'error': 'セッションが見つかりません'}), 404

        if call_session.status == 'ended':
            return jsonify({'error': '既に終了しています'}), 400

        # 通話時間を計算
        now = datetime.now(timezone.utc)
        started_at = call_session.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        duration_seconds = int((now - started_at).total_seconds())
        duration_minutes = max(1, (duration_seconds + 59) // 60)  # 端数切り上げ（最低1分）

        # セッションを更新
        call_session.ended_at = now
        call_session.duration_minutes = duration_minutes
        call_session.status = 'ended'

        # 月次利用量を更新
        year_month = now.strftime('%Y-%m')
        usage = get_or_create_usage(db, tenant_id, year_month)
        usage.used_minutes = (usage.used_minutes or 0) + duration_minutes

        # プランに応じた課金計算
        plan = get_tenant_plan(tenant_id)
        plan_cfg = PLAN_CONFIG.get(plan, PLAN_CONFIG['free'])
        total_charge = calculate_extra_charge(
            plan,
            usage.used_minutes,
            plan_cfg['free_minutes'],
            plan_cfg['charge_per_60min']
        )
        usage.extra_charge = total_charge

        # Daily.coのルームを削除（コスト節約）
        delete_daily_room(call_session.room_name)

        db.commit()

        return jsonify({
            'success': True,
            'duration_minutes': duration_minutes,
            'used_minutes_this_month': usage.used_minutes,
            'extra_charge': usage.extra_charge,
            'plan': plan,
        })

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/usage', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def get_usage():
    """今月のビデオ通話利用量を取得"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    db = SessionLocal()
    try:
        year_month = datetime.now().strftime('%Y-%m')
        usage = db.query(TVideoCallUsage).filter(
            and_(
                TVideoCallUsage.tenant_id == tenant_id,
                TVideoCallUsage.year_month == year_month
            )
        ).first()

        plan = get_tenant_plan(tenant_id)
        plan_cfg = PLAN_CONFIG.get(plan, PLAN_CONFIG['free'])
        used_minutes = usage.used_minutes if usage else 0
        extra_charge = usage.extra_charge if usage else 0

        return jsonify({
            'year_month': year_month,
            'plan': plan,
            'free_minutes': plan_cfg['free_minutes'],
            'used_minutes': used_minutes,
            'remaining_free_minutes': max(0, plan_cfg['free_minutes'] - used_minutes),
            'extra_charge': extra_charge,
            'charge_per_60min': plan_cfg['charge_per_60min'],
        })
    finally:
        db.close()


@bp.route('/history/<int:client_id>', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def call_history(client_id):
    """顧問先の通話履歴を取得"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    db = SessionLocal()
    try:
        sessions = db.query(TVideoCallSession).filter(
            and_(
                TVideoCallSession.tenant_id == tenant_id,
                TVideoCallSession.client_id == client_id,
                TVideoCallSession.status == 'ended'
            )
        ).order_by(TVideoCallSession.started_at.desc()).limit(20).all()

        history = []
        for s in sessions:
            history.append({
                'id': s.id,
                'started_at': s.started_at.strftime('%Y/%m/%d %H:%M') if s.started_at else '',
                'duration_minutes': s.duration_minutes or 0,
            })

        return jsonify({'history': history})
    finally:
        db.close()
