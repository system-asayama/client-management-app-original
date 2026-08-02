"""
Gmail 受信添付 → 選択ストレージ 自動保存サービス

差出人メールアドレスから顧問先を特定し、添付ファイルを顧問先フォルダへ保存する。
振り分けは以下の優先順で解決:
  1. T_Gmail送信者マッピング（明示的な 差出人→顧問先 の対応）
  2. T_顧問先.email との一致（フォールバック）
  3. いずれも該当しない場合は「未分類」フォルダへ保存（client_id=None）

設定は T_連携設定（provider='gmail'）に保存:
  - api_token : IMAPアプリパスワード
  - extra(JSON): {"email": "...", "imap_host": "...", "since_uid": N}

Web手動同期と定期バッチ（batch_gmail.py）の双方から利用可能。
"""
import json
from io import BytesIO
from datetime import datetime

from app.db import SessionLocal
from app.models_integrations import (
    TIntegrationSetting, TGmailSenderMapping, TReceivedFile,
)
from app.models_clients import TClient, TFile
from app.utils.integrations.gmail_imap import GmailImapClient, GmailImapError
from app.utils.tenant_storage_adapter import get_storage_adapters, upload_to_adapters


def get_active_setting(db, tenant_id: int):
    return (db.query(TIntegrationSetting)
              .filter(TIntegrationSetting.tenant_id == tenant_id,
                      TIntegrationSetting.provider == 'gmail',
                      TIntegrationSetting.status == 'active')
              .order_by(TIntegrationSetting.id.desc())
              .first())


def _load_extra(setting) -> dict:
    try:
        return json.loads(setting.extra) if setting.extra else {}
    except Exception:
        return {}


def _resolve_client_id(db, tenant_id: int, sender_email: str):
    """差出人メールアドレスから顧問先IDとサブフォルダを解決"""
    sender = (sender_email or '').lower()
    if not sender:
        return None, 'Gmail受信/未分類'
    # 1. 明示マッピング
    m = (db.query(TGmailSenderMapping)
           .filter(TGmailSenderMapping.tenant_id == tenant_id,
                   TGmailSenderMapping.sender_email == sender,
                   TGmailSenderMapping.status == 'active')
           .first())
    if m:
        return m.client_id, (m.subfolder or 'Gmail受信')
    # 2. 顧問先の登録メールと一致
    c = (db.query(TClient)
           .filter(TClient.tenant_id == tenant_id, TClient.email.isnot(None))
           .all())
    for client in c:
        if (client.email or '').lower() == sender:
            return client.id, 'Gmail受信'
    # 3. 未分類
    return None, 'Gmail受信/未分類'


def _already_received(db, tenant_id: int, external_id: str) -> bool:
    return db.query(TReceivedFile).filter(
        TReceivedFile.tenant_id == tenant_id,
        TReceivedFile.provider == 'gmail',
        TReceivedFile.external_id == external_id,
    ).first() is not None


def sync_tenant(tenant_id: int) -> dict:
    """指定テナントのGmail新着添付をストレージへ保存"""
    result = {'saved': 0, 'skipped': 0, 'errors': [], 'messages': 0}
    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        if not setting or not setting.api_token:
            result['errors'].append('Gmail連携が未設定です')
            return result

        extra = _load_extra(setting)
        email_address = extra.get('email')
        if not email_address:
            result['errors'].append('メールアドレスが未設定です')
            return result
        since_uid = int(extra.get('since_uid') or 0)
        imap_host = extra.get('imap_host') or 'imap.gmail.com'
        try:
            imap_port = int(extra.get('imap_port') or 993)
        except (TypeError, ValueError):
            imap_port = 993

        client = GmailImapClient(email_address, setting.api_token, host=imap_host, port=imap_port)
        try:
            client.connect()
            messages, max_uid = client.fetch_new_with_attachments(since_uid=since_uid)
        except GmailImapError as e:
            result['errors'].append(str(e))
            return result
        finally:
            client.close()

        result['messages'] = len(messages)
        _adapters_cache = {}
        def _adapters_for(store_id):
            if store_id not in _adapters_cache:
                _adapters_cache[store_id] = get_storage_adapters(tenant_id, store_id=store_id)
            return _adapters_cache[store_id]

        for msg in messages:
            sender = msg['from']
            client_id, subfolder = _resolve_client_id(db, tenant_id, sender)
            client_obj = None
            if client_id:
                client_obj = db.query(TClient).filter(
                    TClient.id == client_id, TClient.tenant_id == tenant_id).first()

            for idx, att in enumerate(msg['attachments']):
                filename = att['filename']
                external_id = f"{msg['uid']}:{idx}:{filename}"
                if _already_received(db, tenant_id, external_id):
                    result['skipped'] += 1
                    continue
                try:
                    folder_path = client_obj.storage_folder_path if client_obj else None
                    adapters = _adapters_for(getattr(client_obj, 'store_id', None) if client_obj else None)
                    storage_url = upload_to_adapters(
                        adapters, att['data'], filename,
                        client_id=(client_obj.id if client_obj else 0),
                        client_folder_path=folder_path,
                        subfolder=subfolder,
                    )
                    db.add(TReceivedFile(
                        tenant_id=tenant_id, provider='gmail',
                        external_id=external_id, room_id=sender,
                        client_id=(client_obj.id if client_obj else None),
                        filename=filename, storage_url=storage_url, status='saved',
                    ))
                    if client_obj:
                        db.add(TFile(
                            client_id=client_obj.id, filename=filename,
                            file_url=storage_url or '',
                            uploader='Gmail自動連携', timestamp=datetime.utcnow(),
                        ))
                    db.commit()
                    result['saved'] += 1
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    db.add(TReceivedFile(
                        tenant_id=tenant_id, provider='gmail',
                        external_id=external_id, room_id=sender,
                        client_id=(client_obj.id if client_obj else None),
                        filename=filename, status='error', error_message=str(e)[:500],
                    ))
                    db.commit()
                    result['errors'].append(f'{filename}: {e}')

        # 処理済みUIDを保存（次回はこれ以降のみ取得）
        if max_uid and max_uid > since_uid:
            extra['since_uid'] = max_uid
            setting.extra = json.dumps(extra, ensure_ascii=False)
            db.commit()

        return result
    finally:
        db.close()


def sync_all_tenants() -> dict:
    """Gmail連携が有効な全テナントを同期（バッチ用）"""
    summary = {'tenants': 0, 'saved': 0, 'skipped': 0, 'errors': []}
    db = SessionLocal()
    try:
        settings = (db.query(TIntegrationSetting)
                      .filter(TIntegrationSetting.provider == 'gmail',
                              TIntegrationSetting.status == 'active')
                      .all())
        tenant_ids = sorted({s.tenant_id for s in settings})
    finally:
        db.close()

    for tid in tenant_ids:
        r = sync_tenant(tid)
        summary['tenants'] += 1
        summary['saved'] += r['saved']
        summary['skipped'] += r['skipped']
        summary['errors'].extend(r['errors'])
    return summary
