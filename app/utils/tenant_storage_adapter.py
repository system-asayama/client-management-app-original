"""
テナント用ストレージアダプタ（Dropbox / GCS）
"""
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from app.db import SessionLocal
from sqlalchemy import text


class StorageAdapterBase:
    """ストレージアダプタの基底クラス"""
    
    def __init__(self, storage_config, tenant_id: int):
        """
        Args:
            storage_config: T_外部ストレージ連携の行
            tenant_id: テナントID
        """
        self.config = storage_config
        self.tenant_id = tenant_id
    
    def upload(self, file_stream, original_name, client_id: int) -> str:
        """
        ファイルをアップロードして、ダウンロード/共有URL を返す
        
        Args:
            file_stream: ファイルストリーム
            original_name: 元のファイル名
            client_id: 顧問先ID
            
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
        
        # 設定からトークンを取得
        token = self.config.access_token if self.config else None
        if not token:
            raise RuntimeError("Dropboxアクセストークンが未設定です")
        
        return dropbox.Dropbox(token)
    
    def upload(self, file_stream, original_name, client_id: int) -> str:
        """Dropboxにファイルをアップロード"""
        import dropbox
        
        dbx = self._get_client()
        safe = secure_filename(original_name) or 'uploaded'
        today = datetime.now().strftime('%Y-%m')
        # テナントID/顧問先ID/年月/ファイル名 の構造で保存
        dropbox_path = f'/tenant-{self.tenant_id}/client-{client_id}/{today}/{safe}'
        
        data = file_stream.read()
        dbx.files_upload(data, dropbox_path, mode=dropbox.files.WriteMode.overwrite)
        
        # 共有リンク取得
        try:
            link = dbx.sharing_create_shared_link_with_settings(dropbox_path).url
        except dropbox.exceptions.ApiError:
            # 既に共有リンクが存在する場合
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
            import json
        except Exception as e:
            raise RuntimeError(f"GCS用 google-cloud-storage がインポートできません: {e}")
        
        # サービスアカウントJSONを環境変数として設定
        if self.config and self.config.service_account_json:
            import tempfile
            # 一時ファイルにサービスアカウントキーを書き込む
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
                f.write(self.config.service_account_json)
                temp_key_path = f.name
            
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_key_path
        
        client = storage.Client()
        bucket_name = self.config.bucket_name if self.config else None
        if not bucket_name:
            raise RuntimeError("GCS_BUCKET が未設定です")
        
        bucket = client.bucket(bucket_name)
        return client, bucket
    
    def upload(self, file_stream, original_name, client_id: int) -> str:
        """GCSにファイルをアップロード"""
        _, bucket = self._get_client_and_bucket()
        safe = secure_filename(original_name) or 'uploaded'
        today = datetime.now().strftime('%Y-%m')
        # テナントID/顧問先ID/年月/ファイル名 の構造で保存
        object_name = f'tenant-{self.tenant_id}/client-{client_id}/{today}/{safe}'
        
        blob = bucket.blob(object_name)
        blob.upload_from_file(file_stream)
        
        return blob.public_url


def get_tenant_storage_config(tenant_id: int):
    """
    テナントのアクティブなストレージ連携設定を取得
    
    Args:
        tenant_id: テナントID
        
    Returns:
        storage_config or None: 連携設定
    """
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT * FROM "T_外部ストレージ連携"
            WHERE tenant_id = :tenant_id AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """), {"tenant_id": tenant_id})
        return result.fetchone()
    finally:
        db.close()


def get_storage_adapter(tenant_id: int) -> StorageAdapterBase:
    """
    テナントIDに応じたストレージアダプタを取得
    
    Args:
        tenant_id: テナントID
        
    Returns:
        StorageAdapterBase: ストレージアダプタインスタンス
    """
    config = get_tenant_storage_config(tenant_id)
    
    if not config:
        raise RuntimeError(
            "ストレージが設定されていません。"
            "テナント管理画面でDropboxまたはGoogle Cloud Storageと連携してください。"
        )
    
    provider = (config.provider or '').strip().lower()
    if provider == 'dropbox':
        return DropboxAdapter(config, tenant_id)
    elif provider in ('gcs', 'google', 'google_cloud_storage'):
        return GCSAdapter(config, tenant_id)
    else:
        raise RuntimeError(f"未対応のストレージプロバイダーです: {provider}")
