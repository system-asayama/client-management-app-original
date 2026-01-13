"""
T_テナントテーブルにopenai_api_keyカラムを追加するマイグレーション
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
ADD COLUMN IF NOT EXISTS openai_api_key VARCHAR(255);
"""

try:
    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()
    print("✓ マイグレーション成功: T_テナントテーブルにopenai_api_keyカラムを追加しました")
except Exception as e:
    print(f"✗ マイグレーション失敗: {e}")
    exit(1)
