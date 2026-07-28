"""
ストレージ保存済みの受信資料 → 会計ソフト（freee等）アップロードサービス

トリガー方針:
  ChatWork/Gmail で受信 → ストレージへ保存（T_受信ファイル）→ 本サービスで会計ソフトへ。
  受信と会計アップロードを分離することで、誤送信の抑止と再送を容易にする。

Web の手動アップロード／一括同期エンドポイントと、定期バッチの双方から利用可能。
"""
from datetime import datetime, timedelta
import requests

from app.db import SessionLocal
from app.models_integrations import TReceivedFile
from app.models_accounting import TAccountingConnection, TAccountingUploadLog
from app.utils.accounting import get_provider, AccountingError

FETCH_TIMEOUT = 60


def _fetch_bytes(url: str) -> bytes:
    """ストレージのURLからファイル本体を取得"""
    if not url:
        raise AccountingError('保存先URLが空です')
    resp = requests.get(url, timeout=FETCH_TIMEOUT)
    if resp.status_code >= 400:
        raise AccountingError(f'ストレージからの取得に失敗しました ({resp.status_code})')
    return resp.content


def get_connection(db, tenant_id: int, client_id: int):
    """顧問先の有効な会計ソフト連携を取得"""
    return (db.query(TAccountingConnection)
              .filter(TAccountingConnection.tenant_id == tenant_id,
                      TAccountingConnection.client_id == client_id,
                      TAccountingConnection.status == 'active')
              .order_by(TAccountingConnection.id.desc())
              .first())


def _ensure_token(db, conn) -> str:
    """アクセストークンが有効か確認し、期限切れならリフレッシュして返す"""
    provider = get_provider(conn.provider)
    now = datetime.utcnow()
    # 期限の60秒前を過ぎていたらリフレッシュ
    if conn.token_expires_at and conn.token_expires_at - timedelta(seconds=60) <= now:
        if not conn.refresh_token:
            raise AccountingError('リフレッシュトークンがありません。再連携が必要です')
        tok = provider.refresh(conn.refresh_token)
        conn.access_token = tok['access_token']
        if tok.get('refresh_token'):
            conn.refresh_token = tok['refresh_token']
        if tok.get('expires_in'):
            conn.token_expires_at = now + timedelta(seconds=int(tok['expires_in']))
        db.commit()
    return conn.access_token


def _already_uploaded(db, provider: str, source_id: int) -> bool:
    return db.query(TAccountingUploadLog).filter(
        TAccountingUploadLog.provider == provider,
        TAccountingUploadLog.source_type == 'received_file',
        TAccountingUploadLog.source_id == source_id,
        TAccountingUploadLog.status == 'uploaded',
    ).first() is not None


def upload_received_file(received_file_id: int) -> dict:
    """1件の受信ファイルを会計ソフトへアップロード"""
    db = SessionLocal()
    try:
        rf = db.query(TReceivedFile).filter(TReceivedFile.id == received_file_id).first()
        if not rf:
            return {'ok': False, 'error': '受信ファイルが見つかりません'}
        if rf.status != 'saved':
            return {'ok': False, 'error': 'ストレージ未保存のファイルです'}
        if not rf.client_id:
            return {'ok': False, 'error': '顧問先が未割当のため送信できません'}

        conn = get_connection(db, rf.tenant_id, rf.client_id)
        if not conn or not conn.company_id:
            return {'ok': False, 'error': '会計ソフト連携が未設定です'}

        if _already_uploaded(db, conn.provider, rf.id):
            return {'ok': True, 'skipped': True}

        provider = get_provider(conn.provider)
        try:
            access_token = _ensure_token(db, conn)
            data = _fetch_bytes(rf.storage_url)
            res = provider.upload_receipt(
                access_token, conn.company_id, data,
                rf.filename or f'receipt_{rf.id}',
                description=f'自動連携: {rf.filename or ""}',
                document_type='other',
            )
            db.add(TAccountingUploadLog(
                tenant_id=rf.tenant_id, client_id=rf.client_id,
                provider=conn.provider, source_type='received_file',
                source_id=rf.id, external_id=res.get('external_id'),
                filename=rf.filename, status='uploaded',
            ))
            db.commit()
            return {'ok': True, 'external_id': res.get('external_id')}
        except Exception as e:  # noqa: BLE001
            db.rollback()
            db.add(TAccountingUploadLog(
                tenant_id=rf.tenant_id, client_id=rf.client_id,
                provider=conn.provider, source_type='received_file',
                source_id=rf.id, filename=rf.filename,
                status='error', error_message=str(e)[:500],
            ))
            db.commit()
            return {'ok': False, 'error': str(e)}
    finally:
        db.close()


