"""
ファイル共有機能ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from app.db import get_conn, SessionLocal
from app.utils.storage_adapter import get_storage_adapter
from app.utils.decorators import require_roles, ROLES
from app.models_clients import TClient, TFile
from sqlalchemy import and_

bp = Blueprint('files', __name__, url_prefix='/files')


def ensure_org_in_session():
    """セッションに事業所IDを設定（暫定）"""
    if 'org_id' not in session:
        session['org_id'] = 1


@bp.route('/client/<int:client_id>', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def client_files(client_id):
    """顧問先ごとのファイル共有"""
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
            f = request.files.get('file')
            if f and f.filename:
                try:
                    # ストレージアダプタを使用してアップロード
                    ensure_org_in_session()
                    org_id = session['org_id']
                    adapter = get_storage_adapter(org_id)
                    url = adapter.upload(f.stream, f.filename)
                    
                    # T_ファイルテーブルに保存
                    new_file = TFile(
                        client_id=client_id,
                        filename=f.filename,
                        file_url=url,
                        uploader=user_name,
                        timestamp=datetime.now()
                    )
                    db.add(new_file)
                    db.commit()
                    flash('ファイルをアップロードしました', 'success')
                except Exception as e:
                    db.rollback()
                    flash(f'ファイルアップロードエラー: {str(e)}', 'error')
                    print(f"ファイルアップロードエラー: {e}")
                
                return redirect(url_for('files.client_files', client_id=client_id))
        
        # ファイル一覧を取得
        files = db.query(TFile).filter(
            TFile.client_id == client_id
        ).order_by(TFile.id.desc()).all()
        
        return render_template('client_files.html', client=client, files=files)
    finally:
        db.close()


@bp.route('/', methods=['GET', 'POST'])
def files():
    """ファイル一覧・アップロード（旧版）"""
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
