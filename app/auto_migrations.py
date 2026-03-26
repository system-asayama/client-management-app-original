"""
自動マイグレーションモジュール

アプリケーション起動時に自動的にデータベーススキーマを更新します。
MySQL と PostgreSQL の両方に対応しています。
"""

import logging
from sqlalchemy import text, inspect
from app.db import SessionLocal, engine

logger = logging.getLogger(__name__)


def get_db_type():
    """データベースの種類を判定"""
    dialect_name = engine.dialect.name
    return dialect_name  # 'mysql', 'postgresql', 'sqlite' など


def column_exists(session, table_name, column_name):
    """指定されたテーブルにカラムが存在するかチェック"""
    try:
        db_type = get_db_type()
        
        if db_type == 'postgresql':
            # PostgreSQL用のクエリ
            result = session.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_name = :table_name 
                AND column_name = :column_name
            """), {"table_name": table_name, "column_name": column_name})
        else:
            # MySQL用のクエリ
            result = session.execute(text(f"""
                SELECT COUNT(*) 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table_name}' 
                AND COLUMN_NAME = '{column_name}'
            """))
        
        count = result.scalar()
        return count > 0
    except Exception as e:
        logger.error(f"カラム存在チェックエラー: {e}")
        return False


def table_exists(session, table_name):
    """指定されたテーブルが存在するかチェック"""
    try:
        db_type = get_db_type()
        
        if db_type == 'postgresql':
            # PostgreSQL用のクエリ
            result = session.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_name = :table_name
            """), {"table_name": table_name})
        else:
            # MySQL用のクエリ
            result = session.execute(text(f"""
                SELECT COUNT(*) 
                FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table_name}'
            """))
        
        count = result.scalar()
        return count > 0
    except Exception as e:
        logger.error(f"テーブル存在チェックエラー: {e}")
        return False


