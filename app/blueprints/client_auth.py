"""
クライアント（顧問先）認証ブループリント
- ログイン / ログアウト
- 招待リンクからのアカウント登録
"""
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import SessionLocal
from app.models_client_users import TClientUser, TClientInvitation
from app.models_clients import TClient

bp = Blueprint('client_auth', __name__, url_prefix='/client')


# ===========================
# ログイン
# ===========================
@bp.route('/login', methods=['GET', 'POST'])
def login():
    """クライアントログイン画面"""
    # すでにログイン済みならマイページへ
    if session.get('role') in ('client_admin', 'client_employee'):
        return redirect(url_for('client_mypage.dashboard'))

    error = None
    if request.method == 'POST':
        login_id = (request.form.get('login_id') or '').strip()
        password = request.form.get('password') or ''

        if not login_id or not password:
            error = 'ログインIDとパスワードを入力してください。'
        else:
            db = SessionLocal()
            try:
                user = db.query(TClientUser).filter(
                    TClientUser.login_id == login_id,
                    TClientUser.active == 1
                ).first()

                if user and user.password_hash and check_password_hash(user.password_hash, password):
                    # クライアント情報も取得
                    client = db.query(TClient).filter(TClient.id == user.client_id).first()
                    # セッションに保存
                    session.clear()
                    session['role'] = user.role
                    session['user_id'] = user.id
                    session['user_name'] = user.name
                    session['client_id'] = user.client_id
                    session['client_name'] = client.name if client else ''
                    session['tenant_id'] = client.tenant_id if client else None
                    return redirect(url_for('client_mypage.dashboard'))
                else:
                    error = 'ログインIDまたはパスワードが正しくありません。'
            finally:
                db.close()

    return render_template('client_login.html', error=error)


# ===========================
# ログアウト
# ===========================
@bp.route('/logout')
def logout():
    """クライアントログアウト"""
    session.clear()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('client_auth.login'))


# ===========================
# 招待リンクからの登録
# ===========================
@bp.route('/invite/<token>', methods=['GET', 'POST'])
def accept_invite(token):
    """招待リンクからアカウント登録"""
    db = SessionLocal()
    try:
        invitation = db.query(TClientInvitation).filter(
            TClientInvitation.token == token,
            TClientInvitation.used == 0
        ).first()

        if not invitation:
            flash('この招待リンクは無効または使用済みです。', 'error')
            return redirect(url_for('client_auth.login'))

        # 有効期限チェック
        if invitation.expires_at and invitation.expires_at < datetime.utcnow():
            flash('この招待リンクは期限切れです。', 'error')
            return redirect(url_for('client_auth.login'))

        client = db.query(TClient).filter(TClient.id == invitation.client_id).first()
        if not client:
            flash('顧問先情報が見つかりません。', 'error')
            return redirect(url_for('client_auth.login'))

        error = None
        if request.method == 'POST':
            login_id = (request.form.get('login_id') or '').strip()
            name = (request.form.get('name') or '').strip()
            email = (request.form.get('email') or invitation.email or '').strip()
            password = request.form.get('password') or ''
            confirm = request.form.get('confirm') or ''

            if not login_id or not name or not email or not password or not confirm:
                error = 'すべての項目を入力してください。'
            elif len(password) < 8:
                error = 'パスワードは8文字以上にしてください。'
            elif password != confirm:
                error = 'パスワード（確認）が一致しません。'
            else:
                # ログインID重複チェック
                existing = db.query(TClientUser).filter(
                    TClientUser.login_id == login_id
                ).first()
                if existing:
                    error = 'このログインIDはすでに使用されています。'
                else:
                    # アカウント作成
                    new_user = TClientUser(
                        client_id=invitation.client_id,
                        login_id=login_id,
                        name=name,
                        email=email,
                        password_hash=generate_password_hash(password),
                        role=invitation.role,
                        active=1
                    )
                    db.add(new_user)
                    # 招待を使用済みにする
                    invitation.used = 1
                    db.commit()
                    flash('アカウントを作成しました。ログインしてください。', 'success')
                    return redirect(url_for('client_auth.login'))

        return render_template(
            'client_register.html',
            token=token,
            client=client,
            invitation=invitation,
            error=error
        )
    finally:
        db.close()
