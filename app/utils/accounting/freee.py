"""
freee会計 連携プロバイダ

- OAuth2（認可コードフロー / リフレッシュ）
- 事業所一覧取得
- ファイルボックス（証憑）アップロード： POST /api/1/receipts （multipart/form-data）

アプリ登録情報は環境変数から取得:
  FREEE_CLIENT_ID       : freeeアプリのClient ID
  FREEE_CLIENT_SECRET   : freeeアプリのClient Secret
  FREEE_REDIRECT_URI    : 登録済みリダイレクトURI
"""
import os
import mimetypes
from io import BytesIO
import requests

from .base import AccountingProvider, AccountingError

ACCOUNTS_BASE = 'https://accounts.secure.freee.co.jp'
API_BASE = 'https://api.freee.co.jp'
TIMEOUT = 60


class FreeeProvider(AccountingProvider):
    name = 'freee'

    def __init__(self, tenant_id=None):
        from .app_config import get_app_config
        self.tenant_id = tenant_id
        c = get_app_config('freee', tenant_id)
        self.client_id = c['client_id']
        self.client_secret = c['client_secret']
        self.redirect_uri = c['redirect_uri']

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    # ------- OAuth2 -------
    def authorize_url(self, state: str) -> str:
        from urllib.parse import urlencode
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'state': state,
        }
        return f'{ACCOUNTS_BASE}/public_api/authorize?{urlencode(params)}'

    def _token_request(self, data: dict) -> dict:
        data.update({
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
        })
        resp = requests.post(f'{ACCOUNTS_BASE}/public_api/token',
                            data=data, timeout=TIMEOUT)
        if resp.status_code >= 400:
            raise AccountingError(f'freeeトークン取得エラー ({resp.status_code}): {resp.text[:200]}')
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
        resp = requests.get(f'{API_BASE}/api/1/companies',
                            headers=self._headers(access_token), timeout=TIMEOUT)
        if resp.status_code == 401:
            raise AccountingError('freee認証に失敗しました（トークンを確認してください）')
        if resp.status_code >= 400:
            raise AccountingError(f'freee事業所取得エラー ({resp.status_code}): {resp.text[:200]}')
        companies = resp.json().get('companies', [])
        return [{'id': str(c.get('id')),
                 'name': c.get('display_name') or c.get('name')}
                for c in companies]

    def upload_receipt(self, access_token: str, company_id: str,
                       file_bytes: bytes, filename: str,
                       description: str = None,
                       document_type: str = 'other') -> dict:
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        data = {'company_id': str(company_id)}
        if description:
            data['description'] = description[:255]
        if document_type:
            data['document_type'] = document_type
        files = {'receipt': (filename, BytesIO(file_bytes), mime)}
        resp = requests.post(f'{API_BASE}/api/1/receipts',
                            headers=self._headers(access_token),
                            data=data, files=files, timeout=TIMEOUT)
        if resp.status_code == 401:
            raise AccountingError('freee認証に失敗しました（トークンを確認してください）')
        if resp.status_code >= 400:
            raise AccountingError(f'freeeアップロードエラー ({resp.status_code}): {resp.text[:300]}')
        receipt = (resp.json() or {}).get('receipt', {})
        return {'external_id': str(receipt.get('id')) if receipt.get('id') else None}
