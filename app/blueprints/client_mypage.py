"""
クライアント（顧問先）マイページブループリント
- ダッシュボード
- チャット
- ファイル共有
- 会社基本情報（管理者のみ編集）
- 従業員管理（管理者のみ）
"""
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import SessionLocal
from app.models_client_users import TClientUser, TClientInvitation
from app.models_clients import TClient, TMessage, TFile, TMessageRead
from sqlalchemy import func
from app.utils.tenant_storage_adapter import get_storage_adapter

bp = Blueprint('client_mypage', __name__, url_prefix='/mypage')


# ===========================
# デコレータ
# ===========================
def require_client_login(f):
    """クライアントログイン必須デコレータ"""
    @wraps(f)
    def decorated(*args, **kwargs):
        role = session.get('role')
        if role not in ('client_admin', 'client_employee'):
            flash('ログインが必要です。', 'warning')
            return redirect(url_for('client_auth.login'))
        return f(*args, **kwargs)
    return decorated


def require_client_admin(f):
    """クライアント管理者のみアクセス可能デコレータ"""
    @wraps(f)
    def decorated(*args, **kwargs):
        role = session.get('role')
        if role != 'client_admin':
            flash('この操作には管理者権限が必要です。', 'warning')
            return redirect(url_for('client_mypage.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ===========================
# ダッシュボード
# ===========================
@bp.route('/')
@require_client_login
def dashboard():
    """クライアントマイページ ダッシュボード"""
    client_id = session.get('client_id')
    reader_id = session.get('login_id', '')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        # 未読メッセージ数（staff=税理士側が送ったメッセージのうち未読のもの）
        all_staff_msgs = db.query(TMessage).filter(
            TMessage.client_id == client_id,
            TMessage.sender_type == 'staff'
        ).all()
        read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'client',
            TMessageRead.reader_id == reader_id
        ).all()}
        unread_count = sum(1 for m in all_staff_msgs if m.id not in read_ids)
        # 最近のメッセージ（最新5件）
        recent_messages = db.query(TMessage).filter(
            TMessage.client_id == client_id
        ).order_by(TMessage.timestamp.desc()).limit(5).all()
        # 最近のファイル（最新5件）
        recent_files = db.query(TFile).filter(
            TFile.client_id == client_id
        ).order_by(TFile.timestamp.desc()).limit(5).all()
        return render_template(
            'client_mypage_dashboard.html',
            client=client,
            recent_messages=recent_messages,
            recent_files=recent_files,
            unread_count=unread_count
        )
    finally:
        db.close()


# ===========================
# チャット
# ===========================
@bp.route('/chat', methods=['GET', 'POST'])
@require_client_login
def chat():
    """クライアントチャット"""
    client_id = session.get('client_id')
    user_name = session.get('user_name', '匿名')
    reader_id = session.get('login_id', '')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        if request.method == 'POST':
            message_text = (request.form.get('message') or '').strip()
            if message_text:
                new_msg = TMessage(
                    client_id=client_id,
                    sender=user_name,
                    sender_type='client',
                    message=message_text
                )
                db.add(new_msg)
                db.commit()
            return redirect(url_for('client_mypage.chat'))

        messages = db.query(TMessage).filter(
            TMessage.client_id == client_id
        ).order_by(TMessage.timestamp.asc()).all()

        # 既読済みメッセージIDセット
        read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'client',
            TMessageRead.reader_id == reader_id
        ).all()}

        # staff側の未読メッセージを既読に登録（ページを開いたら全て既読）
        first_unread_id = None
        for msg in messages:
            if msg.sender_type == 'staff' and msg.id not in read_ids:
                if first_unread_id is None:
                    first_unread_id = msg.id
                db.add(TMessageRead(
                    message_id=msg.id,
                    reader_type='client',
                    reader_id=reader_id
                ))
        db.commit()

        return render_template(
            'client_mypage_chat.html',
            client=client,
            messages=messages,
            read_ids=read_ids,
            first_unread_id=first_unread_id
        )
    finally:
        db.close()


