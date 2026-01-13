"""
外部ユーザー機能ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session
from datetime import datetime
from app.db import get_conn

bp = Blueprint('external', __name__, url_prefix='/external')


@bp.route('/<int:client_id>', methods=['GET', 'POST'])
def external_portal(client_id):
    """外部ユーザー専用ポータル"""
    if 'external_user' not in session:
        return redirect(url_for('auth.ext_login'))
    
    conn = get_conn()
    client = conn.execute("SELECT * FROM T_顧問先 WHERE id = ?", (client_id,)).fetchone()
    
    if not client:
        conn.close()
        return "顧問先が見つかりません", 404
    
    # メッセージ投稿処理
    if request.method == 'POST' and 'message' in request.form:
        sender = session['external_user']
        message = request.form['message']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute(
            "INSERT INTO T_メッセージ (sender, message, timestamp, client_id) VALUES (?, ?, ?, ?)",
            (sender, message, timestamp, client_id)
        )
        conn.commit()
    
    # メッセージ一覧取得
    messages = conn.execute(
        "SELECT * FROM T_メッセージ WHERE client_id = ? ORDER BY id DESC LIMIT 50",
        (client_id,)
    ).fetchall()
    
    # ファイル一覧取得
    files = conn.execute(
        "SELECT * FROM T_ファイル WHERE client_id = ? ORDER BY id DESC LIMIT 20",
        (client_id,)
    ).fetchall()
    
    conn.close()
    
    # 外部ユーザーが管理者かどうか
    ext_is_admin = session.get('ext_is_admin', False)
    
    return render_template(
        'external_portal.html',
        client=client,
        client_id=client_id,
        messages=reversed(messages),
        files=files,
        ext_is_admin=ext_is_admin,
        page_msg=1,
        page_files=1
    )


@bp.route('/invite/<int:client_id>', methods=['GET', 'POST'])
def invite_external(client_id):
    """外部ユーザー招待"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    client = conn.execute("SELECT * FROM T_顧問先 WHERE id = ?", (client_id,)).fetchone()
    
    if not client:
        conn.close()
        return "顧問先が見つかりません", 404
    
    if request.method == 'POST':
        email = request.form['email']
        name = request.form.get('name', '')
        
        # 招待処理（実際にはメール送信などが必要）
        # ここでは簡易的にT_外部ユーザーテーブルに登録
        conn.execute(
            "INSERT INTO T_外部ユーザー (email, name, client_id) VALUES (?, ?, ?)",
            (email, name, client_id)
        )
        conn.commit()
        conn.close()
        
        return render_template('invite_external_done.html', email=email, client=client)
    
    conn.close()
    return render_template('invite_external_form.html', client=client, client_id=client_id)
