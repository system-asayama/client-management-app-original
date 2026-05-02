# BreederOS — 犬の繁殖データプラットフォーム

> 単なる繁殖ツールではなく、ブリーダーと飼い主を繋ぐ**業界標準データプラットフォーム**

Flask 製のマルチテナント SaaS。繁殖管理・遺伝分析・飼い主連携・課金・KPI を統合し、データが蓄積されるほど価値が高まるネットワーク効果を実現します。

本番環境: [https://samurai-hub.com](https://samurai-hub.com)

---

## プラットフォームアーキテクチャ

```
飼い主増加 → データ増加 → 分析精度向上 → ブリーダー価値向上 → ブリーダー増加 → さらに飼い主増加
```

---

## プラットフォーム機能（新規追加）

### 1. プラン課金システム

| プラン | 月額 | 主な機能 |
|--------|------|----------|
| フリー | 無料 | 犬5頭まで・簡易COI・基本交配評価 |
| スタンダード | 月額 | 犬無制限・詳細COI・AVK・遺伝病リスク |
| プロ | 月額 | 繁殖履歴分析・候補比較・詳細レポート |
| エンタープライズ | 別途 | API連携・カスタム分析・専用サポート |

**実装:** `app/models_breeder.py`（Plan/Subscription/StripeCustomer/FeatureUsage）、`app/services/plan_guard.py`

### 2. ブリーダープロフィール・評価スコア

- ブリーダーページ公開（kennel_name, location, verified バッジ）
- 評価スコア算出（平均COI・産子生存率・疾患発生率・繁殖成功率・データ登録率）
- ランク付け（S/A/B/C）・強み/弱みの自動分析

**実装:** `app/models_breeder.py`（BreederProfile/BreederScore）、`app/services/breeder_score.py`

### 3. 管理者KPIダッシュボード

- アクティブブリーダー数・飼い主数・登録犬数をリアルタイム集計
- KPIスナップショット（日次記録）・Chart.js によるトレンドグラフ

**実装:** `app/models_breeder.py`（KpiSnapshot）、`/breeder/admin/kpi`

### 4. プランガード（機能制限）

- プランに応じて機能アクセスを制御
- フリープランでは高度な分析機能をブロック → アップグレード誘導
- `@require_plan('pro')` デコレータで各エンドポイントを保護

### 5. ブリーダー検索・リード獲得

- 犬種・地域・ケンネル名での検索
- 飼い主 → ブリーダーへのリード獲得フロー

### 6. ロックイン戦略

- データエクスポートはプロプラン以上で利用可能
- 繁殖履歴・スコア履歴の蓄積により乗り換えコストが増加
- 独自スコア（BreederScore）により他社との差別化

---

## DBスキーマ（プラットフォーム関連）

| テーブル | 説明 |
|----------|------|
| `plans` | プラン定義（free/standard/pro/enterprise） |
| `subscriptions` | テナント別サブスクリプション状態 |
| `stripe_customers` | Stripe顧客ID管理 |
| `feature_usages` | 機能利用ログ（KPI計測用） |
| `breeder_profiles` | ブリーダー公開プロフィール |
| `breeder_scores` | ブリーダー評価スコア（定期更新） |
| `kpi_snapshots` | 日次KPIスナップショット |
| `breeder_reviews` | ブリーダーレビュー（将来拡張用） |

---

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