# ===========================
# ファイル共有
# ===========================
@bp.route('/files', methods=['GET', 'POST'])
@require_client_login
def files():
    """クライアントファイル共有"""
    client_id = session.get('client_id')
    tenant_id = session.get('tenant_id')
    user_name = session.get('user_name', '匿名')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()

        if request.method == 'POST':
            f = request.files.get('file')
            if f and f.filename:
                try:
                    adapter = get_storage_adapter(tenant_id)
                    file_url = adapter.upload(f, client_id)
                    new_file = TFile(
                        client_id=client_id,
                        filename=f.filename,
                        file_url=file_url,
                        uploader=user_name
                    )
                    db.add(new_file)
                    db.commit()
                    flash('ファイルをアップロードしました。', 'success')
                except Exception as e:
                    flash(f'アップロードエラー: {str(e)}', 'error')
            else:
                flash('ファイルを選択してください。', 'warning')
            return redirect(url_for('client_mypage.files'))

        file_list = db.query(TFile).filter(
            TFile.client_id == client_id
        ).order_by(TFile.timestamp.desc()).all()
        return render_template(
            'client_mypage_files.html',
            client=client,
            files=file_list
        )
    finally:
        db.close()


# ===========================
# 会社基本情報
# ===========================
@bp.route('/company', methods=['GET', 'POST'])
@require_client_login
def company():
    """会社基本情報（管理者のみ編集可能）"""
    from app.models_company import TCompanyInfo
    client_id = session.get('client_id')
    role = session.get('role')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        company_info = db.query(TCompanyInfo).filter(
            TCompanyInfo.顧問先ID == client_id
        ).first()

        if request.method == 'POST':
            # 管理者のみ編集可能
            if role != 'client_admin':
                flash('会社基本情報の編集には管理者権限が必要です。', 'error')
                return redirect(url_for('client_mypage.company'))

            fields = [
                '会社名', '郵便番号', '都道府県', '市区町村番地',
                '建物名部屋番号', '電話番号1', '電話番号2',
                'ファックス番号', 'メールアドレス', '担当者名', '業種', '法人番号'
            ]
            従業員数_raw = request.form.get('従業員数') or None
            従業員数 = int(従業員数_raw) if 従業員数_raw and 従業員数_raw.isdigit() else None

            if company_info:
                for field in fields:
                    setattr(company_info, field, request.form.get(field) or None)
                company_info.従業員数 = 従業員数
            else:
                company_info = TCompanyInfo(顧問先ID=client_id)
                for field in fields:
                    setattr(company_info, field, request.form.get(field) or None)
                company_info.従業員数 = 従業員数
                db.add(company_info)
            db.commit()
            flash('会社基本情報を更新しました。', 'success')
            return redirect(url_for('client_mypage.company'))

        return render_template(
            'client_mypage_company.html',
            client=client,
            company_info=company_info,
            can_edit=(role == 'client_admin')
        )
    finally:
        db.close()


# ===========================
# 従業員管理（管理者のみ）
# ===========================
@bp.route('/members')
@require_client_login
@require_client_admin
def members():
    """クライアント従業員一覧"""
    client_id = session.get('client_id')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        users = db.query(TClientUser).filter(
            TClientUser.client_id == client_id
        ).order_by(TClientUser.id.asc()).all()
        return render_template(
            'client_mypage_members.html',
            client=client,
            users=users
        )
    finally:
        db.close()


@bp.route('/members/invite', methods=['GET', 'POST'])
@require_client_login
@require_client_admin
def invite_member():
    """メンバー招待"""
    client_id = session.get('client_id')
    user_id = session.get('user_id')
    role = session.get('role')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        invite_url = None
        if request.method == 'POST':
            email = (request.form.get('email') or '').strip()
            invite_role = request.form.get('role') or 'client_employee'
            if invite_role not in ('client_admin', 'client_employee'):
                invite_role = 'client_employee'

            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(days=7)
            invitation = TClientInvitation(
                client_id=client_id,
                token=token,
                email=email if email else None,
                role=invite_role,
                invited_by_role=role,
                invited_by_id=user_id,
                used=0,
                expires_at=expires_at
            )
            db.add(invitation)
            db.commit()
            invite_url = url_for('client_auth.accept_invite', token=token, _external=True)
            flash(f'招待リンクを作成しました。有効期限: 7日間', 'success')

        return render_template(
            'client_mypage_invite.html',
            client=client,
            invite_url=invite_url
        )
    finally:
        db.close()


