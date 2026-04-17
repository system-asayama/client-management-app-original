# -*- coding: utf-8 -*-
"""
データベースマイグレーション
アプリケーション起動時に自動的に実行される
"""

from sqlalchemy import text
from app.db import SessionLocal
import logging

logger = logging.getLogger(__name__)


def check_column_exists(db, table_name, column_name):
    """カラムが存在するかチェック"""
    try:
        result = db.execute(text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = CURRENT_SCHEMA() "
            "AND TABLE_NAME = :table_name "
            "AND COLUMN_NAME = :column_name"
        ), {"table_name": table_name, "column_name": column_name})
        count = result.scalar()
        return count > 0
    except Exception as e:
        logger.error(f"カラム存在チェックエラー: {e}")
        return False


def add_column_if_not_exists(db, table_name, column_name, column_definition):
    """カラムが存在しない場合は追加（PostgreSQL用）"""
    try:
        if not check_column_exists(db, table_name, column_name):
            sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_definition}'
            logger.info(f"カラムを追加: {table_name}.{column_name}")
            db.execute(text(sql))
            db.commit()
            logger.info(f"カラム追加完了: {table_name}.{column_name}")
            return True
        else:
            logger.info(f"カラムは既に存在: {table_name}.{column_name}")
            return False
    except Exception as e:
        logger.error(f"カラム追加エラー: {table_name}.{column_name} - {e}")
        db.rollback()
        return False


def check_table_exists(db, table_name):
    """テーブルが存在するかチェック"""
    try:
        result = db.execute(text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = CURRENT_SCHEMA() "
            "AND TABLE_NAME = :table_name"
        ), {"table_name": table_name})
        count = result.scalar()
        return count > 0
    except Exception as e:
        logger.error(f"テーブル存在チェックエラー: {e}")
        return False


def create_employee_store_table(db):
    """従業員_店舗中間テーブルを作成"""
    try:
        if not check_table_exists(db, "T_従業員_店舗"):
            logger.info("T_従業員_店舗テーブルを作成します")
            db.execute(text(
                'CREATE TABLE "T_従業員_店舗" ('
                '  "id" SERIAL PRIMARY KEY,'
                '  "employee_id" INTEGER NOT NULL,'
                '  "store_id" INTEGER NOT NULL,'
                '  "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,'
                '  FOREIGN KEY ("employee_id") REFERENCES "T_従業員"("id") ON DELETE CASCADE,'
                '  FOREIGN KEY ("store_id") REFERENCES "T_店舗"("id") ON DELETE CASCADE'
                ')'
            ))
            db.commit()
            logger.info("T_従業員_店舗テーブル作成完了")
            return True
        else:
            logger.info("T_従業員_店舗テーブルは既に存在します")
            return False
    except Exception as e:
        logger.error(f"T_従業員_店舗テーブル作成エラー: {e}")
        db.rollback()
        return False


