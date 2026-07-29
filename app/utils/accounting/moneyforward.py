"""
マネーフォワード クラウド 連携プロバイダ

- OAuth2（認可コードフロー / リフレッシュ）
- 事業者（オフィス）一覧取得
- 証憑ファイルのアップロード（multipart/form-data）

【重要】マネーフォワードのAPIはパートナー審査制で、利用するプロダクト・契約
プランによってエンドポイントやフィールド名が異なる。そのため MF 固有のパスは
環境変数で上書き可能にし、既定値はクラウド共通基盤の一般的な値を用いている。
本番接続時は自社のMFパートナーAPIドキュメントで各パスを必ず確認すること。

環境変数:
  MF_CLIENT_ID       : MFアプリのClient ID（必須）
  MF_CLIENT_SECRET   : MFアプリのClient Secret（必須）
  MF_REDIRECT_URI    : 登録済みリダイレクトURI（必須）
  MF_SCOPE           : OAuthスコープ（既定: 'office:read receipt:write'）
  MF_AUTH_BASE       : 認可/トークンのベースURL（既定: https://api.biz.moneyforward.com）
  MF_API_BASE        : APIベースURL（既定: https://api.biz.moneyforward.com）
  MF_OFFICE_PATH     : 事業者一覧のパス（既定: /api/v1/offices）
  MF_UPLOAD_PATH     : 証憑アップロードのパス（既定: /api/v1/receipts）
  MF_UPLOAD_FILE_FIELD : アップロード時のファイルフィールド名（既定: 'file'）
"""
import os
import mimetypes
from io import BytesIO
import requests

from .base import AccountingProvider, AccountingError

TIMEOUT = 60


class MoneyForwardProvider(AccountingProvider):
    name = 'moneyforward'

    def __init__(self):
        from .app_config import get_app_config
        c = get_app_config('moneyforward')
        self.client_id = c['client_id']
        self.client_secret = c['client_secret']
        self.redirect_uri = c['redirect_uri']
        self.scope = os.environ.get('MF_SCOPE', 'office:read receipt:write')
        self.auth_base = os.environ.get('MF_AUTH_BASE', 'https://api.biz.moneyforward.com').rstrip('/')
        self.api_base = os.environ.get('MF_API_BASE', 'https://api.biz.moneyforward.com').rstrip('/')
        self.office_path = os.environ.get('MF_OFFICE_PATH', '/api/v1/offices')
        self.upload_path = os.environ.get('MF_UPLOAD_PATH', '/api/v1/receipts')
        self.file_field = os.environ.get('MF_UPLOAD_FILE_FIELD', 'file')

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    # ------- OAuth2 -------
    def authorize_url(self, state: str) -> str:
        from urllib.parse import urlencode
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': self.scope,
            'state': state,
        }
        return f'{self.auth_base}/authorize?{urlencode(params)}'

    def _token_request(self, data: dict) -> dict:
        data.update({
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
        })
        resp = requests.post(f'{self.auth_base}/token', data=data, timeout=TIMEOUT)
        if resp.status_code >= 400:
            raise AccountingError(f'MFトークン取得エラー ({resp.status_code}): {resp.text[:200]}')
        j = resp.json()
        return {
            'access_token': j.get('access_token'),
            'refresh_token': j.get('refresh_token'),
            'expires_in': j.get('expires_in'),
        }

    def exchange_code(self, code: str) -> dict:
        return self._token_request({'grant_type': 'authorization_code', 'code': code})

    def refresh(self, refresh_token: str) -> dict:
        return self._token_request({'grant_type': 'refresh_token',
                                    'refresh_token': refresh_token})

    # ------- API -------
    def _headers(self, access_token: str):
        return {'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'}

    def list_companies(self, access_token: str) -> list:
        """事業者（オフィス）一覧。取得できない場合は空を返し、UIでの手動入力に委ねる。"""
        try:
            resp = requests.get(f'{self.api_base}{self.office_path}',
                                headers=self._headers(access_token), timeout=TIMEOUT)
        except Exception:
            return []
        if resp.status_code == 401:
            raise AccountingError('MF認証に失敗しました（トークンを確認してください）')
        if resp.status_code >= 400:
            # オフィスAPIが未提供/権限外の場合は手動入力にフォールバック
            return []
        body = resp.json() if resp.content else {}
        # レスポンス構造の揺れに対応（offices / data / 直接リスト）
        offices = body.get('offices') or body.get('data') or (body if isinstance(body, list) else [])
        result = []
        for o in offices:
            oid = o.get('id') or o.get('office_id')
            oname = o.get('name') or o.get('office_name') or str(oid)
            if oid is not None:
                result.append({'id': str(oid), 'name': oname})
        return result

    def upload_receipt(self, access_token: str, company_id: str,
                       file_bytes: bytes, filename: str,
                       description: str = None,
                       document_type: str = 'other') -> dict:
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        data = {}
        if company_id:
            data['office_id'] = str(company_id)
        if description:
            data['memo'] = description[:255]
        files = {self.file_field: (filename, BytesIO(file_bytes), mime)}
        resp = requests.post(f'{self.api_base}{self.upload_path}',
                            headers=self._headers(access_token),
                            data=data, files=files, timeout=TIMEOUT)
        if resp.status_code == 401:
            raise AccountingError('MF認証に失敗しました（トークンを確認してください）')
        if resp.status_code >= 400:
            raise AccountingError(f'MFアップロードエラー ({resp.status_code}): {resp.text[:300]}')
        body = resp.json() if resp.content else {}
        # ID位置の揺れに対応
        ext = (body.get('id') or (body.get('receipt') or {}).get('id')
               or (body.get('data') or {}).get('id'))
        return {'external_id': str(ext) if ext else None}
