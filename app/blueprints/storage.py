"""
ストレージ設定ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session
from app.db import get_conn
from app.utils.storage_adapter import get_active_storage_row

bp = Blueprint('storage', __name__, url_prefix='/storage')


@bp.route('/<int:org_id>', methods=['GET', 'POST'])
def storage_settings(org_id):
    """ストレージ設定画面"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    
    # 現在の設定を取得
    row = get_active_storage_row(org_id)
    
    # ビュー用データの準備
    view = {}
    if row:
        view['provider'] = row.get('provider', '')
        view['status'] = row.get('status', '')
        view['更新日時'] = row.get('updated_at', '')
        
        provider = (row.get('provider') or '').strip().lower()
        view['connected_provider'] = provider
        
        if provider == 'dropbox':
            view['is_dropbox_connected'] = True
            view['dropbox_app_key'] = row.get('app_key', '')
            view['dropbox_app_secret'] = row.get('app_secret', '')
            view['dropbox_refresh_token'] = row.get('refresh_token', '')
            view['dropbox_access_token'] = row.get('access_token', '')
        elif provider in ('gcs', 'google', 'google_cloud_storage'):
            view['is_gcs_connected'] = True
            view['gcs_bucket'] = row.get('bucket_name', '')
            view['gcs_sa_json_mask'] = '（設定済み）' if row.get('service_account_json') else '（未設定）'
            view['gcs_oauth_refresh_token'] = row.get('oauth_refresh_token', '')
    
    if request.method == 'POST':
        # 設定の更新処理
        provider = request.form.get('provider', '').strip().lower()
        
        if provider == 'dropbox':
            app_key = request.form.get('dropbox_app_key', '')
            app_secret = request.form.get('dropbox_app_secret', '')
            refresh_token = request.form.get('dropbox_refresh_token', '')
            
            conn.execute("""
                INSERT OR REPLACE INTO T_外部ストレージ連携 
                (事業所ID, provider, app_key, app_secret, refresh_token, status)
                VALUES (?, ?, ?, ?, ?, 'active')
            """, (org_id, 'dropbox', app_key, app_secret, refresh_token))
            
        elif provider in ('gcs', 'google'):
            bucket_name = request.form.get('gcs_bucket', '')
            sa_json = request.form.get('gcs_sa_json', '')
            
            conn.execute("""
                INSERT OR REPLACE INTO T_外部ストレージ連携 
                (事業所ID, provider, bucket_name, service_account_json, status)
                VALUES (?, ?, ?, ?, 'active')
            """, (org_id, 'gcs', bucket_name, sa_json))
        
        conn.commit()
        conn.close()
        
        return redirect(url_for('storage.storage_settings', org_id=org_id))
    
    conn.close()
    
    return render_template('storage_settings.html', org_id=org_id, row=row, view=view)
