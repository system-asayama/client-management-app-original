"""
会計ソフトOAuthアプリ認証情報のローダー（3階層）

優先順位（下にいくほど優先）:
  1. 環境変数（FREEE_*/MF_*）… デプロイ時の既定値
  2. プラットフォーム共通設定（tenant_id=0 / システム管理者が画面で設定）
  3. テナント設定（各事務所が画面で設定）

会計ソフトは各テナント（税理士事務所）が契約するのが基本だが、プラットフォーム
運営者が共有のOAuthアプリを提供したい場合はプラットフォーム共通設定を使う。
"""
import os

# プラットフォーム共通設定を表す擬似テナントID（実在しないID）
PLATFORM_TENANT_ID = 0

_ENV_KEYS = {
    'freee': ('FREEE_CLIENT_ID', 'FREEE_CLIENT_SECRET', 'FREEE_REDIRECT_URI'),
    'moneyforward': ('MF_CLIENT_ID', 'MF_CLIENT_SECRET', 'MF_REDIRECT_URI'),
}


def _apply_row(cfg: dict, row) -> str:
    """DB行の値でcfgを上書き（値が入っている項目のみ）。上書きした場合の出所を返す"""
    applied = False
    if row:
        if row.client_id:
            cfg['client_id'] = row.client_id
            applied = True
        if row.client_secret:
            cfg['client_secret'] = row.client_secret
            applied = True
        if row.redirect_uri:
            cfg['redirect_uri'] = row.redirect_uri
            applied = True
    return applied


def get_app_config(provider: str, tenant_id: int = None) -> dict:
    """プロバイダのOAuthアプリ認証情報を返す（環境変数→共通→テナント）
    Returns: {'client_id', 'client_secret', 'redirect_uri', 'source'}
      source: 'tenant' / 'platform' / 'env' / '' （client_idの実効出所）
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
    source = 'env' if cfg['client_id'] else ''

    try:
        from app.db import SessionLocal
        from app.models_accounting import TAccountingAppConfig
        db = SessionLocal()
        try:
            # プラットフォーム共通（tenant_id=0）
            plat = (db.query(TAccountingAppConfig)
                      .filter(TAccountingAppConfig.tenant_id == PLATFORM_TENANT_ID,
                              TAccountingAppConfig.provider == provider).first())
            if _apply_row(cfg, plat):
                source = 'platform'
            # テナント設定（最優先）
            if tenant_id:
                row = (db.query(TAccountingAppConfig)
                         .filter(TAccountingAppConfig.tenant_id == tenant_id,
                                 TAccountingAppConfig.provider == provider).first())
                if _apply_row(cfg, row):
                    source = 'tenant'
        finally:
            db.close()
    except Exception:
        pass

    cfg['source'] = source
    return cfg
