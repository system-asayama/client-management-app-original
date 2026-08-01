"""
テナント用ストレージ設定ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.db import SessionLocal
from app.models_login import TTenant
from sqlalchemy import text
from app.utils.decorators import require_roles, ROLES
from app.utils.tenant_storage_adapter import (
    get_dropbox_app_credentials, DROPBOX_APP_KEY, DROPBOX_APP_SECRET,
)

bp = Blueprint('tenant_storage', __name__, url_prefix='/tenant/storage')


def _deactivate_scope(db, tenant_id, store_id):
    """指定スコープ（店舗 or テナント全体）の既存設定のみを無効化する。
    他スコープの設定は温存する。
    """
    if store_id:
        db.execute(text("""
            UPDATE "T_外部ストレージ連携" SET status = 'inactive'
            WHERE tenant_id = :tenant_id AND store_id = :store_id
        """), {"tenant_id": tenant_id, "store_id": store_id})
    else:
        db.execute(text("""
            UPDATE "T_外部ストレージ連携" SET status = 'inactive'
            WHERE tenant_id = :tenant_id AND store_id IS NULL
        """), {"tenant_id": tenant_id})


def _get_dropbox_client(storage_config, db=None, tenant_id=None):
    """リフレッシュトークンを使ってDropboxクライアントを取得（自動更新対応）"""
    import dropbox

    token = storage_config.access_token
    refresh_token = storage_config.refresh_token if hasattr(storage_config, 'refresh_token') else None

    if refresh_token:
        # リフレッシュトークンがある場合は自動更新クライアントを使用
        # App Key/Secret はテナント専用アプリ優先（無ければ共通の既定値）
        app_key, app_secret = get_dropbox_app_credentials(tenant_id or session.get('tenant_id'))
        dbx_base = dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret
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


def _scope_store_id(db, tenant_id):
    """リクエストから店舗スコープ(store_id)を解決する。
    store_id が無い/不正/このテナントの店舗でない場合は None（＝テナント全体）を返す。
    """
    raw = request.values.get('store_id')
    if not raw:
        return None
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return None
    try:
        row = db.execute(text('SELECT id FROM "T_店舗" WHERE id = :sid AND tenant_id = :tid'),
                         {"sid": sid, "tid": tenant_id}).fetchone()
    except Exception:
        row = None
    return sid if row else None


def _scope_name(db, tenant_id, store_id):
    """スコープの表示名（店舗名 or テナント全体）。
    T_店舗 の店舗名カラムは「名称」（日本語）なので name にエイリアスして取得する。
    """
    if not store_id:
        return None
    try:
        row = db.execute(text('SELECT "名称" AS name FROM "T_店舗" WHERE id = :sid AND tenant_id = :tid'),
                         {"sid": store_id, "tid": tenant_id}).fetchone()
        return row.name if row else None
    except Exception:
        return None


def _get_storage_config(db, tenant_id, store_id=None):
    """現在のアクティブなストレージ設定を取得（指定スコープの設定のみ）。
    store_id 指定時はその店舗の設定、None のときはテナント全体（store_id IS NULL）の設定。
    """
    try:
        if store_id:
            result = db.execute(text("""
                SELECT * FROM "T_外部ストレージ連携"
                WHERE tenant_id = :tenant_id AND status = 'active' AND store_id = :store_id
                ORDER BY id DESC LIMIT 1
            """), {"tenant_id": tenant_id, "store_id": store_id})
            return result.fetchone()
        result = db.execute(text("""
            SELECT * FROM "T_外部ストレージ連携"
            WHERE tenant_id = :tenant_id AND status = 'active' AND store_id IS NULL
            ORDER BY id DESC LIMIT 1
        """), {"tenant_id": tenant_id})
        return result.fetchone()
    except Exception:
        # store_id 列が無い旧スキーマ互換
        result = db.execute(text("""
            SELECT * FROM "T_外部ストレージ連携"
            WHERE tenant_id = :tenant_id AND status = 'active'
            ORDER BY id DESC LIMIT 1
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
        try:
            view['scope_store_id'] = storage_config.store_id
        except Exception:
            view['scope_store_id'] = None
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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def storage_settings():
    """ストレージ連携設定トップ（一覧）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        storage_config = _get_storage_config(db, tenant_id, store_id)
        view = _build_view(storage_config)
        return render_template('tenant_storage_settings.html', view=view,
                               store_id=store_id,
                               store_name=_scope_name(db, tenant_id, store_id))
    finally:
        db.close()


# ===========================
# Dropbox 設定ページ
# ===========================
@bp.route('/dropbox', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def storage_dropbox():
    """Dropbox連携設定ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        storage_config = _get_storage_config(db, tenant_id, store_id)
        view = _build_view(storage_config)

        if request.method == 'POST':
            access_token = request.form.get('dropbox_access_token', '').strip()
            base_folder_path = request.form.get('base_folder_path', '').strip()

            if access_token:
                # 同スコープの既存設定のみを無効化
                _deactivate_scope(db, tenant_id, store_id)
                db.execute(text("""
                    INSERT INTO "T_外部ストレージ連携"
                    (tenant_id, store_id, provider, access_token, base_folder_path, status)
                    VALUES (:tenant_id, :store_id, 'dropbox', :access_token, :base_folder_path, 'active')
                """), {
                    "tenant_id": tenant_id,
                    "store_id": store_id,
                    "access_token": access_token,
                    "base_folder_path": base_folder_path or None
                })
                db.commit()
                flash('Dropbox連携を設定しました', 'success')
                return redirect(url_for('tenant_storage.storage_dropbox', store_id=store_id))
            else:
                flash('アクセストークンを入力してください', 'error')

        return render_template('tenant_storage_dropbox.html', view=view,
                               store_id=store_id,
                               store_name=_scope_name(db, tenant_id, store_id))
    finally:
        db.close()


