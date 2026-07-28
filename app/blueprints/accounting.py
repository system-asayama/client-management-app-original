"""
会計ソフト連携ブループリント（freee / マネーフォワード 対応・抽象化層）

- 顧問先ごとに会計ソフトをOAuth連携し、アップロード先の事業所を選択
- ストレージ保存済みの受信資料を会計ソフトのファイルボックスへ手動/一括アップロード
"""
import json
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash,
)
from datetime import datetime, timedelta

from app.db import SessionLocal
from app.models_clients import TClient
from app.models_integrations import TReceivedFile
from app.models_accounting import TAccountingConnection, TAccountingUploadLog
from app.utils.decorators import require_roles, ROLES
from app.utils.accounting import (
    get_provider, AccountingError, SUPPORTED_PROVIDERS, provider_label,
)
from app.services.accounting_upload import (
    upload_received_file, upload_tenant_pending, get_connection,
    _pending_received_files,
)

bp = Blueprint('accounting', __name__, url_prefix='/accounting')


def _require_tenant():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return None
    return tenant_id


def _providers_status():
    """対応プロバイダとアプリ設定状況をUI用に返す"""
    out = []
    for name in SUPPORTED_PROVIDERS:
        try:
            configured = get_provider(name).is_configured()
        except Exception:
            configured = False
        out.append({'name': name, 'label': provider_label(name), 'configured': configured})
    return out


