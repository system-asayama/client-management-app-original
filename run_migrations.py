#!/usr/bin/env python3
"""
Heroku releaseフェーズで実行されるマイグレーションスクリプト
"""
import os
import sys

# アプリケーションのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.db import get_db_connection, _is_pg


def migrate_internal_chat_and_notice_read(conn, is_pg):
    """社内チャット・お知らせ既読テーブルのマイグレーション（PostgreSQL/SQLite対応）"""
    cur = conn.cursor()
    # PostgreSQL用SQL（SERIALを使用）
    pg_tables = [
        ("T_社内チャットルーム", """
            CREATE TABLE IF NOT EXISTS "T_社内チャットルーム" (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                name VARCHAR(255),
                room_type VARCHAR(20) DEFAULT 'direct',
                created_by_id INTEGER,
                created_by_type VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """),
        ("T_社内チャットメンバー", """
            CREATE TABLE IF NOT EXISTS "T_社内チャットメンバー" (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                staff_type VARCHAR(20) DEFAULT 'admin',
                staff_name VARCHAR(255),
                joined_at TIMESTAMP DEFAULT NOW()
            )
        """),
        ("T_社内メッセージ", """
            CREATE TABLE IF NOT EXISTS "T_社内メッセージ" (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                sender_type VARCHAR(20) DEFAULT 'admin',
                sender_name VARCHAR(255),
                message TEXT,
                message_type VARCHAR(20) DEFAULT 'text',
                file_url TEXT,
                file_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """),
        ("T_社内メッセージ既読", """
            CREATE TABLE IF NOT EXISTS "T_社内メッセージ既読" (
                id SERIAL PRIMARY KEY,
                message_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                staff_type VARCHAR(20) DEFAULT 'admin',
                read_at TIMESTAMP DEFAULT NOW()
            )
        """),
        ("T_お知らせ既読", """
            CREATE TABLE IF NOT EXISTS "T_お知らせ既読" (
                id SERIAL PRIMARY KEY,
                notice_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                staff_type VARCHAR(20) DEFAULT 'admin',
                read_at TIMESTAMP DEFAULT NOW()
            )
        """),
    ]
    # SQLite用SQL
    sqlite_tables = [
        ("T_社内チャットルーム", """
            CREATE TABLE IF NOT EXISTS "T_社内チャットルーム" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                name TEXT,
                room_type TEXT DEFAULT 'direct',
                created_by_id INTEGER,
                created_by_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """),
        ("T_社内チャットメンバー", """
            CREATE TABLE IF NOT EXISTS "T_社内チャットメンバー" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                staff_type TEXT DEFAULT 'admin',
                staff_name TEXT,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """),
        ("T_社内メッセージ", """
            CREATE TABLE IF NOT EXISTS "T_社内メッセージ" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                sender_type TEXT DEFAULT 'admin',
                sender_name TEXT,
                message TEXT,
                message_type TEXT DEFAULT 'text',
                file_url TEXT,
                file_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """),
        ("T_社内メッセージ既読", """
            CREATE TABLE IF NOT EXISTS "T_社内メッセージ既読" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                staff_type TEXT DEFAULT 'admin',
                read_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """),
        ("T_お知らせ既読", """
            CREATE TABLE IF NOT EXISTS "T_お知らせ既読" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                staff_type TEXT DEFAULT 'admin',
                read_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """),
    ]
    tables = pg_tables if is_pg else sqlite_tables
    for table_name, sql in tables:
        try:
            cur.execute(sql)
            conn.commit()
            print(f"  ✅ {table_name}テーブルを確認/作成しました")
        except Exception as e:
            print(f"  ⚠️  {table_name}テーブル作成エラー: {e}")
            conn.rollback()


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
            ('salary_office_notification',     'INTEGER DEFAULT 0'),
            ('withholding_tax_special',        'INTEGER DEFAULT 0'),
            ('tax_filing_extension',           'INTEGER DEFAULT 0'),
            ('corp_tax_extension',             'INTEGER DEFAULT 0'),
            ('consumption_tax_extension',      'INTEGER DEFAULT 0'),
            ('local_tax_extension',            'INTEGER DEFAULT 0'),
            ('prefectural_tax_extension',      'INTEGER DEFAULT 0'),
            ('municipal_tax_extension',        'INTEGER DEFAULT 0'),
            ('has_fixed_asset_tax',            'INTEGER DEFAULT 0'),
            ('has_depreciable_asset_tax',      'INTEGER DEFAULT 0'),
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

        # マイグレーション: T_納税実績テーブルを作成
        print("\n[マイグレーション] T_納税実績テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_納税実績'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_納税実績" (
                            id SERIAL PRIMARY KEY,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            fiscal_year INTEGER NOT NULL,
                            fiscal_end_month INTEGER NOT NULL,
                            corporate_tax INTEGER,
                            local_corporate_tax INTEGER,
                            consumption_tax INTEGER,
                            local_consumption_tax INTEGER,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_納税実績テーブルを作成しました")
                else:
                    print("  ℹ️  T_納税実績テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_納税実績'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_納税実績" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            client_id INTEGER NOT NULL,
                            fiscal_year INTEGER NOT NULL,
                            fiscal_end_month INTEGER NOT NULL,
                            corporate_tax INTEGER,
                            local_corporate_tax INTEGER,
                            consumption_tax INTEGER,
                            local_consumption_tax INTEGER,
                            created_at TEXT,
                            updated_at TEXT
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_納税実績テーブルを作成しました")
                else:
                    print("  ℹ️  T_納税実績テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_納税実績_都道府県テーブルを作成
        print("\n[マイグレーション] T_納税実績_都道府県テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_納税実績_都道府県'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_納税実績_都道府県" (
                            id SERIAL PRIMARY KEY,
                            tax_record_id INTEGER NOT NULL REFERENCES "T_納税実績"(id) ON DELETE CASCADE,
                            prefecture_name VARCHAR(100) NOT NULL,
                            equal_levy INTEGER,
                            income_levy INTEGER,
                            business_tax INTEGER,
                            special_business_tax INTEGER
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_納税実績_都道府県テーブルを作成しました")
                else:
                    print("  ℹ️  T_納税実績_都道府県テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_納税実績_都道府県'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_納税実績_都道府県" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            tax_record_id INTEGER NOT NULL,
                            prefecture_name TEXT NOT NULL,
                            equal_levy INTEGER,
                            income_levy INTEGER,
                            business_tax INTEGER,
                            special_business_tax INTEGER
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_納税実績_都道府県テーブルを作成しました")
                else:
                    print("  ℹ️  T_納税実績_都道府県テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_納税実績_市区町村テーブルを作成
        print("\n[マイグレーション] T_納税実績_市区町村テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_納税実績_市区町村'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_納税実績_市区町村" (
                            id SERIAL PRIMARY KEY,
                            tax_record_id INTEGER NOT NULL REFERENCES "T_納税実績"(id) ON DELETE CASCADE,
                            municipality_name VARCHAR(100) NOT NULL,
                            equal_levy INTEGER,
                            corporate_tax_levy INTEGER
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_納税実績_市区町村テーブルを作成しました")
                else:
                    print("  ℹ️  T_納税実績_市区町村テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_納税実績_市区町村'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_納税実績_市区町村" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            tax_record_id INTEGER NOT NULL,
                            municipality_name TEXT NOT NULL,
                            equal_levy INTEGER,
                            corporate_tax_levy INTEGER
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_納税実績_市区町村テーブルを作成しました")
                else:
                    print("  ℹ️  T_納税実績_市区町村テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_申告先_税務署テーブルを作成
        print("\n[マイグレーション] T_申告先_税務署テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_申告先_税務署'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_申告先_税務署" (
                            id SERIAL PRIMARY KEY,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            tax_office_name VARCHAR(100) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_申告先_税務署テーブルを作成しました")
                else:
                    print("  ℹ️  T_申告先_税務署テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_申告先_税務署'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_申告先_税務署" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            client_id INTEGER NOT NULL,
                            tax_office_name TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_申告先_税務署テーブルを作成しました")
                else:
                    print("  ℹ️  T_申告先_税務署テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_申告先_都道府県テーブルを作成
        print("\n[マイグレーション] T_申告先_都道府県テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_申告先_都道府県'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_申告先_都道府県" (
                            id SERIAL PRIMARY KEY,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            prefecture_name VARCHAR(100) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_申告先_都道府県テーブルを作成しました")
                else:
                    print("  ℹ️  T_申告先_都道府県テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_申告先_都道府県'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_申告先_都道府県" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            client_id INTEGER NOT NULL,
                            prefecture_name TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_申告先_都道府県テーブルを作成しました")
                else:
                    print("  ℹ️  T_申告先_都道府県テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_申告先_市区町村テーブルを作成
        print("\n[マイグレーション] T_申告先_市区町村テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_申告先_市区町村'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_申告先_市区町村" (
                            id SERIAL PRIMARY KEY,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            municipality_name VARCHAR(100) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_申告先_市区町村テーブルを作成しました")
                else:
                    print("  ℹ️  T_申告先_市区町村テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_申告先_市区町村'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_申告先_市区町村" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            client_id INTEGER NOT NULL,
                            municipality_name TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_申告先_市区町村テーブルを作成しました")
                else:
                    print("  ℹ️  T_申告先_市区町村テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_会社拠点情報テーブルを作成
        print("\n[マイグレーション] T_会社拠点情報テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_会社拠点情報'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_会社拠点情報" (
                            id SERIAL PRIMARY KEY,
                            company_id INTEGER NOT NULL REFERENCES "T_会社基本情報"(id) ON DELETE CASCADE,
                            branch_type VARCHAR(10) NOT NULL DEFAULT '支店',
                            branch_name VARCHAR(255),
                            "郵便番号" VARCHAR(20),
                            "都道府県" VARCHAR(50),
                            "市区町村番地" VARCHAR(255),
                            "建物名部屋番号" VARCHAR(255),
                            "電話番号1" VARCHAR(50),
                            "電話番号2" VARCHAR(50),
                            "ファックス番号" VARCHAR(50),
                            "メールアドレス" VARCHAR(255),
                            "担当者名" VARCHAR(100),
                            "当拠点従業員数" INTEGER,
                            sort_order INTEGER DEFAULT 0
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_会社拠点情報テーブルを作成しました")
                else:
                    print("  ℹ️  T_会社拠点情報テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_会社拠点情報'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_会社拠点情報" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            company_id INTEGER NOT NULL,
                            branch_type TEXT NOT NULL DEFAULT '支店',
                            branch_name TEXT,
                            郵便番号 TEXT,
                            都道府県 TEXT,
                            市区町村番地 TEXT,
                            建物名部屋番号 TEXT,
                            電話番号1 TEXT,
                            電話番号2 TEXT,
                            ファックス番号 TEXT,
                            メールアドレス TEXT,
                            担当者名 TEXT,
                            当拠点従業員数 INTEGER,
                            sort_order INTEGER DEFAULT 0
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_会社拠点情報テーブルを作成しました")
                else:
                    print("  ℹ️  T_会社拠点情報テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_会社拠点情報に当拠点従業員数カラムを追加
        print("\n[マイグレーション] T_会社拠点情報に当拠点従業員数カラムを追加")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'T_会社拠点情報' AND column_name = '当拠点従業員数'
                """)
                if not cur.fetchone():
                    cur.execute('ALTER TABLE "T_会社拠点情報" ADD COLUMN "当拠点従業員数" INTEGER')
                    conn.commit()
                    print("  ✅ 当拠点従業員数カラムを追加しました")
                else:
                    print("  ℹ️  当拠点従業員数カラムは既に存在します（スキップ）")
            else:
                cur.execute("PRAGMA table_info('T_会社拠点情報')")
                cols = [row[1] for row in cur.fetchall()]
                if '当拠点従業員数' not in cols:
                    cur.execute('ALTER TABLE "T_会社拠点情報" ADD COLUMN 当拠点従業員数 INTEGER')
                    conn.commit()
                    print("  ✅ 当拠点従業員数カラムを追加しました")
                else:
                    print("  ℹ️  当拠点従業員数カラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_外部ストレージ連携にbase_folder_pathカラムを追加
        print("\n[マイグレーション] T_外部ストレージ連携にbase_folder_pathカラムを追加")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'T_外部ストレージ連携' AND column_name = 'base_folder_path'
                """)
                if not cur.fetchone():
                    cur.execute('ALTER TABLE "T_外部ストレージ連携" ADD COLUMN base_folder_path TEXT')
                    conn.commit()
                    print("  ✅ base_folder_pathカラムを追加しました")
                else:
                    print("  ℹ️  base_folder_pathカラムは既に存在します（スキップ）")
            else:
                cur.execute("PRAGMA table_info('T_外部ストレージ連携')")
                cols = [row[1] for row in cur.fetchall()]
                if 'base_folder_path' not in cols:
                    cur.execute('ALTER TABLE "T_外部ストレージ連携" ADD COLUMN base_folder_path TEXT')
                    conn.commit()
                    print("  ✅ base_folder_pathカラムを追加しました")
                else:
                    print("  ℹ️  base_folder_pathカラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_管理者にphone・positionカラムを追加
        print("\n[マイグレーション] T_管理者にphone・positionカラムを追加")
        try:
            if _is_pg(conn):
                for col, coltype in [('phone', 'VARCHAR(50)'), ('position', 'VARCHAR(100)')]:
                    cur.execute(f"""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'T_管理者' AND column_name = '{col}'
                    """)
                    if not cur.fetchone():
                        cur.execute(f'ALTER TABLE "T_管理者" ADD COLUMN {col} {coltype}')
                        conn.commit()
                        print(f"  ✅ T_管理者.{col}カラムを追加しました")
                    else:
                        print(f"  ℹ️  T_管理者.{col}カラムは既に存在します（スキップ）")
            else:
                cur.execute("PRAGMA table_info('T_管理者')")
                cols = [row[1] for row in cur.fetchall()]
                for col, coltype in [('phone', 'TEXT'), ('position', 'TEXT')]:
                    if col not in cols:
                        cur.execute(f'ALTER TABLE "T_管理者" ADD COLUMN {col} {coltype}')
                        conn.commit()
                        print(f"  ✅ T_管理者.{col}カラムを追加しました")
                    else:
                        print(f"  ℹ️  T_管理者.{col}カラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_従業員にphone・positionカラムを追加
        print("\n[マイグレーション] T_従業員にphone・positionカラムを追加")
        try:
            if _is_pg(conn):
                for col, coltype in [('phone', 'VARCHAR(50)'), ('position', 'VARCHAR(100)')]:
                    cur.execute(f"""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'T_従業員' AND column_name = '{col}'
                    """)
                    if not cur.fetchone():
                        cur.execute(f'ALTER TABLE "T_従業員" ADD COLUMN {col} {coltype}')
                        conn.commit()
                        print(f"  ✅ T_従業員.{col}カラムを追加しました")
                    else:
                        print(f"  ℹ️  T_従業員.{col}カラムは既に存在します（スキップ）")
            else:
                cur.execute("PRAGMA table_info('T_従業員')")
                cols = [row[1] for row in cur.fetchall()]
                for col, coltype in [('phone', 'TEXT'), ('position', 'TEXT')]:
                    if col not in cols:
                        cur.execute(f'ALTER TABLE "T_従業員" ADD COLUMN {col} {coltype}')
                        conn.commit()
                        print(f"  ✅ T_従業員.{col}カラムを追加しました")
                    else:
                        print(f"  ℹ️  T_従業員.{col}カラムは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_お知らせテーブルを作成
        print("\n[マイグレーション] T_お知らせテーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_お知らせ'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_お知らせ" (
                            id SERIAL PRIMARY KEY,
                            tenant_id INTEGER NOT NULL REFERENCES "T_テナント"(id) ON DELETE CASCADE,
                            title VARCHAR(255) NOT NULL,
                            body TEXT,
                            author_id INTEGER,
                            author_name VARCHAR(255),
                            is_important INTEGER DEFAULT 0,
                            published_at TIMESTAMP,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_お知らせテーブルを作成しました")
                else:
                    print("  ℹ️  T_お知らせテーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_お知らせ'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_お知らせ" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            tenant_id INTEGER NOT NULL,
                            title TEXT NOT NULL,
                            body TEXT,
                            author_id INTEGER,
                            author_name TEXT,
                            is_important INTEGER DEFAULT 0,
                            published_at DATETIME,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_お知らせテーブルを作成しました")
                else:
                    print("  ℹ️  T_お知らせテーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_勤怠テーブルを作成
        print("\n[マイグレーション] T_勤怠テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_勤怠'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_勤怠" (
                            id SERIAL PRIMARY KEY,
                            tenant_id INTEGER NOT NULL REFERENCES "T_テナント"(id) ON DELETE CASCADE,
                            staff_id INTEGER NOT NULL,
                            staff_type VARCHAR(20) NOT NULL DEFAULT 'admin',
                            staff_name VARCHAR(255),
                            work_date DATE NOT NULL,
                            clock_in TIMESTAMP,
                            clock_out TIMESTAMP,
                            break_minutes INTEGER DEFAULT 60,
                            note TEXT,
                            status VARCHAR(20) DEFAULT 'normal',
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_勤怠テーブルを作成しました")
                else:
                    print("  ℹ️  T_勤怠テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_勤怠'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_勤怠" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            tenant_id INTEGER NOT NULL,
                            staff_id INTEGER NOT NULL,
                            staff_type TEXT NOT NULL DEFAULT 'admin',
                            staff_name TEXT,
                            work_date DATE NOT NULL,
                            clock_in DATETIME,
                            clock_out DATETIME,
                            break_minutes INTEGER DEFAULT 60,
                            note TEXT,
                            status TEXT DEFAULT 'normal',
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_勤怠テーブルを作成しました")
                else:
                    print("  ℹ️  T_勤怠テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # マイグレーション: T_顧問先担当テーブルを作成
        print("\n[マイグレーション] T_顧問先担当テーブルを作成")
        try:
            if _is_pg(conn):
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'T_顧問先担当'
                """)
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_顧問先担当" (
                            id SERIAL PRIMARY KEY,
                            tenant_id INTEGER NOT NULL REFERENCES "T_テナント"(id) ON DELETE CASCADE,
                            client_id INTEGER NOT NULL REFERENCES "T_顧問先"(id) ON DELETE CASCADE,
                            staff_id INTEGER NOT NULL,
                            staff_type VARCHAR(20) NOT NULL DEFAULT 'admin',
                            is_primary INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_顧問先担当テーブルを作成しました")
                else:
                    print("  ℹ️  T_顧問先担当テーブルは既に存在します（スキップ）")
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='T_顧問先担当'")
                if not cur.fetchone():
                    cur.execute("""
                        CREATE TABLE "T_顧問先担当" (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            tenant_id INTEGER NOT NULL,
                            client_id INTEGER NOT NULL,
                            staff_id INTEGER NOT NULL,
                            staff_type TEXT NOT NULL DEFAULT 'admin',
                            is_primary INTEGER DEFAULT 0,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    print("  ✅ T_顧問先担当テーブルを作成しました")
                else:
                    print("  ℹ️  T_顧問先担当テーブルは既に存在します（スキップ）")
        except Exception as e:
            print(f"  ⚠️  マイグレーションエラー: {e}")
            conn.rollback()

        # T_勤怠にbreak_start・break_endカラムを追加
        print("\n[マイグレーション] T_勤怠にbreak_start・break_endカラムを追加...")
        try:
            is_pg = _is_pg(conn)
            if is_pg:
                for col, col_type in [('break_start', 'TIMESTAMP'), ('break_end', 'TIMESTAMP')]:
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'T_勤怠' AND column_name = %s
                    """, (col,))
                    if not cur.fetchone():
                        cur.execute(f'ALTER TABLE "T_勤怠" ADD COLUMN {col} TIMESTAMP')
                        conn.commit()
                        print(f'  ✅ T_勤怠.{col}カラムを追加しました')
                    else:
                        print(f'  ℹ️  T_勤怠.{col}カラムは既に存在します（スキップ）')
            else:
                cur.execute('PRAGMA table_info("T_勤怠")')
                existing = [row[1] for row in cur.fetchall()]
                for col in ['break_start', 'break_end']:
                    if col not in existing:
                        cur.execute(f'ALTER TABLE "T_勤怠" ADD COLUMN {col} DATETIME')
                        conn.commit()
                        print(f'  ✅ T_勤怠.{col}カラムを追加しました')
                    else:
                        print(f'  ℹ️  T_勤怠.{col}カラムは既に存在します（スキップ）')
        except Exception as e:
            print(f'  ⚠️  マイグレーションエラー: {e}')
            conn.rollback()

        # 社内チャット・お知らせ既読テーブルのマイグレーション
        print("\n[マイグレーション] 社内チャット・お知らせ既読テーブルを作成...")
        try:
            is_pg = _is_pg(conn)
            migrate_internal_chat_and_notice_read(conn, is_pg)
        except Exception as e:
            print(f"  ⚠️  社内チャットマイグレーションエラー: {e}")
        # T_テナントにandroid_apk_urlカラムを追加
        print("\n[マイグレーション] T_テナントにandroid_apk_urlカラムを追加...")
        try:
            is_pg = _is_pg(conn)
            if is_pg:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'T_テナント' AND column_name = 'android_apk_url'
                """)
                if not cur.fetchone():
                    cur.execute('ALTER TABLE "T_テナント" ADD COLUMN android_apk_url TEXT')
                    conn.commit()
                    print('  ✅ T_テナント.android_apk_urlカラムを追加しました')
                else:
                    print('  ℹ️  T_テナント.android_apk_urlカラムは既に存在します（スキップ）')
            else:
                cur.execute('PRAGMA table_info("T_テナント")')
                existing = [row[1] for row in cur.fetchall()]
                if 'android_apk_url' not in existing:
                    cur.execute('ALTER TABLE "T_テナント" ADD COLUMN android_apk_url TEXT')
                    conn.commit()
                    print('  ✅ T_テナント.android_apk_urlカラムを追加しました')
                else:
                    print('  ℹ️  T_テナント.android_apk_urlカラムは既に存在します（スキップ）')
        except Exception as e:
            print(f'  ⚠️  android_apk_urlマイグレーションエラー: {e}')
            conn.rollback()
        # T_テナントにandroid_apk_versionカラムを追加
        print("\n[マイグレーション] T_テナントにandroid_apk_versionカラムを追加...")
        try:
            is_pg = _is_pg(conn)
            if is_pg:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'T_\u30c6\u30ca\u30f3\u30c8' AND column_name = 'android_apk_version'
                """)
                if not cur.fetchone():
                    cur.execute('ALTER TABLE "T_\u30c6\u30ca\u30f3\u30c8" ADD COLUMN android_apk_version VARCHAR(20)')
                    conn.commit()
                    print('  \u2705 T_\u30c6\u30ca\u30f3\u30c8.android_apk_version\u30ab\u30e9\u30e0\u3092\u8ffd\u52a0\u3057\u307e\u3057\u305f')
                else:
                    print('  \u2139\ufe0f  T_\u30c6\u30ca\u30f3\u30c8.android_apk_version\u30ab\u30e9\u30e0\u306f\u65e2\u306b\u5b58\u5728\u3057\u307e\u3059\uff08\u30b9\u30ad\u30c3\u30d7\uff09')
            else:
                cur.execute('PRAGMA table_info("T_\u30c6\u30ca\u30f3\u30c8")')
                existing = [row[1] for row in cur.fetchall()]
                if 'android_apk_version' not in existing:
                    cur.execute('ALTER TABLE "T_\u30c6\u30ca\u30f3\u30c8" ADD COLUMN android_apk_version VARCHAR(20)')
                    conn.commit()
                    print('  \u2705 T_\u30c6\u30ca\u30f3\u30c8.android_apk_version\u30ab\u30e9\u30e0\u3092\u8ffd\u52a0\u3057\u307e\u3057\u305f')
                else:
                    print('  \u2139\ufe0f  T_\u30c6\u30ca\u30f3\u30c8.android_apk_version\u30ab\u30e9\u30e0\u306f\u65e2\u306b\u5b58\u5728\u3057\u307e\u3059\uff08\u30b9\u30ad\u30c3\u30d7\uff09')
        except Exception as e:
            print(f'  \u26a0\ufe0f  android_apk_version\u30de\u30a4\u30b0\u30ec\u30fc\u30b7\u30e7\u30f3\u30a8\u30e9\u30fc: {e}')
            conn.rollback()

        # 通帳明細・クレジット明細テーブルの自動作成
        print("\n[マイグレーション] 通帳明細・クレジット明細テーブルを作成...")
        try:
            from app.db import Base, engine
            from app import models_voucher  # noqa: F401 - TBankStatement、TCreditStatementなどをBaseに登録
            Base.metadata.create_all(bind=engine)
            print("  ✅ 通帳明細・クレジット明細テーブル作成完了")
        except Exception as e:
            print(f"  ⚠️ 通帳明細・クレジット明細テーブル作成エラー: {e}")

        print("\n" + "=" * 60)
        print("マイグレーション完了")
        print("=" * 60)
        conn.close()
    except Exception as e:
        print(f"\n⚠️  マイグレーション全体でエラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    run_migrations()
