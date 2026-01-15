#!/usr/bin/env python3
"""
Heroku releaseフェーズで実行されるマイグレーションスクリプト
"""
import os
import sys

# アプリケーションのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.db import get_db_connection, _is_pg

def run_migrations():
    """マイグレーションを実行"""
    print("=" * 60)
    print("マイグレーション開始")
    print("=" * 60)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # マイグレーション1: T_管理者テーブルにactiveカラムを追加
        print("\n[マイグレーション] T_管理者テーブルにactiveカラムを追加...")
        
        try:
            if _is_pg(conn):
                # PostgreSQL: カラムが存在するか確認
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'T_管理者' AND column_name = 'active'
                """)
                if not cur.fetchone():
                    print("  - activeカラムが存在しません。追加します...")
                    cur.execute('ALTER TABLE "T_管理者" ADD COLUMN active INTEGER DEFAULT 1')
                    cur.execute('UPDATE "T_管理者" SET active = 1 WHERE active IS NULL')
                    conn.commit()
                    print("  ✅ T_管理者テーブルにactiveカラムを追加しました")
                else:
                    print("  ℹ️  activeカラムは既に存在します（スキップ）")
            else:
                # SQLite: PRAGMAでカラムを確認
                cur.execute('PRAGMA table_info("T_管理者")')
                columns = [row[1] for row in cur.fetchall()]
                if 'active' not in columns:
                    print("  - activeカラムが存在しません。追加します...")
                    cur.execute('ALTER TABLE "T_管理者" ADD COLUMN active INTEGER DEFAULT 1')
                    cur.execute('UPDATE "T_管理者" SET active = 1 WHERE active IS NULL')
                    conn.commit()
                    print("  ✅ T_管理者テーブルにactiveカラムを追加しました")
                else:
                    print("  ℹ️  activeカラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise
        
        # マイグレーション2: T_従業員テーブルにactiveカラムを追加
        print("\n[マイグレーション] T_従業員テーブルにactiveカラムを追加...")
        
        try:
            if _is_pg(conn):
                # PostgreSQL: カラムが存在するか確認
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'T_従業員' AND column_name = 'active'
                """)
                if not cur.fetchone():
                    print("  - activeカラムが存在しません。追加します...")
                    cur.execute('ALTER TABLE "T_従業員" ADD COLUMN active INTEGER DEFAULT 1')
                    cur.execute('UPDATE "T_従業員" SET active = 1 WHERE active IS NULL')
                    conn.commit()
                    print("  ✅ T_従業員テーブルにactiveカラムを追加しました")
                else:
                    print("  ℹ️  activeカラムは既に存在します（スキップ）")
            else:
                # SQLite: PRAGMAでカラムを確認
                cur.execute('PRAGMA table_info("T_従業員")')
                columns = [row[1] for row in cur.fetchall()]
                if 'active' not in columns:
                    print("  - activeカラムが存在しません。追加します...")
                    cur.execute('ALTER TABLE "T_従業員" ADD COLUMN active INTEGER DEFAULT 1')
                    cur.execute('UPDATE "T_従業員" SET active = 1 WHERE active IS NULL')
                    conn.commit()
                    print("  ✅ T_従業員テーブルにactiveカラムを追加しました")
                else:
                    print("  ℹ️  activeカラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise
        
        # マイグレーション3: T_テナント管理者_テナントテーブルにcan_manage_tenant_adminsカラムを追加
        print("\n[マイグレーション] T_テナント管理者_テナントテーブルにcan_manage_tenant_adminsカラムを追加...")
        
        try:
            if _is_pg(conn):
                # PostgreSQL: カラムが存在するか確認
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'T_テナント管理者_テナント' AND column_name = 'can_manage_tenant_admins'
                """)
                if not cur.fetchone():
                    print("  - can_manage_tenant_adminsカラムが存在しません。追加します...")
                    cur.execute('ALTER TABLE "T_テナント管理者_テナント" ADD COLUMN can_manage_tenant_admins INTEGER DEFAULT 0')
                    conn.commit()
                    print("  ✅ T_テナント管理者_テナントテーブルにcan_manage_tenant_adminsカラムを追加しました")
                else:
                    print("  ℹ️  can_manage_tenant_adminsカラムは既に存在します（スキップ）")
            else:
                # SQLite: PRAGMAでカラムを確認
                cur.execute('PRAGMA table_info("T_テナント管理者_テナント")')
                columns = [row[1] for row in cur.fetchall()]
                if 'can_manage_tenant_admins' not in columns:
                    print("  - can_manage_tenant_adminsカラムが存在しません。追加します...")
                    cur.execute('ALTER TABLE "T_テナント管理者_テナント" ADD COLUMN can_manage_tenant_admins INTEGER DEFAULT 0')
                    conn.commit()
                    print("  ✅ T_テナント管理者_テナントテーブルにcan_manage_tenant_adminsカラムを追加しました")
                else:
                    print("  ℹ️  can_manage_tenant_adminsカラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise
        
        # マイグレーション4: T_テナントアプリ設定とT_店舗アプリ設定のapp_name→app_idに変更
        print("\n[マイグレーション] T_テナントアプリ設定とT_店舗アプリ設定のapp_name→app_idに変更...")
        
        try:
            if _is_pg(conn):
                # T_テナントアプリ設定のapp_nameをapp_idに変更
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'T_テナントアプリ設定' AND column_name = 'app_name'
                """)
                if cur.fetchone():
                    print("  - T_テナントアプリ設定.app_nameをapp_idに変更します...")
                    cur.execute('ALTER TABLE "T_テナントアプリ設定" RENAME COLUMN app_name TO app_id')
                    conn.commit()
                    print("  ✅ T_テナントアプリ設定.app_nameをapp_idに変更しました")
                else:
                    print("  ℹ️  T_テナントアプリ設定.app_nameは既にapp_idです（スキップ）")
                
                # T_店舗アプリ設定のapp_nameをapp_idに変更
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'T_店舗アプリ設定' AND column_name = 'app_name'
                """)
                if cur.fetchone():
                    print("  - T_店舗アプリ設定.app_nameをapp_idに変更します...")
                    cur.execute('ALTER TABLE "T_店舗アプリ設定" RENAME COLUMN app_name TO app_id')
                    conn.commit()
                    print("  ✅ T_店舗アプリ設定.app_nameをapp_idに変更しました")
                else:
                    print("  ℹ️  T_店舗アプリ設定.app_nameは既にapp_idです（スキップ）")
            else:
                # SQLite: カラム名変更はテーブル再作成が必要
                print("  ℹ️  SQLiteではカラム名変更をスキップします")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise
        
        # マイグレーション: T_会社基本情報テーブル作成
        print("\n[マイグレーション] T_会社基本情報テーブル作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'T_会社基本情報'
                    );
                """)
                exists = cur.fetchone()[0]
                
                if not exists:
                    print("  - T_会社基本情報 テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_会社基本情報" (
                            id SERIAL PRIMARY KEY,
                            "顧問先ID" INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            "会社名" VARCHAR(255),
                            "郵便番号" VARCHAR(20),
                            "都道府県" VARCHAR(50),
                            "市区町村番地" VARCHAR(255),
                            "建物名部屋番号" VARCHAR(255),
                            "電話番号1" VARCHAR(50),
                            "電話番号2" VARCHAR(50),
                            "ファックス番号" VARCHAR(50),
                            "メールアドレス" VARCHAR(255),
                            "担当者名" VARCHAR(100),
                            "業種" VARCHAR(100),
                            "従業員数" INTEGER,
                            "法人番号" VARCHAR(50)
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_会社基本情報 テーブルを作成しました")
                else:
                    print("  ℹ️  T_会社基本情報 テーブルは既に存在します（スキップ）")
            else:
                # SQLite用の処理
                cur.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='T_会社基本情報'
                """)
                if not cur.fetchone():
                    print("  - T_会社基本情報 テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_会社基本情報" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            "顧問先ID" INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            "会社名" TEXT,
                            "郵便番号" TEXT,
                            "都道府県" TEXT,
                            "市区町村番地" TEXT,
                            "建物名部屋番号" TEXT,
                            "電話番号1" TEXT,
                            "電話番号2" TEXT,
                            "ファックス番号" TEXT,
                            "メールアドレス" TEXT,
                            "担当者名" TEXT,
                            "業種" TEXT,
                            "従業員数" INTEGER,
                            "法人番号" TEXT
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_会社基本情報 テーブルを作成しました")
                else:
                    print("  ℹ️  T_会社基本情報 テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise
        
        # マイグレーション: T_メッセージテーブル作成
        print("\n[マイグレーション] T_メッセージテーブル作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'T_メッセージ'
                    );
                """)
                exists = cur.fetchone()[0]
                
                if not exists:
                    print("  - T_メッセージ テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_メッセージ" (
                            id SERIAL PRIMARY KEY,
                            sender VARCHAR(255) NOT NULL,
                            message TEXT NOT NULL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_メッセージ テーブルを作成しました")
                else:
                    print("  ℹ️  T_メッセージ テーブルは既に存在します（スキップ）")
            else:
                cur.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='T_メッセージ'
                """)
                if not cur.fetchone():
                    print("  - T_メッセージ テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_メッセージ" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            sender TEXT NOT NULL,
                            message TEXT NOT NULL,
                            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_メッセージ テーブルを作成しました")
                else:
                    print("  ℹ️  T_メッセージ テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise
        
        # マイグレーション: T_ファイルテーブル作成
        print("\n[マイグレーション] T_ファイルテーブル作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'T_ファイル'
                    );
                """)
                exists = cur.fetchone()[0]
                
                if not exists:
                    print("  - T_ファイル テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_ファイル" (
                            id SERIAL PRIMARY KEY,
                            filename TEXT NOT NULL,
                            uploader VARCHAR(255) NOT NULL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_ファイル テーブルを作成しました")
                else:
                    print("  ℹ️  T_ファイル テーブルは既に存在します（スキップ）")
            else:
                cur.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='T_ファイル'
                """)
                if not cur.fetchone():
                    print("  - T_ファイル テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_ファイル" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            filename TEXT NOT NULL,
                            uploader TEXT NOT NULL,
                            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_ファイル テーブルを作成しました")
                else:
                    print("  ℹ️  T_ファイル テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise
        
        print("\n" + "=" * 60)
        print("マイグレーション完了")
        print("=" * 60)
        conn.close()
    except Exception as e:
        print(f"\n⚠️  マイグレーション全体でエラーが発生しました: {e}")
        raise