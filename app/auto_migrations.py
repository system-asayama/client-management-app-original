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

        # 4b-2. T_テナントに gps_interval_seconds カラムを追加
        if not column_exists(session, 'T_テナント', 'gps_interval_seconds'):
            logger.info("T_テナントテーブルに gps_interval_seconds カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_テナント"
                    ADD COLUMN gps_interval_seconds INTEGER
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_テナント".gps_interval_seconds IS 'GPS位置記録間隔（秒）。設定時はgps_interval_minutesより優先される'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_テナント`
                    ADD COLUMN `gps_interval_seconds` INT DEFAULT NULL
                    COMMENT 'GPS位置記録間隔（秒）。設定時はgps_interval_minutesより優先される'
                """))
            session.commit()
            logger.info("✓ gps_interval_seconds カラムを追加しました")
        else:
            logger.info("- gps_interval_seconds カラムは既に存在します（スキップ）")

        # 4c. T_テナントに gps_continuous カラムを追加
        if not column_exists(session, 'T_テナント', 'gps_continuous'):
            logger.info("T_テナントテーブルに gps_continuous カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_テナント"
                    ADD COLUMN gps_continuous INTEGER DEFAULT 0
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_テナント`
                    ADD COLUMN `gps_continuous` INT DEFAULT 0
                    COMMENT 'GPS常時記録モード（1=常時記録, 0=間隔記録）'
                """))
            session.commit()
            logger.info("✓ gps_continuous カラムを追加しました")
        else:
            logger.info("- gps_continuous カラムは既に存在します")

        # 4d. T_テナントに gps_realtime_enabled カラムを追加
        if not column_exists(session, 'T_テナント', 'gps_realtime_enabled'):
            logger.info("T_テナントテーブルに gps_realtime_enabled カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_テナント"
                    ADD COLUMN gps_realtime_enabled INTEGER DEFAULT 0
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_テナント`
                    ADD COLUMN `gps_realtime_enabled` INT DEFAULT 0
                    COMMENT 'リアルタイム追跡モード（1=有効, 0=無効）'
                """))
            session.commit()
            logger.info("✓ gps_realtime_enabled カラムを追加しました")
        else:
            logger.info("- gps_realtime_enabled カラムは既に存在します")

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

        # 8. T_管理者に face_photo_url カラムを追加
        if not column_exists(session, 'T_管理者', 'face_photo_url'):
            logger.info("T_管理者テーブルに face_photo_url カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_管理者"
                    ADD COLUMN face_photo_url TEXT
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_管理者".face_photo_url IS '顔認証用写真URL（Base64またはストレージURL）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_管理者`
                    ADD COLUMN `face_photo_url` TEXT COMMENT '顔認証用写真URL（Base64またはストレージURL）'
                """))
            session.commit()
            logger.info("✓ T_管理者.face_photo_url カラムを追加しました")
        else:
            logger.info("- T_管理者.face_photo_url カラムは既に存在します（スキップ）")

        # 8b. T_従業員に face_photo_url カラムを追加
        if not column_exists(session, 'T_従業員', 'face_photo_url'):
            logger.info("T_従業員テーブルに face_photo_url カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_従業員"
                    ADD COLUMN face_photo_url TEXT
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_従業員".face_photo_url IS '顔認証用写真URL（Base64またはストレージURL）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_従業員`
                    ADD COLUMN `face_photo_url` TEXT COMMENT '顔認証用写真URL（Base64またはストレージURL）'
                """))
            session.commit()
            logger.info("✓ T_従業員.face_photo_url カラムを追加しました")
        else:
            logger.info("- T_従業員.face_photo_url カラムは既に存在します（スキップ）")

        # T_従業員テーブルに gps_mode カラムを追加
        if not column_exists(session, 'T_従業員', 'gps_mode'):
            logger.info("T_従業員テーブルに gps_mode カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_従業員"
                    ADD COLUMN gps_mode VARCHAR(20) DEFAULT 'always'
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_従業員".gps_mode IS 'GPS追跡モード: always=常時追跡, checkin_only=出退勤時のみ'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_従業員`
                    ADD COLUMN `gps_mode` VARCHAR(20) DEFAULT 'always'
                    COMMENT 'GPS追跡モード: always=常時追跡, checkin_only=出退勤時のみ'
                """))
            session.commit()
            logger.info("✓ T_従業員.gps_mode カラムを追加しました")
        else:
            logger.info("- T_従業員.gps_mode カラムは既に存在します（スキップ）")

        # T_アプリ管理者グループ テーブルを作成
        if not table_exists(session, 'T_アプリ管理者グループ'):
            logger.info("T_アプリ管理者グループ テーブルを作成中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    CREATE TABLE "T_アプリ管理者グループ" (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        active INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                session.execute(text("""
                    CREATE TABLE `T_アプリ管理者グループ` (
                        `id` INT NOT NULL AUTO_INCREMENT,
                        `name` VARCHAR(255) NOT NULL,
                        `description` TEXT,
                        `active` INT DEFAULT 1,
                        `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                        `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        PRIMARY KEY (`id`)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """))
            session.commit()
            logger.info("✓ T_アプリ管理者グループ テーブルを作成しました")
        else:
            logger.info("- T_アプリ管理者グループ テーブルは既に存在します")

        # T_管理者テーブルに app_manager_group_id カラムを追加
        if not column_exists(session, 'T_管理者', 'app_manager_group_id'):
            logger.info("T_管理者テーブルに app_manager_group_id カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_管理者"
                    ADD COLUMN app_manager_group_id INTEGER NULL
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_管理者".app_manager_group_id
                    IS 'アプリ管理者グループID（アプリ管理者ロールの場合に使用）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_管理者`
                    ADD COLUMN `app_manager_group_id` INT NULL
                    COMMENT 'アプリ管理者グループID（アプリ管理者ロールの場合に使用）'
                """))
            session.commit()
            logger.info("✓ T_管理者.app_manager_group_id カラムを追加しました")
        else:
            logger.info("- T_管理者.app_manager_group_id カラムは既に存在します（スキップ）")

        # T_管理者テーブルに can_distribute_apps カラムを追加
        if not column_exists(session, 'T_管理者', 'can_distribute_apps'):
            logger.info("T_管理者テーブルに can_distribute_apps カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_管理者"
                    ADD COLUMN can_distribute_apps INTEGER DEFAULT 0
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_管理者".can_distribute_apps
                    IS 'アプリ配布権限（1=配布可能、0=不可）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_管理者`
                    ADD COLUMN `can_distribute_apps` INT DEFAULT 0
                    COMMENT 'アプリ配布権限（1=配布可能、0=不可）'
                """))
            session.commit()
            logger.info("✓ T_管理者.can_distribute_apps カラムを追加しました")
        else:
            logger.info("- T_管理者.can_distribute_apps カラムは既に存在します（スキップ）")

        # T_顧問先テーブルに store_id カラムを追加（店舗ベースアーキテクチャ対応）
        if not column_exists(session, 'T_顧問先', 'store_id'):
            logger.info("T_顧問先テーブルに store_id カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_顧問先"
                    ADD COLUMN store_id INTEGER NULL
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_顧問先".store_id IS '担当店舗ID（T_店舗.id）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_顧問先`
                    ADD COLUMN `store_id` INT NULL
                    COMMENT '担当店舗ID（T_店舗.id）'
                """))
            session.commit()
            logger.info("✓ T_顧問先.store_id カラムを追加しました")
        else:
            logger.info("- T_顧問先.store_id カラムは既に存在します（スキップ）")

        # T_勤怠テーブルに store_id カラムを追加（店舗ベースアーキテクチャ対応）
        if not column_exists(session, 'T_勤怠', 'store_id'):
            logger.info("T_勤怠テーブルに store_id カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_勤怠"
                    ADD COLUMN store_id INTEGER NULL
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_勤怠".store_id IS '店舗ID（T_店舗.id）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_勤怠`
                    ADD COLUMN `store_id` INT NULL
                    COMMENT '店舗ID（T_店舗.id）'
                """))
            session.commit()
            logger.info("✓ T_勤怠.store_id カラムを追加しました")
        else:
            logger.info("- T_勤怠.store_id カラムは既に存在します（スキップ）")

        # T_管理者テーブルに gps_mode カラムを追加
        if not column_exists(session, 'T_管理者', 'gps_mode'):
            logger.info("T_管理者テーブルに gps_mode カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_管理者"
                    ADD COLUMN gps_mode VARCHAR(20) DEFAULT 'always'
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_管理者".gps_mode IS 'GPS追跡モード: always=常時追跡, checkin_only=出退勤時のみ'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_管理者`
                    ADD COLUMN `gps_mode` VARCHAR(20) DEFAULT 'always'
                    COMMENT 'GPS追跡モード: always=常時追跡, checkin_only=出退勤時のみ'
                """))
            session.commit()
            logger.info("✓ T_管理者.gps_mode カラムを追加しました")
        else:
            logger.info("- T_管理者.gps_mode カラムは既に存在します（スキップ）")

        # T_テナントテーブルに truck_apk_url カラムを追加
        if not column_exists(session, 'T_テナント', 'truck_apk_url'):
            logger.info("T_テナントテーブルに truck_apk_url カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_テナント"
                    ADD COLUMN truck_apk_url TEXT NULL
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_テナント".truck_apk_url IS 'トラック運行管理アプリのAPKダウンロードURL'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_テナント`
                    ADD COLUMN `truck_apk_url` TEXT NULL
                    COMMENT 'トラック運行管理アプリのAPKダウンロードURL'
                """))
            session.commit()
            logger.info("✓ T_テナント.truck_apk_url カラムを追加しました")
        else:
            logger.info("- T_テナント.truck_apk_url カラムは既に存在します（スキップ）")

        # T_テナントテーブルに truck_apk_version カラムを追加
        if not column_exists(session, 'T_テナント', 'truck_apk_version'):
            logger.info("T_テナントテーブルに truck_apk_version カラムを追加中...")
            if db_type == 'postgresql':
                session.execute(text("""
                    ALTER TABLE "T_テナント"
                    ADD COLUMN truck_apk_version VARCHAR(20) NULL
                """))
                session.execute(text("""
                    COMMENT ON COLUMN "T_テナント".truck_apk_version IS 'トラック運行管理アプリのAPKバージョン（例: v1.0.0）'
                """))
            else:
                session.execute(text("""
                    ALTER TABLE `T_テナント`
                    ADD COLUMN `truck_apk_version` VARCHAR(20) NULL
                    COMMENT 'トラック運行管理アプリのAPKバージョン（例: v1.0.0）'
                """))
            session.commit()
            logger.info("✓ T_テナント.truck_apk_version カラムを追加しました")
        else:
            logger.info("- T_テナント.truck_apk_version カラムは既に存在します（スキップ）")

        # T_テナントテーブルにSMTPメール設定カラムを追加
        smtp_columns = [
            ('smtp_host',       'VARCHAR(255) NULL',  'SMTPサーバーホスト名'),
            ('smtp_port',       'INT NULL',           'SMTPポート番号'),
            ('smtp_username',   'VARCHAR(255) NULL',  'SMTPユーザー名'),
            ('smtp_password',   'TEXT NULL',          'SMTPパスワード'),
            ('smtp_use_tls',    'INT DEFAULT 1',      'TLS使用: 1=STARTTLS, 2=SSL/TLS, 0=なし'),
            ('smtp_from_email', 'VARCHAR(255) NULL',  '差出人メールアドレス'),
            ('smtp_from_name',  'VARCHAR(255) NULL',  '差出人名'),
        ]
        for col_name, col_def, col_comment in smtp_columns:
            if not column_exists(session, 'T_テナント', col_name):
                logger.info(f"T_テナントテーブルに {col_name} カラムを追加中...")
                try:
                    if db_type == 'postgresql':
                        session.execute(text(f'ALTER TABLE "T_テナント" ADD COLUMN "{col_name}" {col_def}'))
                    else:
                        session.execute(text(f'ALTER TABLE `T_テナント` ADD COLUMN `{col_name}` {col_def} COMMENT \'{col_comment}\''))
                    session.commit()
                    logger.info(f"✓ T_テナント.{col_name} カラムを追加しました")
                except Exception as col_err:
                    session.rollback()
                    logger.error(f"カラム追加エラー: T_テナント.{col_name} - {col_err}")
            else:
                logger.info(f"- T_テナント.{col_name} カラムは既に存在します（スキップ）")

        # T_店舗テーブルにSMTPメール設定カラムを追加（店舗単位）
        store_smtp_columns = [
            ('smtp_host',       'VARCHAR(255) NULL',  'SMTPサーバーホスト名'),
            ('smtp_port',       'INT NULL',           'SMTPポート番号'),
            ('smtp_username',   'VARCHAR(255) NULL',  'SMTPユーザー名'),
            ('smtp_password',   'TEXT NULL',          'SMTPパスワード'),
            ('smtp_use_tls',    'INT DEFAULT 1',      'TLS使用: 1=STARTTLS, 2=SSL/TLS, 0=なし'),
            ('smtp_from_email', 'VARCHAR(255) NULL',  '差出人メールアドレス'),
            ('smtp_from_name',  'VARCHAR(255) NULL',  '差出人名'),
        ]
        for col_name, col_def, col_comment in store_smtp_columns:
            if not column_exists(session, 'T_店舗', col_name):
                logger.info(f"T_店舗テーブルに {col_name} カラムを追加中...")
                try:
                    if db_type == 'postgresql':
                        session.execute(text(f'ALTER TABLE "T_店舗" ADD COLUMN "{col_name}" {col_def}'))
                    else:
                        session.execute(text(f'ALTER TABLE `T_店舗` ADD COLUMN `{col_name}` {col_def} COMMENT \'{col_comment}\''))
                    session.commit()
                    logger.info(f"✓ T_店舗.{col_name} カラムを追加しました")
                except Exception as col_err:
                    session.rollback()
                    logger.error(f"カラム追加エラー: T_店舗.{col_name} - {col_err}")
            else:
                logger.info(f"- T_店舗.{col_name} カラムは既に存在します（スキップ）")

        # T_アプリ管理者グループテーブルにplanカラムを追加
        if not column_exists(session, 'T_アプリ管理者グループ', 'plan'):
            logger.info("T_アプリ管理者グループテーブルに plan カラムを追加中...")
            try:
                if db_type == 'postgresql':
                    session.execute(text("""
                        ALTER TABLE "T_アプリ管理者グループ"
                        ADD COLUMN plan VARCHAR(50) DEFAULT 'individual'
                    """))
                else:
                    session.execute(text("""
                        ALTER TABLE `T_アプリ管理者グループ`
                        ADD COLUMN `plan` VARCHAR(50) DEFAULT 'individual'
                        COMMENT 'プラン種別: unlimited / 10app_pack / individual'
                    """))
                session.commit()
                logger.info("✓ T_アプリ管理者グループ.plan カラムを追加しました")
            except Exception as col_err:
                session.rollback()
                logger.error(f"カラム追加エラー: T_アプリ管理者グループ.plan - {col_err}")
        else:
            logger.info("- T_アプリ管理者グループ.plan カラムは既に存在します（スキップ）")

        # T_アプリ管理者グループテーブルにenabled_appsカラムを追加
        if not column_exists(session, 'T_アプリ管理者グループ', 'enabled_apps'):
            logger.info("T_アプリ管理者グループテーブルに enabled_apps カラムを追加中...")
            try:
                if db_type == 'postgresql':
                    session.execute(text("""
                        ALTER TABLE "T_アプリ管理者グループ"
                        ADD COLUMN enabled_apps TEXT NULL
                    """))
                else:
                    session.execute(text("""
                        ALTER TABLE `T_アプリ管理者グループ`
                        ADD COLUMN `enabled_apps` TEXT NULL
                        COMMENT '選択済みアプリIDのJSON配列'
                    """))
                session.commit()
                logger.info("✓ T_アプリ管理者グループ.enabled_apps カラムを追加しました")
            except Exception as col_err:
                session.rollback()
                logger.error(f"カラム追加エラー: T_アプリ管理者グループ.enabled_apps - {col_err}")
        else:
            logger.info("- T_アプリ管理者グループ.enabled_apps カラムは既に存在します（スキップ）")

        # ─── trucks テーブル詳細カラム追加 ───────────────────────────
        trucks_new_columns = [
            ('owner_name',        'VARCHAR(100) NULL',  '所有者'),
            ('user_name',         'VARCHAR(100) NULL',  '使用者'),
            ('base_location',     'VARCHAR(200) NULL',  '所属（営業所・拠点）'),
            ('vehicle_type',      'VARCHAR(100) NULL',  '車種・型式'),
            ('year',              'INT NULL',           '年式'),
            ('color',             'VARCHAR(50) NULL',   '車体色'),
            ('vin',               'VARCHAR(100) NULL',  '車台番号'),
            ('engine_number',     'VARCHAR(100) NULL',  'エンジン番号'),
            ('shaken_expiry',     'DATE NULL',          '車検満了日'),
            ('shaken_number',     'VARCHAR(100) NULL',  '車検証番号'),
            ('insurance_company', 'VARCHAR(200) NULL',  '保険会社名'),
            ('insurance_policy',  'VARCHAR(100) NULL',  '証券番号'),
            ('insurance_expiry',  'DATE NULL',          '保険満了日'),
            ('photo_path',        'VARCHAR(500) NULL',  '車両写真パス'),
            ('photo_name',        'VARCHAR(200) NULL',  '車両写真元ファイル名'),
        ]
        if table_exists(session, 'trucks'):
            for col_name, col_def, col_comment in trucks_new_columns:
                if not column_exists(session, 'trucks', col_name):
                    logger.info(f"trucksテーブルに {col_name} カラムを追加中...")
                    try:
                        if db_type == 'postgresql':
                            session.execute(text(f'ALTER TABLE trucks ADD COLUMN "{col_name}" {col_def}'))
                        else:
                            session.execute(text(f"ALTER TABLE `trucks` ADD COLUMN `{col_name}` {col_def} COMMENT '{col_comment}'"))
                        session.commit()
                        logger.info(f"✓ trucks.{col_name} カラムを追加しました")
                    except Exception as col_err:
                        session.rollback()
                        logger.error(f"カラム追加エラー: trucks.{col_name} - {col_err}")
                else:
                    logger.info(f"- trucks.{col_name} カラムは既に存在します（スキップ）")

        # ─── truck_accident_records テーブル作成 ──────────────────────
        if not table_exists(session, 'truck_accident_records'):
            logger.info("truck_accident_records テーブルを作成中...")
            try:
                if db_type == 'postgresql':
                    session.execute(text("""
                        CREATE TABLE truck_accident_records (
                            id SERIAL PRIMARY KEY,
                            truck_id INTEGER NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
                            accident_date DATE NOT NULL,
                            location VARCHAR(300),
                            description TEXT,
                            damage_level VARCHAR(20),
                            repair_cost FLOAT,
                            repair_completed BOOLEAN DEFAULT FALSE,
                            note TEXT,
                            tenant_id INTEGER,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """))
                else:
                    session.execute(text("""
                        CREATE TABLE `truck_accident_records` (
                            `id` INT AUTO_INCREMENT PRIMARY KEY,
                            `truck_id` INT NOT NULL,
                            `accident_date` DATE NOT NULL,
                            `location` VARCHAR(300),
                            `description` TEXT,
                            `damage_level` VARCHAR(20),
                            `repair_cost` FLOAT,
                            `repair_completed` TINYINT(1) DEFAULT 0,
                            `note` TEXT,
                            `tenant_id` INT,
                            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (`truck_id`) REFERENCES `trucks`(`id`) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                session.commit()
                logger.info("✓ truck_accident_records テーブルを作成しました")
            except Exception as tbl_err:
                session.rollback()
                logger.error(f"テーブル作成エラー: truck_accident_records - {tbl_err}")
        else:
            logger.info("- truck_accident_records テーブルは既に存在します（スキップ）")

        # ─── truck_inspection_records テーブル作成 ────────────────────
        if not table_exists(session, 'truck_inspection_records'):
            logger.info("truck_inspection_records テーブルを作成中...")
            try:
                if db_type == 'postgresql':
                    session.execute(text("""
                        CREATE TABLE truck_inspection_records (
                            id SERIAL PRIMARY KEY,
                            truck_id INTEGER NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
                            inspection_date DATE NOT NULL,
                            inspection_type VARCHAR(50),
                            inspector VARCHAR(100),
                            result VARCHAR(20),
                            next_inspection_date DATE,
                            mileage INTEGER,
                            description TEXT,
                            cost FLOAT,
                            note TEXT,
                            tenant_id INTEGER,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """))
                else:
                    session.execute(text("""
                        CREATE TABLE `truck_inspection_records` (
                            `id` INT AUTO_INCREMENT PRIMARY KEY,
                            `truck_id` INT NOT NULL,
                            `inspection_date` DATE NOT NULL,
                            `inspection_type` VARCHAR(50),
                            `inspector` VARCHAR(100),
                            `result` VARCHAR(20),
                            `next_inspection_date` DATE,
                            `mileage` INT,
                            `description` TEXT,
                            `cost` FLOAT,
                            `note` TEXT,
                            `tenant_id` INT,
                            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (`truck_id`) REFERENCES `trucks`(`id`) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                session.commit()
                logger.info("✓ truck_inspection_records テーブルを作成しました")
            except Exception as tbl_err:
                session.rollback()
                logger.error(f"テーブル作成エラー: truck_inspection_records - {tbl_err}")
        else:
            logger.info("- truck_inspection_records テーブルは既に存在します（スキップ）")

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

def run_truck_doc_migrations():
    """車検証・保険証ファイルカラムをtrucksテーブルに追加"""
    session = SessionLocal()
    db_type = get_db_type()
    try:
        logger.info(f"truck_doc_migrations 開始... (DB: {db_type})")
        new_cols = [
            ("shaken_doc_path",    "VARCHAR(500)"),
            ("shaken_doc_name",    "VARCHAR(200)"),
            ("insurance_doc_path", "VARCHAR(500)"),
            ("insurance_doc_name", "VARCHAR(200)"),
        ]
        for col_name, col_type in new_cols:
            try:
                if not column_exists(session, 'trucks', col_name):
                    session.execute(text(f"ALTER TABLE trucks ADD COLUMN {col_name} {col_type}"))
                    session.commit()
                    logger.info(f"✓ trucks.{col_name} カラムを追加しました")
                else:
                    logger.info(f"- trucks.{col_name} は既に存在します（スキップ）")
            except Exception as col_err:
                session.rollback()
                logger.error(f"カラム追加エラー: trucks.{col_name} - {col_err}")
    except Exception as e:
        session.rollback()
        logger.error(f"✗ truck_doc_migrations エラー: {e}")
    finally:
        session.close()


def run_breeder_new_table_migrations():
    """
    Churupi相当機能のための新テーブルを作成する。
    - genetic_test_results  : 遺伝疾患検査結果
    - show_records          : ドッグショー記録
    - public_cartes         : 公開カルテ
    - kennel_profiles       : 犬舎プロフィール
    - event_presetsにdays_offsetカラム追加
    """
    session = SessionLocal()
    db_type = get_db_type()
    is_pg = (db_type == 'postgresql')

    def _create(table_name, mysql_ddl, pg_ddl):
        if table_exists(session, table_name):
            logger.info(f"- {table_name} テーブルは既に存在します（スキップ）")
            return
        try:
            session.execute(text(pg_ddl if is_pg else mysql_ddl))
            session.commit()
            logger.info(f"✓ {table_name} テーブルを作成しました")
        except Exception as e:
            session.rollback()
            logger.error(f"テーブル作成エラー: {table_name} - {e}")

    try:
        logger.info(f"run_breeder_new_table_migrations 開始... (DB: {db_type})")

        # ── genetic_test_results ──────────────────────────────────────
        _create(
            'genetic_test_results',
            """
            CREATE TABLE `genetic_test_results` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT,
                `store_id` INT,
                `dog_id` INT,
                `puppy_id` INT,
                `disease_name` VARCHAR(200) NOT NULL,
                `result` ENUM('clear','carrier','affected','unknown') NOT NULL DEFAULT 'unknown',
                `tested_at` DATE,
                `lab_name` VARCHAR(200),
                `certificate_url` TEXT,
                `notes` TEXT,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_gtr_tenant (`tenant_id`),
                INDEX idx_gtr_dog (`dog_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE genetic_test_results (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER,
                store_id INTEGER,
                dog_id INTEGER,
                puppy_id INTEGER,
                disease_name VARCHAR(200) NOT NULL,
                result VARCHAR(20) NOT NULL DEFAULT 'unknown',
                tested_at DATE,
                lab_name VARCHAR(200),
                certificate_url TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # ── show_records ──────────────────────────────────────────────
        _create(
            'show_records',
            """
            CREATE TABLE `show_records` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT,
                `store_id` INT,
                `dog_id` INT,
                `puppy_id` INT,
                `show_name` VARCHAR(300) NOT NULL,
                `show_date` DATE NOT NULL,
                `location` VARCHAR(300),
                `title_earned` VARCHAR(200),
                `placement` VARCHAR(100),
                `judge_name` VARCHAR(200),
                `notes` TEXT,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_sr_tenant (`tenant_id`),
                INDEX idx_sr_dog (`dog_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE show_records (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER,
                store_id INTEGER,
                dog_id INTEGER,
                puppy_id INTEGER,
                show_name VARCHAR(300) NOT NULL,
                show_date DATE NOT NULL,
                location VARCHAR(300),
                title_earned VARCHAR(200),
                placement VARCHAR(100),
                judge_name VARCHAR(200),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # ── public_cartes ─────────────────────────────────────────────
        _create(
            'public_cartes',
            """
            CREATE TABLE `public_cartes` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT,
                `store_id` INT,
                `dog_id` INT,
                `puppy_id` INT,
                `public_token` VARCHAR(64) NOT NULL UNIQUE,
                `is_published` TINYINT(1) NOT NULL DEFAULT 0,
                `intro_text` TEXT,
                `view_count` INT NOT NULL DEFAULT 0,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_pc_tenant (`tenant_id`),
                INDEX idx_pc_token (`public_token`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE public_cartes (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER,
                store_id INTEGER,
                dog_id INTEGER,
                puppy_id INTEGER,
                public_token VARCHAR(64) NOT NULL UNIQUE,
                is_published SMALLINT NOT NULL DEFAULT 0,
                intro_text TEXT,
                view_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # ── kennel_profiles ───────────────────────────────────────────
        _create(
            'kennel_profiles',
            """
            CREATE TABLE `kennel_profiles` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT,
                `store_id` INT,
                `kennel_name` VARCHAR(200),
                `intro_text` TEXT,
                `address` VARCHAR(300),
                `phone` VARCHAR(30),
                `email` VARCHAR(320),
                `website_url` TEXT,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_kp_tenant (`tenant_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE kennel_profiles (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER,
                store_id INTEGER,
                kennel_name VARCHAR(200),
                intro_text TEXT,
                address VARCHAR(300),
                phone VARCHAR(30),
                email VARCHAR(320),
                website_url TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # ── event_presetsにdays_offsetカラムを追加 ─────────────────────
        if table_exists(session, 'event_presets'):
            if not column_exists(session, 'event_presets', 'days_offset'):
                try:
                    if is_pg:
                        session.execute(text(
                            "ALTER TABLE event_presets ADD COLUMN days_offset INTEGER DEFAULT 0"
                        ))
                    else:
                        session.execute(text(
                            "ALTER TABLE `event_presets` ADD COLUMN `days_offset` INT DEFAULT 0 COMMENT '起点日からのオフセット日数'"
                        ))
                    session.commit()
                    logger.info("✓ event_presets.days_offset カラムを追加しました")
                except Exception as e:
                    session.rollback()
                    logger.error(f"event_presets.days_offset 追加エラー: {e}")
            else:
                logger.info("- event_presets.days_offset は既に存在します（スキップ）")

        logger.info("✓ run_breeder_new_table_migrations 完了")

    except Exception as e:
        session.rollback()
        logger.error(f"✗ run_breeder_new_table_migrations エラー: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        session.close()


def run_pedigree_ancestor_migration():
    """pedigree_ancestorsテーブルを作成するマイグレーション"""
    from sqlalchemy import create_engine, text
    from app.db import get_db_url
    import logging
    logger = logging.getLogger(__name__)

    engine = create_engine(get_db_url())
    session = engine.connect()
    try:
        is_pg = 'postgresql' in str(engine.url)

        def table_exists(conn, name):
            if is_pg:
                r = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=:n"), {'n': name})
            else:
                r = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() AND table_name=:n"), {'n': name})
            return r.scalar() > 0

        if not table_exists(session, 'pedigree_ancestors'):
            if is_pg:
                session.execute(text("""
                    CREATE TABLE pedigree_ancestors (
                        id SERIAL PRIMARY KEY,
                        dog_id INTEGER NOT NULL REFERENCES dogs(id) ON DELETE CASCADE,
                        generation INTEGER NOT NULL COMMENT_PG,
                        position VARCHAR(20) NOT NULL,
                        name VARCHAR(300),
                        registration_number VARCHAR(100),
                        breed VARCHAR(100),
                        color VARCHAR(100),
                        country_prefix VARCHAR(20),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """.replace('COMMENT_PG', '')))
            else:
                session.execute(text("""
                    CREATE TABLE `pedigree_ancestors` (
                        `id` INT AUTO_INCREMENT PRIMARY KEY,
                        `dog_id` INT NOT NULL,
                        `generation` INT NOT NULL COMMENT '世代（1=父母, 2=祖父母, 3=曾祖父母, 4=高祖父母）',
                        `position` VARCHAR(20) NOT NULL COMMENT '位置コード（例: sire, dam, sire_sire等）',
                        `name` VARCHAR(300) COMMENT '犬名',
                        `registration_number` VARCHAR(100) COMMENT '登録番号',
                        `breed` VARCHAR(100) COMMENT '犬種',
                        `color` VARCHAR(100) COMMENT '毛色',
                        `country_prefix` VARCHAR(20) COMMENT '国プレフィックス',
                        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (`dog_id`) REFERENCES `dogs`(`id`) ON DELETE CASCADE
                    )
                """))
            session.commit()
            logger.info("✓ pedigree_ancestors テーブルを作成しました")
        else:
            logger.info("- pedigree_ancestors テーブルは既に存在します（スキップ）")
    except Exception as e:
        session.rollback()
        logger.error(f"✗ run_pedigree_ancestor_migration エラー: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        session.close()


def run_truck_schedule_migration():
    """truck_schedulesテーブルを作成する"""
    from sqlalchemy import create_engine, text
    from .db import get_db_url
    engine_local = create_engine(get_db_url())
    conn = engine_local.connect()
    try:
        is_pg = 'postgresql' in str(engine_local.url)
        def tbl_exists(c, name):
            if is_pg:
                r = c.execute(text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=:n"), {'n': name})
            else:
                r = c.execute(text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() AND table_name=:n"), {'n': name})
            return r.scalar() > 0
        if not tbl_exists(conn, 'truck_schedules'):
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE truck_schedules (
                        id SERIAL PRIMARY KEY,
                        schedule_date DATE NOT NULL,
                        driver_id INTEGER REFERENCES truck_drivers(id),
                        truck_id INTEGER REFERENCES trucks(id),
                        route_id INTEGER REFERENCES truck_routes(id),
                        start_time VARCHAR(5),
                        end_time VARCHAR(5),
                        note TEXT,
                        tenant_id INTEGER,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE `truck_schedules` (
                        `id` INT AUTO_INCREMENT PRIMARY KEY,
                        `schedule_date` DATE NOT NULL,
                        `driver_id` INT,
                        `truck_id` INT,
                        `route_id` INT,
                        `start_time` VARCHAR(5),
                        `end_time` VARCHAR(5),
                        `note` TEXT,
                        `tenant_id` INT,
                        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """))
            conn.commit()
            logger.info("✓ truck_schedules テーブルを作成しました")
        else:
            logger.info("- truck_schedules テーブルは既に存在します（スキップ）")
    except Exception as e:
        conn.rollback()
        import traceback
        logger.error(f"✗ run_truck_schedule_migration エラー: {e}")
        logger.error(traceback.format_exc())
    finally:
        conn.close()


def run_truck_schedule_migration():
    """truck_schedulesテーブルを作成する"""
    from sqlalchemy import create_engine, text
    from .db import get_db_url
    engine_local = create_engine(get_db_url())
    conn = engine_local.connect()
    try:
        is_pg = 'postgresql' in str(engine_local.url)
        def tbl_exists(c, name):
            if is_pg:
                r = c.execute(text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=:n"), {'n': name})
            else:
                r = c.execute(text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() AND table_name=:n"), {'n': name})
            return r.scalar() > 0
        if not tbl_exists(conn, 'truck_schedules'):
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE truck_schedules (
                        id SERIAL PRIMARY KEY,
                        schedule_date DATE NOT NULL,
                        driver_id INTEGER REFERENCES truck_drivers(id),
                        truck_id INTEGER REFERENCES trucks(id),
                        route_id INTEGER REFERENCES truck_routes(id),
                        start_time VARCHAR(5),
                        end_time VARCHAR(5),
                        note TEXT,
                        tenant_id INTEGER,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE `truck_schedules` (
                        `id` INT AUTO_INCREMENT PRIMARY KEY,
                        `schedule_date` DATE NOT NULL,
                        `driver_id` INT,
                        `truck_id` INT,
                        `route_id` INT,
                        `start_time` VARCHAR(5),
                        `end_time` VARCHAR(5),
                        `note` TEXT,
                        `tenant_id` INT,
                        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """))
            conn.commit()
            logger.info("✓ truck_schedules テーブルを作成しました")
        else:
            logger.info("- truck_schedules テーブルは既に存在します（スキップ）")
    except Exception as e:
        conn.rollback()
        import traceback
        logger.error(f"✗ run_truck_schedule_migration エラー: {e}")
        logger.error(traceback.format_exc())
    finally:
        conn.close()


def run_truck_store_id_migration():
    """trucks・truck_driversテーブルにstore_idカラムを追加するマイグレーション"""
    from app.utils.db import get_db_connection, _sql
    from sqlalchemy import text
    conn = get_db_connection()
    try:
        # trucks.store_id
        try:
            conn.execute(text('SELECT store_id FROM trucks LIMIT 1'))
            logger.info("- trucks.store_id カラムは既に存在します（スキップ）")
        except Exception:
            conn.rollback()
            conn.execute(text('ALTER TABLE trucks ADD COLUMN store_id INTEGER'))
            conn.commit()
            logger.info("✓ trucks.store_id カラムを追加しました")

        # truck_drivers.store_id
        try:
            conn.execute(text('SELECT store_id FROM truck_drivers LIMIT 1'))
            logger.info("- truck_drivers.store_id カラムは既に存在します（スキップ）")
        except Exception:
            conn.rollback()
            conn.execute(text('ALTER TABLE truck_drivers ADD COLUMN store_id INTEGER'))
            conn.commit()
            logger.info("✓ truck_drivers.store_id カラムを追加しました")

        # truck_routes.store_id
        try:
            conn.execute(text('SELECT store_id FROM truck_routes LIMIT 1'))
            logger.info("- truck_routes.store_id カラムは既に存在します（スキップ）")
        except Exception:
            conn.rollback()
            conn.execute(text('ALTER TABLE truck_routes ADD COLUMN store_id INTEGER'))
            conn.commit()
            logger.info("✓ truck_routes.store_id カラムを追加しました")
    except Exception as e:
        conn.rollback()
        import traceback
        logger.error(f"✗ run_truck_store_id_migration エラー: {e}")
        logger.error(traceback.format_exc())
    finally:
        conn.close()


def run_platform_table_migrations():
    """
    収益化・プラットフォーム機能に必要なテーブルを作成するマイグレーション。
    plans / subscriptions / stripe_customers / feature_usages /
    breeder_profiles / breeder_scores / kpi_snapshots / breeder_reviews
    """
    from sqlalchemy import text, inspect as sa_inspect
    session = SessionLocal()
    try:
        bind = session.get_bind()
        is_pg = bind.dialect.name == 'postgresql'

        def _tbl_exists(name):
            insp = sa_inspect(bind)
            return name in insp.get_table_names()

        def _create(tname, pg_ddl, my_ddl=None):
            if _tbl_exists(tname):
                logger.info(f"- {tname} は既に存在します（スキップ）")
                return
            ddl = pg_ddl if is_pg else (my_ddl or pg_ddl)
            try:
                session.execute(text(ddl))
                session.commit()
                logger.info(f"✓ {tname} テーブルを作成しました")
            except Exception as e:
                session.rollback()
                logger.error(f"✗ {tname} 作成エラー: {e}")

        _create('plans', """
            CREATE TABLE plans (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) NOT NULL UNIQUE,
                display_name VARCHAR(100),
                price_monthly INTEGER DEFAULT 0,
                max_dogs INTEGER,
                max_owners INTEGER,
                features JSONB DEFAULT '[]',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """, """
            CREATE TABLE `plans` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `name` VARCHAR(50) NOT NULL UNIQUE,
                `display_name` VARCHAR(100),
                `price_monthly` INT DEFAULT 0,
                `max_dogs` INT,
                `max_owners` INT,
                `features` JSON,
                `is_active` TINYINT(1) DEFAULT 1,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        if _tbl_exists('plans'):
            try:
                result = session.execute(text("SELECT COUNT(*) FROM plans")).scalar()
                if result == 0:
                    session.execute(text("""
                        INSERT INTO plans (name, display_name, price_monthly, max_dogs, max_owners, features)
                        VALUES
                        ('free','フリープラン',0,5,3,'["basic_coi","basic_mating_eval","owner_app","health_log"]'),
                        ('standard','スタンダード',4980,NULL,NULL,'["basic_coi","advanced_coi","avk_analysis","genetic_disease","basic_mating_eval","advanced_mating_eval","basic_report","owner_app","health_log","medical_event","vaccine_schedule"]'),
                        ('pro','プロ',9800,NULL,NULL,'["basic_coi","advanced_coi","avk_analysis","genetic_disease","basic_mating_eval","advanced_mating_eval","breeding_history","puppy_data","line_analysis","candidate_ranking","basic_report","advanced_report","pdf_report","survival_analysis","breeder_score","owner_app","health_log","medical_event","vaccine_schedule","priority_support"]'),
                        ('enterprise','エンタープライズ',0,NULL,NULL,'["basic_coi","advanced_coi","avk_analysis","genetic_disease","basic_mating_eval","advanced_mating_eval","breeding_history","puppy_data","line_analysis","candidate_ranking","basic_report","advanced_report","pdf_report","survival_analysis","breeder_score","owner_app","health_log","medical_event","vaccine_schedule","priority_support","api_access","data_export","custom_analysis"]')
                    """))
                    session.commit()
                    logger.info("✓ デフォルトプランを挿入しました")
            except Exception as e:
                session.rollback()
                logger.error(f"plans 初期データ挿入エラー: {e}")

        _create('subscriptions', """
            CREATE TABLE subscriptions (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                plan_id INTEGER REFERENCES plans(id),
                status VARCHAR(50) DEFAULT 'active',
                stripe_subscription_id VARCHAR(255),
                current_period_start TIMESTAMP,
                current_period_end TIMESTAMP,
                cancel_at_period_end BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """, """
            CREATE TABLE `subscriptions` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT NOT NULL,
                `plan_id` INT,
                `status` VARCHAR(50) DEFAULT 'active',
                `stripe_subscription_id` VARCHAR(255),
                `current_period_start` DATETIME,
                `current_period_end` DATETIME,
                `cancel_at_period_end` TINYINT(1) DEFAULT 0,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        _create('stripe_customers', """
            CREATE TABLE stripe_customers (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL UNIQUE,
                stripe_customer_id VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """, """
            CREATE TABLE `stripe_customers` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT NOT NULL UNIQUE,
                `stripe_customer_id` VARCHAR(255) NOT NULL,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        _create('feature_usages', """
            CREATE TABLE feature_usages (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                feature_key VARCHAR(100) NOT NULL,
                user_id INTEGER,
                meta JSONB,
                used_at TIMESTAMP DEFAULT NOW()
            )
        """, """
            CREATE TABLE `feature_usages` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT NOT NULL,
                `feature_key` VARCHAR(100) NOT NULL,
                `user_id` INT,
                `meta` JSON,
                `used_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_fu_tenant_feature` (`tenant_id`, `feature_key`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        _create('breeder_profiles', """
            CREATE TABLE breeder_profiles (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL UNIQUE,
                kennel_name VARCHAR(200),
                location_prefecture VARCHAR(50),
                location_city VARCHAR(100),
                website VARCHAR(500),
                description TEXT,
                main_breeds JSONB DEFAULT '[]',
                years_experience INTEGER DEFAULT 0,
                is_public SMALLINT DEFAULT 0,
                is_verified SMALLINT DEFAULT 0,
                avatar_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """, """
            CREATE TABLE `breeder_profiles` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT NOT NULL UNIQUE,
                `kennel_name` VARCHAR(200),
                `location_prefecture` VARCHAR(50),
                `location_city` VARCHAR(100),
                `website` VARCHAR(500),
                `description` TEXT,
                `main_breeds` JSON,
                `years_experience` INT DEFAULT 0,
                `is_public` TINYINT(1) DEFAULT 0,
                `is_verified` TINYINT(1) DEFAULT 0,
                `avatar_url` VARCHAR(500),
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        _create('breeder_scores', """
            CREATE TABLE breeder_scores (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                total_score FLOAT DEFAULT 0,
                rank VARCHAR(5) DEFAULT 'D',
                health_score FLOAT DEFAULT 0,
                coi_score FLOAT DEFAULT 0,
                data_score FLOAT DEFAULT 0,
                breeding_score FLOAT DEFAULT 0,
                owner_feedback_score FLOAT DEFAULT 0,
                avg_coi FLOAT,
                puppy_survival_rate FLOAT,
                disease_incidence_rate FLOAT,
                breeding_success_rate FLOAT,
                data_completeness_rate FLOAT,
                owner_retention_rate FLOAT,
                strengths JSONB DEFAULT '[]',
                weaknesses JSONB DEFAULT '[]',
                improvement_tips JSONB DEFAULT '[]',
                calculated_at TIMESTAMP DEFAULT NOW()
            )
        """, """
            CREATE TABLE `breeder_scores` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `tenant_id` INT NOT NULL,
                `total_score` FLOAT DEFAULT 0,
                `rank` VARCHAR(5) DEFAULT 'D',
                `health_score` FLOAT DEFAULT 0,
                `coi_score` FLOAT DEFAULT 0,
                `data_score` FLOAT DEFAULT 0,
                `breeding_score` FLOAT DEFAULT 0,
                `owner_feedback_score` FLOAT DEFAULT 0,
                `avg_coi` FLOAT,
                `puppy_survival_rate` FLOAT,
                `disease_incidence_rate` FLOAT,
                `breeding_success_rate` FLOAT,
                `data_completeness_rate` FLOAT,
                `owner_retention_rate` FLOAT,
                `strengths` JSON,
                `weaknesses` JSON,
                `improvement_tips` JSON,
                `calculated_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_bs_tenant` (`tenant_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        _create('kpi_snapshots', """
            CREATE TABLE kpi_snapshots (
                id SERIAL PRIMARY KEY,
                snapshot_date DATE NOT NULL UNIQUE,
                active_breeders INTEGER DEFAULT 0,
                active_owners INTEGER DEFAULT 0,
                total_dogs INTEGER DEFAULT 0,
                total_health_logs INTEGER DEFAULT 0,
                total_coi_calcs INTEGER DEFAULT 0,
                paying_tenants INTEGER DEFAULT 0,
                mrr FLOAT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """, """
            CREATE TABLE `kpi_snapshots` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `snapshot_date` DATE NOT NULL UNIQUE,
                `active_breeders` INT DEFAULT 0,
                `active_owners` INT DEFAULT 0,
                `total_dogs` INT DEFAULT 0,
                `total_health_logs` INT DEFAULT 0,
                `total_coi_calcs` INT DEFAULT 0,
                `paying_tenants` INT DEFAULT 0,
                `mrr` FLOAT DEFAULT 0,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        _create('breeder_reviews', """
            CREATE TABLE breeder_reviews (
                id SERIAL PRIMARY KEY,
                breeder_tenant_id INTEGER NOT NULL,
                reviewer_owner_id INTEGER,
                rating FLOAT NOT NULL,
                comment TEXT,
                is_anonymous BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """, """
            CREATE TABLE `breeder_reviews` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `breeder_tenant_id` INT NOT NULL,
                `reviewer_owner_id` INT,
                `rating` FLOAT NOT NULL,
                `comment` TEXT,
                `is_anonymous` TINYINT(1) DEFAULT 1,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_br_breeder` (`breeder_tenant_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        logger.info("✓ run_platform_table_migrations 完了")
    except Exception as e:
        session.rollback()
        logger.error(f"✗ run_platform_table_migrations エラー: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        session.close()
