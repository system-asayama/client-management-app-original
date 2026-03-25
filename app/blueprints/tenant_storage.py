"""
テナント用ストレージ設定ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.db import SessionLocal
from app.models_login import TTenant
from sqlalchemy import text
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('tenant_storage', __name__, url_prefix='/tenant/storage')

DROPBOX_APP_KEY = 'mwfin8b98ui38m8'
DROPBOX_APP_SECRET = '1qwwluws6do5ht0'


def _get_dropbox_client(storage_config, db=None, tenant_id=None):
    """リフレッシュトークンを使ってDropboxクライアントを取得（自動更新対応）"""
    import dropbox

    token = storage_config.access_token
    refresh_token = storage_config.refresh_token if hasattr(storage_config, 'refresh_token') else None

    if refresh_token:
        # リフレッシュトークンがある場合は自動更新クライアントを使用
        dbx_base = dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=DROPBOX_APP_KEY,
            app_secret=DROPBOX_APP_SECRET
        )
    else:
        # リフレッシュトークンがない場合は通常のアクセストークンを使用
        dbx_base = dropbox.Dropbox(oauth2_access_token=token)

    # チームスペース対応
    try:
        acc = dbx_base.users_get_current_account()
        root_ns = acc.root_info.root_namespace_id if (acc.root_info and acc.root_info.root_namespace_id) else None
    except Exception:
        root_ns = None

    if root_ns:
        return dbx_base.with_path_root(dropbox.common.PathRoot.namespace_id(root_ns))
    return dbx_base


def _get_storage_config(db, tenant_id):
    """現在のアクティブなストレージ設定を取得"""
    result = db.execute(text("""
        SELECT * FROM "T_外部ストレージ連携"
        WHERE tenant_id = :tenant_id AND status = 'active'
        ORDER BY id DESC
        LIMIT 1
    """), {"tenant_id": tenant_id})
    return result.fetchone()


def _build_view(storage_config):
    """テンプレート用のビューデータを構築"""
    view = {
        'is_connected': False,
        'provider': None,
        'dropbox_access_token': '',
        'dropbox_base_folder': '',
        'gcs_bucket': '',
        'gcs_service_account_json_masked': ''
    }
    if storage_config:
        view['is_connected'] = True
        view['provider'] = storage_config.provider
        if storage_config.provider == 'dropbox':
            token = storage_config.access_token or ''
            if len(token) > 10:
                view['dropbox_access_token'] = token[:6] + '...' + token[-4:]
            else:
                view['dropbox_access_token'] = '（設定済み）'
            # base_folder_pathが存在する場合は取得
            try:
                view['dropbox_base_folder'] = storage_config.base_folder_path or ''
            except Exception:
                view['dropbox_base_folder'] = ''
        elif storage_config.provider == 'gcs':
            view['gcs_bucket'] = storage_config.bucket_name or ''
            view['gcs_service_account_json_masked'] = '（設定済み）' if storage_config.service_account_json else ''
    return view


# ===========================
# 一覧ページ（トップ）
# ===========================
@bp.route('/', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def storage_settings():
    """ストレージ連携設定トップ（一覧）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        storage_config = _get_storage_config(db, tenant_id)
        view = _build_view(storage_config)
        return render_template('tenant_storage_settings.html', view=view)
    finally:
        db.close()