@bp.route('/', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def index():
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        clients = (db.query(TClient)
                     .filter(TClient.tenant_id == tenant_id)
                     .order_by(TClient.name).all())
        conns = (db.query(TAccountingConnection)
                   .filter(TAccountingConnection.tenant_id == tenant_id)
                   .all())
        conn_by_client = {c.client_id: c for c in conns if c.status == 'active'}
        pending = _pending_received_files(db, tenant_id)
        logs = (db.query(TAccountingUploadLog)
                  .filter(TAccountingUploadLog.tenant_id == tenant_id)
                  .order_by(TAccountingUploadLog.id.desc()).limit(20).all())
        client_names = {c.id: c.name for c in clients}
        return render_template('accounting.html',
                               clients=clients, conn_by_client=conn_by_client,
                               pending=pending, logs=logs,
                               client_names=client_names,
                               providers=_providers_status(),
                               provider_label=provider_label)
    finally:
        db.close()


@bp.route('/connect/<provider>/<int:client_id>', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def connect(provider, client_id):
    """会計ソフトのOAuth認可画面へリダイレクト"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    if provider not in SUPPORTED_PROVIDERS:
        flash('未対応の会計ソフトです', 'error')
        return redirect(url_for('accounting.index'))

    try:
        prov = get_provider(provider)
    except AccountingError as e:
        flash(str(e), 'error')
        return redirect(url_for('accounting.index'))

    if not prov.is_configured():
        flash(f'{provider_label(provider)}のアプリ設定（環境変数）が未設定です', 'error')
        return redirect(url_for('accounting.index'))

    import secrets
    nonce = secrets.token_hex(8)
    session['acc_oauth_state'] = nonce
    state = json.dumps({'t': tenant_id, 'c': client_id, 'n': nonce, 'p': provider})
    return redirect(prov.authorize_url(state))


@bp.route('/callback/<provider>', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def callback(provider):
    """OAuth認可コールバック → トークン取得 → 事業所選択へ"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    if provider not in SUPPORTED_PROVIDERS:
        flash('未対応の会計ソフトです', 'error')
        return redirect(url_for('accounting.index'))

    code = request.args.get('code')
    state_raw = request.args.get('state', '')
    if not code:
        flash('認可がキャンセルされました', 'error')
        return redirect(url_for('accounting.index'))

    try:
        st = json.loads(state_raw)
    except Exception:
        flash('不正なstateです', 'error')
        return redirect(url_for('accounting.index'))

    if (st.get('n') != session.get('acc_oauth_state')
            or st.get('t') != tenant_id or st.get('p') != provider):
        flash('OAuth検証に失敗しました', 'error')
        return redirect(url_for('accounting.index'))
    client_id = st.get('c')

    prov = get_provider(provider)
    try:
        tok = prov.exchange_code(code)
        companies = prov.list_companies(tok['access_token'])
    except AccountingError as e:
        flash(f'{provider_label(provider)}連携に失敗しました: {e}', 'error')
        return redirect(url_for('accounting.index'))

    session['acc_pending'] = {
        'provider': provider,
        'client_id': client_id,
        'access_token': tok['access_token'],
        'refresh_token': tok['refresh_token'],
        'expires_in': tok.get('expires_in'),
    }
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        client_name = client.name if client else ''
    finally:
        db.close()
    return render_template('accounting_select_company.html',
                           companies=companies, client_id=client_id,
                           client_name=client_name, provider=provider,
                           provider_label=provider_label(provider))


@bp.route('/save_company', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def save_company():
    """選択（または手動入力）した事業所で連携を確定"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    pending = session.get('acc_pending')
    if not pending:
        flash('連携情報が失われました。最初からやり直してください', 'error')
        return redirect(url_for('accounting.index'))

    company_id = (request.form.get('company_id') or '').strip()
    company_name = (request.form.get('company_name') or '').strip()
    provider = pending['provider']
    client_id = pending['client_id']
    if not company_id:
        flash('事業所を選択または入力してください', 'error')
        return redirect(url_for('accounting.index'))

    expires_at = None
    if pending.get('expires_in'):
        expires_at = datetime.utcnow() + timedelta(seconds=int(pending['expires_in']))

    db = SessionLocal()
    try:
        conn = get_connection(db, tenant_id, client_id)
        if conn:
            conn.provider = provider
            conn.company_id = company_id
            conn.company_name = company_name or company_id
            conn.access_token = pending['access_token']
            conn.refresh_token = pending['refresh_token']
            conn.token_expires_at = expires_at
            conn.status = 'active'
        else:
            db.add(TAccountingConnection(
                tenant_id=tenant_id, client_id=client_id, provider=provider,
                company_id=company_id, company_name=company_name or company_id,
                access_token=pending['access_token'],
                refresh_token=pending['refresh_token'],
                token_expires_at=expires_at, status='active',
            ))
        db.commit()
        flash(f'{provider_label(provider)}連携を保存しました（事業所: {company_name or company_id}）', 'success')
    finally:
        db.close()
    session.pop('acc_pending', None)
    session.pop('acc_oauth_state', None)
    return redirect(url_for('accounting.index'))


@bp.route('/disconnect/<int:client_id>', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def disconnect(client_id):
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        conn = get_connection(db, tenant_id, client_id)
        if conn:
            conn.status = 'disabled'
            db.commit()
            flash('連携を解除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('accounting.index'))


@bp.route('/upload/<int:received_file_id>', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def upload_one(received_file_id):
    """1件を手動アップロード"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        rf = db.query(TReceivedFile).filter(
            TReceivedFile.id == received_file_id,
            TReceivedFile.tenant_id == tenant_id).first()
        ok = rf is not None
    finally:
        db.close()
    if not ok:
        flash('対象ファイルが見つかりません', 'error')
        return redirect(url_for('accounting.index'))

    res = upload_received_file(received_file_id)
    if res.get('ok') and res.get('skipped'):
        flash('この資料は既にアップロード済みです', 'warning')
    elif res.get('ok'):
        flash('会計ソフトへアップロードしました', 'success')
    else:
        flash(f"アップロード失敗: {res.get('error')}", 'error')
    return redirect(url_for('accounting.index'))


@bp.route('/upload_all', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def upload_all():
    """未送信の保存済み資料を一括アップロード"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    r = upload_tenant_pending(tenant_id)
    msg = f"一括アップロード: 成功 {r['uploaded']}件 / スキップ {r['skipped']}件"
    if r['errors']:
        msg += f" / エラー {len(r['errors'])}件"
        flash(msg, 'warning')
        for e in r['errors'][:5]:
            flash(e, 'error')
    else:
        flash(msg, 'success')
    return redirect(url_for('accounting.index'))
