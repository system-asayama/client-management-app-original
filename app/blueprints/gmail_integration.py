"""
Gmail連携ブループリント（IMAPポーリング方式）

- メールアドレス + アプリパスワードの登録（疎通確認）
- 差出人メールアドレス → 顧問先 の紐付け
- 手動同期（新着添付をストレージへ保存）
"""
import json
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash,
)
from app.db import SessionLocal
from app.models_integrations import (
    TIntegrationSetting, TGmailSenderMapping, TReceivedFile,
)
from app.models_clients import TClient
from app.utils.decorators import require_roles, ROLES
from app.utils.integrations.gmail_imap import GmailImapClient, GmailImapError
from app.services.gmail_sync import sync_tenant, get_active_setting, _load_extra

bp = Blueprint('gmail_integration', __name__, url_prefix='/integrations/gmail')


def _require_tenant():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return None
    return tenant_id


@bp.route('/', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def settings():
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    from app.utils.integrations.mail import MAIL_PROVIDERS
    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        extra = _load_extra(setting) if setting else {}
        mappings = (db.query(TGmailSenderMapping)
                      .filter(TGmailSenderMapping.tenant_id == tenant_id)
                      .order_by(TGmailSenderMapping.id.desc()).all())
        clients = (db.query(TClient)
                     .filter(TClient.tenant_id == tenant_id)
                     .order_by(TClient.name).all())
        recent = (db.query(TReceivedFile)
                    .filter(TReceivedFile.tenant_id == tenant_id,
                            TReceivedFile.provider == 'gmail')
                    .order_by(TReceivedFile.id.desc()).limit(20).all())
        client_names = {c.id: c.name for c in clients}
        from app.services.scheduler import get_state
        return render_template('integrations_gmail.html',
                               setting=setting, gmail_email=extra.get('email'),
                               providers=MAIL_PROVIDERS,
                               current_provider=extra.get('provider', 'gmail'),
                               gmail_host=extra.get('imap_host', ''),
                               gmail_port=extra.get('imap_port', 993),
                               mappings=mappings, clients=clients,
                               recent=recent, client_names=client_names,
                               sched=get_state())
    finally:
        db.close()


@bp.route('/save_account', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def save_account():
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    from app.utils.integrations.mail import resolve_host_port, ImapMailClient, MailError

    email_address = (request.form.get('email') or '').strip()
    app_password = (request.form.get('app_password') or '').strip()
    provider = (request.form.get('provider') or 'gmail').strip()
    host_in = (request.form.get('imap_host') or '').strip()
    port_in = request.form.get('imap_port')
    host, port = resolve_host_port(provider, host_in, port_in)

    # 既存トークンを取得（パスワードが伏字（*のみ）の場合は変更なしとして流用）
    db = SessionLocal()
    try:
        existing = get_active_setting(db, tenant_id)
        existing_token = existing.api_token if existing else None
    finally:
        db.close()
    if app_password and set(app_password) == {'*'}:
        app_password = existing_token or ''

    if not email_address or not app_password:
        flash('メールアドレスとアプリパスワードを入力してください', 'error')
        return redirect(url_for('gmail_integration.settings'))

    # 疎通確認（プロバイダ非依存のIMAPで確認）
    try:
        ImapMailClient(email_address, app_password, host, port).verify()
    except MailError as e:
        flash(f'メール接続に失敗しました: {e}', 'error')
        return redirect(url_for('gmail_integration.settings'))

    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        extra = _load_extra(setting) if setting else {}
        extra['email'] = email_address
        extra['provider'] = provider
        extra['imap_host'] = host
        extra['imap_port'] = port
        # since_uid は既存値を維持（再設定時に取りこぼさない）
        if setting:
            setting.api_token = app_password
            setting.extra = json.dumps(extra, ensure_ascii=False)
            setting.status = 'active'
        else:
            db.add(TIntegrationSetting(
                tenant_id=tenant_id, provider='gmail',
                api_token=app_password,
                extra=json.dumps(extra, ensure_ascii=False),
                status='active',
            ))
        db.commit()
        flash('メール連携を保存しました', 'success')
    finally:
        db.close()
    return redirect(url_for('gmail_integration.settings'))


@bp.route('/map', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def map_sender():
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    sender_email = (request.form.get('sender_email') or '').strip().lower()
    client_id = request.form.get('client_id')
    subfolder = (request.form.get('subfolder') or 'Gmail受信').strip()
    if not sender_email or not client_id:
        flash('差出人メールと顧問先を指定してください', 'error')
        return redirect(url_for('gmail_integration.settings'))

    db = SessionLocal()
    try:
        existing = (db.query(TGmailSenderMapping)
                      .filter(TGmailSenderMapping.tenant_id == tenant_id,
                              TGmailSenderMapping.sender_email == sender_email)
                      .first())
        if existing:
            existing.client_id = int(client_id)
            existing.subfolder = subfolder
            existing.status = 'active'
        else:
            db.add(TGmailSenderMapping(
                tenant_id=tenant_id, sender_email=sender_email,
                client_id=int(client_id), subfolder=subfolder, status='active',
            ))
        db.commit()
        flash('差出人の紐付けを保存しました', 'success')
    finally:
        db.close()
    return redirect(url_for('gmail_integration.settings'))


@bp.route('/map/<int:mapping_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def map_delete(mapping_id):
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        m = (db.query(TGmailSenderMapping)
               .filter(TGmailSenderMapping.id == mapping_id,
                       TGmailSenderMapping.tenant_id == tenant_id)
               .first())
        if m:
            db.delete(m)
            db.commit()
            flash('紐付けを削除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('gmail_integration.settings'))


@bp.route('/oauth-setup', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def oauth_setup():
    """メールOAuth（Google Workspace / Microsoft 365）用の自前アプリ認証情報の設定＋手順書。

    各事務所が自分でOAuthアプリを登録し、Client ID/Secret をここに登録する。
    実際の「接続」フローは各担当のマイページから行う（次段階）。
    """
    from app.models_integrations import TMailOAuthConfig
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    # 登録時に使うリダイレクトURI（プロバイダ側に登録してもらう値）
    root = request.url_root  # 例: https://xxx.herokuapp.com/
    redirect_uris = {
        'google': root + 'integrations/mail/oauth/google/callback',
        'microsoft': root + 'integrations/mail/oauth/microsoft/callback',
    }

    db = SessionLocal()
    try:
        rows = (db.query(TMailOAuthConfig)
                  .filter(TMailOAuthConfig.tenant_id == tenant_id).all())
        cfg = {}
        for r in rows:
            cfg[r.provider] = {
                'client_id': r.client_id or '',
                'client_id_masked': (r.client_id[:6] + '…' + r.client_id[-4:]) if (r.client_id and len(r.client_id) > 12) else (r.client_id or ''),
                'has_secret': bool(r.client_secret),
                'ms_tenant_id': r.ms_tenant_id or '',
                'status': r.status,
            }
        return render_template('integrations_mail_oauth.html',
                               cfg=cfg, redirect_uris=redirect_uris)
    finally:
        db.close()


@bp.route('/oauth-setup/save', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def oauth_setup_save():
    """メールOAuthの Client ID/Secret を保存（プロバイダ単位）"""
    from app.models_integrations import TMailOAuthConfig
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    provider = (request.form.get('provider') or '').strip().lower()
    if provider not in ('google', 'microsoft'):
        flash('プロバイダの指定が不正です', 'error')
        return redirect(url_for('gmail_integration.oauth_setup'))

    client_id = (request.form.get('client_id') or '').strip()
    client_secret = (request.form.get('client_secret') or '').strip()
    ms_tenant_id = (request.form.get('ms_tenant_id') or '').strip()

    db = SessionLocal()
    try:
        row = (db.query(TMailOAuthConfig)
                 .filter(TMailOAuthConfig.tenant_id == tenant_id,
                         TMailOAuthConfig.provider == provider).first())
        if not row:
            row = TMailOAuthConfig(tenant_id=tenant_id, provider=provider, status='active')
            db.add(row)
        if client_id:
            row.client_id = client_id
        # シークレットは伏字（●のみ等）や空なら変更しない
        if client_secret and set(client_secret) not in ({'●'}, {'*'}, {'•'}):
            row.client_secret = client_secret
        if provider == 'microsoft':
            row.ms_tenant_id = ms_tenant_id or row.ms_tenant_id
        row.status = 'active'
        db.commit()
        flash(f'{"Google" if provider == "google" else "Microsoft"} のOAuth設定を保存しました', 'success')
    finally:
        db.close()
    return redirect(url_for('gmail_integration.oauth_setup'))


@bp.route('/sync', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def sync():
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    result = sync_tenant(tenant_id)
    msg = f"同期完了: 保存 {result['saved']}件 / スキップ {result['skipped']}件"
    if result['errors']:
        msg += f" / エラー {len(result['errors'])}件"
        flash(msg, 'warning')
        for e in result['errors'][:5]:
            flash(e, 'error')
    else:
        flash(msg, 'success')
    return redirect(url_for('gmail_integration.settings'))
