"""
マイグレーション: T_従業員テーブルにgps_modeカラムを追加

GPS追跡モードを従業員個人単位で設定できるようにする。
- always: 勤務中常時GPS追跡（デフォルト）
- checkin_only: 出退勤打刻時のみGPS送信
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, engine
from sqlalchemy import text


def run_migration():
    db = SessionLocal()
    try:
        # カラムが既に存在するか確認
        result = db.execute(text("""
            SELECT COUNT(*) as cnt
            FROM information_schema.columns
            WHERE table_name = 'T_従業員'
            AND column_name = 'gps_mode'
        """)).fetchone()

        if result and result[0] > 0:
            print("gps_modeカラムは既に存在します。スキップします。")
            return

        # カラムを追加
        db.execute(text("""
            ALTER TABLE `T_従業員`
            ADD COLUMN `gps_mode` VARCHAR(20) DEFAULT 'always'
            COMMENT 'GPS追跡モード: always=常時追跡, checkin_only=出退勤時のみ'
        """))
        db.commit()
        print("T_従業員テーブルにgps_modeカラムを追加しました。")

    except Exception as e:
        db.rollback()
        print(f"マイグレーションエラー: {e}")
        raise
    finally:
        db.close()


if __name__ == '__main__':
    run_migration()
