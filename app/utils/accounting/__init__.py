"""会計ソフト連携プロバイダのファクトリ"""
from .base import AccountingProvider, AccountingError
from .freee import FreeeProvider
from .moneyforward import MoneyForwardProvider


# 対応プロバイダ（表示順）
SUPPORTED_PROVIDERS = ['freee', 'moneyforward']

PROVIDER_LABELS = {
    'freee': 'freee',
    'moneyforward': 'マネーフォワード',
}


def get_provider(name: str, tenant_id: int = None) -> AccountingProvider:
    """プロバイダ名からインスタンスを返す（テナントの認証情報を読み込む）"""
    name = (name or 'freee').strip().lower()
    if name == 'freee':
        return FreeeProvider(tenant_id=tenant_id)
    if name in ('moneyforward', 'mf', 'money_forward'):
        return MoneyForwardProvider(tenant_id=tenant_id)
    raise AccountingError(f'未対応の会計ソフトです: {name}')


def provider_label(name: str) -> str:
    return PROVIDER_LABELS.get((name or '').strip().lower(), name or '')
