from app.db import engine
from sqlalchemy import inspect

inspector = inspect(engine)
tables = inspector.get_table_names()

print('既存テーブル:')
for t in sorted(tables):
    print(f'  - {t}')

print()
if 'T_会社基本情報' in tables:
    print('✅ T_会社基本情報 テーブルは存在します')
    columns = inspector.get_columns('T_会社基本情報')
    print('カラム:')
    for col in columns:
        print(f'  - {col["name"]}: {col["type"]}')
else:
    print('❌ T_会社基本情報 テーブルは存在しません')
