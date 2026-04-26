"""
新機能用マイグレーション
- event_presetsテーブルにdays_offset, trigger_event, task_typeカラム追加
- negotiationsテーブルにkanban_order, kanban_stage追加
- dogsテーブルにcoi_value追加
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    migrations = [
        # event_presets拡張
        ("ALTER TABLE event_presets ADD COLUMN days_offset INTEGER DEFAULT 0",
         "event_presets", "days_offset"),
        ("ALTER TABLE event_presets ADD COLUMN trigger_event VARCHAR(50) DEFAULT 'birth'",
         "event_presets", "trigger_event"),
        ("ALTER TABLE event_presets ADD COLUMN task_type VARCHAR(50) DEFAULT 'todo'",
         "event_presets", "task_type"),
        # negotiations拡張（カンバン用）
        ("ALTER TABLE negotiations ADD COLUMN kanban_order INTEGER DEFAULT 0",
         "negotiations", "kanban_order"),
        ("ALTER TABLE negotiations ADD COLUMN kanban_stage VARCHAR(50) DEFAULT 'inquiry'",
         "negotiations", "kanban_stage"),
        ("ALTER TABLE negotiations ADD COLUMN lost_reason TEXT",
         "negotiations", "lost_reason"),
        ("ALTER TABLE negotiations ADD COLUMN contract_date DATE",
         "negotiations", "contract_date"),
        # dogs拡張（COI）
        ("ALTER TABLE dogs ADD COLUMN coi_value REAL",
         "dogs", "coi_value"),
        ("ALTER TABLE dogs ADD COLUMN show_titles TEXT",
         "dogs", "show_titles"),
    ]

    for sql, table, col in migrations:
        # カラムが既に存在するかチェック
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        if col not in cols:
            try:
                cur.execute(sql)
                print(f"✅ {table}.{col} 追加")
            except Exception as e:
                print(f"⚠️ {table}.{col}: {e}")
        else:
            print(f"⏭️ {table}.{col} は既に存在")

    conn.commit()
    conn.close()
    print("マイグレーション完了")

if __name__ == '__main__':
    run()
