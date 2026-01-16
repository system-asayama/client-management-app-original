"""
ファイル共有機能ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from app.db import SessionLocal
from app.utils.tenant_storage_adapter import get_storage_adapter
from app.utils.decorators import require_roles, ROLES
from app.models_clients import TClient, TFile
from sqlalchemy import and_

bp = Blueprint('files', __name__, url_prefix='/files')


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
                    # テナントのストレージアダプタを取得
                    adapter = get_storage_adapter(tenant_id)
                    
                    # ファイルをアップロード
                    file_url = adapter.upload(f.stream, f.filename, client_id)
                    
                    # データベースに記録
                    new_file = TFile(
                        client_id=client_id,
                        filename=f.filename,
                        file_url=file_url,
                        uploader=user_name,
                        timestamp=datetime.now()
                    )
                    db.add(new_file)
                    db.commit()
                    
                    flash(f'ファイル「{f.filename}」をアップロードしました', 'success')
                except RuntimeError as e:
                    flash(f'エラー: {str(e)}', 'error')
                    if 'ストレージが設定されていません' in str(e):
                        flash('テナント管理画面でストレージ連携を設定してください', 'warning')
                except Exception as e:
                    flash(f'アップロードエラー: {str(e)}', 'error')
                    db.rollback()
                
                return redirect(url_for('files.client_files', client_id=client_id))
        
        # アップロード済みファイル一覧を取得
        files = db.query(TFile).filter(
            TFile.client_id == client_id
        ).order_by(TFile.timestamp.desc()).all()
        
        return render_template(
            'client_files.html',
            client=client,
            files=files
        )
        
    finally:
        db.close()
