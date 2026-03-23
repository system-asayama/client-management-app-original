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
        self.config = storage_config
        self.tenant_id = tenant_id
    
    def upload(self, file_stream, original_name, client_id: int,
               client_folder_path: str = None, subfolder: str = None) -> str:
        """
        ファイルをアップロードして、ダウンロード/共有URL を返す
        
        Args:
            file_stream: ファイルストリーム
            original_name: 元のファイル名
            client_id: 顧問先ID
            client_folder_path: 顧問先のストレージ内ベースフォルダパス
            subfolder: ベースフォルダ内のサブフォルダ（その都度指定）
        Returns:
            str: ダウンロード/共有URL
        """
        raise NotImplementedError

    def list_folders(self, client_folder_path: str) -> list:
        """
        顧問先フォルダ内のサブフォルダ一覧を返す
        
        Args:
            client_folder_path: 顧問先のベースフォルダパス
        Returns:
            list[str]: サブフォルダ名のリスト
        """
        raise NotImplementedError

    def create_folder(self, client_folder_path: str, folder_name: str) -> bool:
        """
        顧問先フォルダ内に新しいサブフォルダを作成する
        
        Args:
            client_folder_path: 顧問先のベースフォルダパス
            folder_name: 作成するフォルダ名
        Returns:
            bool: 成功したか
        """
        raise NotImplementedError


class DropboxAdapter(StorageAdapterBase):
    """Dropboxストレージアダプタ"""
    
    def _get_client(self):
        try:
            import dropbox
        except Exception as e:
            raise RuntimeError(f"Dropbox SDK がインポートできません: {e}")
        token = self.config.access_token if self.config else None
        if not token:
            raise RuntimeError("Dropboxアクセストークンが未設定です")
        return dropbox.Dropbox(token)
    
    def upload(self, file_stream, original_name, client_id: int,
               client_folder_path: str = None, subfolder: str = None) -> str:
        import dropbox
        dbx = self._get_client()
        safe = secure_filename(original_name) or 'uploaded'

        if client_folder_path:
            base_path = client_folder_path.rstrip('/')
        else:
            base_path = f'/tenant-{self.tenant_id}/client-{client_id}'

        if subfolder:
            folder_path = f'{base_path}/{subfolder.strip("/")}'
        else:
            today = datetime.now().strftime('%Y-%m')
            folder_path = f'{base_path}/{today}'

        dropbox_path = f'{folder_path}/{safe}'
        data = file_stream.read()
        dbx.files_upload(data, dropbox_path, mode=dropbox.files.WriteMode.overwrite)

        try:
            link = dbx.sharing_create_shared_link_with_settings(dropbox_path).url
        except dropbox.exceptions.ApiError:
            res = dbx.sharing_list_shared_links(path=dropbox_path, direct_only=True)
            link = res.links[0].url if res.links else None

        if link and link.endswith('?dl=0'):
            link = link[:-1] + '1'
        return link or dropbox_path

    def list_folders(self, client_folder_path: str) -> list:
        """Dropboxの顧問先フォルダ内サブフォルダ一覧を返す"""
        import dropbox
        dbx = self._get_client()
        base_path = (client_folder_path or '').rstrip('/')
        if not base_path:
            return []
        try:
            result = dbx.files_list_folder(base_path)
            folders = []
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FolderMetadata):
                    folders.append(entry.name)
            # ページネーション
            while result.has_more:
                result = dbx.files_list_folder_continue(result.cursor)
                for entry in result.entries:
                    if isinstance(entry, dropbox.files.FolderMetadata):
                        folders.append(entry.name)
            return sorted(folders)
        except dropbox.exceptions.ApiError:
            # フォルダが存在しない場合など
            return []

    def create_folder(self, client_folder_path: str, folder_name: str) -> bool:
        """Dropboxに新しいサブフォルダを作成する"""
        import dropbox
        dbx = self._get_client()
        base_path = (client_folder_path or '').rstrip('/')
        new_path = f'{base_path}/{folder_name.strip("/")}'
        try:
            dbx.files_create_folder_v2(new_path)
            return True
        except dropbox.exceptions.ApiError as e:
            # 既に存在する場合はOK
            if 'path/conflict/folder' in str(e):
                return True
            raise RuntimeError(f"フォルダ作成に失敗しました: {e}")


class GCSAdapter(StorageAdapterBase):
    """Google Cloud Storageアダプタ"""
    
    def _get_client_and_bucket(self):
        try:
            from google.cloud import storage
        except Exception as e:
            raise RuntimeError(f"GCS用 google-cloud-storage がインポートできません: {e}")
        
        if self.config and self.config.service_account_json:
            import tempfile
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
    
    def upload(self, file_stream, original_name, client_id: int,
               client_folder_path: str = None, subfolder: str = None) -> str:
        _, bucket = self._get_client_and_bucket()
        safe = secure_filename(original_name) or 'uploaded'

        if client_folder_path:
            base_path = client_folder_path.strip('/')
        else:
            base_path = f'tenant-{self.tenant_id}/client-{client_id}'

        if subfolder:
            folder_path = f'{base_path}/{subfolder.strip("/")}'
        else:
            today = datetime.now().strftime('%Y-%m')
            folder_path = f'{base_path}/{today}'

        object_name = f'{folder_path}/{safe}'
        blob = bucket.blob(object_name)
        blob.upload_from_file(file_stream)
        return blob.public_url

    def list_folders(self, client_folder_path: str) -> list:
        """GCSの顧問先フォルダ内サブフォルダ一覧を返す"""
        _, bucket = self._get_client_and_bucket()
        base_prefix = (client_folder_path or '').strip('/') + '/'
        blobs = bucket.list_blobs(prefix=base_prefix, delimiter='/')
        # delimiter='/' を使うと response.prefixes にサブフォルダが入る
        _ = list(blobs)  # イテレートしてprefixesを確定させる
        folders = []
        for prefix in blobs.prefixes:
            folder_name = prefix.rstrip('/').split('/')[-1]
            if folder_name:
                folders.append(folder_name)
        return sorted(folders)

    def create_folder(self, client_folder_path: str, folder_name: str) -> bool:
        """GCSに新しいサブフォルダを作成する（空のプレースホルダーオブジェクト）"""
        _, bucket = self._get_client_and_bucket()
        base_path = (client_folder_path or '').strip('/')
        placeholder = f'{base_path}/{folder_name.strip("/")}/.keep'
        blob = bucket.blob(placeholder)
        blob.upload_from_string('')
        return True


def get_tenant_storage_config(tenant_id: int):
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
