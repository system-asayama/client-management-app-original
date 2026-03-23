"""
顧問先管理ブループリント（SQLAlchemy版）
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.db import SessionLocal
from app.models_clients import TClient
from app.utils.decorators import require_roles, ROLES
from sqlalchemy import and_

bp = Blueprint('clients', __name__, url_prefix='/clients')


@bp.route('/')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def clients():
    """顧問先一覧"""
    print(f"[DEBUG] Session keys: {list(session.keys())}")
    print(f"[DEBUG] Session content: {dict(session)}")
    tenant_id = session.get('tenant_id')
    print(f"[DEBUG] tenant_id from session: {tenant_id}")
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        clients = db.query(TClient).filter(TClient.tenant_id == tenant_id).order_by(TClient.id.desc()).all()
        return render_template('clients.html', clients=clients)
    finally:
        db.close()


@bp.route('/add', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def add_client():
    """顧問先追加"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    if request.method == 'POST':
        client_type = request.form.get('type')
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        notes = request.form.get('notes')
        
        db = SessionLocal()
        try:
            new_client = TClient(
                tenant_id=tenant_id,
                type=client_type,
                name=name,
                email=email,
                phone=phone,
                notes=notes
            )
            db.add(new_client)
            db.commit()
            flash('顧問先を追加しました', 'success')
            return redirect(url_for('clients.clients'))
        except Exception as e:
            db.rollback()
            flash(f'エラーが発生しました: {str(e)}', 'error')
        finally:
            db.close()
    
    return render_template('add_client.html')


@bp.route('/<int:client_id>')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def client_info(client_id):
    """顧問先詳細"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # 会社基本情報を取得
        company = db.query(TCompanyInfo).filter(TCompanyInfo.顧問先ID == client_id).first()
        
        return render_template('client_info.html', client=client, company=company)
    finally:
        db.close()


@bp.route('/<int:client_id>/chat')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def client_chat(client_id):
    """顧問先チャット"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # チャット機能は今後実装
        return render_template('client_chat.html', client=client, messages=[])
    finally:
        db.close()


# ========================================
# 会社基本情報管理機能
# ========================================

@bp.route('/company/<int:company_id>')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def company_info(company_id):
    """会社基本情報詳細"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # テナントIDの検証（顧問先経由）
        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))
        
        return render_template('company_info_company.html', company=company)
    finally:
        db.close()


@bp.route('/company/create/<int:client_id>', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def company_create(client_id):
    """会社基本情報新規登録"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        # 顧問先の存在確認とテナントID検証
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # 既に会社基本情報が登録されているかチェック
        existing_company = db.query(TCompanyInfo).filter(
            TCompanyInfo.顧問先ID == client_id
        ).first()
        
        if existing_company:
            flash('この顧問先の会社基本情報は既に登録されています', 'info')
            return redirect(url_for('clients.company_info', company_id=existing_company.id))
        
        if request.method == 'POST':
            new_company = TCompanyInfo(
                顧問先ID=client_id,
                会社名=request.form.get('会社名'),
                郵便番号=request.form.get('郵便番号'),
                都道府県=request.form.get('都道府県'),
                市区町村番地=request.form.get('市区町村番地'),
                建物名部屋番号=request.form.get('建物名部屋番号'),
                電話番号1=request.form.get('電話番号1'),
                電話番号2=request.form.get('電話番号2'),
                ファックス番号=request.form.get('ファックス番号'),
                メールアドレス=request.form.get('メールアドレス'),
                担当者名=request.form.get('担当者名'),
                業種=request.form.get('業種'),
                従業員数=int(request.form.get('従業員数')) if request.form.get('従業員数') else None,
                法人番号=request.form.get('法人番号')
            )
            db.add(new_company)
            db.commit()
            flash('会社基本情報を登録しました', 'success')
            return redirect(url_for('clients.client_info', client_id=client_id))
        
        return render_template('company_create.html', client=client)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.client_info', client_id=client_id))
    finally:
        db.close()


@bp.route('/company/<int:company_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def company_edit(company_id):
    """会社基本情報編集"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # テナントIDの検証
        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))
        
        if request.method == 'POST':
            company.会社名 = request.form.get('会社名')
            company.郵便番号 = request.form.get('郵便番号')
            company.都道府県 = request.form.get('都道府県')
            company.市区町村番地 = request.form.get('市区町村番地')
            company.建物名部屋番号 = request.form.get('建物名部屋番号')
            company.電話番号1 = request.form.get('電話番号1')
            company.電話番号2 = request.form.get('電話番号2')
            company.ファックス番号 = request.form.get('ファックス番号')
            company.メールアドレス = request.form.get('メールアドレス')
            company.担当者名 = request.form.get('担当者名')
            company.業種 = request.form.get('業種')
            company.従業員数 = int(request.form.get('従業員数')) if request.form.get('従業員数') else None
            company.法人番号 = request.form.get('法人番号')
            
            db.commit()
            flash('会社基本情報を更新しました', 'success')
            return redirect(url_for('clients.company_info', company_id=company_id))
        
        clients_list = db.query(TClient).filter(TClient.tenant_id == tenant_id).all()
        return render_template('company_edit.html', company=company, clients=clients_list)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.company_info', company_id=company_id))
    finally:
        db.close()


@bp.route('/company/<int:company_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def company_delete(company_id):
    """会社基本情報削除"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # テナントIDの検証
        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))
        
        client_id = company.顧問先ID
        db.delete(company)
        db.commit()
        flash('会社基本情報を削除しました', 'success')
        return redirect(url_for('clients.client_info', client_id=client_id))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.clients'))
    finally:
        db.close()


# ========================================
# クライアントアカウント管理（税理士事務所側）
# ========================================

