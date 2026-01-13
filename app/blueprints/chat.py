"""
チャット機能ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session
from datetime import datetime
from app.db import get_conn

bp = Blueprint('chat', __name__, url_prefix='/chat')


@bp.route('/', methods=['GET', 'POST'])
def chat():
    """全体チャットルーム"""
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
