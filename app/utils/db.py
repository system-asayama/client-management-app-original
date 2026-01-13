# -*- coding: utf-8 -*-
"""
データベース接続
"""

import os
import sqlite3
from urllib.parse import urlparse

# ---- psycopg2 の有無 ----
try:
    import psycopg2
except Exception:
    psycopg2 = None


def _is_pg(conn) -> bool:
    """PostgreSQL/SQLite 判定"""
    return conn.__class__.__module__.startswith("psycopg2")


def _sql(conn, text: str) -> str:
    """プレースホルダ統一（PostgreSQL: %s ／ SQLite: ?）"""
    return text if _is_pg(conn) else text.replace("%s", "?")


def get_db_connection():
    """
    データベース接続を返す（get_dbのエイリアス）
    """
    return get_db()


def get_db():
    """
    優先順位：
      1) .env/環境変数の DATABASE_URL
      2) ローカル Postgres accounting_dev (postgres / n-N31415926!!)
      3) SQLite
    戻り値: DB接続オブジェクト
    
    注意: テーブル作成はSQLAlchemy (app/db.py) のBase.metadata.create_all()で行われます
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        db_url = "postgresql://postgres:n-N31415926!!@localhost:5432/accounting_dev"

    # --- Try PostgreSQL ---
    if psycopg2:
        try:
            url = urlparse(db_url)
            sslmode = "disable" if (url.hostname in ("localhost", "127.0.0.1")) else "require"
            conn = psycopg2.connect(
                dbname=url.path[1:],
                user=url.username,
                password=url.password,
                host=url.hostname,
                port=url.port,
                sslmode=sslmode,
                application_name="login_system"
            )
            conn.autocommit = True
            print(f"✅ PostgreSQL 接続成功: {url.hostname}:{url.port}/{url.path[1:]}")
            return conn
        except Exception as e:
            print(f"⚠️ PostgreSQL接続失敗 → SQLiteへフォールバック: {e}")

    # --- SQLite フォールバック ---
    os.makedirs("database", exist_ok=True)
    conn = sqlite3.connect("database/login_auth.db", detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    print("⚠️ SQLite にフォールバック: database/login_auth.db")
    return conn
