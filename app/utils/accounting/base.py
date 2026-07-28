"""
会計ソフト連携プロバイダの抽象基底クラス

freee / マネーフォワード 等を同一インターフェースで扱うための抽象化層。
新しい会計ソフトを追加する場合は本クラスを継承して実装する。
"""


class AccountingError(RuntimeError):
    """会計ソフト連携エラー"""
    pass


class AccountingProvider:
    """会計ソフト連携プロバイダの基底クラス"""

    name = 'base'

    def is_configured(self) -> bool:
        """アプリ側の連携設定（client_id/secret 等）が揃っているか"""
        raise NotImplementedError

    def authorize_url(self, state: str) -> str:
        """OAuth認可画面のURLを返す"""
        raise NotImplementedError

    def exchange_code(self, code: str) -> dict:
        """認可コードをトークンに交換
        Returns: {'access_token', 'refresh_token', 'expires_in'}
        """
        raise NotImplementedError

    def refresh(self, refresh_token: str) -> dict:
        """リフレッシュトークンでアクセストークンを更新
        Returns: {'access_token', 'refresh_token', 'expires_in'}
        """
        raise NotImplementedError

    def list_companies(self, access_token: str) -> list:
        """接続先の事業所一覧を返す
        Returns: [{'id': str, 'name': str}, ...]
        """
        raise NotImplementedError

    def upload_receipt(self, access_token: str, company_id: str,
                       file_bytes: bytes, filename: str,
                       description: str = None,
                       document_type: str = 'other') -> dict:
        """証憑ファイルをアップロード
        Returns: {'external_id': str}
        """
        raise NotImplementedError
