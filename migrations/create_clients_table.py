"""
T_顧問先テーブル作成マイグレーション
"""
import os
import psycopg2
from urllib.parse import urlparse

def run_migration():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL環境変数が設定されていません")
        return False
    
    # Heroku PostgreSQLのURLを修正（postgres:// → postgresql://）
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # T_顧問先テーブルを作成
        cur.execute("""
            CREATE TABLE IF NOT EXISTS "T_顧問先" (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES "T_テナント"(id) ON DELETE CASCADE,
                type VARCHAR(50),
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                phone VARCHAR(50),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # インデックスを作成
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_tenant_id ON "T_顧問先"(tenant_id)
        """)
        
        conn.commit()
        print("✅ T_顧問先テーブルを作成しました")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ マイグレーションエラー: {e}")
        return False


if __name__ == '__main__':
    run_migration()
