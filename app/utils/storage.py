"""
マルチストレージ連携ユーティリティ

以下のストレージサービスに対応:
- AWS S3
- Google Cloud Storage (GCS)
- Cloudflare R2
- Wasabi
- Backblaze B2
- Dropbox
- ローカルストレージ（開発・テスト用）
"""

import os
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid


class BaseStorage:
    """ストレージ基底クラス"""
    
    def upload_file(self, file_obj, original_filename, folder='uploads'):
        """
        ファイルをアップロードする
        
        Args:
            file_obj: Flaskのファイルオブジェクト
            original_filename: 元のファイル名
            folder: フォルダ名
        
        Returns:
            dict: {
                'success': bool,
                'url': str,
                'key': str,
                'original_filename': str,
                'error': str
            }
        """
        raise NotImplementedError
    
    def delete_file(self, key):
        """ファイルを削除する"""
        raise NotImplementedError
    
    def is_enabled(self):
        """ストレージが有効かどうか"""
        raise NotImplementedError


class S3Storage(BaseStorage):
    """S3およびS3互換ストレージ（GCS、R2、Wasabi、Backblaze B2など）"""
    
    def __init__(self):
        self.bucket_name = os.environ.get('AWS_S3_BUCKET_NAME')
        self.region = os.environ.get('AWS_S3_REGION', 'ap-northeast-1')
        self.endpoint_url = os.environ.get('AWS_S3_ENDPOINT_URL')
        
        self.s3_client = None
        if self.bucket_name:
            try:
                import boto3
                self.s3_client = boto3.client(
                    's3',
                    region_name=self.region,
                    endpoint_url=self.endpoint_url if self.endpoint_url else None
                )
            except Exception as e:
                print(f"S3クライアントの初期化に失敗しました: {e}")
    
    def is_enabled(self):
        return self.s3_client is not None and self.bucket_name is not None
    
    def upload_file(self, file_obj, original_filename, folder='uploads'):
        if not self.is_enabled():
            return {'success': False, 'error': 'S3が設定されていません'}
        
        try:
            from botocore.exceptions import ClientError
            
            filename = secure_filename(original_filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = str(uuid.uuid4())[:8]
            unique_filename = f"{timestamp}_{unique_id}_{filename}"
            s3_key = f"{folder}/{unique_filename}"
            
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': file_obj.content_type or 'application/octet-stream',
                    'ContentDisposition': f'inline; filename="{filename}"'
                }
            )
            
            if self.endpoint_url:
                file_url = f"{self.endpoint_url}/{self.bucket_name}/{s3_key}"
            else:
                file_url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            
            return {
                'success': True,
                'url': file_url,
                'key': s3_key,
                'original_filename': filename
            }
        except Exception as e:
            return {'success': False, 'error': f'S3アップロードエラー: {str(e)}'}
    
    def delete_file(self, s3_key):
        if not self.is_enabled():
            return {'success': False, 'error': 'S3が設定されていません'}
        
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': f'S3削除エラー: {str(e)}'}


