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


def _set_primary_assignment(db, tenant_id, store_id, connection_id):
    """スコープ（店舗 or 本部既定=None）の「主に使用する接続」を connection_id に設定。
    既存の主割当は解除してから新しい割当を作る。
    """
    from app.models_integrations import TStoreStorageAssignment
    q = db.query(TStoreStorageAssignment).filter(
        TStoreStorageAssignment.tenant_id == tenant_id,
        TStoreStorageAssignment.status == 'active',
        TStoreStorageAssignment.is_primary == 1)
    if store_id is None:
        q = q.filter(TStoreStorageAssignment.store_id.is_(None))
    else:
        q = q.filter(TStoreStorageAssignment.store_id == store_id)
    for a in q.all():
        a.is_primary = 0
        a.status = 'inactive'
    db.add(TStoreStorageAssignment(
        tenant_id=tenant_id, store_id=store_id,
        connection_id=connection_id, is_primary=1, status='active'))


def _add_connection(db, tenant_id, scope_store_id, name=None, **fields):
    """接続プールに新しい接続を追加し、そのスコープの主割当に設定する。
    scope_store_id は登録元（本部=None / 店舗=ID）で、その店舗（or 本部既定）に自動割当。
    戻り値: 追加した接続。
    """
    from app.models_integrations import TStorageConnection
    conn = TStorageConnection(
        tenant_id=tenant_id, store_id=scope_store_id, name=name,
        status='active', **fields)
    db.add(conn)
    db.flush()  # id を確定
    _set_primary_assignment(db, tenant_id, scope_store_id, conn.id)
    return conn


def _dropbox_account_ref(access_token, refresh_token, tenant_id):
    """Dropboxアカウントの識別子（account_id）を取得する。失敗時は None。"""
    try:
        import dropbox
        if refresh_token:
            app_key, app_secret = get_dropbox_app_credentials(tenant_id)
            dbx = dropbox.Dropbox(oauth2_refresh_token=refresh_token,
                                  app_key=app_key, app_secret=app_secret)
        else:
            dbx = dropbox.Dropbox(oauth2_access_token=access_token)
        acc = dbx.users_get_current_account()
        return getattr(acc, 'account_id', None)
    except Exception:
        return None


def _connect_dropbox(db, tenant_id, store_id, access_token, refresh_token, name,
                     base_folder_path=None):
    """Dropbox接続を追加。ただし同じアカウントが同スコープに既にあれば、
    新規作成せず既存を更新（重複を作らない）。戻り値: (接続, 更新したか)。
    """
    from app.models_integrations import TStorageConnection
    account_ref = _dropbox_account_ref(access_token, refresh_token, tenant_id)
    existing = None
    if account_ref:
        q = db.query(TStorageConnection).filter(
            TStorageConnection.tenant_id == tenant_id,
            TStorageConnection.provider == 'dropbox',
            TStorageConnection.status == 'active',
            TStorageConnection.account_ref == account_ref)
        q = q.filter(TStorageConnection.store_id.is_(None)) if store_id is None \
            else q.filter(TStorageConnection.store_id == store_id)
        existing = q.order_by(TStorageConnection.id.desc()).first()
    if existing:
        existing.access_token = access_token
        if refresh_token:
            existing.refresh_token = refresh_token
        if base_folder_path is not None:
            existing.base_folder_path = base_folder_path
        existing.status = 'active'
        _set_primary_assignment(db, tenant_id, store_id, existing.id)
        return existing, True
    conn = _add_connection(db, tenant_id, store_id, name=name, provider='dropbox',
                           access_token=access_token, refresh_token=refresh_token,
                           account_ref=account_ref, base_folder_path=base_folder_path)
    return conn, False


def _store_name(db, tenant_id, store_id):
    if not store_id:
        return None
    try:
        row = db.execute(text('SELECT "名称" AS name FROM "T_店舗" WHERE id=:s AND tenant_id=:t'),
                         {"s": store_id, "t": tenant_id}).fetchone()
        return row.name if row else None
    except Exception:
        return None


