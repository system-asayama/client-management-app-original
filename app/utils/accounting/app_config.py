"""
会計ソフトOAuthアプリ認証情報のローダー（テナント単位）

会計ソフトは各テナント（税理士事務所）が契約するため、認証情報はテナント単位。
優先順位: テナント設定（T_テナント会計ソフトアプリ設定）→ 環境変数（プラットフォーム共通）
"""
import os

_ENV_KEYS = {
    'freee': ('FREEE_CLIENT_ID', 'FREEE_CLIENT_SECRET', 'FREEE_REDIRECT_URI'),
    'moneyforward': ('MF_CLIENT_ID', 'MF_CLIENT_SECRET', 'MF_REDIRECT_URI'),
}


def get_app_config(provider: str, tenant_id: int = None) -> dict:
    """プロバイダのOAuthアプリ認証情報を返す（テナント設定→環境変数）
    Returns: {'client_id', 'client_secret', 'redirect_uri'}
    """
    provider = (provider or '').strip().lower()
    if provider in ('mf', 'money_forward'):
        provider = 'moneyforward'
    env = _ENV_KEYS.get(provider, ('', '', ''))
    cfg = {
        'client_id': os.environ.get(env[0], '') if env[0] else '',
        'client_secret': os.environ.get(env[1], '') if env[1] else '',
        'redirect_uri': os.environ.get(env[2], '') if env[2] else '',
    }
    # テナント設定で上書き（値が入っている項目のみ）
    if tenant_id:
        try:
            from app.db import SessionLocal
            from app.models_accounting import TAccountingAppConfig
            db = SessionLocal()
            try:
                row = (db.query(TAccountingAppConfig)
                         .filter(TAccountingAppConfig.tenant_id == tenant_id,
                                 TAccountingAppConfig.provider == provider).first())
                if row:
                    if row.client_id:
                        cfg['client_id'] = row.client_id
                    if row.client_secret:
                        cfg['client_secret'] = row.client_secret
                    if row.redirect_uri:
                        cfg['redirect_uri'] = row.redirect_uri
            finally:
                db.close()
        except Exception:
            pass
    return cfg
