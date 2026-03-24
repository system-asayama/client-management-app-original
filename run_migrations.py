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
                            client_id INTEGER REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            sender VARCHAR(255) NOT NULL,
                            message TEXT NOT NULL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_メッセージ テーブルを作成しました")
                else:
                    print("  ℹ️  T_メッセージ テーブルは既に存在します（スキップ）")
                    # client_idカラムが存在するか確認し、なければ追加
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = 'T_メッセージ' AND column_name = 'client_id';
                    """)
                    if not cur.fetchone():
                        print("  - client_idカラムを追加中...")
                        cur.execute("""
                            ALTER TABLE "T_メッセージ" 
                            ADD COLUMN client_id INTEGER REFERENCES "T_顧問先"(id) ON DELETE CASCADE;
                        """)
                        conn.commit()
                        print("  ✅ client_idカラムを追加しました")
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
                            client_id INTEGER REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            filename TEXT NOT NULL,
                            file_url TEXT NOT NULL,
                            uploader VARCHAR(255) NOT NULL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_ファイル テーブルを作成しました")
                else:
                    print("  ℹ️  T_ファイル テーブルは既に存在します（スキップ）")
                    # client_idカラムが存在するか確認し、なければ追加
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = 'T_ファイル' AND column_name = 'client_id';
                    """)
                    if not cur.fetchone():
                        print("  - client_idカラムを追加中...")
                        cur.execute("""
                            ALTER TABLE "T_ファイル" 
                            ADD COLUMN client_id INTEGER REFERENCES "T_顧問先"(id) ON DELETE CASCADE;
                        """)
                        conn.commit()
                        print("  ✅ client_idカラムを追加しました")
                    # file_urlカラムが存在するか確認し、なければ追加
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = 'T_ファイル' AND column_name = 'file_url';
                    """)
                    if not cur.fetchone():
                        print("  - file_urlカラムを追加中...")
                        cur.execute("""
                            ALTER TABLE "T_ファイル" 
                            ADD COLUMN file_url TEXT NOT NULL DEFAULT '';
                        """)
                        conn.commit()
                        print("  ✅ file_urlカラムを追加しました")
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
        
        # マイグレーション: T_外部ストレージ連携テーブル作成
        print("\n[マイグレーション] T_外部ストレージ連携テーブル作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'T_外部ストレージ連携'
                    );
                """)
                exists = cur.fetchone()[0]
                
                if not exists:
                    print("  - T_外部ストレージ連携 テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_外部ストレージ連携" (
                            id SERIAL PRIMARY KEY,
                            tenant_id INTEGER NOT NULL REFERENCES "T_テナント"(id) ON DELETE CASCADE,
                            provider VARCHAR(50) NOT NULL,
                            access_token TEXT,
                            refresh_token TEXT,
                            bucket_name TEXT,
                            service_account_json TEXT,
                            status VARCHAR(20) DEFAULT 'active',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_外部ストレージ連携 テーブルを作成しました")
                else:
                    print("  ℹ️  T_外部ストレージ連携 テーブルは既に存在します（スキップ）")
            else:
                cur.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='T_外部ストレージ連携'
                """)
                if not cur.fetchone():
                    print("  - T_外部ストレージ連携 テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_外部ストレージ連携" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            tenant_id INTEGER NOT NULL REFERENCES "T_テナント"(id) ON DELETE CASCADE,
                            provider TEXT NOT NULL,
                            access_token TEXT,
                            refresh_token TEXT,
                            bucket_name TEXT,
                            service_account_json TEXT,
                            status TEXT DEFAULT 'active',
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_外部ストレージ連携 テーブルを作成しました")
                else:
                    print("  ℹ️  T_外部ストレージ連携 テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise
        
        # マイグレーション: T_クライアントユーザーテーブル作成
        print("\n[マイグレーション] T_クライアントユーザーテーブル作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'T_クライアントユーザー'
                    );
                """)
                exists = cur.fetchone()[0]
                if not exists:
                    print("  - T_クライアントユーザー テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_クライアントユーザー" (
                            id SERIAL PRIMARY KEY,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            login_id VARCHAR(255) UNIQUE NOT NULL,
                            name VARCHAR(255) NOT NULL,
                            email VARCHAR(255) NOT NULL,
                            password_hash TEXT,
                            role VARCHAR(50) DEFAULT 'client_employee',
                            active INTEGER DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_クライアントユーザー テーブルを作成しました")
                else:
                    print("  ℹ️  T_クライアントユーザー テーブルは既に存在します（スキップ）")
            else:
                cur.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='T_クライアントユーザー'
                """)
                if not cur.fetchone():
                    print("  - T_クライアントユーザー テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_クライアントユーザー" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            login_id TEXT UNIQUE NOT NULL,
                            name TEXT NOT NULL,
                            email TEXT NOT NULL,
                            password_hash TEXT,
                            role TEXT DEFAULT 'client_employee',
                            active INTEGER DEFAULT 1,
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_クライアントユーザー テーブルを作成しました")
                else:
                    print("  ℹ️  T_クライアントユーザー テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise

        # マイグレーション: T_クライアント招待テーブル作成
        print("\n[マイグレーション] T_クライアント招待テーブル作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'T_クライアント招待'
                    );
                """)
                exists = cur.fetchone()[0]
                if not exists:
                    print("  - T_クライアント招待 テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_クライアント招待" (
                            id SERIAL PRIMARY KEY,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            token VARCHAR(255) UNIQUE NOT NULL,
                            email VARCHAR(255),
                            role VARCHAR(50) DEFAULT 'client_employee',
                            invited_by_role VARCHAR(50),
                            invited_by_id INTEGER,
                            used INTEGER DEFAULT 0,
                            expires_at TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_クライアント招待 テーブルを作成しました")
                else:
                    print("  ℹ️  T_クライアント招待 テーブルは既に存在します（スキップ）")
            else:
                cur.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='T_クライアント招待'
                """)
                if not cur.fetchone():
                    print("  - T_クライアント招待 テーブルを作成中...")
                    cur.execute("""
                        CREATE TABLE "T_クライアント招待" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            token TEXT UNIQUE NOT NULL,
                            email TEXT,
                            role TEXT DEFAULT 'client_employee',
                            invited_by_role TEXT,
                            invited_by_id INTEGER,
                            used INTEGER DEFAULT 0,
                            expires_at TEXT,
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_クライアント招待 テーブルを作成しました")
                else:
                    print("  ℹ️  T_クライアント招待 テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise

        # マイグレーション: T_メッセージにsender_typeカラムを追加
        print("\n[マイグレーション] T_メッセージにsender_typeカラムを追加")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'T_メッセージ' AND column_name = 'sender_type'
                """)
                if not cur.fetchone():
                    cur.execute('ALTER TABLE "T_メッセージ" ADD COLUMN sender_type VARCHAR(20) DEFAULT \'staff\'')
                    conn.commit()
                    print("  ✅ sender_typeカラムを追加しました")
                else:
                    print("  ℹ️  sender_typeカラムは既に存在します（スキップ）")
            else:
                cur.execute('PRAGMA table_info("T_メッセージ")')
                columns = [row[1] for row in cur.fetchall()]
                if 'sender_type' not in columns:
                    cur.execute('ALTER TABLE "T_メッセージ" ADD COLUMN sender_type TEXT DEFAULT \'staff\'')
                    conn.commit()
                    print("  ✅ sender_typeカラムを追加しました")
                else:
                    print("  ℹ️  sender_typeカラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_メッセージ既読テーブル作成
        print("\n[マイグレーション] T_メッセージ既読テーブル作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'T_メッセージ既読'
                    );
                """)
                exists = cur.fetchone()[0]
                if not exists:
                    cur.execute("""
                        CREATE TABLE "T_メッセージ既読" (
                            id SERIAL PRIMARY KEY,
                            message_id INTEGER NOT NULL REFERENCES "T_メッセージ"(id) ON DELETE CASCADE,
                            reader_type VARCHAR(20) NOT NULL,
                            reader_id VARCHAR(255) NOT NULL,
                            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(message_id, reader_type, reader_id)
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_メッセージ既読 テーブルを作成しました")
                else:
                    print("  ℹ️  T_メッセージ既読 テーブルは既に存在します（スキップ）")
            else:
                cur.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='T_メッセージ既読'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_メッセージ既読" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            message_id INTEGER NOT NULL REFERENCES "T_メッセージ"(id) ON DELETE CASCADE,
                            reader_type TEXT NOT NULL,
                            reader_id TEXT NOT NULL,
                            read_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(message_id, reader_type, reader_id)
                        );
                    """)
                    conn.commit()
                    print("  ✅ T_メッセージ既読 テーブルを作成しました")
                else:
                    print("  ℹ️  T_メッセージ既読 テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()
            raise

        # マイグレーション: T_顧問先にstorage_folder_pathカラムを追加
        print("\n[マイグレーション] T_顧問先にstorage_folder_pathカラムを追加")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'T_顧問先' AND column_name = 'storage_folder_path'
                """)
                if not cur.fetchone():
                    cur.execute('ALTER TABLE "T_顧問先" ADD COLUMN storage_folder_path VARCHAR(500)')
                    conn.commit()
                    print("  ✅ storage_folder_pathカラムを追加しました")
                else:
                    print("  ℹ️  storage_folder_pathカラムは既に存在します（スキップ）")
            else:
                cur.execute('PRAGMA table_info("T_顧問先")')
                columns = [row[1] for row in cur.fetchall()]
                if 'storage_folder_path' not in columns:
                    cur.execute('ALTER TABLE "T_顧問先" ADD COLUMN storage_folder_path TEXT')
                    conn.commit()
                    print("  ✅ storage_folder_pathカラムを追加しました")
                else:
                    print("  ℹ️  storage_folder_pathカラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_メッセージにファイル対応カラムを追加
        print("\n[マイグレーション] T_メッセージにmessage_type/file_url/file_nameカラムを追加")
        try:
            if _is_pg(conn):
                for col_name, col_def in [
                    ('message_type', "VARCHAR(20) DEFAULT 'text'"),
                    ('file_url', 'TEXT'),
                    ('file_name', 'VARCHAR(500)'),
                ]:
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'T_メッセージ' AND column_name = %s
                    """, (col_name,))
                    if not cur.fetchone():
                        cur.execute(f'ALTER TABLE "T_メッセージ" ADD COLUMN {col_name} {col_def}')
                        conn.commit()
                        print(f"  ✅ {col_name}カラムを追加しました")
                    else:
                        print(f"  ℹ️  {col_name}カラムは既に存在します（スキップ）")
                # messageカラムをNULL許容に変更
                cur.execute("""
                    SELECT is_nullable FROM information_schema.columns
                    WHERE table_name = 'T_メッセージ' AND column_name = 'message'
                """)
                row = cur.fetchone()
                if row and row[0] == 'NO':
                    cur.execute('ALTER TABLE "T_メッセージ" ALTER COLUMN message DROP NOT NULL')
                    conn.commit()
                    print("  ✅ messageカラムをNULL許容に変更しました")
            else:
                cur.execute('PRAGMA table_info("T_メッセージ")')
                columns = [row[1] for row in cur.fetchall()]
                for col_name, col_def in [
                    ('message_type', "TEXT DEFAULT 'text'"),
                    ('file_url', 'TEXT'),
                    ('file_name', 'TEXT'),
                ]:
                    if col_name not in columns:
                        cur.execute(f'ALTER TABLE "T_メッセージ" ADD COLUMN {col_name} {col_def}')
                        conn.commit()
                        print(f"  ✅ {col_name}カラムを追加しました")
                    else:
                        print(f"  ℹ️  {col_name}カラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_テナントにprofessionカラムを追加
        print("\n[マイグレーション] T_テナントにprofessionカラムを追加")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'T_テナント' AND column_name = 'profession'
                """)
                if not cur.fetchone():
                    cur.execute('ALTER TABLE "T_テナント" ADD COLUMN profession VARCHAR(50)')
                    conn.commit()
                    print("  ✅ professionカラムを追加しました")
                else:
                    print("  ℹ️  professionカラムは既に存在します（スキップ）")
            else:
                cur.execute('PRAGMA table_info("T_テナント")')
                columns = [row[1] for row in cur.fetchall()]
                if 'profession' not in columns:
                    cur.execute('ALTER TABLE "T_テナント" ADD COLUMN profession TEXT')
                    conn.commit()
                    print("  ✅ professionカラムを追加しました")
                else:
                    print("  ℹ️  professionカラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_顧問先に士業固有カラムを追加
        print("\n[マイグレーション] T_顧問先に士業固有カラムを追加")
        client_columns = [
            ('address',                  'VARCHAR(500)'),
            ('industry',                 'VARCHAR(100)'),
            ('fiscal_year_end',          'VARCHAR(10)'),
            ('contract_start_date',      'VARCHAR(20)'),
            ('tax_accountant_code',      'VARCHAR(50)'),
            ('tax_id_number',            'VARCHAR(20)'),
            ('case_number',              'VARCHAR(100)'),
            ('case_type',                'VARCHAR(100)'),
            ('opposing_party',           'VARCHAR(255)'),
            ('audit_type',               'VARCHAR(100)'),
            ('listed',                   'INTEGER DEFAULT 0'),
            ('employee_count',           'INTEGER'),
            ('labor_insurance_number',   'VARCHAR(50)'),
            ('social_insurance_number',  'VARCHAR(50)'),
            ('payroll_closing_day',      'VARCHAR(10)'),
        ]
        try:
            for col_name, col_def in client_columns:
                if _is_pg(conn):
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'T_顧問先' AND column_name = %s
                    """, (col_name,))
                    if not cur.fetchone():
                        cur.execute(f'ALTER TABLE "T_顧問先" ADD COLUMN {col_name} {col_def}')
                        conn.commit()
                        print(f"  ✅ {col_name}カラムを追加しました")
                    else:
                        print(f"  ℹ️  {col_name}カラムは既に存在します（スキップ）")
                else:
                    cur.execute('PRAGMA table_info("T_顧問先")')
                    columns = [row[1] for row in cur.fetchall()]
                    if col_name not in columns:
                        cur.execute(f'ALTER TABLE "T_顧問先" ADD COLUMN {col_name} TEXT')
                        conn.commit()
                        print(f"  ✅ {col_name}カラムを追加しました")
                    else:
                        print(f"  ℹ️  {col_name}カラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_顧問先に税務申告基本情報カラムを追加
        print("\n[マイグレーション] T_顧問先に税務申告基本情報カラムを追加")
        tax_columns = [
            ('fiscal_year_start_month',       'INTEGER'),
            ('fiscal_year_end_month',          'INTEGER'),
            ('established_date',               'VARCHAR(20)'),
            ('establishment_notification',     'INTEGER DEFAULT 0'),
            ('blue_return',                    'INTEGER DEFAULT 0'),
            ('consumption_tax_payer',          'INTEGER DEFAULT 0'),
            ('consumption_tax_method',         'VARCHAR(50)'),
            ('consumption_tax_calc',           'VARCHAR(50)'),
            ('qualified_invoice_registered',   'INTEGER DEFAULT 0'),
            ('qualified_invoice_number',       'VARCHAR(50)'),
        ]
        try:
            for col_name, col_def in tax_columns:
                if _is_pg(conn):
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'T_顧問先' AND column_name = %s
                    """, (col_name,))
                    if not cur.fetchone():
                        cur.execute(f'ALTER TABLE "T_顧問先" ADD COLUMN {col_name} {col_def}')
                        conn.commit()
                        print(f"  ✅ {col_name}カラムを追加しました")
                    else:
                        print(f"  ℹ️  {col_name}カラムは既に存在します（スキップ）")
                else:
                    cur.execute('PRAGMA table_info("T_顧問先")')
                    columns = [row[1] for row in cur.fetchall()]
                    if col_name not in columns:
                        cur.execute(f'ALTER TABLE "T_顧問先" ADD COLUMN {col_name} TEXT')
                        conn.commit()
                        print(f"  ✅ {col_name}カラムを追加しました")
                    else:
                        print(f"  ℹ️  {col_name}カラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_受託業務テーブルを作成
        print("\n[マイグレーション] T_受託業務テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_受託業務'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_受託業務" (
                            id SERIAL PRIMARY KEY,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            tenant_id INTEGER NOT NULL REFERENCES "T_テナント"(id),
                            work_name VARCHAR(255) NOT NULL,
                            start_date VARCHAR(20),
                            fee INTEGER,
                            fee_cycle VARCHAR(20),
                            notes TEXT,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_受託業務テーブルを作成しました")
                else:
                    print("  ℹ️  T_受託業務テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_受託業務'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_受託業務" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            client_id INTEGER NOT NULL,
                            tenant_id INTEGER NOT NULL,
                            work_name TEXT NOT NULL,
                            start_date TEXT,
                            fee INTEGER,
                            fee_cycle TEXT,
                            notes TEXT,
                            created_at TEXT,
                            updated_at TEXT
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_受託業務テーブルを作成しました")
                else:
                    print("  ℹ️  T_受託業務テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        print("\n" + "=" * 60)
        print("マイグレーション完了")
        print("=" * 60)
        conn.close()
    except Exception as e:
        print(f"\n⚠️  マイグレーション全体でエラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    run_migrations()
