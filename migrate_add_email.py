#!/usr/bin/env python3
"""
データベースマイグレーション: T_管理者テーブルにemailカラムを追加
"""
import os
import sys

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils import get_db, _sql

def migrate():
    """T_管理者テーブルにemailカラムを追加"""
    print("🔄 マイグレーション開始: T_管理者テーブルにemailカラムを追加")
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # カラムが既に存在するかチェック
        cur.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='T_管理者' AND column_name='email'
        ''')
        
        if cur.fetchone():
            print("✅ emailカラムは既に存在しています")
            conn.close()
            return
        
        # emailカラムを追加
        print("📝 emailカラムを追加中...")
        cur.execute('ALTER TABLE "T_管理者" ADD COLUMN email TEXT')
        conn.commit()
        print("✅ emailカラムを追加しました")
        
    except Exception as e:
        print(f"⚠️ エラーが発生しました: {e}")
        print("📝 別の方法でカラムを追加します...")
        
        try:
            # PostgreSQLの場合、IF NOT EXISTSが使えない場合があるので、
            # エラーを無視してカラムを追加
            cur.execute('ALTER TABLE "T_管理者" ADD COLUMN IF NOT EXISTS email TEXT')
            conn.commit()
            print("✅ emailカラムを追加しました")
        except Exception as e2:
            print(f"❌ カラムの追加に失敗しました: {e2}")
            conn.rollback()
    
    finally:
        conn.close()
    
    print("✅ マイグレーション完了")

if __name__ == "__main__":
    migrate()