@bp.route('/<int:client_id>/accounts')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def client_accounts(client_id):
    """顧問先のクライアントアカウント一覧"""
    from app.models_client_users import TClientUser
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        users = db.query(TClientUser).filter(
            TClientUser.client_id == client_id
        ).order_by(TClientUser.id.asc()).all()
        return render_template('client_accounts.html', client=client, users=users)
    finally:
        db.close()


@bp.route('/<int:client_id>/accounts/issue', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def issue_client_account(client_id):
    """クライアント初期アカウント発行"""
    import secrets
    from datetime import datetime, timedelta
    from app.models_client_users import TClientUser, TClientInvitation
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        invite_url = None
        if request.method == 'POST':
            issue_type = request.form.get('issue_type', 'invite')  # invite or direct

            if issue_type == 'invite':
                # 招待リンク方式
                email = (request.form.get('email') or '').strip()
                role = request.form.get('role') or 'client_admin'
                if role not in ('client_admin', 'client_employee'):
                    role = 'client_admin'
                token = secrets.token_urlsafe(32)
                expires_at = datetime.utcnow() + timedelta(days=7)
                invitation = TClientInvitation(
                    client_id=client_id,
                    token=token,
                    email=email if email else None,
                    role=role,
                    invited_by_role=session.get('role'),
                    invited_by_id=session.get('user_id'),
                    used=0,
                    expires_at=expires_at
                )
                db.add(invitation)
                db.commit()
                from flask import url_for as _url_for
                invite_url = _url_for('client_auth.accept_invite', token=token, _external=True)
                flash('招待リンクを作成しました。', 'success')
            else:
                # 直接アカウント作成方式
                from werkzeug.security import generate_password_hash
                login_id = (request.form.get('login_id') or '').strip()
                name = (request.form.get('name') or '').strip()
                email = (request.form.get('email') or '').strip()
                password = request.form.get('password') or ''
                role = request.form.get('role') or 'client_admin'
                if role not in ('client_admin', 'client_employee'):
                    role = 'client_admin'

                if not login_id or not name or not email or not password:
                    flash('すべての項目を入力してください。', 'error')
                    return render_template('issue_client_account.html', client=client, invite_url=None)

                existing = db.query(TClientUser).filter(TClientUser.login_id == login_id).first()
                if existing:
                    flash('このログインIDはすでに使用されています。', 'error')
                    return render_template('issue_client_account.html', client=client, invite_url=None)

                new_user = TClientUser(
                    client_id=client_id,
                    login_id=login_id,
                    name=name,
                    email=email,
                    password_hash=generate_password_hash(password),
                    role=role,
                    active=1
                )
                db.add(new_user)
                db.commit()
                flash(f'クライアントアカウントを作成しました。ログインID: {login_id}', 'success')
                return redirect(url_for('clients.client_accounts', client_id=client_id))

        return render_template('issue_client_account.html', client=client, invite_url=invite_url)
    finally:
        db.close()


@bp.route('/<int:client_id>/accounts/<int:user_id>/toggle', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def toggle_client_account(client_id, user_id):
    """クライアントアカウントの有効/無効切り替え"""
    from app.models_client_users import TClientUser
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        user = db.query(TClientUser).filter(
            TClientUser.id == user_id,
            TClientUser.client_id == client_id
        ).first()
        if user:
            user.active = 0 if user.active == 1 else 1
            db.commit()
            status = '有効' if user.active == 1 else '無効'
            flash(f'{user.name} を{status}にしました。', 'success')
        else:
            flash('ユーザーが見つかりません。', 'error')
    finally:
        db.close()
    return redirect(url_for('clients.client_accounts', client_id=client_id))


# ========================================
# チャット機能
# ========================================

@bp.route('/chat', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chat():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    
    from datetime import datetime
    from app.utils.db import get_db, _sql
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        if request.method == 'POST':
            sender = session.get('username', 'Unknown')
            message = request.form.get('message', '')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            sql = _sql(conn, 'INSERT INTO "T_メッセージ" (sender, message, timestamp) VALUES (%s, %s, %s)')
            cur.execute(sql, (sender, message, timestamp))
            # autocommit=Trueのためconn.commit()は不要
            return redirect(url_for('clients.chat'))
        
        sql = _sql(conn, 'SELECT * FROM "T_メッセージ" ORDER BY id DESC LIMIT 20')
        cur.execute(sql)
        messages = cur.fetchall()
        return render_template('chat.html', messages=list(reversed(messages)))
    finally:
        conn.close()


# ========================================
# ファイル共有機能
# ========================================

@bp.route('/files', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def files():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    
    from datetime import datetime
    from app.utils.db import get_db, _sql
    from app.utils.storage import storage_manager
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        if request.method == 'POST':
            f = request.files.get('file')
            if f and f.filename:
                uploader = session.get('username', 'Unknown')
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # S3にアップロード
                if storage_manager.is_enabled():
                    result = storage_manager.upload_file(f, f.filename)
                    if result['success']:
                        # filenameにS3のURLを保存
                        sql = _sql(conn, 'INSERT INTO "T_ファイル" (filename, uploader, timestamp) VALUES (%s, %s, %s)')
                        cur.execute(sql, (result['url'], uploader, timestamp))
                        flash('ファイルをアップロードしました', 'success')
                    else:
                        flash(f'アップロードエラー: {result["error"]}', 'error')
                else:
                    flash('ストレージ連携が設定されていません。環境変数を確認してください。', 'error')
                
                return redirect(url_for('clients.files'))
        
        sql = _sql(conn, 'SELECT * FROM "T_ファイル" ORDER BY id DESC')
        cur.execute(sql)
        files_list = cur.fetchall()
        return render_template('files.html', files=files_list)
    finally:
        conn.close()
