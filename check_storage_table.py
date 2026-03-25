from app.db import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    result = db.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'T_外部ストレージ連携' ORDER BY ordinal_position"
    ))
    rows = result.fetchall()
    if rows:
        for row in rows:
            print(row)
    else:
        print("テーブルが見つかりません")
        # テーブル一覧を表示
        r2 = db.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
        ))
        print("=== 全テーブル一覧 ===")
        for row in r2:
            print(row[0])
finally:
    db.close()
