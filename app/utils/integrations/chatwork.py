"""
ChatWork API クライアント（最小実装）

APIリファレンス: https://developer.chatwork.com/reference
認証: HTTPヘッダ  X-ChatWorkToken: <api_token>
"""
import requests

API_BASE = 'https://api.chatwork.com/v2'
TIMEOUT = 30


class ChatworkError(RuntimeError):
    """ChatWork API 呼び出しエラー"""
    pass


class ChatworkClient:
    def __init__(self, api_token: str):
        if not api_token:
            raise ChatworkError('ChatWork APIトークンが未設定です')
        self.token = api_token.strip()

    @property
    def _headers(self):
        return {'X-ChatWorkToken': self.token}

    def _get(self, path: str, params: dict = None):
        resp = requests.get(f'{API_BASE}{path}', headers=self._headers,
                            params=params or {}, timeout=TIMEOUT)
        if resp.status_code == 401:
            raise ChatworkError('ChatWork認証に失敗しました（トークンを確認してください）')
        if resp.status_code >= 400:
            raise ChatworkError(f'ChatWork APIエラー ({resp.status_code}): {resp.text[:200]}')
        return resp.json()

    def get_me(self) -> dict:
        """トークンの疎通確認（自分の情報を取得）"""
        return self._get('/me')

    def list_rooms(self) -> list:
        """参加中のルーム一覧を取得"""
        return self._get('/rooms')

    def list_files(self, room_id, account_id=None) -> list:
        """ルーム内のアップロードファイル一覧を取得"""
        params = {}
        if account_id:
            params['account_id'] = account_id
        return self._get(f'/rooms/{room_id}/files', params=params)

    def get_file_download_url(self, room_id, file_id) -> dict:
        """ファイルのダウンロードURL（一時URL）付き詳細を取得"""
        return self._get(f'/rooms/{room_id}/files/{file_id}',
                        params={'create_download_url': 1})

    def download_file_bytes(self, download_url: str) -> bytes:
        """一時ダウンロードURLからファイル本体を取得"""
        resp = requests.get(download_url, timeout=TIMEOUT)
        if resp.status_code >= 400:
            raise ChatworkError(f'ファイルのダウンロードに失敗しました ({resp.status_code})')
        return resp.content
