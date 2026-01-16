"""
テナント用ストレージ設定ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.db import SessionLocal
from app.models import TTenant
from sqlalchemy import text
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('tenant_storage', __name__, url_prefix='/tenant/storage')


@bp.route('/', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def storage_settings():
    """テナントのストレージ設定画面"""
    tenant_id = session.get('tenant_id')
    
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        # 現在のストレージ設定を取得
        result = db.execute(text("""
            SELECT * FROM "T_外部ストレージ連携"
            WHERE tenant_id = :tenant_id AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """), {"tenant_id": tenant_id})
        storage_config = result.fetchone()
        
        if request.method == 'POST':
            provider = request.form.get('provider', '').strip().lower()
            
            # 既存の設定を無効化
            db.execute(text("""
                UPDATE "T_外部ストレージ連携"
                SET status = 'inactive'
                WHERE tenant_id = :tenant_id
            """), {"tenant_id": tenant_id})
            
            if provider == 'dropbox':
                access_token = request.form.get('dropbox_access_token', '').strip()
                
                if access_token:
                    db.execute(text("""
                        INSERT INTO "T_外部ストレージ連携" 
                        (tenant_id, provider, access_token, status)
                        VALUES (:tenant_id, 'dropbox', :access_token, 'active')
                    """), {
                        "tenant_id": tenant_id,
                        "access_token": access_token
                    })
                    db.commit()
                    flash('Dropbox連携を設定しました', 'success')
                else:
                    flash('アクセストークンを入力してください', 'error')
                    
            elif provider == 'gcs':
                bucket_name = request.form.get('gcs_bucket', '').strip()
                service_account_json = request.form.get('gcs_service_account_json', '').strip()
                
                if bucket_name and service_account_json:
                    db.execute(text("""
                        INSERT INTO "T_外部ストレージ連携" 
                        (tenant_id, provider, bucket_name, service_account_json, status)
                        VALUES (:tenant_id, 'gcs', :bucket_name, :service_account_json, 'active')
                    """), {
                        "tenant_id": tenant_id,
                        "bucket_name": bucket_name,
                        "service_account_json": service_account_json
                    })
                    db.commit()
                    flash('Google Cloud Storage連携を設定しました', 'success')
                else:
                    flash('バケット名とサービスアカウントJSONを入力してください', 'error')
            
            return redirect(url_for('tenant_storage.storage_settings'))
        
        # ビュー用データの準備
        view = {
            'is_connected': False,
            'provider': None,
            'dropbox_access_token': '',
            'gcs_bucket': '',
            'gcs_service_account_json_masked': ''
        }
        
        if storage_config:
            view['is_connected'] = True
            view['provider'] = storage_config.provider
            
            if storage_config.provider == 'dropbox':
                token = storage_config.access_token or ''
                # トークンをマスク表示
                if len(token) > 10:
                    view['dropbox_access_token'] = token[:6] + '...' + token[-4:]
                else:
                    view['dropbox_access_token'] = '（設定済み）'
                    
            elif storage_config.provider == 'gcs':
                view['gcs_bucket'] = storage_config.bucket_name or ''
                view['gcs_service_account_json_masked'] = '（設定済み）' if storage_config.service_account_json else ''
        
        return render_template('tenant_storage_settings.html', view=view)
        
    finally:
        db.close()


@bp.route('/disconnect', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def disconnect_storage():
    """ストレージ連携を解除"""
    tenant_id = session.get('tenant_id')
    
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        db.execute(text("""
            UPDATE "T_外部ストレージ連携"
            SET status = 'inactive'
            WHERE tenant_id = :tenant_id
        """), {"tenant_id": tenant_id})
        db.commit()
        flash('ストレージ連携を解除しました', 'success')
    finally:
        db.close()
    
    return redirect(url_for('tenant_storage.storage_settings'))
