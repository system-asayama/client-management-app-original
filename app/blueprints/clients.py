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
    
    if request.method == 'POST':
        sender = session.get('username', 'Unknown')
        message = request.form.get('message', '')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        sql = _sql(conn, 'INSERT INTO "T_メッセージ" (sender, message, timestamp) VALUES (%s, %s, %s)')
        cur.execute(sql, (sender, message, timestamp))
        conn.commit()
        conn.close()
        return redirect(url_for('clients.chat'))
    
    sql = _sql(conn, 'SELECT * FROM "T_メッセージ" ORDER BY id DESC LIMIT 20')
    cur.execute(sql)
    messages = cur.fetchall()
    conn.close()
    return render_template('chat.html', messages=list(reversed(messages)))


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
    from werkzeug.utils import secure_filename
    import os
    
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        f = request.files.get('file')
        if f and f.filename:
            # ファイルを一時的に保存（実際のストレージ連携は後で実装）
            filename = secure_filename(f.filename)
            upload_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            f.save(filepath)
            
            uploader = session.get('username', 'Unknown')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # filenameにファイルパスを保存（元のスキーマに合わせる）
            sql = _sql(conn, 'INSERT INTO "T_ファイル" (filename, uploader, timestamp) VALUES (%s, %s, %s)')
            cur.execute(sql, (filename, uploader, timestamp))
            conn.commit()
            conn.close()
            return redirect(url_for('clients.files'))
    
    sql = _sql(conn, 'SELECT * FROM "T_ファイル" ORDER BY id DESC')
    cur.execute(sql)
    files_list = cur.fetchall()
    conn.close()
    return render_template('files.html', files=files_list)