class DropboxStorage(BaseStorage):
    """Dropboxストレージ"""
    
    def __init__(self):
        self.access_token = os.environ.get('DROPBOX_ACCESS_TOKEN')
        self.dbx = None
        
        if self.access_token:
            try:
                import dropbox
                self.dbx = dropbox.Dropbox(self.access_token)
                # 接続テスト
                self.dbx.users_get_current_account()
            except Exception as e:
                print(f"Dropboxクライアントの初期化に失敗しました: {e}")
                self.dbx = None
    
    def is_enabled(self):
        return self.dbx is not None
    
    def upload_file(self, file_obj, original_filename, folder='uploads'):
        if not self.is_enabled():
            return {'success': False, 'error': 'Dropboxが設定されていません'}
        
        try:
            import dropbox
            
            filename = secure_filename(original_filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = str(uuid.uuid4())[:8]
            unique_filename = f"{timestamp}_{unique_id}_{filename}"
            dropbox_path = f"/{folder}/{unique_filename}"
            
            # ファイルをアップロード
            file_obj.seek(0)
            self.dbx.files_upload(
                file_obj.read(),
                dropbox_path,
                mode=dropbox.files.WriteMode.add
            )
            
            # 共有リンクを作成
            try:
                shared_link = self.dbx.sharing_create_shared_link(dropbox_path)
                file_url = shared_link.url.replace('?dl=0', '?raw=1')
            except dropbox.exceptions.ApiError as e:
                # 既に共有リンクが存在する場合
                links = self.dbx.sharing_list_shared_links(path=dropbox_path).links
                if links:
                    file_url = links[0].url.replace('?dl=0', '?raw=1')
                else:
                    raise e
            
            return {
                'success': True,
                'url': file_url,
                'key': dropbox_path,
                'original_filename': filename
            }
        except Exception as e:
            return {'success': False, 'error': f'Dropboxアップロードエラー: {str(e)}'}
    
    def delete_file(self, dropbox_path):
        if not self.is_enabled():
            return {'success': False, 'error': 'Dropboxが設定されていません'}
        
        try:
            self.dbx.files_delete_v2(dropbox_path)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': f'Dropbox削除エラー: {str(e)}'}


class LocalStorage(BaseStorage):
    """ローカルストレージ（開発・テスト用、Herokuでは非推奨）"""
    
    def __init__(self):
        self.upload_folder = os.environ.get('LOCAL_UPLOAD_FOLDER', '/tmp/uploads')
        os.makedirs(self.upload_folder, exist_ok=True)
    
    def is_enabled(self):
        return True
    
    def upload_file(self, file_obj, original_filename, folder='uploads'):
        try:
            filename = secure_filename(original_filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = str(uuid.uuid4())[:8]
            unique_filename = f"{timestamp}_{unique_id}_{filename}"
            
            folder_path = os.path.join(self.upload_folder, folder)
            os.makedirs(folder_path, exist_ok=True)
            
            filepath = os.path.join(folder_path, unique_filename)
            file_obj.save(filepath)
            
            # ローカルファイルパスをURLとして返す（実際のURLではない）
            file_url = f"/uploads/{folder}/{unique_filename}"
            
            return {
                'success': True,
                'url': file_url,
                'key': filepath,
                'original_filename': filename
            }
        except Exception as e:
            return {'success': False, 'error': f'ローカル保存エラー: {str(e)}'}
    
    def delete_file(self, filepath):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': f'ローカル削除エラー: {str(e)}'}


class StorageManager:
    """ストレージマネージャー（自動選択）"""
    
    def __init__(self):
        """
        環境変数STORAGE_TYPEに基づいてストレージを選択
        
        STORAGE_TYPE:
        - 's3' または 'aws': AWS S3
        - 'gcs': Google Cloud Storage
        - 'r2': Cloudflare R2
        - 'wasabi': Wasabi
        - 'backblaze': Backblaze B2
        - 'dropbox': Dropbox
        - 'local': ローカルストレージ
        - 未設定: 自動検出（S3 → Dropbox → ローカル）
        """
        storage_type = os.environ.get('STORAGE_TYPE', '').lower()
        
        if storage_type in ['s3', 'aws', 'gcs', 'r2', 'wasabi', 'backblaze', '']:
            # S3互換ストレージを試行
            self.storage = S3Storage()
            if not self.storage.is_enabled() and storage_type == '':
                # S3が無効な場合、Dropboxを試行
                self.storage = DropboxStorage()
                if not self.storage.is_enabled():
                    # Dropboxも無効な場合、ローカルストレージにフォールバック
                    self.storage = LocalStorage()
                    print("⚠️  外部ストレージが設定されていません。ローカルストレージを使用します（Herokuでは非推奨）")
        elif storage_type == 'dropbox':
            self.storage = DropboxStorage()
        elif storage_type == 'local':
            self.storage = LocalStorage()
        else:
            raise ValueError(f"不明なSTORAGE_TYPE: {storage_type}")
    
    def is_enabled(self):
        return self.storage.is_enabled()
    
    def upload_file(self, file_obj, original_filename, folder='uploads'):
        return self.storage.upload_file(file_obj, original_filename, folder)
    
    def delete_file(self, key):
        return self.storage.delete_file(key)
    
    def get_storage_type(self):
        """現在使用中のストレージタイプを返す"""
        return self.storage.__class__.__name__


# グローバルインスタンス
storage_manager = StorageManager()
