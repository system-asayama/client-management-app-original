"""
会計ソフトOAuthアプリ認証情報のローダー（2階層・すべて画面から設定）

優先順位（下にいくほど優先）:
  1. プラットフォーム共通設定（tenant_id=0 / システム管理者が画面で設定）
  2. テナント設定（各事務所が画面で設定）

会計ソフトは各テナント（税理士事務所）が契約するのが基本。プラットフォーム
運営者が共有のOAuthアプリを提供したい場合は共通設定を使う。いずれも画面から
設定でき、環境変数は不要。
"""

# プラットフォーム共通設定を表す擬似テナントID（実在しないID）
PLATFORM_TENANT_ID = 0


def _apply_row(cfg: dict, row) -> bool:
    """DB行の値でcfgを上書き（値が入っている項目のみ）。上書きした場合Trueを返す"""
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
    """プロバイダのOAuthアプリ認証情報を返す（共通→テナント）
    Returns: {'client_id', 'client_secret', 'redirect_uri', 'source'}
      source: 'tenant' / 'platform' / '' （client_idの実効出所）
    """
    provider = (provider or '').strip().lower()
    if provider in ('mf', 'money_forward'):
        provider = 'moneyforward'
    cfg = {'client_id': '', 'client_secret': '', 'redirect_uri': ''}
    source = ''

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
