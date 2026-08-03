"""
ChatWork 受信ファイル → 選択ストレージ 自動保存サービス

Web の手動同期エンドポイントと、定期実行（スケジューラ）の両方から
呼び出せる共通ロジック。

ChatWork のAPIトークンはアカウント（個人）ごとに発行されるため、2方式に対応:
  - テナント共通トークン（T_連携設定 provider='chatwork'）で、
    staff_account_id IS NULL のルームを巡回（従来方式 / 代表アカウント運用）
  - 担当ごとのトークン（T_担当ChatWork連携）で、その担当に紐付く
    ルーム（staff_account_id = そのアカウント）を巡回（担当ごと運用）

処理概要（各ルーム共通）:
  1. ルーム→顧問先マッピングを走査
  2. 各ルームのファイル一覧を取得し、未受信（T_受信ファイルに無い file_id）を検出
  3. ダウンロード → 顧問先の店舗に応じたストレージへ保存
  4. T_受信ファイル（重複防止ログ）と T_ファイル（顧問先の共有ファイル）へ記録
"""
from io import BytesIO
from datetime import datetime

from app.db import SessionLocal
from app.models_integrations import (
    TIntegrationSetting, TChatworkRoomMapping, TReceivedFile, TStaffChatworkAccount,
)
from app.models_clients import TClient, TFile
from app.utils.integrations.chatwork import ChatworkClient, ChatworkError
from app.utils.tenant_storage_adapter import get_storage_adapters, upload_to_adapters


def get_active_setting(db, tenant_id: int):
    """テナントの有効な ChatWork 連携設定（共通トークン）を取得"""
    return (db.query(TIntegrationSetting)
              .filter(TIntegrationSetting.tenant_id == tenant_id,
                      TIntegrationSetting.provider == 'chatwork',
                      TIntegrationSetting.status == 'active')
              .order_by(TIntegrationSetting.id.desc())
              .first())


def _already_received(db, tenant_id: int, file_id) -> bool:
    return db.query(TReceivedFile).filter(
        TReceivedFile.tenant_id == tenant_id,
        TReceivedFile.provider == 'chatwork',
        TReceivedFile.external_id == str(file_id),
    ).first() is not None


def _process_mappings(db, tenant_id: int, cw_client, mappings, result: dict,
                      staff_id=None, staff_type=None):
    """ルームマッピング群を巡回して新着ファイルをストレージへ保存する共通処理。

    cw_client: 認証済み ChatworkClient（テナント共通 or 担当のトークン）
    mappings : TChatworkRoomMapping のリスト
    result   : {'saved','skipped','errors',...} を加算していく
    staff_id/staff_type: 担当者アカウント経由の場合、担当者個人ストレージを最優先で使う
    """
    # ストレージアダプタ（主＋ミラー）を解決（担当者個人→店舗→本部）。store_id別にキャッシュ
    _adapters_cache = {}
    def _adapters_for(store_id):
        if store_id not in _adapters_cache:
            _adapters_cache[store_id] = get_storage_adapters(
                tenant_id, store_id=store_id,
                staff_id=staff_id, staff_type=staff_type)
        return _adapters_cache[store_id]

    for m in mappings:
        client_obj = db.query(TClient).filter(
            TClient.id == m.client_id,
            TClient.tenant_id == tenant_id,
        ).first()
        if not client_obj:
            continue

        try:
            files = cw_client.list_files(m.room_id)
        except ChatworkError as e:
            result['errors'].append(f'ルーム{m.room_id}: {e}')
            continue

        for f in files or []:
            file_id = f.get('file_id')
            filename = f.get('filename') or f'chatwork_{file_id}'
            if file_id is None:
                continue
            if _already_received(db, tenant_id, file_id):
                result['skipped'] += 1
                continue

            try:
                detail = cw_client.get_file_download_url(m.room_id, file_id)
                download_url = detail.get('download_url')
                if not download_url:
                    raise ChatworkError('ダウンロードURLを取得できませんでした')
                data = cw_client.download_file_bytes(download_url)

                adapters = _adapters_for(getattr(client_obj, 'store_id', None))
                storage_url = upload_to_adapters(
                    adapters, data, filename,
                    client_id=client_obj.id,
                    client_folder_path=client_obj.storage_folder_path,
                    subfolder=(m.subfolder or 'ChatWork受信'),
                )

                db.add(TReceivedFile(
                    tenant_id=tenant_id, provider='chatwork',
                    external_id=str(file_id), room_id=str(m.room_id),
                    client_id=client_obj.id, filename=filename,
                    storage_url=storage_url, status='saved',
                ))
                db.add(TFile(
                    client_id=client_obj.id, filename=filename,
                    file_url=storage_url or '',
                    uploader='ChatWork自動連携',
                    timestamp=datetime.utcnow(),
                ))
                db.commit()
                result['saved'] += 1
            except Exception as e:  # noqa: BLE001 - 1件の失敗で全体を止めない
                db.rollback()
                db.add(TReceivedFile(
                    tenant_id=tenant_id, provider='chatwork',
                    external_id=str(file_id), room_id=str(m.room_id),
                    client_id=client_obj.id, filename=filename,
                    status='error', error_message=str(e)[:500],
                ))
                db.commit()
                result['errors'].append(f'{filename}: {e}')


