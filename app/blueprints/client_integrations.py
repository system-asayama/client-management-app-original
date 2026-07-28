"""
顧問先ごとの連携設定ハブ

顧問先詳細から、その顧問先の連携をまとめて設定・確認する:
  - ChatWork ルーム紐付け（この顧問先のルーム）
  - Gmail 差出人紐付け（この顧問先の差出人）
  - 会計ソフト連携（freee / MF）の状態と、この顧問先の資料アップロード

認証情報（ChatWork APIトークン / Gmailアカウント）は事務所共通のため、
未設定の場合は事務所共通の設定画面への導線を表示する。
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash,
)
from app.db import SessionLocal
from app.models_clients import TClient
from app.models_integrations import (
    TIntegrationSetting, TChatworkRoomMapping, TGmailSenderMapping, TReceivedFile,
)
from app.models_accounting import TAccountingConnection, TAccountingUploadLog
from app.utils.decorators import require_roles, ROLES
from app.utils.accounting import SUPPORTED_PROVIDERS, provider_label, get_provider
from app.services.accounting_upload import upload_client_pending

bp = Blueprint('client_integrations', __name__, url_prefix='/clients')


def _tenant_client(db, client_id):
    """テナント越境を防ぎつつ顧問先を取得"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return None, None
    client = db.query(TClient).filter(
        TClient.id == client_id, TClient.tenant_id == tenant_id).first()
    return tenant_id, client


