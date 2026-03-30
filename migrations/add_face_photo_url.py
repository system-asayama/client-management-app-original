"""
マイグレーション: T_従業員・T_管理者テーブルに face_photo_url カラムを追加

実行方法:
    python migrations/add_face_photo_url.py

対象テーブル:
    - T_従業員 (TJugyoin)
    - T_管理者 (TKanrisha)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        # T_従業員 に face_photo_url を追加
        try:
            conn.execute(text(
                "ALTER TABLE \"T_従業員\" ADD COLUMN face_photo_url TEXT"
            ))
            conn.commit()
            print("✅ T_従業員.face_photo_url カラムを追加しました")
        except Exception as e:
            if 'already exists' in str(e).lower() or 'duplicate column' in str(e).lower():
                print("ℹ️  T_従業員.face_photo_url は既に存在します（スキップ）")
            else:
                print(f"⚠️  T_従業員.face_photo_url 追加エラー: {e}")

        # T_管理者 に face_photo_url を追加
        try:
            conn.execute(text(
                "ALTER TABLE \"T_管理者\" ADD COLUMN face_photo_url TEXT"
            ))
            conn.commit()
            print("✅ T_管理者.face_photo_url カラムを追加しました")
        except Exception as e:
            if 'already exists' in str(e).lower() or 'duplicate column' in str(e).lower():
                print("ℹ️  T_管理者.face_photo_url は既に存在します（スキップ）")
            else:
                print(f"⚠️  T_管理者.face_photo_url 追加エラー: {e}")

    print("マイグレーション完了")

if __name__ == '__main__':
    run()