def sync_tenant(tenant_id: int) -> dict:
    """テナント共通トークンで staff_account_id IS NULL のルームを同期する（従来方式）。

    Returns:
        dict: {'saved': int, 'skipped': int, 'errors': [str], 'rooms': int}
    """
    result = {'saved': 0, 'skipped': 0, 'errors': [], 'rooms': 0}
    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        if not setting or not setting.api_token:
            # 共通トークン未設定でもエラーにはしない（担当ごと運用のみの場合がある）
            return result

        try:
            client = ChatworkClient(setting.api_token)
        except ChatworkError as e:
            result['errors'].append(str(e))
            return result

        mappings = (db.query(TChatworkRoomMapping)
                      .filter(TChatworkRoomMapping.tenant_id == tenant_id,
                              TChatworkRoomMapping.status == 'active',
                              TChatworkRoomMapping.staff_account_id.is_(None))
                      .all())
        result['rooms'] = len(mappings)
        _process_mappings(db, tenant_id, client, mappings, result)
        return result
    finally:
        db.close()


def sync_staff_account(account_id: int) -> dict:
    """担当ごとの ChatWork アカウント1つを巡回して添付を保存する。"""
    result = {'saved': 0, 'skipped': 0, 'errors': [], 'rooms': 0}
    db = SessionLocal()
    try:
        acc = db.query(TStaffChatworkAccount).filter(
            TStaffChatworkAccount.id == account_id,
            TStaffChatworkAccount.status == 'active').first()
        if not acc or not acc.api_token:
            return result
        tenant_id = acc.tenant_id

        try:
            client = ChatworkClient(acc.api_token)
        except ChatworkError as e:
            result['errors'].append(str(e))
            return result

        mappings = (db.query(TChatworkRoomMapping)
                      .filter(TChatworkRoomMapping.tenant_id == tenant_id,
                              TChatworkRoomMapping.status == 'active',
                              TChatworkRoomMapping.staff_account_id == account_id)
                      .all())
        result['rooms'] = len(mappings)
        _process_mappings(db, tenant_id, client, mappings, result,
                          staff_id=getattr(acc, 'staff_id', None),
                          staff_type=getattr(acc, 'staff_type', None))
        return result
    finally:
        db.close()


def sync_all_tenants() -> dict:
    """ChatWork連携が有効な全対象を同期（スケジューラ用）。

    - テナント共通トークン（従来方式）
    - 担当ごとのアカウント（担当ごと方式）
    の両方を巡回する。
    """
    summary = {'tenants': 0, 'accounts': 0, 'saved': 0, 'skipped': 0, 'errors': []}
    db = SessionLocal()
    try:
        settings = (db.query(TIntegrationSetting)
                      .filter(TIntegrationSetting.provider == 'chatwork',
                              TIntegrationSetting.status == 'active')
                      .all())
        tenant_ids = sorted({s.tenant_id for s in settings})
        staff_account_ids = [a.id for a in db.query(TStaffChatworkAccount).filter(
            TStaffChatworkAccount.status == 'active').all()]
    finally:
        db.close()

    for tid in tenant_ids:
        r = sync_tenant(tid)
        summary['tenants'] += 1
        summary['saved'] += r['saved']
        summary['skipped'] += r['skipped']
        summary['errors'].extend(r['errors'])

    for aid in staff_account_ids:
        r = sync_staff_account(aid)
        summary['accounts'] += 1
        summary['saved'] += r['saved']
        summary['skipped'] += r['skipped']
        summary['errors'].extend(r['errors'])

    return summary