@bp.route('/<int:client_id>/integrations', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def hub(client_id):
    db = SessionLocal()
    try:
        tenant_id, client = _tenant_client(db, client_id)
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        def _active(provider):
            return (db.query(TIntegrationSetting)
                      .filter(TIntegrationSetting.tenant_id == tenant_id,
                              TIntegrationSetting.provider == provider,
                              TIntegrationSetting.status == 'active')
                      .first())

        chatwork_ready = _active('chatwork') is not None
        gmail_ready = _active('gmail') is not None

        cw_rooms = (db.query(TChatworkRoomMapping)
                      .filter(TChatworkRoomMapping.tenant_id == tenant_id,
                              TChatworkRoomMapping.client_id == client_id)
                      .order_by(TChatworkRoomMapping.id.desc()).all())
        gmail_senders = (db.query(TGmailSenderMapping)
                           .filter(TGmailSenderMapping.tenant_id == tenant_id,
                                   TGmailSenderMapping.client_id == client_id)
                           .order_by(TGmailSenderMapping.id.desc()).all())
        acc_conn = (db.query(TAccountingConnection)
                      .filter(TAccountingConnection.tenant_id == tenant_id,
                              TAccountingConnection.client_id == client_id,
                              TAccountingConnection.status == 'active')
                      .first())
        received = (db.query(TReceivedFile)
                      .filter(TReceivedFile.tenant_id == tenant_id,
                              TReceivedFile.client_id == client_id)
                      .order_by(TReceivedFile.id.desc()).limit(15).all())
        upload_logs = (db.query(TAccountingUploadLog)
                         .filter(TAccountingUploadLog.tenant_id == tenant_id,
                                 TAccountingUploadLog.client_id == client_id)
                         .order_by(TAccountingUploadLog.id.desc()).limit(10).all())

        providers = []
        for name in SUPPORTED_PROVIDERS:
            try:
                configured = get_provider(name).is_configured()
            except Exception:
                configured = False
            providers.append({'name': name, 'label': provider_label(name),
                              'configured': configured})

        return render_template('client_integrations.html',
                               client=client,
                               chatwork_ready=chatwork_ready, gmail_ready=gmail_ready,
                               cw_rooms=cw_rooms, gmail_senders=gmail_senders,
                               acc_conn=acc_conn, providers=providers,
                               provider_label=provider_label,
                               received=received, upload_logs=upload_logs)
    finally:
        db.close()


@bp.route('/<int:client_id>/integrations/chatwork_room', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def add_chatwork_room(client_id):
    db = SessionLocal()
    try:
        tenant_id, client = _tenant_client(db, client_id)
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        room_id = (request.form.get('room_id') or '').strip()
        room_name = (request.form.get('room_name') or '').strip()
        subfolder = (request.form.get('subfolder') or 'ChatWork受信').strip()
        if not room_id:
            flash('ルームIDを入力してください', 'error')
            return redirect(url_for('client_integrations.hub', client_id=client_id))
        existing = (db.query(TChatworkRoomMapping)
                      .filter(TChatworkRoomMapping.tenant_id == tenant_id,
                              TChatworkRoomMapping.room_id == room_id).first())
        if existing:
            existing.client_id = client_id
            existing.room_name = room_name or existing.room_name
            existing.subfolder = subfolder
            existing.status = 'active'
        else:
            db.add(TChatworkRoomMapping(
                tenant_id=tenant_id, room_id=room_id, room_name=room_name,
                client_id=client_id, subfolder=subfolder, status='active'))
        db.commit()
        flash('ChatWorkルームを紐付けました', 'success')
    finally:
        db.close()
    return redirect(url_for('client_integrations.hub', client_id=client_id))


@bp.route('/<int:client_id>/integrations/chatwork_room/<int:mapping_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def del_chatwork_room(client_id, mapping_id):
    db = SessionLocal()
    try:
        tenant_id, client = _tenant_client(db, client_id)
        if client:
            m = (db.query(TChatworkRoomMapping)
                   .filter(TChatworkRoomMapping.id == mapping_id,
                           TChatworkRoomMapping.tenant_id == tenant_id,
                           TChatworkRoomMapping.client_id == client_id).first())
            if m:
                db.delete(m)
                db.commit()
                flash('紐付けを削除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('client_integrations.hub', client_id=client_id))


@bp.route('/<int:client_id>/integrations/gmail_sender', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def add_gmail_sender(client_id):
    db = SessionLocal()
    try:
        tenant_id, client = _tenant_client(db, client_id)
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        sender_email = (request.form.get('sender_email') or '').strip().lower()
        subfolder = (request.form.get('subfolder') or 'Gmail受信').strip()
        if not sender_email:
            flash('差出人メールアドレスを入力してください', 'error')
            return redirect(url_for('client_integrations.hub', client_id=client_id))
        existing = (db.query(TGmailSenderMapping)
                      .filter(TGmailSenderMapping.tenant_id == tenant_id,
                              TGmailSenderMapping.sender_email == sender_email).first())
        if existing:
            existing.client_id = client_id
            existing.subfolder = subfolder
            existing.status = 'active'
        else:
            db.add(TGmailSenderMapping(
                tenant_id=tenant_id, sender_email=sender_email,
                client_id=client_id, subfolder=subfolder, status='active'))
        db.commit()
        flash('Gmail差出人を紐付けました', 'success')
    finally:
        db.close()
    return redirect(url_for('client_integrations.hub', client_id=client_id))


@bp.route('/<int:client_id>/integrations/gmail_sender/<int:mapping_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def del_gmail_sender(client_id, mapping_id):
    db = SessionLocal()
    try:
        tenant_id, client = _tenant_client(db, client_id)
        if client:
            m = (db.query(TGmailSenderMapping)
                   .filter(TGmailSenderMapping.id == mapping_id,
                           TGmailSenderMapping.tenant_id == tenant_id,
                           TGmailSenderMapping.client_id == client_id).first())
            if m:
                db.delete(m)
                db.commit()
                flash('紐付けを削除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('client_integrations.hub', client_id=client_id))


@bp.route('/<int:client_id>/integrations/upload_accounting', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def upload_accounting(client_id):
    db = SessionLocal()
    try:
        tenant_id, client = _tenant_client(db, client_id)
        ok = client is not None
    finally:
        db.close()
    if not ok:
        flash('顧問先が見つかりません', 'error')
        return redirect(url_for('clients.clients'))

    r = upload_client_pending(tenant_id, client_id)
    msg = f"アップロード: 成功 {r['uploaded']}件 / スキップ {r['skipped']}件"
    if r['errors']:
        msg += f" / エラー {len(r['errors'])}件"
        flash(msg, 'warning')
        for e in r['errors'][:5]:
            flash(e, 'error')
    else:
        flash(msg, 'success')
    return redirect(url_for('client_integrations.hub', client_id=client_id))