@bp.route('/members/<int:user_id>/toggle', methods=['POST'])
@require_client_login
@require_client_admin
def toggle_member(user_id):
    """メンバーの有効/無効切り替え"""
    client_id = session.get('client_id')
    current_user_id = session.get('user_id')
    db = SessionLocal()
    try:
        user = db.query(TClientUser).filter(
            TClientUser.id == user_id,
            TClientUser.client_id == client_id
        ).first()
        if not user:
            flash('ユーザーが見つかりません。', 'error')
        elif user.id == current_user_id:
            flash('自分自身を無効にすることはできません。', 'error')
        else:
            user.active = 0 if user.active == 1 else 1
            db.commit()
            status = '有効' if user.active == 1 else '無効'
            flash(f'{user.name} を{status}にしました。', 'success')
    finally:
        db.close()
    return redirect(url_for('client_mypage.members'))


# ===========================
# アカウント設定
# ===========================
@bp.route('/account', methods=['GET', 'POST'])
@require_client_login
def account_settings():
    """ログインID・パスワード変更"""
    user_id = session.get('user_id')
    client_id = session.get('client_id')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        user = db.query(TClientUser).filter(TClientUser.id == user_id).first()
        if not user:
            flash('ユーザーが見つかりません。', 'error')
            return redirect(url_for('client_mypage.dashboard'))

        if request.method == 'POST':
            action = request.form.get('action')

            # ログインID変更
            if action == 'change_login_id':
                new_login_id = (request.form.get('new_login_id') or '').strip()
                current_password = request.form.get('current_password_id') or ''
                if not new_login_id:
                    flash('新しいログインIDを入力してください。', 'error')
                elif not check_password_hash(user.password_hash, current_password):
                    flash('現在のパスワードが正しくありません。', 'error')
                else:
                    # 重複チェック
                    existing = db.query(TClientUser).filter(
                        TClientUser.login_id == new_login_id,
                        TClientUser.id != user_id
                    ).first()
                    if existing:
                        flash('そのログインIDはすでに使用されています。', 'error')
                    else:
                        user.login_id = new_login_id
                        db.commit()
                        session['login_id'] = new_login_id
                        flash('ログインIDを変更しました。', 'success')

            # メールアドレス変更
            elif action == 'change_email':
                new_email = (request.form.get('new_email') or '').strip()
                current_password = request.form.get('current_password_email') or ''
                if not new_email:
                    flash('新しいメールアドレスを入力してください。', 'error')
                elif not check_password_hash(user.password_hash, current_password):
                    flash('現在のパスワードが正しくありません。', 'error')
                else:
                    user.email = new_email
                    db.commit()
                    flash('メールアドレスを変更しました。', 'success')

            # パスワード変更
            elif action == 'change_password':
                current_password = request.form.get('current_password') or ''
                new_password = request.form.get('new_password') or ''
                confirm_password = request.form.get('confirm_password') or ''
                if not check_password_hash(user.password_hash, current_password):
                    flash('現在のパスワードが正しくありません。', 'error')
                elif len(new_password) < 8:
                    flash('新しいパスワードは8文字以上で入力してください。', 'error')
                elif new_password != confirm_password:
                    flash('新しいパスワードと確認用パスワードが一致しません。', 'error')
                else:
                    user.password_hash = generate_password_hash(new_password)
                    db.commit()
                    flash('パスワードを変更しました。', 'success')

            return redirect(url_for('client_mypage.account_settings'))

        return render_template(
            'client_mypage_account.html',
            client=client,
            user=user
        )
    finally:
        db.close()
