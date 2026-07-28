"""会計ソフト連携プロバイダのファクトリ"""
from .base import AccountingProvider, AccountingError
from .freee import FreeeProvider


def get_provider(name: str) -> AccountingProvider:
    """プロバイダ名からインスタンスを返す"""
    name = (name or 'freee').strip().lower()
    if name == 'freee':
        return FreeeProvider()
    # マネーフォワード等は今後追加（抽象化層は準備済み）
    raise AccountingError(f'未対応の会計ソフトです: {name}')


SUPPORTED_PROVIDERS = ['freee']  # 'moneyforward' は今後追加
