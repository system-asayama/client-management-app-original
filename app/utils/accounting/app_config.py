"""
会計ソフトOAuthアプリ認証情報のローダー

優先順位: DB（T_会計ソフトアプリ設定）→ 環境変数
画面から設定した値をDBに保存し、未設定項目は環境変数にフォールバックする。
"""
import os

_ENV_KEYS = {
    'freee': ('FREEE_CLIENT_ID', 'FREEE_CLIENT_SECRET', 'FREEE_REDIRECT_URI'),
    'moneyforward': ('MF_CLIENT_ID', 'MF_CLIENT_SECRET', 'MF_REDIRECT_URI'),
}


def get_app_config(provider: str) -> dict:
    """プロバイダのOAuthアプリ認証情報を返す
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
    # DBの設定で上書き（値が入っている項目のみ）
    try:
        from app.db import SessionLocal
        from app.models_accounting import TAccountingAppConfig
        db = SessionLocal()
        try:
            row = (db.query(TAccountingAppConfig)
                     .filter(TAccountingAppConfig.provider == provider).first())
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
        # テーブル未作成時などは環境変数の値のまま
        pass
    return cfg
