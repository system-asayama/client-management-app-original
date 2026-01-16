"""
チャット機能ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from app.db import get_conn, SessionLocal
from app.utils.decorators import require_roles, ROLES
from app.models_clients import TClient, TMessage
from sqlalchemy import and_

bp = Blueprint('chat', __name__, url_prefix='/chat')


@bp.route('/client/<int:client_id>', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def client_chat(client_id):
    """顧問先ごとのチャットルーム"""
    tenant_id = session.get('tenant_id')
    user_name = session.get('user_name', '匿名')
    
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        # 顧問先の存在確認
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        if request.method == 'POST':
            message_text = request.form.get('message')
            if message_text:
                new_message = TMessage(
                    client_id=client_id,
                    sender=user_name,
                    message=message_text,
                    timestamp=datetime.now()
                )
                db.add(new_message)
                db.commit()
                return redirect(url_for('chat.client_chat', client_id=client_id))
        
        # メッセージ一覧を取得
        messages = db.query(TMessage).filter(
            TMessage.client_id == client_id
        ).order_by(TMessage.id.asc()).all()
        
        return render_template('client_chat.html', client=client, messages=messages)
    finally:
        db.close()


@bp.route('/', methods=['GET', 'POST'])
def chat():
    """全体チャットルーム（旧版）"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    
    if request.method == 'POST':
        sender = session['user']
        message = request.form['message']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute(
            "INSERT INTO T_メッセージ (sender, message, timestamp) VALUES (?, ?, ?)",
            (sender, message, timestamp)
        )
        conn.commit()
    
    messages = conn.execute("SELECT * FROM T_メッセージ ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    
    return render_template('chat.html', messages=reversed(messages))
