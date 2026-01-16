"""
外部ストレージ連携ユーティリティ

AWS S3およびS3互換ストレージ（MinIO、Wasabi、Backblaze B2など）との連携を提供します。
"""

import os
import boto3
from botocore.exceptions import ClientError
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid


class StorageManager:
    """外部ストレージ管理クラス"""
    
    def __init__(self):
        """
        環境変数から設定を読み込む
        
        必要な環境変数:
        - AWS_ACCESS_KEY_ID: アクセスキーID
        - AWS_SECRET_ACCESS_KEY: シークレットアクセスキー
        - AWS_S3_BUCKET_NAME: バケット名
        - AWS_S3_REGION: リージョン（デフォルト: ap-northeast-1）
        - AWS_S3_ENDPOINT_URL: カスタムエンドポイント（S3互換ストレージ用、オプション）
        """
        self.bucket_name = os.environ.get('AWS_S3_BUCKET_NAME')
        self.region = os.environ.get('AWS_S3_REGION', 'ap-northeast-1')
        self.endpoint_url = os.environ.get('AWS_S3_ENDPOINT_URL')
        
        # S3クライアントの初期化
        self.s3_client = None
        if self.bucket_name:
            try:
                self.s3_client = boto3.client(
                    's3',
                    region_name=self.region,
                    endpoint_url=self.endpoint_url if self.endpoint_url else None
                )
            except Exception as e:
                print(f"S3クライアントの初期化に失敗しました: {e}")
    
    def is_enabled(self):
        """ストレージ連携が有効かどうかを確認"""
        return self.s3_client is not None and self.bucket_name is not None
    
    def upload_file(self, file_obj, original_filename, folder='uploads'):
        """
        ファイルをS3にアップロードする
        
        Args:
            file_obj: Flaskのファイルオブジェクト
            original_filename: 元のファイル名
            folder: S3内のフォルダ名（デフォルト: uploads）
        
        Returns:
            dict: {
                'success': bool,
                'url': str (成功時のファイルURL),
                'key': str (S3オブジェクトキー),
                'error': str (失敗時のエラーメッセージ)
            }
        """
        if not self.is_enabled():
            return {
                'success': False,
                'error': 'ストレージ連携が設定されていません'
            }
        
        try:
            # 安全なファイル名を生成
            filename = secure_filename(original_filename)
            
            # ユニークなファイル名を生成（重複を避けるため）
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = str(uuid.uuid4())[:8]
            unique_filename = f"{timestamp}_{unique_id}_{filename}"
            
            # S3オブジェクトキー
            s3_key = f"{folder}/{unique_filename}"
            
            # ファイルをS3にアップロード
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': file_obj.content_type or 'application/octet-stream',
                    'ContentDisposition': f'inline; filename="{filename}"'
                }
            )
            
            # ファイルURLを生成
            if self.endpoint_url:
                # カスタムエンドポイントの場合
                file_url = f"{self.endpoint_url}/{self.bucket_name}/{s3_key}"
            else:
                # AWS S3の場合
                file_url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            
            return {
                'success': True,
                'url': file_url,
                'key': s3_key,
                'original_filename': filename
            }
        
        except ClientError as e:
            return {
                'success': False,
                'error': f'S3アップロードエラー: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'アップロードエラー: {str(e)}'
            }
    
    def delete_file(self, s3_key):
        """
        S3からファイルを削除する
        
        Args:
            s3_key: S3オブジェクトキー
        
        Returns:
            dict: {
                'success': bool,
                'error': str (失敗時のエラーメッセージ)
            }
        """
        if not self.is_enabled():
            return {
                'success': False,
                'error': 'ストレージ連携が設定されていません'
            }
        
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return {'success': True}
        
        except ClientError as e:
            return {
                'success': False,
                'error': f'S3削除エラー: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'削除エラー: {str(e)}'
            }
    
    def generate_presigned_url(self, s3_key, expiration=3600):
        """
        署名付きURLを生成する（一時的なアクセス用）
        
        Args:
            s3_key: S3オブジェクトキー
            expiration: URL有効期限（秒、デフォルト: 3600秒=1時間）
        
        Returns:
            str: 署名付きURL、またはNone（失敗時）
        """
        if not self.is_enabled():
            return None
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            print(f"署名付きURL生成エラー: {e}")
            return None


# グローバルインスタンス
storage_manager = StorageManager()
