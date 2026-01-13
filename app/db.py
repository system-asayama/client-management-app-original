import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# SQLite接続関数（顧問先管理機能用）
import sqlite3

def get_conn():
    """
    SQLiteデータベース接続を取得
    顧問先管理機能で使用
    """
    os.makedirs('database', exist_ok=True)
    conn = sqlite3.connect('database/database.db')
    conn.row_factory = sqlite3.Row
    return conn
