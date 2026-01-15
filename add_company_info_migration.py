# add_company_info_migration.py - T_会社基本情報テーブル作成マイグレーション
from app.db import engine
from sqlalchemy import text

def migrate():
    """T_会社基本情報テーブルを作成する"""
    with engine.begin() as conn:
        # テーブルが既に存在するかチェック
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'T_会社基本情報'
            );
        """))
        exists = result.scalar()
        
        if exists:
            print("✅ T_会社基本情報 テーブルは既に存在します")
            return
        
        print("📝 T_会社基本情報 テーブルを作成中...")
        conn.execute(text("""
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
        """))
        print("✅ T_会社基本情報 テーブルを作成しました")

if __name__ == '__main__':
    migrate()
