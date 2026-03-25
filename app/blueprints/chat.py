"""
チャット機能ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
from datetime import datetime
import urllib.parse
import requests as http_requests
from app.db import get_conn, SessionLocal
from app.utils.decorators import require_roles, ROLES
from app.models_clients import TClient, TMessage, TMessageRead
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
        
        reader_id = session.get('user_name', user_name)

        if request.method == 'POST':
            message_text = (request.form.get('message') or '').strip()
            uploaded_file = request.files.get('chat_file')

            if uploaded_file and uploaded_file.filename:
                # ファイル送信処理
                try:
                    from app.utils.tenant_storage_adapter import get_storage_adapter
                    adapter = get_storage_adapter(tenant_id)
                    client_folder = getattr(client, 'storage_folder_path', None)
                    file_url = adapter.upload(
                        uploaded_file.stream, uploaded_file.filename, client_id,
                        client_folder_path=client_folder,
                        subfolder=None
                    )
                    # ファイルをT_ファイル共有に保存
                    from app.models_clients import TFile
                    new_file = TFile(
                        client_id=client_id,
                        filename=uploaded_file.filename,
                        file_url=file_url,
                        uploader=user_name,
                        timestamp=datetime.now()
                    )
                    db.add(new_file)
                    # チャットにファイルメッセージを追加
                    new_message = TMessage(
                        client_id=client_id,
                        sender=user_name,
                        sender_type='staff',
                        message=message_text if message_text else None,
                        message_type='file',
                        file_url=file_url,
                        file_name=uploaded_file.filename,
                        timestamp=datetime.now()
                    )
                    db.add(new_message)
                    db.commit()
                    flash(f'ファイル「{uploaded_file.filename}」を送信しました', 'success')
                except Exception as e:
                    db.rollback()
                    flash(f'ファイル送信エラー: {str(e)}', 'error')
            elif message_text:
                # テキストメッセージ送信
                new_message = TMessage(
                    client_id=client_id,
                    sender=user_name,
                    sender_type='staff',
                    message=message_text,
                    message_type='text',
                    timestamp=datetime.now()
                )
                db.add(new_message)
                db.commit()
            return redirect(url_for('chat.client_chat', client_id=client_id))

        # メッセージ一覧を取得
        messages = db.query(TMessage).filter(
            TMessage.client_id == client_id
        ).order_by(TMessage.id.asc()).all()

        # 既読済みメッセージIDセット（staff側が既読にしたもの）
        read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'staff',
            TMessageRead.reader_id == reader_id
        ).all()}

        # client側の未読メッセージを既読に登録
        first_unread_id = None
        for msg in messages:
            if msg.sender_type == 'client' and msg.id not in read_ids:
                if first_unread_id is None:
                    first_unread_id = msg.id
                db.add(TMessageRead(
                    message_id=msg.id,
                    reader_type='staff',
                    reader_id=reader_id
                ))
        db.commit()

        # client側が既読にしたメッセージIDセット（自分（staff）が送ったメッセージの既読状態）
        client_read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'client'
        ).all()}

        return render_template('client_chat.html', client=client, messages=messages,
                               read_ids=read_ids, first_unread_id=first_unread_id,
                               client_read_ids=client_read_ids)
    finally:
        db.close()


@bp.route('/download/message/<int:message_id>')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def download_message_file(message_id):
    """チャットメッセージのファイルをプロキシ経由でダウンロードする"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        msg = db.query(TMessage).filter(TMessage.id == message_id).first()
        if not msg or not msg.file_url:
            flash('ファイルが見つかりません', 'error')
            return redirect(url_for('chat.client_chat', client_id=msg.client_id if msg else 0))
        file_url = msg.file_url
        original_name = msg.file_name or 'download'
        # Cloudinary URLからfl_attachmentを除去（既に含まれている場合）
        if '/fl_attachment:' in file_url:
            import re
            file_url = re.sub(r'/fl_attachment:[^/]+/', '/', file_url)
        resp = http_requests.get(file_url, stream=True, timeout=30)
        resp.raise_for_status()
        encoded_name = urllib.parse.quote(original_name, safe='')
        content_type = resp.headers.get('Content-Type', 'application/octet-stream')
        def generate():
            for chunk in resp.iter_content(chunk_size=8192):
                yield chunk
        return Response(
            generate(),
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}",
                'Content-Type': content_type,
            }
        )
    except Exception as e:
        flash(f'ダウンロードエラー: {str(e)}', 'error')
        return redirect(url_for('chat.client_chat', client_id=0))
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
