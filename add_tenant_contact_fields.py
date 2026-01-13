"""
T_テナントテーブルに郵便番号、住所、電話番号、emailカラムを追加するマイグレーション
"""
import os
from sqlalchemy import create_engine, text

# DATABASE_URLを取得
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("エラー: DATABASE_URL環境変数が設定されていません")
    exit(1)

# Herokuのpostgresをpostgresqlに変換
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)

# マイグレーションSQL
migration_sql = """
ALTER TABLE "T_テナント" 
ADD COLUMN IF NOT EXISTS 郵便番号 VARCHAR(10),
ADD COLUMN IF NOT EXISTS 住所 VARCHAR(500),
ADD COLUMN IF NOT EXISTS 電話番号 VARCHAR(20),
ADD COLUMN IF NOT EXISTS email VARCHAR(255),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
"""

try:
    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()
    print("✓ マイグレーション成功: T_テナントテーブルにカラムを追加しました")
except Exception as e:
    print(f"✗ マイグレーション失敗: {e}")
    exit(1)
