# Client Management System (顧問先管理システム)

Flask製の顧問先・クライアント管理システム

## 概要

このアプリケーションは、税理士法人や会計事務所が顧問先（クライアント）を効率的に管理するためのシステムです。

## 主な機能

### 顧問先管理
- 顧問先の登録・編集・削除
- 顧問先情報の一覧表示
- 顧問先詳細情報の閲覧

### 4ロール認証システム
- **システム管理者 (system_admin)**: 全テナント横断の最高権限
- **テナント管理者 (tenant_admin)**: テナント単位の管理者
- **管理者 (admin)**: 店舗/拠点などの管理者
- **従業員 (employee)**: 一般従業員

### データベース対応
- PostgreSQL / SQLite 自動切り替え
- 優先順位: .env/環境変数 DATABASE_URL → ローカルPostgreSQL → SQLite
- スキーマ自動作成（冪等性保証）

### セキュリティ機能
- パスワードハッシュ化（werkzeug.security）
- CSRF保護
- セッション管理
- ロールベースアクセス制御

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example`を`.env`にコピーして編集:

```bash
cp .env.example .env
```

`.env`ファイルの内容:

```env
SECRET_KEY=your-secret-key-here-change-in-production
DATABASE_URL=postgresql://postgres:password@localhost:5432/client_management_dev
```

### 3. アプリケーションの起動

#### ローカル開発環境

```bash
python wsgi.py
```

または

```bash
flask run
```

#### 本番環境（Heroku等）

```bash
gunicorn wsgi:app
```

## データベーススキーマ

### T_顧問先 (T_Client)
- 顧問先情報を管理
- フィールド: id, tenant_id, name, postal_code, address, phone, email, created_at, updated_at

### T_管理者
- システム管理者、テナント管理者、管理者のログイン情報を管理
- フィールド: id, login_id, name, password_hash, role, tenant_id, created_at, updated_at

### T_従業員
- 従業員のログイン情報を管理
- フィールド: id, email, login_id, name, password_hash, tenant_id, role, created_at, updated_at

### T_テナント
- テナント情報を管理
- フィールド: id, name, created_at

## ルーティング

### 認証関連
- `/` - トップページ（ロール別リダイレクト）
- `/select_login` - ログイン選択画面
- `/first_admin_setup` - 初回管理者セットアップ
- `/system_admin_login` - システム管理者ログイン
- `/tenant_admin_login` - テナント管理者ログイン
- `/admin_login` - 管理者ログイン
- `/employee_login` - 従業員ログイン
- `/logout` - ログアウト

### ダッシュボード
- `/system_admin/` - システム管理者ダッシュボード
- `/tenant_admin/` - テナント管理者ダッシュボード
- `/admin/` - 管理者ダッシュボード
- `/employee/mypage` - 従業員マイページ

### 顧問先管理
- `/clients/` - 顧問先一覧
- `/clients/add` - 顧問先追加
- `/clients/<id>` - 顧問先詳細
- `/clients/<id>/edit` - 顧問先編集
- `/clients/<id>/delete` - 顧問先削除

## ディレクトリ構造

```
client-management-app-original/
├── app/
│   ├── __init__.py          # アプリケーションファクトリ
│   ├── config.py            # 設定ファイル
│   ├── logging.py           # ロギング設定
│   ├── models_clients.py    # 顧問先モデル
│   ├── utils/               # ユーティリティモジュール
│   ├── blueprints/          # Blueprint（機能別ルート）
│   │   ├── clients.py       # 顧問先管理
│   │   ├── auth.py          # 認証関連
│   │   ├── system_admin.py  # システム管理者
│   │   ├── tenant_admin.py  # テナント管理者
│   │   └── ...
│   └── templates/           # Jinjaテンプレート
│       ├── clients.html     # 顧問先一覧
│       ├── client_info.html # 顧問先詳細
│       └── ...
├── database/                # SQLiteデータベース（.gitignore）
├── requirements.txt         # 依存パッケージ
├── .env.example             # 環境変数サンプル
├── wsgi.py                  # WSGIエントリーポイント
├── Procfile                 # Heroku設定
└── README.md                # このファイル
```

## 開発

### テストサーバーの起動

```bash
python wsgi.py
```

ブラウザで `http://localhost:5000` にアクセス

### 初回セットアップ

1. アプリケーションを起動
2. 自動的に `/first_admin_setup` にリダイレクトされる
3. 最初のシステム管理者アカウントを作成
4. ログイン画面からログイン

## アプリ識別情報

- **アプリ名**: `client-management`
- **表示名**: 顧問先管理システム
- **スコープ**: tenant
- **説明**: 顧問先・クライアント管理システム

## ライセンス

MIT License

---

最終更新: 2026-01-24
