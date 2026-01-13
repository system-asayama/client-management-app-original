"""
外部ストレージアダプタ（Dropbox / GCS）
"""
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from app.db import get_conn


class StorageAdapterBase:
    """ストレージアダプタの基底クラス"""
    
    def __init__(self, row_or_none, org_id: int):
        """
        Args:
            row_or_none: T_外部ストレージ連携の行（無い場合は None）
            org_id: 事業所ID
        """
        self.row = row_or_none
        self.org_id = org_id
    
    def upload(self, file_stream, original_name) -> str:
        """
        ファイルをアップロードして、ダウンロード/共有URL を返す
        
        Args:
            file_stream: ファイルストリーム
            original_name: 元のファイル名
            
        Returns:
            str: ダウンロード/共有URL
        """
        raise NotImplementedError


class DropboxAdapter(StorageAdapterBase):
    """Dropboxストレージアダプタ"""
    
    def _get_client(self):
        """Dropboxクライアントを取得"""
        try:
            import dropbox
        except Exception as e:
            raise RuntimeError(f"Dropbox SDK がインポートできません: {e}")
        
        # 環境変数または設定からトークンを取得
        token = os.environ.get('DROPBOX_ACCESS_TOKEN')
        if not token:
            raise RuntimeError("Dropboxアクセストークンが未設定です（環境変数DROPBOX_ACCESS_TOKEN）")
        
        return dropbox.Dropbox(token)
    
    def upload(self, file_stream, original_name) -> str:
        """Dropboxにファイルをアップロード"""
        import dropbox
        
        dbx = self._get_client()
        safe = secure_filename(original_name) or 'uploaded'
        today = datetime.now().strftime('%Y-%m')
        dropbox_path = f'/org-{self.org_id}/{today}/{safe}'
        
        data = file_stream.read()
        dbx.files_upload(data, dropbox_path, mode=dropbox.files.WriteMode.overwrite)
        
        # 共有リンク取得
        try:
            link = dbx.sharing_create_shared_link_with_settings(dropbox_path).url
        except dropbox.exceptions.ApiError:
            res = dbx.sharing_list_shared_links(path=dropbox_path, direct_only=True)
            link = res.links[0].url if res.links else None
        
        # ダイレクトダウンロードリンクに変換
        if link and link.endswith('?dl=0'):
            link = link[:-1] + '1'
        
        return link or dropbox_path


class GCSAdapter(StorageAdapterBase):
    """Google Cloud Storageアダプタ"""
    
    def _get_client_and_bucket(self):
        """GCSクライアントとバケットを取得"""
        try:
            from google.cloud import storage
        except Exception as e:
            raise RuntimeError(f"GCS用 google-cloud-storage がインポートできません: {e}")
        
        client = storage.Client()
        bucket_name = os.environ.get('GCS_BUCKET')
        if not bucket_name:
            raise RuntimeError("GCS_BUCKET 環境変数が未設定です")
        
        bucket = client.bucket(bucket_name)
        return client, bucket
    
    def upload(self, file_stream, original_name) -> str:
        """GCSにファイルをアップロード"""
        _, bucket = self._get_client_and_bucket()
        
        safe = secure_filename(original_name) or 'uploaded'
        today = datetime.now().strftime('%Y-%m')
        object_name = f'org-{self.org_id}/{today}/{safe}'
        
        blob = bucket.blob(object_name)
        blob.upload_from_file(file_stream)
        
        return blob.public_url


def table_exists(name: str) -> bool:
    """テーブルの存在チェック"""
    conn = get_conn()
    r = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone()
    conn.close()
    return bool(r)


def get_active_storage_row(org_id: int):
    """
    アクティブなストレージ連携設定を取得
    
    Args:
        org_id: 事業所ID
        
    Returns:
        sqlite3.Row or None: 連携設定行
    """
    if not table_exists('T_外部ストレージ連携'):
        return None
    
    conn = get_conn()
    row = conn.execute("""
        SELECT * FROM T_外部ストレージ連携
        WHERE 事業所ID=? AND status='active'
        ORDER BY id DESC
        LIMIT 1
    """, (org_id,)).fetchone()
    conn.close()
    return row


def get_storage_adapter(org_id: int) -> StorageAdapterBase:
    """
    事業所IDに応じたストレージアダプタを取得
    
    Args:
        org_id: 事業所ID
        
    Returns:
        StorageAdapterBase: ストレージアダプタインスタンス
    """
    row = get_active_storage_row(org_id)
    
    if row:
        provider = (row['provider'] or '').strip().lower()
        if provider == 'dropbox':
            return DropboxAdapter(row, org_id)
        elif provider in ('gcs', 'google', 'google_cloud_storage'):
            return GCSAdapter(row, org_id)
        else:
            raise RuntimeError(f"未対応のproviderです: {provider}")
    else:
        # フォールバック：Dropbox
        return DropboxAdapter(None, org_id)