def _default_conn_name(db, tenant_id, store_id, provider):
    label = {'dropbox': 'Dropbox', 'gcs': 'Google Cloud Storage'}.get((provider or '').lower(), provider or 'ストレージ')
    sn = _store_name(db, tenant_id, store_id)
    base = f'{label}（{sn}）' if sn else f'{label}（本部）'
    # 同名がすでにある場合は連番を付けて見分けられるようにする
    try:
        existing = {r.name for r in db.execute(text('''
            SELECT name FROM "T_外部ストレージ連携"
            WHERE tenant_id = :t AND status = 'active' AND name IS NOT NULL
        '''), {"t": tenant_id}).fetchall()}
    except Exception:
        existing = set()
    if base not in existing:
        return base
    n = 2
    while f'{base}({n})' in existing:
        n += 1
    return f'{base}({n})'


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


def _scope_access_ok(db, tenant_id, store_id):
    """このスコープ（テナント全体 or 店舗）を操作してよいユーザーか判定する。
    - 本部系（system_admin / tenant_admin / app_manager）: テナント全体・任意店舗OK
    - 店舗管理者（admin）: 自分が所属する店舗のみOK（テナント全体設定は不可）
    """
    role = session.get('role')
    if role in (ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['APP_MANAGER']):
        return True
    if role == ROLES['ADMIN']:
        if not store_id:
            return False  # 店舗管理者はテナント全体（本部）設定は不可
        try:
            row = db.execute(text('SELECT 1 FROM "T_管理者_店舗" WHERE admin_id = :a AND store_id = :s'),
                             {"a": session.get('user_id'), "s": store_id}).fetchone()
            return bool(row)
        except Exception:
            return False
    return False


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
    """現在“実際に使われる”ストレージ接続を取得する。
    ファイル保存と同じ解決（割当→旧スコープ）を使い、画面表示と実挙動を一致させる。
    """
    from app.utils.tenant_storage_adapter import get_tenant_storage_config
    return get_tenant_storage_config(tenant_id, store_id=store_id)


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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def storage_settings():
    """ストレージ連携設定トップ（一覧）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        if not _scope_access_ok(db, tenant_id, store_id):
            flash('この設定を操作する権限がありません（店舗管理者は自店のみ設定できます）', 'error')
            return redirect(url_for('staff_mypage.dashboard'))
        storage_config = _get_storage_config(db, tenant_id, store_id)
        view = _build_view(storage_config)

        # 店舗スコープでは、この店舗に登録された接続一覧と使用中を渡す（2つ目以降の管理用）
        store_conns = []
        current_conn_id = None
        if store_id:
            from app.models_integrations import TStorageConnection, TStoreStorageAssignment
            _plabel = {'dropbox': 'Dropbox', 'gcs': 'Google Cloud Storage', 'cloudinary': 'Cloudinary'}
            cs = (db.query(TStorageConnection)
                    .filter(TStorageConnection.tenant_id == tenant_id,
                            TStorageConnection.store_id == store_id,
                            TStorageConnection.status == 'active')
                    .order_by(TStorageConnection.id.desc()).all())
            # この店舗スコープの割当（役割）を取得
            role_map = {}
            for a in (db.query(TStoreStorageAssignment)
                        .filter(TStoreStorageAssignment.tenant_id == tenant_id,
                                TStoreStorageAssignment.store_id == store_id,
                                TStoreStorageAssignment.status == 'active').all()):
                role_map[a.connection_id] = 'primary' if a.is_primary == 1 else 'mirror'
                if a.is_primary == 1:
                    current_conn_id = a.connection_id
            store_conns = [{'id': c.id, 'name': c.name or f'接続{c.id}',
                            'provider': _plabel.get((c.provider or '').lower(), c.provider or ''),
                            'role': role_map.get(c.id)} for c in cs]

        # 隔離モード（店舗ごと fail-closed）の現在値
        storage_isolated = False
        if store_id:
            try:
                _r = db.execute(text('SELECT storage_isolated FROM "T_店舗" WHERE id = :s'),
                                {"s": store_id}).fetchone()
                storage_isolated = bool(_r and _r[0])
            except Exception:
                storage_isolated = False

        return render_template('tenant_storage_settings.html', view=view,
                               store_id=store_id,
                               store_name=_scope_name(db, tenant_id, store_id),
                               store_conns=store_conns, current_conn_id=current_conn_id,
                               storage_isolated=storage_isolated)
    finally:
        db.close()


# ===========================
# Dropbox 設定ページ
# ===========================
@bp.route('/dropbox', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def storage_dropbox():
    """Dropbox連携設定ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        if not _scope_access_ok(db, tenant_id, store_id):
            flash('この設定を操作する権限がありません（店舗管理者は自店のみ設定できます）', 'error')
            return redirect(url_for('staff_mypage.dashboard'))
        storage_config = _get_storage_config(db, tenant_id, store_id)
        view = _build_view(storage_config)

        if request.method == 'POST':
            access_token = request.form.get('dropbox_access_token', '').strip()
            base_folder_path = request.form.get('base_folder_path', '').strip()

            if access_token:
                # 同じアカウントなら重複を作らず既存を更新
                _, updated = _connect_dropbox(
                    db, tenant_id, store_id, access_token, None,
                    name=_default_conn_name(db, tenant_id, store_id, 'dropbox'),
                    base_folder_path=base_folder_path or None)
                db.commit()
                flash('既存の接続を更新しました（重複は作成していません）' if updated else 'Dropbox連携を設定しました', 'success')
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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
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
        access_ok = _scope_access_ok(db, tenant_id, store_id)
    finally:
        db.close()
    if not access_ok:
        flash('この設定を操作する権限がありません（店舗管理者は自店のみ設定できます）', 'error')
        return redirect(url_for('staff_mypage.dashboard'))
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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
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
    _db = SessionLocal()
    try:
        _ok = _scope_access_ok(_db, tenant_id, store_id)
    finally:
        _db.close()
    if not _ok:
        flash('この設定を操作する権限がありません', 'error')
        return redirect(url_for('staff_mypage.dashboard'))

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
            # 同じアカウントなら重複を作らず既存を更新
            _, updated = _connect_dropbox(
                db, tenant_id, store_id, access_token, refresh_token,
                name=_default_conn_name(db, tenant_id, store_id, 'dropbox'))
            db.commit()
            flash('既存のDropbox接続を更新しました（重複は作成していません）' if updated else 'Dropboxとの連携が完了しました！', 'success')
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


