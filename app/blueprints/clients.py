"""
顧問先管理ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session
from app.db import get_conn

bp = Blueprint('clients', __name__, url_prefix='/clients')


@bp.route('/')
def clients():
    """顧問先一覧"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    rows = conn.execute("SELECT * FROM T_顧問先 ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('clients.html', clients=rows)


@bp.route('/add', methods=['GET', 'POST'])
def add_client():
    """顧問先追加"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        client_type = request.form['type']
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        notes = request.form['notes']
        
        conn = get_conn()
        conn.execute(
            "INSERT INTO T_顧問先 (type, name, email, phone, notes) VALUES (?, ?, ?, ?, ?)",
            (client_type, name, email, phone, notes)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('clients.clients'))
    
    return render_template('add_client.html')


@bp.route('/<int:client_id>')
def client_info(client_id):
    """顧問先詳細"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    client = conn.execute("SELECT * FROM T_顧問先 WHERE id = ?", (client_id,)).fetchone()
    company = conn.execute("SELECT * FROM T_会社基本情報 WHERE 顧問先ID = ?", (client_id,)).fetchone()
    conn.close()
    
    if client is None:
        return "顧問先が見つかりません", 404
    
    return render_template('client_info.html', client=client, company=company)


@bp.route('/<int:client_id>/chat', methods=['GET', 'POST'])
def client_chat(client_id):
    """顧問先別チャット"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    client = conn.execute("SELECT * FROM T_顧問先 WHERE id = ?", (client_id,)).fetchone()
    
    if client is None:
        conn.close()
        return "顧問先が見つかりません", 404
    
    if request.method == 'POST':
        from datetime import datetime
        sender = session['user']
        message = request.form['message']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute(
            "INSERT INTO T_メッセージ (sender, message, timestamp, client_id) VALUES (?, ?, ?, ?)",
            (sender, message, timestamp, client_id)
        )
        conn.commit()
    
    messages = conn.execute(
        "SELECT * FROM T_メッセージ WHERE client_id = ? ORDER BY id DESC LIMIT 20",
        (client_id,)
    ).fetchall()
    conn.close()
    
    return render_template('client_chat.html', client=client, messages=reversed(messages))