# ===========================
# Dropbox 設定ページ
# ===========================
@bp.route('/dropbox', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def storage_dropbox():
    """Dropbox連携設定ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        storage_config = _get_storage_config(db, tenant_id)
        view = _build_view(storage_config)

        if request.method == 'POST':
            access_token = request.form.get('dropbox_access_token', '').strip()
            base_folder_path = request.form.get('base_folder_path', '').strip()

            if access_token:
                # 既存設定を無効化
                db.execute(text("""
                    UPDATE "T_外部ストレージ連携"
                    SET status = 'inactive'
                    WHERE tenant_id = :tenant_id
                """), {"tenant_id": tenant_id})
                db.execute(text("""
                    INSERT INTO "T_外部ストレージ連携"
                    (tenant_id, provider, access_token, base_folder_path, status)
                    VALUES (:tenant_id, 'dropbox', :access_token, :base_folder_path, 'active')
                """), {
                    "tenant_id": tenant_id,
                    "access_token": access_token,
                    "base_folder_path": base_folder_path or None
                })
                db.commit()
                flash('Dropbox連携を設定しました', 'success')
                return redirect(url_for('tenant_storage.storage_dropbox'))
            else:
                flash('アクセストークンを入力してください', 'error')

        return render_template('tenant_storage_dropbox.html', view=view)
    finally:
        db.close()


# ===========================
# Dropbox OAuth2 認可フロー
# ===========================
@bp.route('/dropbox/oauth/start', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def dropbox_oauth_start():
    """DropboxのOAuth2認可フローを開始する"""
    from dropbox import DropboxOAuth2Flow
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_storage.storage_dropbox'))

    redirect_uri = url_for('tenant_storage.dropbox_oauth_callback', _external=True)
    csrf_token = f"dropbox_csrf_{tenant_id}"
    session['dropbox_csrf_token'] = csrf_token

    auth_flow = DropboxOAuth2Flow(
        consumer_key=DROPBOX_APP_KEY,
        redirect_uri=redirect_uri,
        session=session,
        csrf_token_session_key='dropbox_csrf_token',
        consumer_secret=DROPBOX_APP_SECRET,
        token_access_type='offline'
    )
    authorize_url = auth_flow.start()
    return redirect(authorize_url)


@bp.route('/dropbox/oauth/callback', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def dropbox_oauth_callback():
    """DropboxのOAuth2コールバック処理"""
    from dropbox import DropboxOAuth2Flow
    from dropbox.exceptions import BadRequestException, BadStateException, CsrfException, NotApprovedException, ProviderException

    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_storage.storage_dropbox'))

    redirect_uri = url_for('tenant_storage.dropbox_oauth_callback', _external=True)
    auth_flow = DropboxOAuth2Flow(
        consumer_key=DROPBOX_APP_KEY,
        redirect_uri=redirect_uri,
        session=session,
        csrf_token_session_key='dropbox_csrf_token',
        consumer_secret=DROPBOX_APP_SECRET,
        token_access_type='offline'
    )

    try:
        oauth_result = auth_flow.finish(request.args)
        access_token = oauth_result.access_token
        refresh_token = oauth_result.refresh_token

        db = SessionLocal()
        try:
            # 既存設定を無効化
            db.execute(text("""
                UPDATE "T_外部ストレージ連携"
                SET status = 'inactive'
                WHERE tenant_id = :tenant_id
            """), {"tenant_id": tenant_id})
            # 新しいトークンを保存
            db.execute(text("""
                INSERT INTO "T_外部ストレージ連携"
                (tenant_id, provider, access_token, refresh_token, status)
                VALUES (:tenant_id, 'dropbox', :access_token, :refresh_token, 'active')
            """), {
                "tenant_id": tenant_id,
                "access_token": access_token,
                "refresh_token": refresh_token
            })
            db.commit()
            flash('Dropboxとの連携が完了しました！', 'success')
        except Exception as e:
            db.rollback()
            flash(f'DB保存に失敗しました: {e}', 'error')
        finally:
            db.close()

    except BadStateException:
        flash('セッションが切れました。もう一度お試しください。', 'error')
    except CsrfException:
        flash('セキュリティエラーが発生しました。もう一度お試しください。', 'error')
    except NotApprovedException:
        flash('Dropboxの認証がキャンセルされました。', 'warning')
    except Exception as e:
        flash(f'Dropbox連携に失敗しました: {e}', 'error')

    return redirect(url_for('tenant_storage.storage_dropbox'))


# ===========================
# Dropbox フォルダ一覧API
# ===========================
@bp.route('/dropbox/folders', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def dropbox_folders():
    """DropboxのフォルダツリーをJSON形式で返す"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    path = request.args.get('path', '')  # '' = ルート

    db = SessionLocal()
    try:
        storage_config = _get_storage_config(db, tenant_id)
        if not storage_config or storage_config.provider != 'dropbox':
            return jsonify({'error': 'Dropboxが設定されていません'}), 400

        token = storage_config.access_token
        if not token:
            return jsonify({'error': 'アクセストークンが未設定です'}), 400
    finally:
        db.close()

    try:
        import dropbox
        dbx = _get_dropbox_client(storage_config)
        result = dbx.files_list_folder(path, include_non_downloadable_files=False)
        folders = []
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FolderMetadata):
                folders.append({
                    'id': entry.path_lower,
                    'name': entry.name,
                    'path': entry.path_display,
                    'has_children': True  # 展開時に確認
                })
        # ページネーション
        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FolderMetadata):
                    folders.append({
                        'id': entry.path_lower,
                        'name': entry.name,
                        'path': entry.path_display,
                        'has_children': True
                    })
        folders.sort(key=lambda x: x['name'].lower())
        return jsonify({'folders': folders, 'path': path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===========================
# Dropbox フォルダ作成API
# ===========================
@bp.route('/dropbox/create-folder', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def dropbox_create_folder():
    """Dropboxに新規フォルダを作成する"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    data = request.get_json()
    folder_path = (data or {}).get('folder_path', '').strip()
    if not folder_path:
        return jsonify({'error': 'フォルダパスを指定してください'}), 400

    db = SessionLocal()
    try:
        storage_config = _get_storage_config(db, tenant_id)
        if not storage_config or storage_config.provider != 'dropbox':
            return jsonify({'error': 'Dropboxが設定されていません'}), 400
        token = storage_config.access_token
    finally:
        db.close()

    try:
        import dropbox
        from dropbox.exceptions import ApiError
        dbx = _get_dropbox_client(storage_config)

        # パスが / で始まらない場合は追加
        if not folder_path.startswith('/'):
            folder_path = '/' + folder_path
        result = dbx.files_create_folder_v2(folder_path, autorename=False)
        created_path = result.metadata.path_display
        return jsonify({'success': True, 'path': created_path, 'name': result.metadata.name})
    except Exception as e:
        err_str = str(e)
        if 'path/conflict' in err_str or 'folder_conflict' in err_str or 'already exists' in err_str.lower():
            return jsonify({'error': 'そのフォルダは既に存在します'}), 409
        return jsonify({'error': err_str}), 500


# ===========================
# Dropbox ベースフォルダ保存API
# ===========================
@bp.route('/dropbox/set-folder', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def dropbox_set_folder():
    """Dropboxのベースフォルダパスを保存する"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    data = request.get_json()
    folder_path = (data or {}).get('folder_path', '').strip()

    db = SessionLocal()
    try:
        storage_config = _get_storage_config(db, tenant_id)
        if not storage_config or storage_config.provider != 'dropbox':
            return jsonify({'error': 'Dropboxが設定されていません'}), 400

        db.execute(text("""
            UPDATE "T_外部ストレージ連携"
            SET base_folder_path = :folder_path
            WHERE tenant_id = :tenant_id AND status = 'active' AND provider = 'dropbox'
        """), {"folder_path": folder_path or None, "tenant_id": tenant_id})
        db.commit()
        return jsonify({'success': True, 'folder_path': folder_path})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ===========================
# Google Cloud Storage 設定ページ
# ===========================
@bp.route('/gcs', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def storage_gcs():
    """Google Cloud Storage連携設定ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        storage_config = _get_storage_config(db, tenant_id)
        view = _build_view(storage_config)

        if request.method == 'POST':
            bucket_name = request.form.get('gcs_bucket', '').strip()
            service_account_json = request.form.get('gcs_service_account_json', '').strip()
            if bucket_name and service_account_json:
                # 既存設定を無効化
                db.execute(text("""
                    UPDATE "T_外部ストレージ連携"
                    SET status = 'inactive'
                    WHERE tenant_id = :tenant_id
                """), {"tenant_id": tenant_id})
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
                return redirect(url_for('tenant_storage.storage_gcs'))
            else:
                flash('バケット名とサービスアカウントJSONを入力してください', 'error')

        return render_template('tenant_storage_gcs.html', view=view)
    finally:
        db.close()


# ===========================
# 連携解除
# ===========================
@bp.route('/disconnect', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def disconnect_storage():
    """ストレージ連携を解除"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    provider = request.form.get('provider', '')
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

    # 解除後は元のページに戻す
    if provider == 'dropbox':
        return redirect(url_for('tenant_storage.storage_dropbox'))
    elif provider == 'gcs':
        return redirect(url_for('tenant_storage.storage_gcs'))
    return redirect(url_for('tenant_storage.storage_settings'))
