"""
T_テナント管理者_テナント テーブルに can_manage_tenant_admins カラムを追加するマイグレーション
"""
import os
import sys
from sqlalchemy import create_engine, text

# 環境変数からデータベースURLを取得
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL環境変数が設定されていません")
    sys.exit(1)

# HerokuのPostgreSQLのURLをSQLAlchemy形式に変換
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)

def migrate():
    """マイグレーション実行"""
    with engine.connect() as conn:
        # トランザクション開始
        trans = conn.begin()
        try:
            # カラムが存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='T_テナント管理者_テナント' 
                AND column_name='can_manage_tenant_admins'
            """))
            
            if result.fetchone():
                print("INFO: can_manage_tenant_admins カラムは既に存在します")
            else:
                # カラムを追加
                conn.execute(text("""
                    ALTER TABLE "T_テナント管理者_テナント" 
                    ADD COLUMN can_manage_tenant_admins INTEGER DEFAULT 0
                """))
                print("SUCCESS: can_manage_tenant_admins カラムを追加しました")
            
            # コミット
            trans.commit()
            print("SUCCESS: マイグレーション完了")
            
        except Exception as e:
            trans.rollback()
            print(f"ERROR: マイグレーション失敗: {str(e)}")
            raise

if __name__ == '__main__':
    migrate()