def run_migrations():
    """すべてのマイグレーションを実行"""
    logger.info("マイグレーション開始")
    db = SessionLocal()
    
    try:
        # T_従業員_店舗テーブルを作成
        create_employee_store_table(db)
        # T_店舗テーブルに新しいカラムを追加
        migrations = [
            ("T_店舗", "郵便番号", "VARCHAR(10) NULL"),
            ("T_店舗", "住所", "VARCHAR(500) NULL"),
            ("T_店舗", "電話番号", "VARCHAR(20) NULL"),
            ("T_店舗", "email", "VARCHAR(255) NULL"),
            ("T_店舗", "openai_api_key", "VARCHAR(255) NULL"),
            ("T_店舗", "updated_at", "TIMESTAMP NULL"),
            ("T_管理者_店舗", "is_owner", "INTEGER DEFAULT 0"),
            ("T_管理者_店舗", "can_manage_admins", "INTEGER DEFAULT 0"),
            ("T_テナント", "google_vision_api_key", "TEXT NULL"),
            ("T_テナント", "google_api_key", "TEXT NULL"),
            ("T_テナント", "anthropic_api_key", "TEXT NULL"),
            ("T_テナント", "ai_model", "VARCHAR(50) DEFAULT 'gemini-1.5-flash'"),
            ("T_店舗", "google_vision_api_key", "TEXT NULL"),
            ("T_店舗", "google_api_key", "TEXT NULL"),
            ("T_店舗", "anthropic_api_key", "TEXT NULL"),
            ("T_店舗", "ai_model", "VARCHAR(50) DEFAULT 'gemini-1.5-flash'"),
            ("T_アプリ管理者グループ", "openai_api_key", "TEXT NULL"),
            ("T_アプリ管理者グループ", "google_vision_api_key", "TEXT NULL"),
            ("T_アプリ管理者グループ", "google_api_key", "TEXT NULL"),
            ("T_アプリ管理者グループ", "anthropic_api_key", "TEXT NULL"),
            ("T_管理者", "google_vision_api_key", "TEXT NULL"),
            ("T_管理者", "google_api_key", "TEXT NULL"),
            ("T_管理者", "anthropic_api_key", "TEXT NULL"),
        ]
        
        added_count = 0
        for table_name, column_name, column_def in migrations:
            if add_column_if_not_exists(db, table_name, column_name, column_def):
                added_count += 1
        
        if added_count > 0:
            logger.info(f"マイグレーション完了: {added_count}個のカラムを追加しました")
        else:
            logger.info("マイグレーション完了: 追加するカラムはありませんでした")
        
        # 既存の店舗管理者データを中間テーブルに移行
        migrate_store_admins_data(db)

        # 定款作成テーブルのマイグレーション
        migrate_teikan_table(db)

        # 不動産マネジメントテーブルのマイグレーション
        migrate_property_tables(db)
            
    except Exception as e:
        logger.error(f"マイグレーション実行エラー: {e}")
        db.rollback()
    finally:
        db.close()


def migrate_store_admins_data(db):
    """既存の店舗管理者データを中間テーブルに移行"""
    try:
        logger.info("店舗管理者データ移行開始")
        
        result = db.execute(text(
            'SELECT COUNT(*) FROM "T_管理者_店舗"'
        ))
        existing_count = result.scalar()
        logger.info(f"DEBUG: T_管理者_店舗テーブルの既存データ数: {existing_count}")
        
        if existing_count > 0:
            logger.info("中間テーブルに既にデータが存在するので、オーナー設定のみ実行します")
        else:
            result = db.execute(text(
                'SELECT "id", "tenant_id" FROM "T_管理者" WHERE "role" = \'admin\''
            ))
            admins = result.fetchall()
            
            logger.info(f"T_管理者テーブルから{len(admins)}人の店舗管理者を取得しました")
            
            for admin in admins:
                admin_id = admin[0]
                tenant_id = admin[1]
                logger.info(f"DEBUG: 処理中 admin_id={admin_id}, tenant_id={tenant_id}")
                
                try:
                    result = db.execute(text(
                        'SELECT "id" FROM "T_店舗" WHERE "tenant_id" = :tenant_id'
                    ), {"tenant_id": tenant_id})
                    stores = result.fetchall()
                    logger.info(f"DEBUG: tenant_id={tenant_id} の店舗数: {len(stores)}")
                    
                    for store in stores:
                        store_id = store[0]
                        logger.info(f"DEBUG: 店舗 store_id={store_id} を処理中")
                        
                        result = db.execute(text(
                            'SELECT COUNT(*) FROM "T_管理者_店舗" '
                            'WHERE "admin_id" = :admin_id AND "store_id" = :store_id'
                        ), {"admin_id": admin_id, "store_id": store_id})
                        exists = result.scalar()
                        
                        if exists == 0:
                            logger.info(f"店舗管理者 admin_id={admin_id} を店舗 store_id={store_id} に登録します")
                            db.execute(text(
                                'INSERT INTO "T_管理者_店舗" ("admin_id", "store_id", "is_owner", "can_manage_admins", "active") '
                                'VALUES (:admin_id, :store_id, 0, 0, 1)'
                            ), {"admin_id": admin_id, "store_id": store_id})
                            db.commit()
                except Exception as e:
                    logger.error(f"ERROR: admin_id={admin_id} の処理中にエラー: {e}")
                    db.rollback()
        
        result = db.execute(text(
            'SELECT COUNT(*) FROM "T_管理者_店舗"'
        ))
        count = result.scalar()
        
        if count > 0:
            logger.info(f"中間テーブルに既に{count}件のデータが存在します")
            
            result = db.execute(text(
                'SELECT DISTINCT "store_id" FROM "T_管理者_店舗"'
            ))
            store_ids = [row[0] for row in result.fetchall()]
            
            for store_id in store_ids:
                try:
                    result = db.execute(text(
                        'SELECT COUNT(*) FROM "T_管理者_店舗" '
                        'WHERE "store_id" = :store_id AND "is_owner" = 1'
                    ), {"store_id": store_id})
                    owner_count = result.scalar()
                    
                    if owner_count == 0:
                        result = db.execute(text(
                            'SELECT MIN("admin_id") FROM "T_管理者_店舗" '
                            'WHERE "store_id" = :store_id'
                        ), {"store_id": store_id})
                        first_admin_id = result.scalar()
                        
                        if first_admin_id:
                            db.execute(text(
                                'UPDATE "T_管理者_店舗" '
                                'SET "is_owner" = 1, "can_manage_admins" = 1, "active" = 1 '
                                'WHERE "store_id" = :store_id AND "admin_id" = :admin_id'
                            ), {"store_id": store_id, "admin_id": first_admin_id})
                            db.commit()
                except Exception as e:
                    logger.error(f"ERROR: 店舗ID {store_id} のオーナー設定中にエラー: {e}")
                    db.rollback()
        
        logger.info("店舗管理者データ移行完了")
        
    except Exception as e:
        logger.error(f"店舗管理者データ移行エラー: {e}")
        db.rollback()


