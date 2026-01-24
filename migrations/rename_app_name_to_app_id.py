"""
マイグレーション: app_name を app_id にリネーム (PostgreSQL版)
実行日: 2026-01-24
"""

from app.db import SessionLocal
from sqlalchemy import text

def migrate():
    """T_テナントアプリ設定とT_店舗アプリ設定のapp_nameをapp_idにリネーム"""
    db = SessionLocal()
    
    try:
        print("=== Starting migration: rename app_name to app_id ===")
        
        # T_テナントアプリ設定のカラムをリネーム
        print("Renaming column in T_テナントアプリ設定...")
        try:
            db.execute(text("""
                ALTER TABLE "T_テナントアプリ設定" 
                RENAME COLUMN "app_name" TO "app_id"
            """))
            print("✓ T_テナントアプリ設定.app_name → app_id")
        except Exception as e:
            print(f"✗ T_テナントアプリ設定: {e}")
            # カラムが既に存在しない場合はスキップ
            if "does not exist" in str(e) or "already exists" in str(e):
                print("  (Column already renamed or doesn't exist, skipping)")
            else:
                raise
        
        # T_店舗アプリ設定のカラムをリネーム
        print("Renaming column in T_店舗アプリ設定...")
        try:
            db.execute(text("""
                ALTER TABLE "T_店舗アプリ設定" 
                RENAME COLUMN "app_name" TO "app_id"
            """))
            print("✓ T_店舗アプリ設定.app_name → app_id")
        except Exception as e:
            print(f"✗ T_店舗アプリ設定: {e}")
            # カラムが既に存在しない場合はスキップ
            if "does not exist" in str(e) or "already exists" in str(e):
                print("  (Column already renamed or doesn't exist, skipping)")
            else:
                raise
        
        db.commit()
        print("=== Migration completed successfully ===")
        
    except Exception as e:
        db.rollback()
        print(f"=== Migration failed: {e} ===")
        raise
    finally:
        db.close()

if __name__ == '__main__':
    migrate()
