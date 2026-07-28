"""
ChatWork 受信ファイル → 選択ストレージ 自動保存サービス

Web の手動同期エンドポイントと、定期実行バッチ（batch_chatwork.py）の
両方から呼び出せる共通ロジック。

処理概要:
  1. テナントの ChatWork 連携設定（APIトークン）を取得
  2. ルーム→顧問先マッピングを走査
  3. 各ルームのファイル一覧を取得し、未受信（T_受信ファイルに無い file_id）を検出
  4. ダウンロード → get_storage_adapter(tenant_id).upload() で選択ストレージへ保存
  5. T_受信ファイル（重複防止ログ）と T_ファイル（顧問先の共有ファイル）へ記録
"""
from io import BytesIO
from datetime import datetime

from app.db import SessionLocal
from app.models_integrations import (
    TIntegrationSetting, TChatworkRoomMapping, TReceivedFile,
)
from app.models_clients import TClient, TFile
from app.utils.integrations.chatwork import ChatworkClient, ChatworkError
from app.utils.tenant_storage_adapter import get_storage_adapter


def get_active_setting(db, tenant_id: int):
    """テナントの有効な ChatWork 連携設定を取得"""
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


def sync_tenant(tenant_id: int) -> dict:
    """
    指定テナントの ChatWork 連携ルームを同期し、新着ファイルをストレージへ保存する。

    Returns:
        dict: {'saved': int, 'skipped': int, 'errors': [str], 'rooms': int}
    """
    result = {'saved': 0, 'skipped': 0, 'errors': [], 'rooms': 0}
    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        if not setting or not setting.api_token:
            result['errors'].append('ChatWork連携が未設定です')
            return result

        try:
            client = ChatworkClient(setting.api_token)
        except ChatworkError as e:
            result['errors'].append(str(e))
            return result

        mappings = (db.query(TChatworkRoomMapping)
                      .filter(TChatworkRoomMapping.tenant_id == tenant_id,
                              TChatworkRoomMapping.status == 'active')
                      .all())
        result['rooms'] = len(mappings)

        adapter = get_storage_adapter(tenant_id)

        for m in mappings:
            client_obj = db.query(TClient).filter(
                TClient.id == m.client_id,
                TClient.tenant_id == tenant_id,
            ).first()
            if not client_obj:
                continue

            try:
                files = client.list_files(m.room_id)
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
                    detail = client.get_file_download_url(m.room_id, file_id)
                    download_url = detail.get('download_url')
                    if not download_url:
                        raise ChatworkError('ダウンロードURLを取得できませんでした')
                    data = client.download_file_bytes(download_url)

                    storage_url = adapter.upload(
                        BytesIO(data), filename,
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

        return result
    finally:
        db.close()


def sync_all_tenants() -> dict:
    """ChatWork連携が有効な全テナントを同期（バッチ用）"""
    summary = {'tenants': 0, 'saved': 0, 'skipped': 0, 'errors': []}
    db = SessionLocal()
    try:
        settings = (db.query(TIntegrationSetting)
                      .filter(TIntegrationSetting.provider == 'chatwork',
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
