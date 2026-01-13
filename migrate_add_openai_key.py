#!/usr/bin/env python3
"""
マイグレーション: T_管理者テーブルにopenai_api_keyカラムを追加
"""

import os
import sys
from urllib.parse import urlparse

try:
    import psycopg2
except ImportError:
    print("❌ psycopg2がインストールされていません")
    sys.exit(1)

def main():
    print("🔄 マイグレーション開始: T_管理者テーブルにopenai_api_keyカラムを追加")
    
    # DATABASE_URLを取得
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL環境変数が設定されていません")
        sys.exit(1)
    
    # PostgreSQLに接続
    try:
        url = urlparse(db_url)
        conn = psycopg2.connect(
            dbname=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port,
            sslmode="require",
            application_name="migration"
        )
        conn.autocommit = True
        print(f"✅ PostgreSQL 接続成功")
    except Exception as e:
        print(f"❌ PostgreSQL接続失敗: {e}")
        sys.exit(1)
    
    cur = conn.cursor()
    
    try:
        # openai_api_keyカラムが存在するか確認
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'T_管理者' AND column_name = 'openai_api_key'
        """)
        
        if cur.fetchone():
            print("ℹ️ openai_api_keyカラムは既に存在します")
        else:
            # openai_api_keyカラムを追加
            print("📝 openai_api_keyカラムを追加中...")
            cur.execute('''
                ALTER TABLE "T_管理者" 
                ADD COLUMN openai_api_key TEXT
            ''')
            print("✅ openai_api_keyカラムを追加しました")
        
        print("✅ マイグレーション完了")
        
    except Exception as e:
        print(f"❌ マイグレーション失敗: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