def migrate_teikan_table(db):
    """定款作成テーブルのマイグレーション"""
    try:
        if not check_table_exists(db, "T_定款"):
            logger.info("T_定款テーブルを作成します")
            db.execute(text('''
                CREATE TABLE "T_定款" (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER REFERENCES "T_テナント"(id) ON DELETE SET NULL,
                    store_id INTEGER REFERENCES "T_店舗"(id) ON DELETE SET NULL,
                    created_by INTEGER REFERENCES "T_管理者"(id) ON DELETE SET NULL,
                    company_name VARCHAR(255) NOT NULL DEFAULT '',
                    company_type VARCHAR(50) DEFAULT '合同会社',
                    status VARCHAR(20) DEFAULT 'draft',
                    data_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            logger.info("T_定款テーブル作成完了")
        else:
            add_column_if_not_exists(db, "T_定款", "store_id",
                'INTEGER REFERENCES "T_店舗"(id) ON DELETE SET NULL')
            logger.info("T_定款テーブルは既に存在します")
    except Exception as e:
        logger.error(f"定款テーブルマイグレーションエラー: {e}")
        db.rollback()


def migrate_property_tables(db):
    """不動産マネジメントテーブルのマイグレーション"""
    try:
        # T_物件テーブル
        if not check_table_exists(db, "T_物件"):
            logger.info("T_物件テーブルを作成します")
            db.execute(text('''
                CREATE TABLE "T_物件" (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER REFERENCES "T_テナント"(id) ON DELETE SET NULL,
                    物件名 VARCHAR(255) NOT NULL DEFAULT '',
                    物件種別 VARCHAR(50) DEFAULT 'マンション',
                    郵便番号 VARCHAR(10),
                    住所 VARCHAR(500),
                    建築年 INTEGER,
                    構造 VARCHAR(50),
                    建築面積 NUMERIC(10,2),
                    土地面積 NUMERIC(10,2),
                    取得価格 NUMERIC(15,2),
                    備考 TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            logger.info("T_物件テーブル作成完了")

        # T_部屋テーブル
        if not check_table_exists(db, "T_部屋"):
            logger.info("T_部屋テーブルを作成します")
            db.execute(text('''
                CREATE TABLE "T_部屋" (
                    id SERIAL PRIMARY KEY,
                    property_id INTEGER NOT NULL REFERENCES "T_物件"(id) ON DELETE CASCADE,
                    部屋番号 VARCHAR(50) NOT NULL DEFAULT '',
                    面積 NUMERIC(10,2),
                    間取り数 INTEGER,
                    階数 INTEGER,
                    向き VARCHAR(20),
                    賃貸料 NUMERIC(12,2),
                    管理費 NUMERIC(12,2),
                    ステータス VARCHAR(20) DEFAULT '空室',
                    備考 TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            logger.info("T_部屋テーブル作成完了")

        # T_入居者テーブル
        if not check_table_exists(db, "T_入居者"):
            logger.info("T_入居者テーブルを作成します")
            db.execute(text('''
                CREATE TABLE "T_入居者" (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER REFERENCES "T_テナント"(id) ON DELETE SET NULL,
                    氏名 VARCHAR(100) NOT NULL DEFAULT '',
                    フリガナ VARCHAR(100),
                    生年月日 DATE,
                    電話番号 VARCHAR(20),
                    メール VARCHAR(255),
                    緊急連絡先 VARCHAR(255),
                    備考 TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            logger.info("T_入居者テーブル作成完了")

        # T_契約テーブル
        if not check_table_exists(db, "T_契約"):
            logger.info("T_契約テーブルを作成します")
            db.execute(text('''
                CREATE TABLE "T_契約" (
                    id SERIAL PRIMARY KEY,
                    room_id INTEGER NOT NULL REFERENCES "T_部屋"(id) ON DELETE CASCADE,
                    tenant_person_id INTEGER NOT NULL REFERENCES "T_入居者"(id) ON DELETE CASCADE,
                    契約開始日 DATE,
                    契約終了日 DATE,
                    賃貸料 NUMERIC(12,2),
                    敷金 NUMERIC(12,2),
                    契約ステータス VARCHAR(20) DEFAULT '入居中',
                    備考 TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            logger.info("T_契約テーブル作成完了")

        # T_家購収支テーブル
        if not check_table_exists(db, "T_家購収支"):
            logger.info("T_家購収支テーブルを作成します")
            db.execute(text('''
                CREATE TABLE "T_家購収支" (
                    id SERIAL PRIMARY KEY,
                    property_id INTEGER NOT NULL REFERENCES "T_物件"(id) ON DELETE CASCADE,
                    年月 VARCHAR(7) NOT NULL,
                    収入合計 NUMERIC(15,2) DEFAULT 0,
                    支出合計 NUMERIC(15,2) DEFAULT 0,
                    備考 TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            logger.info("T_家購収支テーブル作成完了")

        # T_減価償却テーブル
        if not check_table_exists(db, "T_減価償却"):
            logger.info("T_減価償却テーブルを作成します")
            db.execute(text('''
                CREATE TABLE "T_減価償却" (
                    id SERIAL PRIMARY KEY,
                    property_id INTEGER REFERENCES "T_物件"(id) ON DELETE CASCADE,
                    tenant_id INTEGER REFERENCES "T_テナント"(id) ON DELETE SET NULL,
                    物件id INTEGER REFERENCES "T_物件"(id) ON DELETE SET NULL,
                    資産名 VARCHAR(255) NOT NULL DEFAULT '',
                    取得価格 NUMERIC(15,2),
                    耐用年数 INTEGER,
                    取得日 DATE,
                    償却方法 VARCHAR(20) DEFAULT '定額法',
                    備考 TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            logger.info("T_減価償却テーブル作成完了")

        # T_シミュレーションテーブル
        if not check_table_exists(db, "T_シミュレーション"):
            logger.info("T_シミュレーションテーブルを作成します")
            db.execute(text('''
                CREATE TABLE "T_シミュレーション" (
                    id SERIAL PRIMARY KEY,
                    property_id INTEGER REFERENCES "T_物件"(id) ON DELETE CASCADE,
                    tenant_id INTEGER REFERENCES "T_テナント"(id) ON DELETE SET NULL,
                    シミュレーション名 VARCHAR(255) NOT NULL DEFAULT '',
                    物件価格 NUMERIC(15,2),
                    自己資金 NUMERIC(15,2),
                    借入金利 NUMERIC(5,3),
                    借入期間 INTEGER,
                    想定賃貸料 NUMERIC(12,2),
                    備考 TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            logger.info("T_シミュレーションテーブル作成完了")

        logger.info("不動産マネジメントテーブルマイグレーション完了")
    except Exception as e:
        logger.error(f"不動産テーブルマイグレーションエラー: {e}")
        db.rollback()
