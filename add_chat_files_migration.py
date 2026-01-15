# このコードをrun_migrations.pyのT_会社基本情報マイグレーションの後に追加する

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
                # SQLite用の処理
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
                # SQLite用の処理
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