def run_auto_migrations():
    """
    自動マイグレーションを実行
    
    アプリケーション起動時に呼び出され、必要なスキーマ変更を自動的に適用します。
    """
    session = SessionLocal()
    db_type = get_db_type()
    
    try:
        logger.info(f"自動マイグレーション開始... (データベース: {db_type})")
        
        # 1. T_管理者テーブルに can_manage_all_tenants カラムを追加
        if not column_exists(session, 'T_管理者', 'can_manage_all_tenants'):
            logger.info("T_管理者テーブルに can_manage_all_tenants カラムを追加中...")
            
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_管理者" 
                    ADD COLUMN can_manage_all_tenants INTEGER DEFAULT 0
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_管理者".can_manage_all_tenants 
                    IS '全テナント管理権限（1=全テナントにアクセス可能、0=作成/招待されたテナントのみ）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_管理者` 
                    ADD COLUMN `can_manage_all_tenants` INT DEFAULT 0 
                    COMMENT '全テナント管理権限（1=全テナントにアクセス可能、0=作成/招待されたテナントのみ）'
                """))
            
            session.commit()
            logger.info("✓ can_manage_all_tenants カラムを追加しました")
        else:
            logger.info("- can_manage_all_tenants カラムは既に存在します")
        
        # 2. T_テナントテーブルに created_by_admin_id カラムを追加
        if not column_exists(session, 'T_テナント', 'created_by_admin_id'):
            logger.info("T_テナントテーブルに created_by_admin_id カラムを追加中...")
            
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_テナント" 
                    ADD COLUMN created_by_admin_id INTEGER NULL
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_テナント".created_by_admin_id 
                    IS 'このテナントを作成したシステム管理者のID'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_テナント` 
                    ADD COLUMN `created_by_admin_id` INT NULL 
                    COMMENT 'このテナントを作成したシステム管理者のID'
                """))
            
            session.commit()
            logger.info("✓ created_by_admin_id カラムを追加しました")
            
            # 外部キー制約を追加（既存データがある場合はスキップ）
            try:
                if db_type == 'postgresql':
                    session.execute(text("""
                        ALTER TABLE "T_テナント" 
                        ADD CONSTRAINT fk_tenant_created_by_admin 
                        FOREIGN KEY (created_by_admin_id) REFERENCES "T_管理者"(id)
                    """))
                else:
                    session.execute(text("""
                        ALTER TABLE `T_テナント` 
                        ADD CONSTRAINT `fk_tenant_created_by_admin` 
                        FOREIGN KEY (`created_by_admin_id`) REFERENCES `T_管理者`(`id`)
                    """))
                
                session.commit()
                logger.info("✓ 外部キー制約を追加しました")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    logger.info("- 外部キー制約は既に存在します")
                    session.rollback()
                else:
                    logger.warning(f"外部キー制約の追加をスキップしました: {e}")
                    session.rollback()
        else:
            logger.info("- created_by_admin_id カラムは既に存在します")
        
        # 3. T_システム管理者_テナント テーブルを作成
        if not table_exists(session, 'T_システム管理者_テナント'):
            logger.info("T_システム管理者_テナント テーブルを作成中...")
            
            if db_type == 'postgresql':
                session.execute(text("""
                    CREATE TABLE "T_システム管理者_テナント" (
                        id SERIAL PRIMARY KEY,
                        admin_id INTEGER NOT NULL,
                        tenant_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT unique_admin_tenant UNIQUE (admin_id, tenant_id),
                        CONSTRAINT fk_sysadmin_tenant_admin FOREIGN KEY (admin_id) REFERENCES "T_管理者"(id) ON DELETE CASCADE,
                        CONSTRAINT fk_sysadmin_tenant_tenant FOREIGN KEY (tenant_id) REFERENCES "T_テナント"(id) ON DELETE CASCADE
                    )
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_システム管理者_テナント".admin_id IS 'システム管理者のID'
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_システム管理者_テナント".tenant_id IS 'テナントID'
                """))
            else:
                session.execute(text("""
                    CREATE TABLE `T_システム管理者_テナント` (
                        `id` INT NOT NULL AUTO_INCREMENT,
                        `admin_id` INT NOT NULL COMMENT 'システム管理者のID',
                        `tenant_id` INT NOT NULL COMMENT 'テナントID',
                        `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (`id`),
                        UNIQUE KEY `unique_admin_tenant` (`admin_id`, `tenant_id`),
                        CONSTRAINT `fk_sysadmin_tenant_admin` FOREIGN KEY (`admin_id`) REFERENCES `T_管理者`(`id`) ON DELETE CASCADE,
                        CONSTRAINT `fk_sysadmin_tenant_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `T_テナント`(`id`) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """))
            
            session.commit()
            logger.info("✓ T_システム管理者_テナント テーブルを作成しました")
        else:
            logger.info("- T_システム管理者_テナント テーブルは既に存在します")
        
        # 4. T_テナントに gps_enabled カラムを追加
        if not column_exists(session, 'T_テナント', 'gps_enabled'):
            logger.info("T_テナントテーブルに gps_enabled カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_テナント"
                    ADD COLUMN gps_enabled INTEGER DEFAULT 0
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_テナント".gps_enabled IS 'GPS位置記録機能の有効/無効（1=有効, 0=無効）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_テナント`
                    ADD COLUMN `gps_enabled` INT DEFAULT 0
                    COMMENT 'GPS位置記録機能の有効/無効（1=有効, 0=無効）'
                """))
            session.commit()
            logger.info("✓ gps_enabled カラムを追加しました")
        else:
            logger.info("- gps_enabled カラムは既に存在します")

        # 4b. T_テナントに gps_interval_minutes カラムを追加
        if not column_exists(session, 'T_テナント', 'gps_interval_minutes'):
            logger.info("T_テナントテーブルに gps_interval_minutes カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_テナント"
                    ADD COLUMN gps_interval_minutes INTEGER DEFAULT 10
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_テナント".gps_interval_minutes IS 'GPS位置記録間隔（分）デフォルト:10'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_テナント`
                    ADD COLUMN `gps_interval_minutes` INT DEFAULT 10
                    COMMENT 'GPS位置記録間隔（分）デフォルト:10'
                """))
            session.commit()
            logger.info("✓ gps_interval_minutes カラムを追加しました")
        else:
            logger.info("- gps_interval_minutes カラムは既に存在します")

        # 5. T_勤怠位置履歴 テーブルを作成（GPS記録）
        if not table_exists(session, 'T_勤怠位置履歴'):
            logger.info("T_勤怠位置履歴 テーブルを作成中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    CREATE TABLE "T_勤怠位置履歴" (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL,
                        attendance_id INTEGER NULL,
                        staff_id INTEGER NOT NULL,
                        staff_type VARCHAR(20) NOT NULL DEFAULT 'admin',
                        latitude DOUBLE PRECISION NOT NULL,
                        longitude DOUBLE PRECISION NOT NULL,
                        accuracy DOUBLE PRECISION NULL,
                        is_background INTEGER DEFAULT 0,
                        recorded_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT fk_loc_tenant FOREIGN KEY (tenant_id) REFERENCES "T_テナント"(id) ON DELETE CASCADE,
                        CONSTRAINT fk_loc_attendance FOREIGN KEY (attendance_id) REFERENCES "T_勤怠"(id) ON DELETE SET NULL
                    )
                """))
            else:
                session.execute(text("""
                    CREATE TABLE `T_勤怠位置履歴` (
                        `id` INT NOT NULL AUTO_INCREMENT,
                        `tenant_id` INT NOT NULL,
                        `attendance_id` INT NULL,
                        `staff_id` INT NOT NULL,
                        `staff_type` VARCHAR(20) NOT NULL DEFAULT 'admin',
                        `latitude` DOUBLE NOT NULL COMMENT '緯度',
                        `longitude` DOUBLE NOT NULL COMMENT '経度',
                        `accuracy` DOUBLE NULL COMMENT '精度（メートル）',
                        `is_background` INT DEFAULT 0 COMMENT 'バックグラウンド取得フラグ',
                        `recorded_at` DATETIME NOT NULL COMMENT '位置情報取得日時',
                        `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (`id`),
                        CONSTRAINT `fk_loc_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `T_テナント`(`id`) ON DELETE CASCADE,
                        CONSTRAINT `fk_loc_attendance` FOREIGN KEY (`attendance_id`) REFERENCES `T_勤怠`(`id`) ON DELETE SET NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """))
            session.commit()
            logger.info("✓ T_勤怠位置履歴 テーブルを作成しました")
        else:
            logger.info("- T_勤怠位置履歴 テーブルは既に存在します")

        logger.info("✓ 自動マイグレーションが正常に完了しました")
        
    except Exception as e:
        session.rollback()
        logger.error(f"✗ 自動マイグレーション中にエラーが発生しました: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # エラーが発生してもアプリケーションは起動を続ける
        # （既存の機能は動作する可能性があるため）
    finally:
        session.close()


if __name__ == "__main__":
    # スタンドアロンで実行する場合
    logging.basicConfig(level=logging.INFO)
    run_auto_migrations()
