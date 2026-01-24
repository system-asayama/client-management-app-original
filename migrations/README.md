# データベースマイグレーション

## app_name → app_id リネーム

### 実行方法

#### ローカル環境
```bash
cd /path/to/app
python3 migrations/rename_app_name_to_app_id.py
```

#### Heroku環境
```bash
heroku run python migrations/rename_app_name_to_app_id.py -a <app-name>
```

### 対象テーブル
- `T_テナントアプリ設定`
- `T_店舗アプリ設定`

### 変更内容
- `app_name` カラムを `app_id` にリネーム
- データ型: VARCHAR(255) NOT NULL

### 注意事項
- このマイグレーションは冪等性があります（複数回実行しても安全）
- カラムが既に存在しない場合はスキップされます
- エラーが発生した場合は自動的にロールバックされます
