"""
既存のT_テナントレコードのupdated_atにcreated_atの値を設定
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
UPDATE "T_テナント" 
SET updated_at = created_at 
WHERE updated_at IS NULL;
"""

try:
    with engine.connect() as conn:
        result = conn.execute(text(migration_sql))
        conn.commit()
        print(f"✓ マイグレーション成功: {result.rowcount}件のレコードを更新しました")
except Exception as e:
    print(f"✗ マイグレーション失敗: {e}")
    exit(1)