def _pending_received_files(db, tenant_id: int, client_id: int = None):
    """会計ソフトへ未アップロードの保存済み受信ファイルを抽出"""
    uploaded_ids = {
        r.source_id for r in db.query(TAccountingUploadLog.source_id).filter(
            TAccountingUploadLog.tenant_id == tenant_id,
            TAccountingUploadLog.source_type == 'received_file',
            TAccountingUploadLog.status == 'uploaded',
        ).all()
    }
    q = db.query(TReceivedFile).filter(
        TReceivedFile.tenant_id == tenant_id,
        TReceivedFile.status == 'saved',
        TReceivedFile.client_id.isnot(None),
    )
    if client_id:
        q = q.filter(TReceivedFile.client_id == client_id)
    return [rf for rf in q.order_by(TReceivedFile.id).all() if rf.id not in uploaded_ids]


def upload_tenant_pending(tenant_id: int) -> dict:
    """テナントの未アップロード保存済み資料を、連携済み顧問先分だけ一括送信"""
    result = {'uploaded': 0, 'skipped': 0, 'errors': []}
    db = SessionLocal()
    try:
        # 連携済みの顧問先IDのみ対象
        connected = {c.client_id for c in db.query(TAccountingConnection).filter(
            TAccountingConnection.tenant_id == tenant_id,
            TAccountingConnection.status == 'active',
        ).all()}
        targets = [rf for rf in _pending_received_files(db, tenant_id)
                   if rf.client_id in connected]
        ids = [rf.id for rf in targets]
    finally:
        db.close()

    for rid in ids:
        r = upload_received_file(rid)
        if r.get('ok') and r.get('skipped'):
            result['skipped'] += 1
        elif r.get('ok'):
            result['uploaded'] += 1
        else:
            result['errors'].append(r.get('error', 'unknown'))
    return result


def upload_client_pending(tenant_id: int, client_id: int) -> dict:
    """特定の顧問先の未アップロード保存済み資料を送信"""
    result = {'uploaded': 0, 'skipped': 0, 'errors': []}
    db = SessionLocal()
    try:
        conn = get_connection(db, tenant_id, client_id)
        if not conn or not conn.company_id:
            return {'uploaded': 0, 'skipped': 0, 'errors': ['この顧問先は会計ソフト未連携です']}
        ids = [rf.id for rf in _pending_received_files(db, tenant_id, client_id)]
    finally:
        db.close()

    for rid in ids:
        r = upload_received_file(rid)
        if r.get('ok') and r.get('skipped'):
            result['skipped'] += 1
        elif r.get('ok'):
            result['uploaded'] += 1
        else:
            result['errors'].append(r.get('error', 'unknown'))
    return result


def upload_all_tenants() -> dict:
    """会計ソフト連携が有効な全テナントを一括送信（バッチ用）"""
    summary = {'tenants': 0, 'uploaded': 0, 'skipped': 0, 'errors': []}
    db = SessionLocal()
    try:
        tenant_ids = sorted({c.tenant_id for c in db.query(TAccountingConnection).filter(
            TAccountingConnection.status == 'active').all()})
    finally:
        db.close()

    for tid in tenant_ids:
        r = upload_tenant_pending(tid)
        summary['tenants'] += 1
        summary['uploaded'] += r['uploaded']
        summary['skipped'] += r['skipped']
        summary['errors'].extend(r['errors'])
    return summary
