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
            # PostgreSQLではダブルクォートを使用し、AFTER句は使用しない
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
        # PostgreSQLでは AFTER 句を使わず、カラムは末尾に追加される
        migrations = [
            ("T_店舗", "郵便番号", "VARCHAR(10) NULL"),
            ("T_店舗", "住所", "VARCHAR(500) NULL"),
            ("T_店舗", "電話番号", "VARCHAR(20) NULL"),
            ("T_店舗", "email", "VARCHAR(255) NULL"),
            ("T_店舗", "openai_api_key", "VARCHAR(255) NULL"),
            ("T_店舗", "updated_at", "TIMESTAMP NULL"),
            # T_管理者_店舗テーブルにオーナーと管理権限カラムを追加
            ("T_管理者_店舗", "is_owner", "INTEGER DEFAULT 0"),
            ("T_管理者_店舗", "can_manage_admins", "INTEGER DEFAULT 0"),
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
            
    except Exception as e:
        logger.error(f"マイグレーション実行エラー: {e}")
        db.rollback()
    finally:
        db.close()


def migrate_store_admins_data(db):
    """既存の店舗管理者データを中間テーブルに移行"""
    try:
        logger.info("店舗管理者データ移行開始")
        
        # まず、中間テーブルに既にデータがあるか確認
        result = db.execute(text(
            'SELECT COUNT(*) FROM "T_管理者_店舗"'
        ))
        existing_count = result.scalar()
        logger.info(f"DEBUG: T_管理者_店舗テーブルの既存データ数: {existing_count}")
        
        # 既存データがある場合、直接オーナー設定に進む
        if existing_count > 0:
            logger.info("中間テーブルに既にデータが存在するので、オーナー設定のみ実行します")
        else:
            # 中間テーブルが空の場合、T_管理者テーブルから店舗管理者を取得して登録
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
                    # このテナントの店舗を取得
                    result = db.execute(text(
                        'SELECT "id" FROM "T_店舗" WHERE "tenant_id" = :tenant_id'
                    ), {"tenant_id": tenant_id})
                    stores = result.fetchall()
                    logger.info(f"DEBUG: tenant_id={tenant_id} の店舗数: {len(stores)}")
                    
                    for store in stores:
                        store_id = store[0]
                        logger.info(f"DEBUG: 店舗 store_id={store_id} を処理中")
                        
                        # 中間テーブルに既に登録されているか確認
                        result = db.execute(text(
                            'SELECT COUNT(*) FROM "T_管理者_店舗" '
                            'WHERE "admin_id" = :admin_id AND "store_id" = :store_id'
                        ), {"admin_id": admin_id, "store_id": store_id})
                        exists = result.scalar()
                        logger.info(f"DEBUG: admin_id={admin_id}, store_id={store_id} の存在チェック: exists={exists}")
                        
                        if exists == 0:
                            # 中間テーブルに登録
                            logger.info(f"店舗管理者 admin_id={admin_id} を店舗 store_id={store_id} に登録します")
                            db.execute(text(
                                'INSERT INTO "T_管理者_店舗" ("admin_id", "store_id", "is_owner", "can_manage_admins", "active") '
                                'VALUES (:admin_id, :store_id, 0, 0, 1)'
                            ), {"admin_id": admin_id, "store_id": store_id})
                            db.commit()
                            logger.info(f"DEBUG: 登録完了 admin_id={admin_id}, store_id={store_id}")
                        else:
                            logger.info(f"DEBUG: スキップ (既に登録済み) admin_id={admin_id}, store_id={store_id}")
                except Exception as e:
                    logger.error(f"ERROR: admin_id={admin_id} の処理中にエラー: {e}")
                    db.rollback()
        
        # T_管理者_店舗テーブルに既存データがあるか確認
        result = db.execute(text(
            'SELECT COUNT(*) FROM "T_管理者_店舗"'
        ))
        count = result.scalar()
        
        if count > 0:
            logger.info(f"中間テーブルに既に{count}件のデータが存在します")
            
            # 各店舗でオーナーが設定されているか確認
            result = db.execute(text(
                'SELECT DISTINCT "store_id" FROM "T_管理者_店舗"'
            ))
            store_ids = [row[0] for row in result.fetchall()]
            
            for store_id in store_ids:
                logger.info(f"DEBUG: 店舗ID {store_id} のオーナーチェック開始")
                
                try:
                    # この店舗にオーナーがいるか確認
                    result = db.execute(text(
                        'SELECT COUNT(*) FROM "T_管理者_店舗" '
                        'WHERE "store_id" = :store_id AND "is_owner" = 1'
                    ), {"store_id": store_id})
                    owner_count = result.scalar()
                    logger.info(f"DEBUG: 店舗ID {store_id} のオーナー数: {owner_count}")
                    
                    if owner_count == 0:
                        # オーナーがいない場合、最初の管理者をオーナーに設定
                        logger.info(f"店舗ID {store_id} にオーナーを設定します")
                        
                        # 最初の管理者IDを取得
                        result = db.execute(text(
                            'SELECT MIN("admin_id") FROM "T_管理者_店舗" '
                            'WHERE "store_id" = :store_id'
                        ), {"store_id": store_id})
                        first_admin_id = result.scalar()
                        logger.info(f"DEBUG: 店舗ID {store_id} の最初の管理者ID: {first_admin_id}")
                        
                        if first_admin_id:
                            db.execute(text(
                                'UPDATE "T_管理者_店舗" '
                                'SET "is_owner" = 1, "can_manage_admins" = 1, "active" = 1 '
                                'WHERE "store_id" = :store_id AND "admin_id" = :admin_id'
                            ), {"store_id": store_id, "admin_id": first_admin_id})
                            db.commit()
                            logger.info(f"店舗ID {store_id} のオーナー設定完了 (admin_id={first_admin_id})")
                        else:
                            logger.warning(f"WARNING: 店舗ID {store_id} に管理者がいません")
                    else:
                        logger.info(f"DEBUG: 店舗ID {store_id} には既にオーナーがいます")
                except Exception as e:
                    logger.error(f"ERROR: 店舗ID {store_id} のオーナー設定中にエラー: {e}")
                    db.rollback()
        
        logger.info("店舗管理者データ移行完了")
        
    except Exception as e:
        logger.error(f"店舗管理者データ移行エラー: {e}")
        db.rollback()
