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

    email_address = (request.form.get('email') or '').strip()
    app_password = (request.form.get('app_password') or '').strip()
    if not email_address or not app_password:
        flash('メールアドレスとアプリパスワードを入力してください', 'error')
        return redirect(url_for('gmail_integration.settings'))

    # 疎通確認
    try:
        GmailImapClient(email_address, app_password).verify()
    except GmailImapError as e:
        flash(f'Gmail接続に失敗しました: {e}', 'error')
        return redirect(url_for('gmail_integration.settings'))

    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        extra = _load_extra(setting) if setting else {}
        extra['email'] = email_address
        extra.setdefault('imap_host', 'imap.gmail.com')
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
        flash('Gmail連携を保存しました', 'success')
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
