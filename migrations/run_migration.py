#!/usr/bin/env python3
"""
マイグレーションスクリプト実行用
T_管理者_店舗テーブルにis_ownerとcan_manage_adminsカラムを追加
"""
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal

def run_migration():
    db = SessionLocal()
    
    try:
        print("マイグレーション開始...")
        
        # is_ownerカラムを追加
        print("1. is_ownerカラムを追加...")
        db.execute("""
            ALTER TABLE `T_管理者_店舗` 
            ADD COLUMN `is_owner` INT DEFAULT 0 COMMENT '店舗のオーナーかどうか（1店舗につき1人）'
        """)
        
        # can_manage_adminsカラムを追加
        print("2. can_manage_adminsカラムを追加...")
        db.execute("""
            ALTER TABLE `T_管理者_店舗` 
            ADD COLUMN `can_manage_admins` INT DEFAULT 0 COMMENT '店舗管理者を管理する権限'
        """)
        
        # インデックスを追加
        print("3. インデックスを追加...")
        db.execute("""
            CREATE INDEX idx_store_admin_owner ON `T_管理者_店舗` (`store_id`, `is_owner`)
        """)
        db.execute("""
            CREATE INDEX idx_store_admin_manage ON `T_管理者_店舗` (`admin_id`, `can_manage_admins`)
        """)
        
        db.commit()
        print("✅ マイグレーション完了！")
        
    except Exception as e:
        db.rollback()
        print(f"❌ エラー: {str(e)}")
        print("マイグレーションをロールバックしました")
        raise
    
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
