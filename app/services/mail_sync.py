"""
担当ごとのメール受信 → 選択ストレージ 自動保存サービス（マルチプロバイダ）

メールは担当者本人の受信箱に届くため、担当スタッフ単位で登録された
メールアカウント（T_担当メール連携）を1つずつ巡回する。
Gmail / Outlook(M365) / Yahoo / iCloud / その他 を IMAP で統一的に扱う。

差出人 → 顧問先 の振り分けは Gmail 実装（gmail_sync）のロジックを再利用する。
"""
from io import BytesIO
from datetime import datetime

from app.db import SessionLocal
from app.models_integrations import TStaffMailAccount, TReceivedFile
from app.models_clients import TClient, TFile
from app.utils.integrations.mail import ImapMailClient, MailError
from app.utils.tenant_storage_adapter import get_storage_adapters, upload_to_adapters
# 差出人→顧問先の解決は Gmail 実装を再利用（明示マッピング→顧問先email一致→未分類）
from app.services.gmail_sync import _resolve_client_id


def _already_received(db, tenant_id: int, external_id: str) -> bool:
    return db.query(TReceivedFile).filter(
        TReceivedFile.tenant_id == tenant_id,
        TReceivedFile.provider == 'mail',
        TReceivedFile.external_id == external_id,
    ).first() is not None


def sync_account(account_id: int) -> dict:
    """1つの担当メールアカウントを巡回して添付を保存する。"""
    result = {'saved': 0, 'skipped': 0, 'errors': [], 'messages': 0}
    db = SessionLocal()
    try:
        acc = db.query(TStaffMailAccount).filter(
            TStaffMailAccount.id == account_id,
            TStaffMailAccount.status == 'active').first()
        if not acc:
            return result
        tenant_id = acc.tenant_id

        client = ImapMailClient(acc.email, acc.app_password, acc.imap_host, acc.imap_port)
        try:
            client.connect()
            messages, max_uid = client.fetch_new_with_attachments(since_uid=acc.since_uid or 0)
        except MailError as e:
            result['errors'].append(f'{acc.email}: {e}')
            return result
        finally:
            client.close()

        result['messages'] = len(messages)
        # 店舗ごとにストレージアダプタを解決（店舗設定→テナント設定）。store_id別にキャッシュ
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
                # アカウント単位でUIDが違うので account.id を含めて一意化
                external_id = f"{acc.id}:{msg['uid']}:{idx}:{filename}"
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
                        subfolder=(subfolder or 'メール受信'),
                    )
                    db.add(TReceivedFile(
                        tenant_id=tenant_id, provider='mail',
                        external_id=external_id, room_id=sender,
                        client_id=(client_obj.id if client_obj else None),
                        filename=filename, storage_url=storage_url, status='saved',
                    ))
                    if client_obj:
                        db.add(TFile(
                            client_id=client_obj.id, filename=filename,
                            file_url=storage_url or '',
                            uploader=f'メール自動連携({acc.email})',
                            timestamp=datetime.utcnow(),
                        ))
                    db.commit()
                    result['saved'] += 1
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    db.add(TReceivedFile(
                        tenant_id=tenant_id, provider='mail',
                        external_id=external_id, room_id=sender,
                        client_id=(client_obj.id if client_obj else None),
                        filename=filename, status='error', error_message=str(e)[:500],
                    ))
                    db.commit()
                    result['errors'].append(f'{filename}: {e}')

        # 処理済みUIDを保存
        if max_uid and max_uid > (acc.since_uid or 0):
            acc.since_uid = max_uid
            db.commit()
        return result
    finally:
        db.close()


def sync_tenant(tenant_id: int) -> dict:
    """テナント内の全担当メールアカウントを巡回。"""
    total = {'saved': 0, 'skipped': 0, 'errors': [], 'accounts': 0}
    db = SessionLocal()
    try:
        ids = [a.id for a in db.query(TStaffMailAccount).filter(
            TStaffMailAccount.tenant_id == tenant_id,
            TStaffMailAccount.status == 'active').all()]
    finally:
        db.close()

    total['accounts'] = len(ids)
    for aid in ids:
        r = sync_account(aid)
        total['saved'] += r['saved']
        total['skipped'] += r['skipped']
        total['errors'].extend(r['errors'])
    return total


def sync_all_tenants() -> dict:
    """メール連携が有効な全テナントを巡回（スケジューラ用）。"""
    summary = {'accounts': 0, 'saved': 0, 'skipped': 0, 'errors': []}
    db = SessionLocal()
    try:
        ids = [a.id for a in db.query(TStaffMailAccount).filter(
            TStaffMailAccount.status == 'active').all()]
    finally:
        db.close()

    summary['accounts'] = len(ids)
    for aid in ids:
        r = sync_account(aid)
        summary['saved'] += r['saved']
        summary['skipped'] += r['skipped']
        summary['errors'].extend(r['errors'])
    return summary