def _get_connection_by_id(db, tenant_id, connection_id):
    """テナント内の有効な接続を id で取得（無ければ None）。"""
    try:
        return db.execute(text('''
            SELECT * FROM "T_外部ストレージ連携"
            WHERE id = :c AND tenant_id = :t AND status = 'active'
        '''), {"c": connection_id, "t": tenant_id}).fetchone()
    except Exception:
        return None


def _resolve_browse_config(db, tenant_id, store_id):
    """フォルダ閲覧に使う接続を解決する。
    connection_id 指定があればその接続（アクセス可否を検証）、無ければ主接続。
    """
    conn_id = request.args.get('connection_id')
    if conn_id and str(conn_id).isdigit():
        row = _get_connection_by_id(db, tenant_id, int(conn_id))
        if row is not None:
            # 店舗管理者は自店が登録した接続のみ閲覧可（他店・本部接続は不可）
            if session.get('role') == ROLES['ADMIN'] and getattr(row, 'store_id', None) != store_id:
                return None
            return row
    return _get_storage_config(db, tenant_id, store_id)


@bp.route('/dropbox/browse-connections', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def dropbox_browse_connections():
    """フォルダ選択で切り替えられる、連携済みDropbox接続の一覧を返す。
    店舗スコープ: その店舗の接続＋本部の接続。本部スコープ: テナント全体。
    店舗管理者は自店の接続のみ。
    """
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'no tenant'}), 401
    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        if not _scope_access_ok(db, tenant_id, store_id):
            return jsonify({'error': '権限がありません'}), 403
        is_admin = session.get('role') == ROLES['ADMIN']
        if store_id and is_admin:
            rows = db.execute(text('''
                SELECT id, name FROM "T_外部ストレージ連携"
                WHERE tenant_id = :t AND status = 'active' AND provider = 'dropbox' AND store_id = :s
                ORDER BY id DESC
            '''), {"t": tenant_id, "s": store_id}).fetchall()
        elif store_id:
            rows = db.execute(text('''
                SELECT id, name FROM "T_外部ストレージ連携"
                WHERE tenant_id = :t AND status = 'active' AND provider = 'dropbox'
                      AND (store_id = :s OR store_id IS NULL)
                ORDER BY id DESC
            '''), {"t": tenant_id, "s": store_id}).fetchall()
        else:
            rows = db.execute(text('''
                SELECT id, name FROM "T_外部ストレージ連携"
                WHERE tenant_id = :t AND status = 'active' AND provider = 'dropbox'
                ORDER BY id DESC
            '''), {"t": tenant_id}).fetchall()
        return jsonify({'connections': [{'id': r.id, 'name': r.name or f'接続{r.id}'} for r in rows]})
    finally:
        db.close()


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
        if not _scope_access_ok(db, tenant_id, store_id):
            return jsonify({'error': '権限がありません'}), 403
        storage_config = _resolve_browse_config(db, tenant_id, store_id)
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
        if not _scope_access_ok(db, tenant_id, store_id):
            return jsonify({'error': '権限がありません'}), 403
        storage_config = _resolve_browse_config(db, tenant_id, store_id)
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
        if not _scope_access_ok(db, tenant_id, store_id):
            return jsonify({'error': '権限がありません'}), 403
        storage_config = _resolve_browse_config(db, tenant_id, store_id)
        if not storage_config or storage_config.provider != 'dropbox':
            return jsonify({'error': 'Dropboxが設定されていません'}), 400

        # 選択中の接続（storage_config）そのものに保存する
        db.execute(text("""
            UPDATE "T_外部ストレージ連携"
            SET base_folder_path = :folder_path
            WHERE id = :cid AND tenant_id = :tenant_id
        """), {"folder_path": folder_path or None, "cid": storage_config.id, "tenant_id": tenant_id})
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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def storage_gcs():
    """Google Cloud Storage連携設定ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        store_id = _scope_store_id(db, tenant_id)
        if not _scope_access_ok(db, tenant_id, store_id):
            flash('この設定を操作する権限がありません（店舗管理者は自店のみ設定できます）', 'error')
            return redirect(url_for('staff_mypage.dashboard'))
        storage_config = _get_storage_config(db, tenant_id, store_id)
        view = _build_view(storage_config)

        if request.method == 'POST':
            bucket_name = request.form.get('gcs_bucket', '').strip()
            service_account_json = request.form.get('gcs_service_account_json', '').strip()
            if bucket_name and service_account_json:
                # 接続プールに追加し、このスコープの主接続に割当
                _add_connection(db, tenant_id, store_id,
                                name=_default_conn_name(db, tenant_id, store_id, 'gcs'),
                                provider='gcs', bucket_name=bucket_name,
                                service_account_json=service_account_json)
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
# 本部：接続一覧＆店舗への割当（プール管理）
# ===========================
@bp.route('/connections', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def connections():
    """接続プールの一覧と、店舗への割当を管理する（本部）。"""
    from app.models_integrations import TStorageConnection, TStoreStorageAssignment
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        conns = (db.query(TStorageConnection)
                   .filter(TStorageConnection.tenant_id == tenant_id,
                           TStorageConnection.status == 'active')
                   .order_by(TStorageConnection.id.desc()).all())
        stores = db.execute(text('SELECT id, "名称" AS name FROM "T_店舗" WHERE tenant_id = :t ORDER BY id'),
                            {"t": tenant_id}).fetchall()
        store_name_map = {s.id: s.name for s in stores}

        def _plabel(p):
            return {'dropbox': 'Dropbox', 'gcs': 'Google Cloud Storage', 'cloudinary': 'Cloudinary'}.get((p or '').lower(), p or '')

        assigns = (db.query(TStoreStorageAssignment)
                     .filter(TStoreStorageAssignment.tenant_id == tenant_id,
                             TStoreStorageAssignment.status == 'active',
                             TStoreStorageAssignment.is_primary == 1).all())
        assign_map = {a.store_id: a.connection_id for a in assigns}

        # 接続ID → その接続を使っている対象（本部既定 / 店舗名）の一覧
        used_by = {}
        for a in assigns:
            label = '本部（既定）' if a.store_id is None else (store_name_map.get(a.store_id) or f'店舗{a.store_id}')
            used_by.setdefault(a.connection_id, []).append(label)
        # 本部既定に割り当てられた接続は、未割当の店舗にも実質使われる
        default_conn_id = assign_map.get(None)

        conn_view = [{
            'id': c.id, 'name': c.name or f'接続{c.id}',
            'provider': _plabel(c.provider),
            'registered_by': (store_name_map.get(c.store_id) or '本部') if c.store_id else '本部',
            'used_by': used_by.get(c.id, []),
            'is_default': (c.id == default_conn_id),
        } for c in conns]

        rows = [{'store_id': None, 'label': '本部（既定）', 'current': assign_map.get(None)}]
        for s in stores:
            rows.append({'store_id': s.id, 'label': s.name, 'current': assign_map.get(s.id)})

        return render_template('tenant_storage_connections.html', conns=conn_view, rows=rows)
    finally:
        db.close()


@bp.route('/connections/assign', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def assign_connection():
    """店舗（or 本部既定）に、プール内の接続を割り当てる。
    本部系は任意スコープ可。店舗管理者は自店のみ（本部既定は不可）。
    """
    from app.models_integrations import TStorageConnection, TStoreStorageAssignment
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    raw = request.form.get('store_id')
    store_id = int(raw) if (raw and raw.isdigit()) else None
    conn_raw = request.form.get('connection_id')
    # 戻り先: 店舗管理者は店舗設定へ、本部は接続管理へ
    back = url_for('tenant_storage.storage_settings', store_id=store_id) if session.get('role') == ROLES['ADMIN'] \
        else url_for('tenant_storage.connections')

    db = SessionLocal()
    try:
        if not _scope_access_ok(db, tenant_id, store_id):
            flash('この割当を操作する権限がありません', 'error')
            return redirect(back)
        if not conn_raw:
            # 割当解除（本部既定にフォールバック）
            aq = db.query(TStoreStorageAssignment).filter(
                TStoreStorageAssignment.tenant_id == tenant_id,
                TStoreStorageAssignment.status == 'active')
            aq = aq.filter(TStoreStorageAssignment.store_id.is_(None)) if store_id is None \
                else aq.filter(TStoreStorageAssignment.store_id == store_id)
            for a in aq.all():
                a.status = 'inactive'
                a.is_primary = 0
            db.commit()
            flash('割当を解除しました', 'success')
        else:
            cid = int(conn_raw)
            # 接続がこのテナントのものか検証
            conn = db.query(TStorageConnection).filter(
                TStorageConnection.id == cid,
                TStorageConnection.tenant_id == tenant_id,
                TStorageConnection.status == 'active').first()
            if not conn:
                flash('指定した接続が見つかりません', 'error')
            else:
                _set_primary_assignment(db, tenant_id, store_id, cid)
                db.commit()
                flash('使用する接続を切り替えました', 'success')
    finally:
        db.close()
    return redirect(back)


def _deactivate_assignment(db, tenant_id, store_id, connection_id):
    """指定スコープ・指定接続の有効な割当（主/ミラー問わず）を無効化する。"""
    from app.models_integrations import TStoreStorageAssignment
    q = db.query(TStoreStorageAssignment).filter(
        TStoreStorageAssignment.tenant_id == tenant_id,
        TStoreStorageAssignment.connection_id == connection_id,
        TStoreStorageAssignment.status == 'active')
    q = q.filter(TStoreStorageAssignment.store_id.is_(None)) if store_id is None \
        else q.filter(TStoreStorageAssignment.store_id == store_id)
    for a in q.all():
        a.status = 'inactive'
        a.is_primary = 0


@bp.route('/connections/role', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def set_connection_role():
    """接続の役割を設定: primary=主に使用 / mirror=ミラー(同時保存) / off=保存先から外す。"""
    from app.models_integrations import TStorageConnection, TStoreStorageAssignment
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    raw = request.form.get('store_id')
    store_id = int(raw) if (raw and raw.isdigit()) else None
    conn_raw = request.form.get('connection_id')
    role = (request.form.get('role') or '').strip()
    back = url_for('tenant_storage.storage_settings', store_id=store_id) if session.get('role') == ROLES['ADMIN'] \
        else url_for('tenant_storage.connections')

    db = SessionLocal()
    try:
        if not _scope_access_ok(db, tenant_id, store_id):
            flash('この操作の権限がありません', 'error')
            return redirect(back)
        if not conn_raw:
            return redirect(back)
        cid = int(conn_raw)
        conn = db.query(TStorageConnection).filter(
            TStorageConnection.id == cid,
            TStorageConnection.tenant_id == tenant_id,
            TStorageConnection.status == 'active').first()
        if not conn:
            flash('指定した接続が見つかりません', 'error')
            return redirect(back)

        if role == 'primary':
            _deactivate_assignment(db, tenant_id, store_id, cid)
            _set_primary_assignment(db, tenant_id, store_id, cid)
            db.commit()
            flash('使用中（主）に設定しました', 'success')
        elif role == 'mirror':
            _deactivate_assignment(db, tenant_id, store_id, cid)
            db.add(TStoreStorageAssignment(
                tenant_id=tenant_id, store_id=store_id,
                connection_id=cid, is_primary=0, status='active'))
            db.commit()
            flash('ミラー（同時保存先）に追加しました', 'success')
        elif role == 'off':
            _deactivate_assignment(db, tenant_id, store_id, cid)
            db.commit()
            flash('保存先から外しました', 'success')
        else:
            flash('不正な操作です', 'error')
    finally:
        db.close()
    return redirect(back)


@bp.route('/isolation', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def toggle_isolation():
    """店舗の隔離モード（fail-closed）を切り替える。
    オン: 専用ストレージが無いとき本部既定へフォールバックせずエラーにする（漏洩防止）。
    """
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    raw = request.form.get('store_id')
    store_id = int(raw) if (raw and raw.isdigit()) else None
    enabled = 1 if (request.form.get('enabled') in ('1', 'on', 'true')) else 0
    back = url_for('tenant_storage.storage_settings', store_id=store_id)

    db = SessionLocal()
    try:
        if not store_id:
            flash('隔離モードは店舗ごとの設定です（本部全体には設定できません）', 'error')
            return redirect(back)
        if not _scope_access_ok(db, tenant_id, store_id):
            flash('この操作の権限がありません', 'error')
            return redirect(back)
        # 対象店舗がこのテナントのものか確認
        row = db.execute(text('SELECT id FROM "T_店舗" WHERE id = :s AND tenant_id = :t'),
                         {"s": store_id, "t": tenant_id}).fetchone()
        if not row:
            flash('店舗が見つかりません', 'error')
            return redirect(back)
        db.execute(text('UPDATE "T_店舗" SET storage_isolated = :v WHERE id = :s'),
                   {"v": enabled, "s": store_id})
        db.commit()
        if enabled:
            flash('隔離モードをオンにしました（専用ストレージ未設定時は保存せずエラーにします）', 'success')
        else:
            flash('隔離モードをオフにしました（未設定時は本部既定へ保存します）', 'success')
    except Exception as e:
        db.rollback()
        flash(f'設定に失敗しました: {e}', 'error')
    finally:
        db.close()
    return redirect(back)


@bp.route('/connections/<int:connection_id>/rename', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def connection_rename(connection_id):
    from app.models_integrations import TStorageConnection
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    name = (request.form.get('name') or '').strip()
    db = SessionLocal()
    try:
        conn = db.query(TStorageConnection).filter(
            TStorageConnection.id == connection_id,
            TStorageConnection.tenant_id == tenant_id).first()
        if conn and name:
            conn.name = name
            db.commit()
            flash('接続名を変更しました', 'success')
    finally:
        db.close()
    return redirect(url_for('tenant_storage.connections'))


@bp.route('/connections/<int:connection_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def connection_delete(connection_id):
    """接続をプールから削除（無効化）。この接続への割当も解除する。"""
    from app.models_integrations import TStorageConnection, TStoreStorageAssignment
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        conn = db.query(TStorageConnection).filter(
            TStorageConnection.id == connection_id,
            TStorageConnection.tenant_id == tenant_id).first()
        if conn:
            conn.status = 'inactive'
            for a in db.query(TStoreStorageAssignment).filter(
                    TStoreStorageAssignment.tenant_id == tenant_id,
                    TStoreStorageAssignment.connection_id == connection_id,
                    TStoreStorageAssignment.status == 'active').all():
                a.status = 'inactive'
                a.is_primary = 0
            db.commit()
            flash('接続を削除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('tenant_storage.connections'))


# ===========================
# 連携解除
# ===========================
@bp.route('/disconnect', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
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
        from app.models_integrations import TStoreStorageAssignment
        store_id = _scope_store_id(db, tenant_id)
        if not _scope_access_ok(db, tenant_id, store_id):
            flash('この設定を操作する権限がありません', 'error')
            return redirect(url_for('staff_mypage.dashboard'))
        cfg = _get_storage_config(db, tenant_id, store_id)
        # 現在このスコープが使っている接続が、このスコープ自身の登録か（継承した本部既定でないか）
        own = bool(cfg and getattr(cfg, 'store_id', None) == store_id)
        revoke_note = None
        # Dropbox は API で認可自体を取り消せる（連携済みアプリからも消える）。自スコープの接続のみ対象
        if provider == 'dropbox' and revoke and own and cfg and (getattr(cfg, 'provider', '') or '').lower() == 'dropbox':
            try:
                dbx = _get_dropbox_client(cfg, tenant_id=tenant_id)
                dbx.auth_token_revoke()
                revoke_note = ('success', 'Dropbox側の認可も取り消しました（Dropboxの「連携済みアプリ」からも削除されます）')
            except Exception as e:  # noqa: BLE001 - 失敗してもアプリ側の解除は続行
                revoke_note = ('warning', f'Dropbox側の認可取り消しに失敗しました（アプリ側の連携は解除しました）。必要なら https://www.dropbox.com/account/connected_apps から手動で解除してください: {e}')
        # このスコープの主割当を解除（未割当なら本部既定にフォールバックする）
        aq = db.query(TStoreStorageAssignment).filter(
            TStoreStorageAssignment.tenant_id == tenant_id,
            TStoreStorageAssignment.status == 'active')
        aq = aq.filter(TStoreStorageAssignment.store_id.is_(None)) if store_id is None \
            else aq.filter(TStoreStorageAssignment.store_id == store_id)
        for a in aq.all():
            a.status = 'inactive'
            a.is_primary = 0
        # このスコープ自身が登録した接続のみ無効化（継承した本部既定は温存）
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
