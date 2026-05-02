# -*- coding: utf-8 -*-
"""
飼い主向けアプリ Blueprint
/owner 以下のルートを担当
- 招待受付・本登録（パスワード設定）
- ログイン・ログアウト
- マイページ（犬一覧）
- 犬別ダッシュボード（体重グラフ・ワクチン・通院履歴）
- 健康ログ記録・状態更新
"""
from __future__ import annotations
import hashlib
import os
import secrets
from datetime import date, datetime, timedelta
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, jsonify
)

bp = Blueprint('owner', __name__, url_prefix='/owner')

# ─── ヘルパー ────────────────────────────────────────────────

def _get_db():
    from app.db import SessionLocal
    return SessionLocal()

def _hash_password(password: str) -> str:
    """SHA-256 + ランダムsaltでパスワードをハッシュ化"""
    salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"

def _verify_password(password: str, stored: str) -> bool:
    """パスワード検証"""
    try:
        salt, h = stored.split('$', 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    except Exception:
        return False

def _owner_login_required(f):
    """飼い主ログイン必須デコレータ"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('owner_id'):
            return redirect(url_for('owner.login'))
        return f(*args, **kwargs)
    return decorated

# ─── 招待受付（ブリーダーが発行したURLにアクセス） ─────────────

@bp.route('/invite/<token>')
def invite(token: str):
    """招待URL受付 → 本登録フォームへ"""
    db = _get_db()
    try:
        from app.models_breeder import Owner
        owner = db.query(Owner).filter(Owner.invite_token == token).first()
        if not owner:
            return render_template('owner/error.html', message='招待URLが無効です。')
        if owner.is_active:
            return redirect(url_for('owner.login'))
        if owner.invite_token_expires and owner.invite_token_expires < datetime.now():
            return render_template('owner/error.html', message='招待URLの有効期限が切れています。ブリーダーに再発行を依頼してください。')
        return render_template('owner/register.html', token=token, owner=owner)
    finally:
        db.close()

@bp.route('/register/<token>', methods=['POST'])
def register(token: str):
    """本登録処理（パスワード設定）"""
    db = _get_db()
    try:
        from app.models_breeder import Owner
        owner = db.query(Owner).filter(Owner.invite_token == token).first()
        if not owner or owner.is_active:
            flash('無効な招待URLです。', 'error')
            return redirect(url_for('owner.login'))
        if owner.invite_token_expires and owner.invite_token_expires < datetime.now():
            flash('招待URLの有効期限が切れています。', 'error')
            return redirect(url_for('owner.login'))

        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()

        if len(password) < 8:
            flash('パスワードは8文字以上で入力してください。', 'error')
            return render_template('owner/register.html', token=token, owner=owner)
        if password != password_confirm:
            flash('パスワードが一致しません。', 'error')
            return render_template('owner/register.html', token=token, owner=owner)

        # 名前・メール更新（フォームから上書き可能）
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        if name:
            owner.name = name
        if email:
            owner.email = email

        owner.password_hash = _hash_password(password)
        owner.is_active = 1
        owner.invite_token = None  # 使用済みトークンを削除
        owner.invite_token_expires = None
        db.commit()

        flash('登録が完了しました。ログインしてください。', 'success')
        return redirect(url_for('owner.login'))
    except Exception as e:
        db.rollback()
        flash('登録中にエラーが発生しました。', 'error')
        return render_template('owner/register.html', token=token, owner=owner)
    finally:
        db.close()

# ─── ログイン・ログアウト ─────────────────────────────────────

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """飼い主ログイン"""
    if session.get('owner_id'):
        return redirect(url_for('owner.mypage'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        db = _get_db()
        try:
            from app.models_breeder import Owner
            owner = db.query(Owner).filter(Owner.email == email).first()
            if not owner or not owner.is_active:
                flash('メールアドレスまたはパスワードが正しくありません。', 'error')
                return render_template('owner/login.html')
            if not owner.password_hash or not _verify_password(password, owner.password_hash):
                flash('メールアドレスまたはパスワードが正しくありません。', 'error')
                return render_template('owner/login.html')

            owner.last_login_at = datetime.now()
            db.commit()

            session['owner_id'] = owner.id
            session['owner_name'] = owner.name
            session['owner_tenant_id'] = owner.tenant_id
            return redirect(url_for('owner.mypage'))
        finally:
            db.close()

    return render_template('owner/login.html')

@bp.route('/logout')
def logout():
    """飼い主ログアウト"""
    session.pop('owner_id', None)
    session.pop('owner_name', None)
    session.pop('owner_tenant_id', None)
    flash('ログアウトしました。', 'info')
    return redirect(url_for('owner.login'))

# ─── マイページ（犬一覧） ─────────────────────────────────────

@bp.route('/')
@bp.route('/mypage')
@_owner_login_required
def mypage():
    """マイページ：自分の犬一覧"""
    db = _get_db()
    try:
        from app.models_breeder import Owner, OwnerDog, Dog, LifeStatus, VaccineSchedule
        owner_id = session['owner_id']
        owner = db.query(Owner).filter(Owner.id == owner_id).first()
        owner_dogs = db.query(OwnerDog).filter(OwnerDog.owner_id == owner_id).all()

        dog_list = []
        today = date.today()
        for od in owner_dogs:
            dog = db.query(Dog).filter(Dog.id == od.dog_id).first()
            if not dog:
                continue

            # 最新の生活状態
            latest_status = db.query(LifeStatus).filter(
                LifeStatus.owner_dog_id == od.id
            ).order_by(LifeStatus.status_date.desc()).first()

            # ワクチンアラート（期限切れ・直近）
            vaccine_alerts = db.query(VaccineSchedule).filter(
                VaccineSchedule.owner_dog_id == od.id,
                VaccineSchedule.completed == 0,
                VaccineSchedule.scheduled_date <= today + timedelta(days=30)
            ).count()

            dog_list.append({
                'owner_dog': od,
                'dog': dog,
                'status': latest_status.status if latest_status else 'healthy',
                'vaccine_alerts': vaccine_alerts,
            })

        return render_template('owner/mypage.html', owner=owner, dog_list=dog_list)
    finally:
        db.close()

# ─── 犬別ダッシュボード ───────────────────────────────────────

@bp.route('/dog/<int:owner_dog_id>')
@_owner_login_required
def dog_dashboard(owner_dog_id: int):
    """犬別ダッシュボード：体重グラフ・ワクチン・通院履歴"""
    db = _get_db()
    try:
        from app.models_breeder import OwnerDog, Dog, HealthLog, MedicalEvent, VaccineSchedule, LifeStatus
        owner_id = session['owner_id']
        od = db.query(OwnerDog).filter(
            OwnerDog.id == owner_dog_id,
            OwnerDog.owner_id == owner_id
        ).first()
        if not od:
            flash('アクセス権限がありません。', 'error')
            return redirect(url_for('owner.mypage'))

        dog = db.query(Dog).filter(Dog.id == od.dog_id).first()
        today = date.today()

        # 体重履歴（直近90日）
        weight_logs = db.query(HealthLog).filter(
            HealthLog.owner_dog_id == owner_dog_id,
            HealthLog.log_date >= today - timedelta(days=90),
            HealthLog.weight.isnot(None)
        ).order_by(HealthLog.log_date.asc()).all()
        weight_data = [
            {'date': str(log.log_date), 'weight': float(log.weight)}
            for log in weight_logs
        ]

        # ワクチンスケジュール
        vaccines = db.query(VaccineSchedule).filter(
            VaccineSchedule.owner_dog_id == owner_dog_id
        ).order_by(VaccineSchedule.scheduled_date.asc()).all()

        # 通院履歴（直近5件）
        medical_events = db.query(MedicalEvent).filter(
            MedicalEvent.owner_dog_id == owner_dog_id
        ).order_by(MedicalEvent.event_date.desc()).limit(5).all()

        # 最新の生活状態
        latest_status = db.query(LifeStatus).filter(
            LifeStatus.owner_dog_id == owner_dog_id
        ).order_by(LifeStatus.status_date.desc()).first()

        # 最新の健康ログ
        latest_health = db.query(HealthLog).filter(
            HealthLog.owner_dog_id == owner_dog_id
        ).order_by(HealthLog.log_date.desc()).first()

        # 年齢計算
        age_str = ''
        if dog and dog.birth_date:
            delta = today - dog.birth_date
            years = delta.days // 365
            months = (delta.days % 365) // 30
            if years > 0:
                age_str = f'{years}歳{months}ヶ月'
            else:
                age_str = f'{months}ヶ月'

        return render_template(
            'owner/dog_dashboard.html',
            owner_dog=od,
            dog=dog,
            age_str=age_str,
            weight_data=weight_data,
            vaccines=vaccines,
            medical_events=medical_events,
            latest_status=latest_status,
            latest_health=latest_health,
            today=today,
        )
    finally:
        db.close()

# ─── 健康ログ記録 ─────────────────────────────────────────────

@bp.route('/dog/<int:owner_dog_id>/health-log', methods=['GET', 'POST'])
@_owner_login_required
def health_log(owner_dog_id: int):
    """健康ログ記録フォーム"""
    db = _get_db()
    try:
        from app.models_breeder import OwnerDog, Dog, HealthLog
        owner_id = session['owner_id']
        od = db.query(OwnerDog).filter(
            OwnerDog.id == owner_dog_id,
            OwnerDog.owner_id == owner_id
        ).first()
        if not od:
            flash('アクセス権限がありません。', 'error')
            return redirect(url_for('owner.mypage'))

        dog = db.query(Dog).filter(Dog.id == od.dog_id).first()

        if request.method == 'POST':
            log = HealthLog(
                owner_dog_id=owner_dog_id,
                log_date=request.form.get('log_date') or date.today(),
                weight=request.form.get('weight') or None,
                food_type=request.form.get('food_type') or None,
                activity_level=request.form.get('activity_level') or None,
                appetite=request.form.get('appetite') or None,
                stool_condition=request.form.get('stool_condition') or None,
                notes=request.form.get('notes') or None,
            )
            db.add(log)
            db.commit()
            flash('健康ログを記録しました。', 'success')
            return redirect(url_for('owner.dog_dashboard', owner_dog_id=owner_dog_id))

        return render_template('owner/health_log.html', owner_dog=od, dog=dog, today=date.today())
    except Exception as e:
        db.rollback()
        flash('記録中にエラーが発生しました。', 'error')
        return redirect(url_for('owner.dog_dashboard', owner_dog_id=owner_dog_id))
    finally:
        db.close()

# ─── 通院履歴記録 ─────────────────────────────────────────────

@bp.route('/dog/<int:owner_dog_id>/medical', methods=['GET', 'POST'])
@_owner_login_required
def medical_event(owner_dog_id: int):
    """通院・医療イベント記録フォーム"""
    db = _get_db()
    try:
        from app.models_breeder import OwnerDog, Dog, MedicalEvent
        owner_id = session['owner_id']
        od = db.query(OwnerDog).filter(
            OwnerDog.id == owner_dog_id,
            OwnerDog.owner_id == owner_id
        ).first()
        if not od:
            flash('アクセス権限がありません。', 'error')
            return redirect(url_for('owner.mypage'))

        dog = db.query(Dog).filter(Dog.id == od.dog_id).first()

        if request.method == 'POST':
            event = MedicalEvent(
                owner_dog_id=owner_dog_id,
                event_date=request.form.get('event_date') or date.today(),
                category=request.form.get('category') or 'checkup',
                title=request.form.get('title', '').strip(),
                severity=request.form.get('severity') or 'mild',
                diagnosed_by_vet=1 if request.form.get('diagnosed_by_vet') else 0,
                treatment=request.form.get('treatment') or None,
                resolved=1 if request.form.get('resolved') else 0,
                notes=request.form.get('notes') or None,
            )
            db.add(event)
            db.commit()
            flash('通院履歴を記録しました。', 'success')
            return redirect(url_for('owner.dog_dashboard', owner_dog_id=owner_dog_id))

        return render_template('owner/medical_event.html', owner_dog=od, dog=dog, today=date.today())
    except Exception as e:
        db.rollback()
        flash('記録中にエラーが発生しました。', 'error')
        return redirect(url_for('owner.dog_dashboard', owner_dog_id=owner_dog_id))
    finally:
        db.close()

# ─── ワクチン完了登録 ─────────────────────────────────────────

@bp.route('/dog/<int:owner_dog_id>/vaccine/<int:vaccine_id>/complete', methods=['POST'])
@_owner_login_required
def vaccine_complete(owner_dog_id: int, vaccine_id: int):
    """ワクチン接種完了マーク"""
    db = _get_db()
    try:
        from app.models_breeder import OwnerDog, VaccineSchedule
        owner_id = session['owner_id']
        od = db.query(OwnerDog).filter(
            OwnerDog.id == owner_dog_id,
            OwnerDog.owner_id == owner_id
        ).first()
        if not od:
            return jsonify({'error': 'unauthorized'}), 403

        vaccine = db.query(VaccineSchedule).filter(
            VaccineSchedule.id == vaccine_id,
            VaccineSchedule.owner_dog_id == owner_dog_id
        ).first()
        if vaccine:
            vaccine.completed = 1
            vaccine.completed_date = date.today()
            db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()

# ─── データ共有設定 ───────────────────────────────────────────

@bp.route('/dog/<int:owner_dog_id>/sharing', methods=['GET', 'POST'])
@_owner_login_required
def sharing_settings(owner_dog_id: int):
    """ブリーダーへのデータ共有設定"""
    db = _get_db()
    try:
        from app.models_breeder import OwnerDog, Dog
        owner_id = session['owner_id']
        od = db.query(OwnerDog).filter(
            OwnerDog.id == owner_dog_id,
            OwnerDog.owner_id == owner_id
        ).first()
        if not od:
            flash('アクセス権限がありません。', 'error')
            return redirect(url_for('owner.mypage'))

        dog = db.query(Dog).filter(Dog.id == od.dog_id).first()

        if request.method == 'POST':
            od.share_health_data = 1 if request.form.get('share_health_data') else 0
            od.share_followup_data = 1 if request.form.get('share_followup_data') else 0
            db.commit()
            flash('共有設定を更新しました。', 'success')
            return redirect(url_for('owner.dog_dashboard', owner_dog_id=owner_dog_id))

        return render_template('owner/sharing_settings.html', owner_dog=od, dog=dog)
    finally:
        db.close()
