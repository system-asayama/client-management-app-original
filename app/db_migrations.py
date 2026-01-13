"""
データベース自動マイグレーション
アプリケーション起動時に実行される
"""
from sqlalchemy import text
from app.database import SessionLocal


def check_column_exists(db, table_name, column_name):
    """カラムが存在するかチェック"""
    try:
        result = db.execute(text(f"""
            SELECT COUNT(*) as count
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table_name}'
            AND COLUMN_NAME = '{column_name}'
        """))
        row = result.fetchone()
        return row[0] > 0
    except Exception as e:
        print(f"Error checking column {column_name}: {e}")
        return False


def run_migrations():
    """自動マイグレーションを実行"""
    db = SessionLocal()
    
    try:
        print("Starting database migrations...")
        
        # T_管理者_店舗テーブルにis_ownerカラムを追加
        if not check_column_exists(db, 'T_管理者_店舗', 'is_owner'):
            print("Adding is_owner column to T_管理者_店舗...")
            db.execute(text("""
                ALTER TABLE `T_管理者_店舗` 
                ADD COLUMN `is_owner` INT DEFAULT 0
            """))
            db.commit()
            print("✓ is_owner column added successfully")
        else:
            print("✓ is_owner column already exists")
        
        # T_管理者_店舗テーブルにcan_manage_adminsカラムを追加
        if not check_column_exists(db, 'T_管理者_店舗', 'can_manage_admins'):
            print("Adding can_manage_admins column to T_管理者_店舗...")
            db.execute(text("""
                ALTER TABLE `T_管理者_店舗` 
                ADD COLUMN `can_manage_admins` INT DEFAULT 0
            """))
            db.commit()
            print("✓ can_manage_admins column added successfully")
        else:
            print("✓ can_manage_admins column already exists")
        
        print("Database migrations completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migrations()
