# -*- coding: utf-8 -*-
"""
アプリ管理者ダッシュボード（税理士事務所などのアプリ配布者用）
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash
from app.db import SessionLocal
from app.models_login import TKanrisha, TAppManagerGroup
from ..utils.decorators import require_roles

bp = Blueprint('app_manager', __name__, url_prefix='/app_manager')


def can_manage_app_managers():
    """現在のユーザーがアプリ管理者管理権限を持つかどうかを判定"""
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id:
        return False
    
    # システム管理者は全権限を持つ
    if role == 'system_admin':
        return True
    
    db = SessionLocal()
    try:
        user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        return user and user.role == 'app_manager' and (user.is_owner == 1 or user.can_manage_admins == 1)
    finally:
        db.close()


def is_owner():
    """現在のユーザーがオーナーかどうかを判定"""
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id:
        return False
    
    # システム管理者は全権限を持つ
    if role == 'system_admin':
        return True
    
    db = SessionLocal()
    try:
        user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        return user and user.role == 'app_manager' and user.is_owner == 1
    finally:
        db.close()


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """アプリ管理者ログイン"""
    if request.method == 'GET':
        return render_template('app_manager_login.html')
    
    login_id = request.form.get('login_id', '').strip()
    password = request.form.get('password', '')
    
    if not login_id or not password:
        flash('ログインIDとパスワードを入力してください', 'error')
        return render_template('app_manager_login.html')
    
    db = SessionLocal()
    try:
        admin = db.query(TKanrisha).filter(
            TKanrisha.login_id == login_id,
            TKanrisha.role == 'app_manager'
        ).first()
        
        if not admin:
            flash('ログインIDまたはパスワードが正しくありません', 'error')
            return render_template('app_manager_login.html')
        
        if admin.active != 1:
            flash('このアカウントは無効化されています', 'error')
            return render_template('app_manager_login.html')
        
        if not check_password_hash(admin.password_hash, password):
            flash('ログインIDまたはパスワードが正しくありません', 'error')
            return render_template('app_manager_login.html')
        
        # セッション設定
        session.clear()  # 既存セッションをクリア
        session['user_id'] = admin.id
        session['role'] = 'app_manager'
        session['user_name'] = admin.name
        session['login_id'] = admin.login_id
        session['app_manager_group_id'] = admin.app_manager_group_id
        session.permanent = True  # セッションを永続化
        
        flash(f'{admin.name}さん、ようこそ!', 'success')
        return redirect(url_for('app_manager.mypage'))
        
    finally:
        db.close()


@bp.route('/logout')
def logout():
    """ログアウト"""
    session.clear()
    flash('ログアウトしました', 'info')
    return redirect(url_for('auth.select_login'))


@bp.route('/')
@require_roles('app_manager', 'system_admin')
def index():
    """アプリ管理者トップページ（ダッシュボードへリダイレクト）"""
    return redirect(url_for('app_manager.dashboard'))


@bp.route('/dashboard')
@require_roles('app_manager', 'system_admin')
def dashboard():
    """アプリ管理者ダッシュボード"""
    role = session.get('role')
    group_id = session.get('app_manager_group_id')
    
    if not group_id:
        flash('アプリ管理者グループが選択されていません', 'error')
        return redirect(url_for('system_admin.mypage') if role == 'system_admin' else url_for('app_manager.login'))
    
    db = SessionLocal()
    try:
        # グループ情報を取得
        group = db.query(TAppManagerGroup).filter(
            TAppManagerGroup.id == group_id
        ).first()
        
        if not group:
            flash('グループが見つかりません', 'error')
            return redirect(url_for('system_admin.mypage') if role == 'system_admin' else url_for('app_manager.login'))
        
        # ユーザー情報を取得
        user_id = session.get('user_id')
        app_manager = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()

        # プラン・利用アプリ数を計算
        from app.blueprints.tenant_admin import AVAILABLE_APPS
        import json
        total_app_count = len(AVAILABLE_APPS)
        if group.plan == 'unlimited':
            enabled_app_count = total_app_count
        elif group.enabled_apps:
            try:
                enabled_app_ids = json.loads(group.enabled_apps)
                enabled_app_count = len(enabled_app_ids)
            except Exception:
                enabled_app_count = 0
        else:
            enabled_app_count = 0

        return render_template(
            'app_manager_dashboard.html',
            app_manager=app_manager,
            group=group,
            is_system_admin_view=(role == 'system_admin'),
            enabled_app_count=enabled_app_count,
            total_app_count=total_app_count
        )
    finally:
        db.close()


@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles('app_manager')
def mypage():
    """アプリ管理者マイページ"""
    user_id = session.get('user_id')
    
    db = SessionLocal()
    try:
        from app.models_login import TTenant, TTenpo
        
        # ユーザー情報を取得
        app_manager = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        if not app_manager:
            return redirect(url_for('app_manager.login'))
        
        # 所属グループ情報を取得
        group = None
        if app_manager.app_manager_group_id:
            group = db.query(TAppManagerGroup).filter(
                TAppManagerGroup.id == app_manager.app_manager_group_id
            ).first()
        
        # ユーザー情報を整形
        user = {
            'id': app_manager.id,
            'login_id': app_manager.login_id,
            'name': app_manager.name,
            'email': app_manager.email,
            'role': 'app_manager',
            'group_name': group.group_name if group else '未所属',
            'group_id': app_manager.app_manager_group_id,
            'created_at': app_manager.created_at,
            'updated_at': app_manager.updated_at
        }
        
        # テナント・店舗リストを取得（アプリ管理者は全テナント・店舗にアクセス可能）
        tenant_list = [{'id': t.id, 'name': t.名称} for t in db.query(TTenant).filter(TTenant.有効 == 1).order_by(TTenant.id).all()]
        store_list = []
        for s in db.query(TTenpo).filter(TTenpo.有効 == 1).order_by(TTenpo.tenant_id, TTenpo.id).all():
            tenant = db.query(TTenant).filter(TTenant.id == s.tenant_id).first()
            store_list.append({
                'id': s.id,
                'name': s.名称,
                'tenant_id': s.tenant_id,
                'tenant_name': tenant.名称 if tenant else ''
            })
        
        # アプリ管理者グループのAPIキーを取得
        group_api = None
        if group:
            group_api = {
                'openai_api_key': getattr(group, 'openai_api_key', None) or '',
                'google_vision_api_key': getattr(group, 'google_vision_api_key', None) or '',
                'google_api_key': getattr(group, 'google_api_key', None) or '',
                'anthropic_api_key': getattr(group, 'anthropic_api_key', None) or '',
                'azure_document_intelligence_endpoint': getattr(group, 'azure_document_intelligence_endpoint', None) or '',
                'azure_document_intelligence_key': getattr(group, 'azure_document_intelligence_key', None) or '',
            }
        
        # POSTリクエスト（APIキー更新）
        if request.method == 'POST':
            action = request.form.get('action', '')
            if action == 'update_api_keys':
                openai_api_key = request.form.get('openai_api_key', '').strip() or None
                google_vision_api_key = request.form.get('google_vision_api_key', '').strip() or None
                google_api_key = request.form.get('google_api_key', '').strip() or None
                anthropic_api_key = request.form.get('anthropic_api_key', '').strip() or None
                azure_document_intelligence_endpoint = request.form.get('azure_document_intelligence_endpoint', '').strip() or None
                azure_document_intelligence_key = request.form.get('azure_document_intelligence_key', '').strip() or None
                
                if group:
                    group.openai_api_key = openai_api_key
                    if hasattr(group, 'google_vision_api_key'):
                        group.google_vision_api_key = google_vision_api_key
                    if hasattr(group, 'google_api_key'):
                        group.google_api_key = google_api_key
                    if hasattr(group, 'anthropic_api_key'):
                        group.anthropic_api_key = anthropic_api_key
                    if hasattr(group, 'azure_document_intelligence_endpoint'):
                        group.azure_document_intelligence_endpoint = azure_document_intelligence_endpoint
                    if hasattr(group, 'azure_document_intelligence_key'):
                        group.azure_document_intelligence_key = azure_document_intelligence_key
                    db.commit()
                    flash('APIキー設定を更新しました', 'success')
                else:
                    flash('グループ情報が見つかりません', 'error')
                return redirect(url_for('app_manager.mypage'))
        
        return render_template(
            'app_manager_mypage.html',
            user=user,
            tenant_list=tenant_list,
            store_list=store_list,
            group_api=group_api
        )
    finally:
        db.close()


@bp.route('/mypage/edit_profile', methods=['GET', 'POST'])
@require_roles('app_manager')
def edit_profile():
    """プロフィール編集"""
    user_id = session.get('user_id')
    
    if request.method == 'GET':
        return render_template('app_manager_mypage_edit_profile.html', app_manager=app_manager)
    
    # POST処理
    login_id = request.form.get('login_id', '').strip()
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    
    if not login_id or not name or not email:
        flash('すべての項目を入力してください', 'error')
        return render_template('app_manager_mypage_edit_profile.html', app_manager=app_manager)
    
    db = SessionLocal()
    try:
        # ログインIDの重複チェック（自分以外）
        existing = db.query(TKanrisha).filter(
            TKanrisha.login_id == login_id,
            TKanrisha.id != app_manager.id
        ).first()
        
        if existing:
            flash('このログインIDは既に使用されています', 'error')
            return render_template('app_manager_mypage_edit_profile.html', app_manager=app_manager)
        
        # 更新
        current_admin = db.query(TKanrisha).filter(TKanrisha.id == app_manager.id).first()
        current_admin.login_id = login_id
        current_admin.name = name
        current_admin.email = email
        db.commit()
        
        # セッション更新
        session['login_id'] = login_id
        session['user_name'] = name
        
        flash('プロフィールを更新しました', 'success')
        return redirect(url_for('app_manager.mypage'))
        
    finally:
        db.close()


@bp.route('/mypage/change_password', methods=['GET', 'POST'])
@require_roles('app_manager')
def change_password():
    """パスワード変更"""
    user_id = session.get('user_id')
    
    if request.method == 'GET':
        return render_template('app_manager_mypage_change_password.html')
    
    # POST処理
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    if not current_password or not new_password or not confirm_password:
        flash('すべての項目を入力してください', 'error')
        return render_template('app_manager_mypage_change_password.html')
    
    if new_password != confirm_password:
        flash('新しいパスワードが一致しません', 'error')
        return render_template('app_manager_mypage_change_password.html')
    
    db = SessionLocal()
    try:
        current_admin = db.query(TKanrisha).filter(TKanrisha.id == app_manager.id).first()
        
        if not check_password_hash(current_admin.password_hash, current_password):
            flash('現在のパスワードが正しくありません', 'error')
            return render_template('app_manager_mypage_change_password.html')
        
        # パスワード更新
        current_admin.password_hash = generate_password_hash(new_password)
        db.commit()
        
        flash('パスワードを変更しました', 'success')
        return redirect(url_for('app_manager.mypage'))
        
    finally:
        db.close()


@bp.route('/select_tenant_from_mypage', methods=['POST'])
def select_tenant_from_mypage():
    """マイページからテナント選択してテナント管理者ダッシュボードへ遷移"""
    # 権限チェック
    if session.get('role') != 'app_manager':
        flash('権限がありません。', 'warning')
        return redirect(url_for('auth.select_login'))
    
    tenant_id = request.form.get('tenant_id')
    
    if not tenant_id:
        flash('テナントを選択してください', 'error')
        return redirect(url_for('app_manager.mypage'))
    
    db = SessionLocal()
    try:
        from app.models_login import TTenant
        
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        if not tenant:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('app_manager.mypage'))
        
        # セッションにテナント情報を設定（app_manager権限のまま）
        session['tenant_id'] = tenant.id
        session.modified = True  # セッションの変更を明示的にマーク
        
        from flask import current_app
        current_app.logger.info(f"DEBUG: セッション設定完了 - role={session.get('role')}, tenant_id={session.get('tenant_id')}")
        redirect_url = url_for('tenant_admin.dashboard')
        current_app.logger.info(f"DEBUG: リダイレクト先={redirect_url}")
        
        return redirect(redirect_url)
        
    finally:
        db.close()


@bp.route('/select_store_from_mypage', methods=['POST'])
def select_store_from_mypage():
    """マイページから店舗選択して店舗管理者ダッシュボードへ遷移"""
    # 権限チェック
    if session.get('role') != 'app_manager':
        flash('権限がありません。', 'warning')
        return redirect(url_for('auth.select_login'))
    
    store_id = request.form.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('app_manager.mypage'))
    
    db = SessionLocal()
    try:
        from app.models_login import TTenpo
        
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('app_manager.mypage'))
        
        # セッションに店舗情報を設定（app_manager権限のまま）
        session['tenant_id'] = store.tenant_id
        session['store_id'] = store.id
        session.modified = True
        
        return redirect(url_for('admin.dashboard'))
        
    finally:
        db.close()


@bp.route('/app_managers')
@require_roles('app_manager', 'system_admin')
def app_managers():
    """アプリ管理者管理（同じグループのアプリ管理者を管理）"""
    user_id = session.get('user_id')
    role = session.get('role')
    group_id = session.get('app_manager_group_id')
    
    if not group_id:
        flash('アプリ管理者グループが選択されていません', 'error')
        return redirect(url_for('system_admin.mypage') if role == 'system_admin' else url_for('app_manager.login'))
    
    db = SessionLocal()
    try:
        # 同じグループのアプリ管理者を取得
        app_managers_list = db.query(TKanrisha).filter(
            TKanrisha.role == 'app_manager',
            TKanrisha.app_manager_group_id == group_id
        ).order_by(
            TKanrisha.is_owner.desc(),
            TKanrisha.can_manage_admins.desc(),
            TKanrisha.id
        ).all()
        
        # 所属グループ情報を取得
        group = db.query(TAppManagerGroup).filter(
            TAppManagerGroup.id == group_id
        ).first()
        
        # 現在のユーザー情報を取得（システム管理者の場合はNone）
        current_app_manager = db.query(TKanrisha).filter(TKanrisha.id == user_id).first() if role == 'app_manager' else None
        
        return render_template(
            'app_manager_app_managers.html',
            app_managers=app_managers_list,
            group=group,
            current_app_manager=current_app_manager,
            is_owner=is_owner(),
            can_manage_app_managers=can_manage_app_managers(),
            is_system_admin_view=(role == 'system_admin')
        )
    finally:
        db.close()


@bp.route('/app_managers/new', methods=['GET', 'POST'])
@require_roles('app_manager', 'system_admin')
def app_manager_new():
    """アプリ管理者新規作成（アプリ管理者管理権限が必要）"""
    # アプリ管理者管理権限チェック
    if not can_manage_app_managers():
        flash('アプリ管理者を作成する権限がありません', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    role = session.get('role')
    group_id = session.get('app_manager_group_id')
    
    if not group_id:
        flash('アプリ管理者グループが選択されていません', 'error')
        return redirect(url_for('system_admin.mypage') if role == 'system_admin' else url_for('app_manager.login'))
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        
        # バリデーション
        if not login_id or not name or not password:
            flash('ログインID、氏名、パスワードは必須です', 'error')
            return render_template('app_manager_app_manager_new.html', 
                                 current_group_id=group_id)
        
        if password != password_confirm:
            flash('パスワードが一致しません', 'error')
            return render_template('app_manager_app_manager_new.html',
                                 current_group_id=group_id)
        
        if len(password) < 8:
            flash('パスワードは8文字以上にしてください', 'error')
            return render_template('app_manager_app_manager_new.html',
                                 current_group_id=group_id)
        
        db = SessionLocal()
        
        try:
            # ログインID重複チェック
            existing = db.query(TKanrisha).filter(TKanrisha.login_id == login_id).first()
            if existing:
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                return render_template('app_manager_app_manager_new.html',
                                     current_group_id=group_id)
            
            # 既存のアプリ管理者が存在するかチェック（同じグループ内）
            existing_admin_count = db.query(TKanrisha).filter(
                TKanrisha.role == 'app_manager',
                TKanrisha.app_manager_group_id == group_id
            ).count()
            
            # 最初の管理者の場合は自動的にオーナーにする
            is_first_admin = (existing_admin_count == 0)
            
            # フォームから権限設定を取得
            active = 1 if request.form.get('active') == '1' else 0
            can_manage = 1 if request.form.get('can_manage_admins') == '1' else 0
            can_distribute_apps = 1 if request.form.get('can_distribute_apps') == '1' else 0
            
            # アプリ管理者作成（同じグループに所属）
            hashed_password = generate_password_hash(password)
            new_admin = TKanrisha(
                login_id=login_id,
                name=name,
                email=email,
                password_hash=hashed_password,
                role='app_manager',
                tenant_id=None,
                app_manager_group_id=group_id,
                active=active if not is_first_admin else 1,
                is_owner=1 if is_first_admin else 0,
                can_manage_admins=can_manage if not is_first_admin else 1,
                can_distribute_apps=can_distribute_apps if not is_first_admin else 1
            )
            db.add(new_admin)
            db.commit()
            
            flash(f'アプリ管理者 "{name}" を作成しました', 'success')
            return redirect(url_for('app_manager.app_managers'))
        finally:
            db.close()
    
    return render_template('app_manager_app_manager_new.html',
                         current_group_id=group_id)


@bp.route('/app_managers/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles('app_manager', 'system_admin')
def app_manager_edit(admin_id):
    """アプリ管理者編集（アプリ管理者管理権限が必要）"""
    # アプリ管理者管理権限チェック
    if not can_manage_app_managers():
        flash('アプリ管理者を編集する権限がありません', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    role = session.get('role')
    group_id = session.get('app_manager_group_id')
    
    if not group_id:
        flash('アプリ管理者グループが選択されていません', 'error')
        return redirect(url_for('system_admin.mypage') if role == 'system_admin' else url_for('app_manager.login'))
    
    db = SessionLocal()
    try:
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            
            # パスワード変更時のバリデーション
            if password:
                if password != password_confirm:
                    flash('パスワードが一致しません', 'error')
                elif len(password) < 8:
                    flash('パスワードは8文字以上にしてください', 'error')
            
            active = 1 if request.form.get('active') == '1' else 0
            can_manage = 1 if request.form.get('can_manage_admins') == '1' else 0
            can_distribute_apps = 1 if request.form.get('can_distribute_apps') == '1' else 0
            
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
            else:
                # ログインIDの重複チェック
                existing = db.query(TKanrisha).filter(
                    TKanrisha.login_id == login_id,
                    TKanrisha.id != admin_id
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                else:
                    admin = db.query(TKanrisha).filter(
                        TKanrisha.id == admin_id,
                        TKanrisha.role == 'app_manager',
                        TKanrisha.app_manager_group_id == group_id
                    ).first()
                    
                    if admin:
                        admin.login_id = login_id
                        admin.name = name
                        admin.email = email
                        admin.active = active
                        # オーナーでない場合のみ管理権限を変更可能
                        if admin.is_owner != 1:
                            admin.can_manage_admins = can_manage
                            admin.can_distribute_apps = can_distribute_apps
                        if password:
                            admin.password_hash = generate_password_hash(password)
                        db.commit()
                        flash('アプリ管理者を更新しました', 'success')
                        return redirect(url_for('app_manager.app_managers'))
                    else:
                        flash('アプリ管理者が見つかりません', 'error')
                        return redirect(url_for('app_manager.app_managers'))
        
        # GETリクエスト時は現在の情報を表示
        admin = db.query(TKanrisha).filter(
            TKanrisha.id == admin_id,
            TKanrisha.role == 'app_manager',
            TKanrisha.app_manager_group_id == group_id
        ).first()
        
        if not admin:
            flash('アプリ管理者が見つかりません', 'error')
            return redirect(url_for('app_manager.app_managers'))
        
        admin_data = {
            'id': admin.id,
            'login_id': admin.login_id,
            'name': admin.name,
            'email': admin.email,
            'active': admin.active,
            'is_owner': admin.is_owner,
            'can_manage_admins': admin.can_manage_admins,
            'can_distribute_apps': getattr(admin, 'can_distribute_apps', 0)
        }
        
        return render_template('app_manager_app_manager_edit.html', admin=admin_data)
    finally:
        db.close()


@bp.route('/app_managers/<int:admin_id>/delete', methods=['POST'])
@require_roles('app_manager', 'system_admin')
def app_manager_delete(admin_id):
    """アプリ管理者削除（オーナーは削除不可）"""
    if not can_manage_app_managers():
        flash('アプリ管理者を削除する権限がありません', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    user_id = session.get('user_id')
    group_id = session.get('app_manager_group_id')
    
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            TKanrisha.id == admin_id,
            TKanrisha.role == 'app_manager',
            TKanrisha.app_manager_group_id == group_id
        ).first()
        
        role = session.get('role')
        if admin:
            # オーナーはシステム管理者のみ削除可能
            if admin.is_owner == 1 and role != 'system_admin':
                flash('オーナーは削除できません', 'error')
            # 自分自身は削除できない
            elif admin.id == user_id:
                flash('自分自身は削除できません', 'error')
            else:
                db.delete(admin)
                db.commit()
                flash('アプリ管理者を削除しました', 'success')
        
        return redirect(url_for('app_manager.app_managers'))
    finally:
        db.close()


@bp.route('/app_managers/<int:admin_id>/toggle', methods=['POST'])
@require_roles('app_manager', 'system_admin')
def app_manager_toggle(admin_id):
    """アプリ管理者の有効/無効切り替え"""
    if not can_manage_app_managers():
        flash('アプリ管理者を管理する権限がありません', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    user_id = session.get('user_id')
    group_id = session.get('app_manager_group_id')
    
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            TKanrisha.id == admin_id,
            TKanrisha.role == 'app_manager',
            TKanrisha.app_manager_group_id == group_id
        ).first()
        
        if admin:
            # オーナーは無効化できない
            if admin.is_owner == 1:
                flash('オーナーは無効化できません', 'error')
            # 自分自身は無効化できない
            elif admin.id == user_id:
                flash('自分自身は無効化できません', 'error')
            else:
                admin.active = 0 if admin.active == 1 else 1
                db.commit()
                status = '有効' if admin.active == 1 else '無効'
                flash(f'アプリ管理者を{status}にしました', 'success')
        
        return redirect(url_for('app_manager.app_managers'))
    finally:
        db.close()


@bp.route('/app_managers/<int:admin_id>/toggle_manage_permission', methods=['POST'])
@require_roles('app_manager')
def toggle_manage_permission(admin_id):
    """アプリ管理者管理権限の付与・剥奪（オーナーのみ）"""
    if not is_owner():
        flash('オーナーのみがこの操作を実行できます', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    # 自分自身の権限は変更できない
    if admin_id == session.get('user_id'):
        flash('自分自身の権限は変更できません', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    current_app_manager = get_current_app_manager()
    if not current_app_manager:
        return redirect(url_for('app_manager.login'))
    
    db = SessionLocal()
    try:
        admin = db.query(TKanrisha).filter(
            TKanrisha.id == admin_id,
            TKanrisha.role == 'app_manager',
            TKanrisha.app_manager_group_id == group_id
        ).first()
        
        if not admin:
            flash('アプリ管理者が見つかりません', 'error')
            return redirect(url_for('app_manager.app_managers'))
        
        # オーナーの権限は変更できない
        if admin.is_owner == 1:
            flash('オーナーの権限は変更できません', 'error')
            return redirect(url_for('app_manager.app_managers'))
        
        # 権限を切り替え
        admin.can_manage_admins = 1 if admin.can_manage_admins == 0 else 0
        db.commit()
        
        status = '付与' if admin.can_manage_admins == 1 else '剥奪'
        flash(f'{admin.name} のアプリ管理者管理権限を{status}しました', 'success')
        return redirect(url_for('app_manager.app_managers'))
    finally:
        db.close()


@bp.route('/app_managers/<int:admin_id>/toggle_distribute_apps_permission', methods=['POST'])
@require_roles('app_manager')
def toggle_distribute_apps_permission(admin_id):
    """アプリ配布権限の付与・剥奪（オーナーのみ）"""
    if not is_owner():
        flash('オーナーのみがこの操作を実行できます', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    # 自分自身の権限は変更できない
    if admin_id == session.get('user_id'):
        flash('自分自身の権限は変更できません', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    current_app_manager = get_current_app_manager()
    if not current_app_manager:
        return redirect(url_for('app_manager.login'))
    
    db = SessionLocal()
    try:
        admin = db.query(TKanrisha).filter(
            TKanrisha.id == admin_id,
            TKanrisha.role == 'app_manager',
            TKanrisha.app_manager_group_id == group_id
        ).first()
        
        if not admin:
            flash('アプリ管理者が見つかりません', 'error')
            return redirect(url_for('app_manager.app_managers'))
        
        # オーナーの権限は変更できない
        if admin.is_owner == 1:
            flash('オーナーの権限は変更できません', 'error')
            return redirect(url_for('app_manager.app_managers'))
        
        # 権限を切り替え
        current_value = getattr(admin, 'can_distribute_apps', 0)
        admin.can_distribute_apps = 1 if current_value == 0 else 0
        db.commit()
        
        status = '付与' if admin.can_distribute_apps == 1 else '剥奪'
        flash(f'{admin.name} のアプリ配布権限を{status}しました', 'success')
        return redirect(url_for('app_manager.app_managers'))
    finally:
        db.close()


@bp.route('/app_managers/<int:admin_id>/transfer_ownership', methods=['POST'])
@require_roles('app_manager')
def transfer_ownership(admin_id):
    """オーナー権限を他のアプリ管理者に移譲"""
    # オーナーのみ実行可能
    if not is_owner():
        flash('オーナーのみがオーナー権限を移譲できます', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    # 自分自身には移譲できない
    if admin_id == session.get('user_id'):
        flash('自分自身にオーナー権限を移譲することはできません', 'error')
        return redirect(url_for('app_manager.app_managers'))
    
    current_app_manager = get_current_app_manager()
    if not current_app_manager:
        return redirect(url_for('app_manager.login'))
    
    db = SessionLocal()
    try:
        # 移譲先が同じグループのアプリ管理者であることを確認
        admin = db.query(TKanrisha).filter(
            TKanrisha.id == admin_id,
            TKanrisha.role == 'app_manager',
            TKanrisha.app_manager_group_id == group_id
        ).first()
        
        if not admin:
            flash('移譲先のアプリ管理者が見つかりません', 'error')
            return redirect(url_for('app_manager.app_managers'))
        
        new_owner_name = admin.name
        
        # このグループの全てのis_ownerを0にしてから、指定したユーザーを1にする
        db.query(TKanrisha).filter(
            TKanrisha.role == 'app_manager',
            TKanrisha.app_manager_group_id == group_id
        ).update({TKanrisha.is_owner: 0})
        admin.is_owner = 1
        admin.can_manage_admins = 1
        admin.can_distribute_apps = 1
        db.commit()
        
        flash(f'オーナー権限を「{new_owner_name}」に移譲しました', 'success')
        return redirect(url_for('app_manager.app_managers'))
    finally:
        db.close()


@bp.route('/tenants')
@require_roles('app_manager', 'system_admin')
def tenants():
    """テナント管理（担当テナントの一覧）"""
    db = SessionLocal()
    try:
        from app.models_login import TTenant
        
        # アプリ管理者は全テナントにアクセス可能
        tenants_list = db.query(TTenant).filter(
            TTenant.有効 == 1
        ).order_by(TTenant.id).all()
        
        return render_template(
            'app_manager_tenants.html',
            tenants=tenants_list
        )
    finally:
        db.close()


@bp.route('/tenants/new', methods=['GET', 'POST'])
@require_roles('app_manager')
def tenant_new():
    """テナント新規作成"""
    app_manager = get_current_app_manager()
    if not app_manager:
        return redirect(url_for('app_manager.login'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        openai_api_key = request.form.get('openai_api_key', '').strip()
        
        if not name or not slug:
            flash('名称とslugは必須です', 'error')
            return render_template('app_manager_tenant_new.html', name=name, slug=slug)
        
        db = SessionLocal()
        
        try:
            from app.models_login import TTenant
            
            # slug重複チェック
            existing = db.query(TTenant).filter(TTenant.slug == slug).first()
            if existing:
                flash(f'slug "{slug}" は既に使用されています', 'error')
                return render_template('app_manager_tenant_new.html', name=name, slug=slug)
            
            # テナント作成
            new_tenant = TTenant(
                名称=name,
                slug=slug,
                郵便番号=postal_code or None,
                住所=address or None,
                電話番号=phone or None,
                email=email or None,
                openai_api_key=openai_api_key or None,
                有効=1
            )
            db.add(new_tenant)
            db.commit()
            
            flash(f'テナント "{name}" を作成しました', 'success')
            return redirect(url_for('app_manager.tenants'))
        finally:
            db.close()
    
    return render_template('app_manager_tenant_new.html')


@bp.route('/app_management')
@require_roles('app_manager', 'system_admin')
def app_management():
    """アプリ配布管理（テナント・店舗別アプリ配布設定）"""
    db = SessionLocal()
    try:
        from app.models_login import TTenant, TTenpo
        
        # テナント一覧を取得
        tenants = db.query(TTenant).filter(TTenant.有効 == 1).order_by(TTenant.id).all()
        
        # 店舗一覧を取得
        stores = db.query(TTenpo).filter(TTenpo.有効 == 1).order_by(TTenpo.tenant_id, TTenpo.id).all()
        
        return render_template(
            'app_manager_app_management.html',
            tenants=tenants,
            stores=stores
        )
    finally:
        db.close()


@bp.route('/plan', methods=['GET', 'POST'])
@require_roles('app_manager', 'system_admin')
def plan():
    """プラン管理・利用アプリ選択"""
    import json
    role = session.get('role')
    group_id = session.get('app_manager_group_id')

    if not group_id:
        flash('アプリ管理者グループが選択されていません', 'error')
        return redirect(url_for('system_admin.mypage') if role == 'system_admin' else url_for('app_manager.login'))

    db = SessionLocal()
    try:
        from app.blueprints.tenant_admin import AVAILABLE_APPS

        group = db.query(TAppManagerGroup).filter(TAppManagerGroup.id == group_id).first()
        if not group:
            flash('グループが見つかりません', 'error')
            return redirect(url_for('app_manager.dashboard'))

        if request.method == 'POST':
            action = request.form.get('action', '')

            if action == 'update_plan':
                new_plan = request.form.get('plan', 'individual')
                if new_plan in ('unlimited', '10app_pack', 'individual'):
                    group.plan = new_plan
                    # 無制限プランは全アプリを自動選択
                    if new_plan == 'unlimited':
                        group.enabled_apps = json.dumps([app['name'] for app in AVAILABLE_APPS])
                    db.commit()
                    flash('プランを更新しました', 'success')
                else:
                    flash('無効なプランです', 'error')
                return redirect(url_for('app_manager.plan'))

            elif action == 'update_apps':
                selected = request.form.getlist('selected_apps')
                current_plan = getattr(group, 'plan', 'individual') or 'individual'
                # 10アプリパックは最大10アプリ
                if current_plan == '10app_pack' and len(selected) > 10:
                    flash('10アプリパックプランは最大10アプリまで選択できます', 'error')
                    return redirect(url_for('app_manager.plan'))
                group.enabled_apps = json.dumps(selected)
                db.commit()
                flash('利用アプリを更新しました', 'success')
                return redirect(url_for('app_manager.plan'))

        current_plan = getattr(group, 'plan', 'individual') or 'individual'
        enabled_apps_raw = getattr(group, 'enabled_apps', None) or '[]'
        try:
            enabled_app_ids = json.loads(enabled_apps_raw)
        except Exception:
            enabled_app_ids = []

        plan_labels = {
            'unlimited': '無制限プラン',
            '10app_pack': '10アプリパックプラン',
            'individual': '個別プラン',
        }

        return render_template(
            'app_manager_plan.html',
            group=group,
            available_apps=AVAILABLE_APPS,
            enabled_app_ids=enabled_app_ids,
            current_plan=current_plan,
            plan_labels=plan_labels,
            is_system_admin_view=(role == 'system_admin')
        )
    finally:
        db.close()


@bp.route('/distribute', methods=['GET', 'POST'])
@require_roles('app_manager', 'system_admin')
def distribute():
    """テナントへのアプリ配布管理"""
    import json
    role = session.get('role')
    group_id = session.get('app_manager_group_id')

    if not group_id:
        flash('アプリ管理者グループが選択されていません', 'error')
        return redirect(url_for('system_admin.mypage') if role == 'system_admin' else url_for('app_manager.login'))

    db = SessionLocal()
    try:
        from app.models_login import TTenant, TTenantAppSetting
        from app.blueprints.tenant_admin import AVAILABLE_APPS

        group = db.query(TAppManagerGroup).filter(TAppManagerGroup.id == group_id).first()
        if not group:
            flash('グループが見つかりません', 'error')
            return redirect(url_for('app_manager.dashboard'))

        # グループが選択した利用可能アプリを取得
        enabled_apps_raw = getattr(group, 'enabled_apps', None) or '[]'
        try:
            enabled_app_ids = json.loads(enabled_apps_raw)
        except Exception:
            enabled_app_ids = []

        # 利用可能アプリの詳細情報
        enabled_apps = [app for app in AVAILABLE_APPS if app['name'] in enabled_app_ids]

        # テナント一覧（全テナント）
        tenants = db.query(TTenant).filter(
            TTenant.有効 == 1
        ).order_by(TTenant.id).all()

        if request.method == 'POST':
            tenant_id = request.form.get('tenant_id')
            selected_apps = request.form.getlist('apps')

            if not tenant_id:
                flash('テナントを選択してください', 'error')
                return redirect(url_for('app_manager.distribute'))

            # 既存の配布設定を削除して再登録
            db.query(TTenantAppSetting).filter(
                TTenantAppSetting.tenant_id == tenant_id
            ).delete()

            for app_id in selected_apps:
                if app_id in enabled_app_ids:
                    setting = TTenantAppSetting(
                        tenant_id=tenant_id,
                        app_id=app_id,
                        enabled=1
                    )
                    db.add(setting)

            db.commit()
            flash('アプリ配布設定を更新しました', 'success')
            return redirect(url_for('app_manager.distribute'))

        # 各テナントの現在の配布設定を取得
        tenant_app_settings = {}
        for tenant in tenants:
            settings = db.query(TTenantAppSetting).filter(
                TTenantAppSetting.tenant_id == tenant.id,
                TTenantAppSetting.enabled == 1
            ).all()
            tenant_app_settings[tenant.id] = [s.app_id for s in settings]

        return render_template(
            'app_manager_distribute.html',
            group=group,
            tenants=tenants,
            enabled_apps=enabled_apps,
            tenant_app_settings=tenant_app_settings,
            is_system_admin_view=(role == 'system_admin')
        )
    finally:
        db.close()
