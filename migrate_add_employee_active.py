#!/usr/bin/env python3
"""
T_従業員テーブルにactiveカラムを追加するマイグレーションスクリプト
"""

import os
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.db import get_db_connection, _is_pg, _sql


def migrate():
    """マイグレーション実行"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # activeカラムが存在するか確認
        if _is_pg(conn):
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'T_従業員' AND column_name = 'active'
            """)
        else:
            cur.execute("PRAGMA table_info(\"T_従業員\")")
            columns = [row[1] for row in cur.fetchall()]
            if 'active' in columns:
                print("✅ activeカラムは既に存在します")
                conn.close()
                return
        
        if _is_pg(conn):
            if cur.fetchone():
                print("✅ activeカラムは既に存在します")
                conn.close()
                return
        
        # activeカラムを追加
        print("🔄 T_従業員テーブルにactiveカラムを追加しています...")
        cur.execute(_sql(conn, 'ALTER TABLE "T_従業員" ADD COLUMN active INTEGER DEFAULT 1'))
        
        # 既存のレコードをすべて有効にする
        cur.execute(_sql(conn, 'UPDATE "T_従業員" SET active = 1 WHERE active IS NULL'))
        
        conn.commit()
        print("✅ マイグレーション完了: activeカラムを追加しました")
        
    except Exception as e:
        print(f"❌ マイグレーションエラー: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()
