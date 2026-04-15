"""
T_テナントテーブルにトラック運行管理アプリのAPK関連カラムを追加するマイグレーション
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text


def run():
    try:
        from app.database import SessionLocal
    except ImportError:
        from app.db import SessionLocal

    db = SessionLocal()
    try:
        def column_exists(table, column):
            result = db.execute(text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                f"AND TABLE_NAME = '{table}' AND COLUMN_NAME = '{column}'"
            ))
            return result.fetchone()[0] > 0

        # truck_apk_url カラムを追加
        if not column_exists('T_テナント', 'truck_apk_url'):
            print("Adding truck_apk_url column to T_テナント...")
            db.execute(text(
                "ALTER TABLE `T_テナント` "
                "ADD COLUMN `truck_apk_url` TEXT NULL "
                "COMMENT 'トラック運行管理アプリのAPKダウンロードURL'"
            ))
            db.commit()
            print("✓ truck_apk_url column added")
        else:
            print("✓ truck_apk_url column already exists")

        # truck_apk_version カラムを追加
        if not column_exists('T_テナント', 'truck_apk_version'):
            print("Adding truck_apk_version column to T_テナント...")
            db.execute(text(
                "ALTER TABLE `T_テナント` "
                "ADD COLUMN `truck_apk_version` VARCHAR(20) NULL "
                "COMMENT 'トラック運行管理アプリのAPKバージョン（例: v1.0.0）'"
            ))
            db.commit()
            print("✓ truck_apk_version column added")
        else:
            print("✓ truck_apk_version column already exists")

        print("Migration completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Migration error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
