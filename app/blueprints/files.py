"""
ファイル共有機能ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session
from datetime import datetime
from app.db import get_conn
from app.utils.storage_adapter import get_storage_adapter

bp = Blueprint('files', __name__, url_prefix='/files')


def ensure_org_in_session():
    """セッションに事業所IDを設定（暫定）"""
    if 'org_id' not in session:
        session['org_id'] = 1


@bp.route('/', methods=['GET', 'POST'])
def files():
    """ファイル一覧・アップロード"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    ensure_org_in_session()
    org_id = session['org_id']
    
    conn = get_conn()
    
    if request.method == 'POST':
        f = request.files.get('file')
        if f and f.filename:
            try:
                # ストレージアダプタを使用してアップロード
                adapter = get_storage_adapter(org_id)
                url = adapter.upload(f.stream, f.filename)
                
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # T_ファイルテーブルに保存（filename にURLを格納）
                conn.execute(
                    "INSERT INTO T_ファイル (filename, uploader, timestamp) VALUES (?, ?, ?)",
                    (url, session['user'], ts)
                )
                conn.commit()
            except Exception as e:
                # エラーハンドリング（ログ出力など）
                print(f"ファイルアップロードエラー: {e}")
    
    rows = conn.execute("SELECT * FROM T_ファイル ORDER BY id DESC").fetchall()
    conn.close()
    
    return render_template('files.html', files=rows)
