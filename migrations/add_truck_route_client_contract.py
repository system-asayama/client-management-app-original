"""
truck_routesテーブルに取引先・荷主（client_name）と請負金額（contract_amount）カラムを追加するマイグレーション
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

        # client_name カラムを追加
        if not column_exists('truck_routes', 'client_name'):
            print("Adding client_name column to truck_routes...")
            db.execute(text(
                "ALTER TABLE truck_routes "
                "ADD COLUMN client_name VARCHAR(200) NULL COMMENT '取引先・荷主'"
            ))
            db.commit()
            print("✓ client_name column added")
        else:
            print("✓ client_name column already exists")

        # contract_amount カラムを追加
        if not column_exists('truck_routes', 'contract_amount'):
            print("Adding contract_amount column to truck_routes...")
            db.execute(text(
                "ALTER TABLE truck_routes "
                "ADD COLUMN contract_amount INT NULL COMMENT '請負金額（円）'"
            ))
            db.commit()
            print("✓ contract_amount column added")
        else:
            print("✓ contract_amount column already exists")

        print("Migration completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Migration error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