# ===========================
# Dropbox OAuth2 認可フロー
# ===========================
@bp.route('/dropbox/oauth/start', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def dropbox_oauth_start():
    """DropboxのOAuth2認可フローを開始する"""
    from dropbox import DropboxOAuth2Flow
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_storage.storage_dropbox'))

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
    finally:
        db.close()
    # OAuthラウンドトリップ後もスコープを保持
    session['dropbox_scope_store_id'] = store_id

    redirect_uri = url_for('tenant_storage.dropbox_oauth_callback', _external=True)
    csrf_token = f"dropbox_csrf_{tenant_id}"
    session['dropbox_csrf_token'] = csrf_token

    # App Key/Secret はテナント専用アプリ優先（無ければ共通の既定値）
    app_key, app_secret = get_dropbox_app_credentials(tenant_id)
    auth_flow = DropboxOAuth2Flow(
        consumer_key=app_key,
        redirect_uri=redirect_uri,
        session=session,
        csrf_token_session_key='dropbox_csrf_token',
        consumer_secret=app_secret,
        token_access_type='offline'
    )
    authorize_url = auth_flow.start()
    return redirect(authorize_url)


@bp.route('/dropbox/oauth/callback', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def dropbox_oauth_callback():
    """DropboxのOAuth2コールバック処理"""
    from dropbox import DropboxOAuth2Flow
    # OAuth関連の例外は dropbox.oauth に定義されている（dropbox.exceptions ではない）
    from dropbox.oauth import BadRequestException, BadStateException, CsrfException, NotApprovedException, ProviderException

    tenant_id = session.get('tenant_id')
    store_id = session.get('dropbox_scope_store_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_storage.storage_dropbox', store_id=store_id))

    redirect_uri = url_for('tenant_storage.dropbox_oauth_callback', _external=True)
    # App Key/Secret はテナント専用アプリ優先（無ければ共通の既定値）
    app_key, app_secret = get_dropbox_app_credentials(tenant_id)
    auth_flow = DropboxOAuth2Flow(
        consumer_key=app_key,
        redirect_uri=redirect_uri,
        session=session,
        csrf_token_session_key='dropbox_csrf_token',
        consumer_secret=app_secret,
        token_access_type='offline'
    )

    try:
        oauth_result = auth_flow.finish(request.args)
        access_token = oauth_result.access_token
        refresh_token = oauth_result.refresh_token

        db = SessionLocal()
        try:
            # 同スコープの既存設定のみを無効化
            _deactivate_scope(db, tenant_id, store_id)
            # 新しいトークンを保存
            db.execute(text("""
                INSERT INTO "T_外部ストレージ連携"
                (tenant_id, store_id, provider, access_token, refresh_token, status)
                VALUES (:tenant_id, :store_id, 'dropbox', :access_token, :refresh_token, 'active')
            """), {
                "tenant_id": tenant_id,
                "store_id": store_id,
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

    session.pop('dropbox_scope_store_id', None)
    return redirect(url_for('tenant_storage.storage_dropbox', store_id=store_id))


# ===========================
# Dropbox 専用アプリ（App Key/Secret）設定
#   共有アプリのユーザー上限を回避するため、各事務所が自分のDropboxアプリを登録する
# ===========================
@bp.route('/dropbox/app', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def dropbox_app():
    """Dropbox専用アプリ（App Key/Secret）の設定＋手順書"""
    from app.models_integrations import TStorageAppConfig
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    store_id = None
    try:
        store_id = int(request.values.get('store_id')) if request.values.get('store_id') else None
    except (TypeError, ValueError):
        store_id = None

    redirect_uri = url_for('tenant_storage.dropbox_oauth_callback', _external=True)
    db = SessionLocal()
    try:
        row = (db.query(TStorageAppConfig)
                 .filter(TStorageAppConfig.tenant_id == tenant_id,
                         TStorageAppConfig.provider == 'dropbox',
                         TStorageAppConfig.status == 'active')
                 .order_by(TStorageAppConfig.id.desc()).first())
        has_app = bool(row and row.app_key and row.app_secret)
        app_key = (row.app_key if row else '') or ''
        return render_template('tenant_storage_dropbox_app.html',
                               redirect_uri=redirect_uri, has_app=has_app,
                               app_key=app_key, store_id=store_id)
    finally:
        db.close()


@bp.route('/dropbox/app/save', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def dropbox_app_save():
    """Dropbox専用アプリの App Key/Secret を保存"""
    from app.models_integrations import TStorageAppConfig
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    store_id = request.values.get('store_id') or None

    app_key = (request.form.get('app_key') or '').strip()
    app_secret = (request.form.get('app_secret') or '').strip()
    if not app_key:
        flash('App Key を入力してください', 'error')
        return redirect(url_for('tenant_storage.dropbox_app', store_id=store_id))

    db = SessionLocal()
    try:
        row = (db.query(TStorageAppConfig)
                 .filter(TStorageAppConfig.tenant_id == tenant_id,
                         TStorageAppConfig.provider == 'dropbox').first())
        if not row:
            row = TStorageAppConfig(tenant_id=tenant_id, provider='dropbox', status='active')
            db.add(row)
        row.app_key = app_key
        # シークレットが伏字（●のみ等）や空なら変更しない
        if app_secret and set(app_secret) not in ({'●'}, {'*'}, {'•'}):
            row.app_secret = app_secret
        row.status = 'active'
        db.commit()
        flash('この事務所専用のDropboxアプリを設定しました', 'success')
    finally:
        db.close()
    return redirect(url_for('tenant_storage.dropbox_app', store_id=store_id))


@bp.route('/dropbox/app/reset', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def dropbox_app_reset():
    """専用アプリ設定を解除し、共通アプリに戻す"""
    from app.models_integrations import TStorageAppConfig
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    store_id = request.values.get('store_id') or None
    db = SessionLocal()
    try:
        db.query(TStorageAppConfig).filter(
            TStorageAppConfig.tenant_id == tenant_id,
            TStorageAppConfig.provider == 'dropbox').delete()
        db.commit()
        flash('共有アプリに戻しました', 'success')
    finally:
        db.close()
    return redirect(url_for('tenant_storage.dropbox_app', store_id=store_id))


# ===========================
# Dropbox フォルダ一覧API
# ===========================
@bp.route('/dropbox/folders', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def dropbox_folders():
    """DropboxのフォルダツリーをJSON形式で返す"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    path = request.args.get('path', '')  # '' = ルート

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        storage_config = _get_storage_config(db, tenant_id, store_id)
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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
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
        store_id = _scope_store_id(db, tenant_id)
        storage_config = _get_storage_config(db, tenant_id, store_id)
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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def dropbox_set_folder():
    """Dropboxのベースフォルダパスを保存する"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 401

    data = request.get_json()
    folder_path = (data or {}).get('folder_path', '').strip()

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        storage_config = _get_storage_config(db, tenant_id, store_id)
        if not storage_config or storage_config.provider != 'dropbox':
            return jsonify({'error': 'Dropboxが設定されていません'}), 400

        if store_id:
            db.execute(text("""
                UPDATE "T_外部ストレージ連携"
                SET base_folder_path = :folder_path
                WHERE tenant_id = :tenant_id AND status = 'active' AND provider = 'dropbox' AND store_id = :store_id
            """), {"folder_path": folder_path or None, "tenant_id": tenant_id, "store_id": store_id})
        else:
            db.execute(text("""
                UPDATE "T_外部ストレージ連携"
                SET base_folder_path = :folder_path
                WHERE tenant_id = :tenant_id AND status = 'active' AND provider = 'dropbox' AND store_id IS NULL
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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def storage_gcs():
    """Google Cloud Storage連携設定ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        storage_config = _get_storage_config(db, tenant_id, store_id)
        view = _build_view(storage_config)

        if request.method == 'POST':
            bucket_name = request.form.get('gcs_bucket', '').strip()
            service_account_json = request.form.get('gcs_service_account_json', '').strip()
            if bucket_name and service_account_json:
                # 同スコープの既存設定のみを無効化
                _deactivate_scope(db, tenant_id, store_id)
                db.execute(text("""
                    INSERT INTO "T_外部ストレージ連携"
                    (tenant_id, store_id, provider, bucket_name, service_account_json, status)
                    VALUES (:tenant_id, :store_id, 'gcs', :bucket_name, :service_account_json, 'active')
                """), {
                    "tenant_id": tenant_id,
                    "store_id": store_id,
                    "bucket_name": bucket_name,
                    "service_account_json": service_account_json
                })
                db.commit()
                flash('Google Cloud Storage連携を設定しました', 'success')
                return redirect(url_for('tenant_storage.storage_gcs', store_id=store_id))
            else:
                flash('バケット名とサービスアカウントJSONを入力してください', 'error')

        return render_template('tenant_storage_gcs.html', view=view,
                               store_id=store_id,
                               store_name=_scope_name(db, tenant_id, store_id))
    finally:
        db.close()


# ===========================
# 連携解除
# ===========================
@bp.route('/disconnect', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def disconnect_storage():
    """ストレージ連携を解除"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    provider = request.form.get('provider', '')
    # revoke=1 のときは Dropbox 側の認可も取り消す（完全削除）
    revoke = request.form.get('revoke') == '1'
    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        revoke_note = None
        # Dropbox は API で認可自体を取り消せる（連携済みアプリからも消える）
        if provider == 'dropbox' and revoke:
            cfg = _get_storage_config(db, tenant_id, store_id)
            if cfg and (getattr(cfg, 'provider', '') or '').lower() == 'dropbox':
                try:
                    dbx = _get_dropbox_client(cfg, tenant_id=tenant_id)
                    dbx.auth_token_revoke()
                    revoke_note = ('success', 'Dropbox側の認可も取り消しました（Dropboxの「連携済みアプリ」からも削除されます）')
                except Exception as e:  # noqa: BLE001 - 失敗してもアプリ側の解除は続行
                    revoke_note = ('warning', f'Dropbox側の認可取り消しに失敗しました（アプリ側の連携は解除しました）。必要なら https://www.dropbox.com/account/connected_apps から手動で解除してください: {e}')
        # 同スコープの設定のみを解除（他スコープは温存）
        _deactivate_scope(db, tenant_id, store_id)
        db.commit()
        flash('ストレージ連携を解除しました', 'success')
        if revoke_note:
            flash(revoke_note[1], revoke_note[0])
    finally:
        db.close()

    # 解除後は元のページに戻す
    if provider == 'dropbox':
        return redirect(url_for('tenant_storage.storage_dropbox', store_id=store_id))
    elif provider == 'gcs':
        return redirect(url_for('tenant_storage.storage_gcs', store_id=store_id))
    return redirect(url_for('tenant_storage.storage_settings', store_id=store_id))
