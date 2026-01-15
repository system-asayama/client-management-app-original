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
@require_roles(ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
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
        
        return render_template('client_info.html', client=client)
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
