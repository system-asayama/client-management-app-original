# ログインシステム移植ガイド

**著者**: Manus AI  
**作成日**: 2025年12月29日  
**バージョン**: 1.0

---

## 1. はじめに

本ガイドは、`login-system-app` を基盤として新しいビジネスアプリケーション（例: `survey-system-app`、`invoice-system-app`）を開発するための手順を詳細に説明します。このログインシステムは、**マルチテナント・マルチストア**のアーキテクチャを採用しており、コンサルタントや会計士が顧客企業に対してサービスを提供する際の認証・権限管理基盤として設計されています。

### 1.1. 対象読者

本ガイドは、以下の読者を対象としています。

- Flaskを使用したWebアプリケーション開発の経験がある開発者
- PostgreSQLやSQLiteなどのリレーショナルデータベースの基本的な知識を持つ方
- Herokuへのデプロイ経験がある、または学習意欲のある方

### 1.2. システムの概要

ログインシステムは、4つのユーザーレベルで構成されています。

| ユーザーレベル         | 説明                                                                 |
| ---------------------- | -------------------------------------------------------------------- |
| **システム管理者**     | 全テナント横断の最高権限を持ち、テナントやアプリケーションを管理     |
| **テナント管理者**     | 特定のテナント内で店舗や管理者を管理                                 |
| **店舗管理者**         | 特定の店舗内で従業員やアプリケーションを管理                         |
| **従業員**             | 店舗内で業務アプリケーションを利用                                   |

このシステムは、**認証・権限管理**と**業務ロジック**を明確に分離しており、ログインシステムを他のアプリケーションに移植することで、迅速に新しいビジネスアプリケーションを構築できます。

---

## 2. 前提条件

移植作業を開始する前に、以下の環境が整っていることを確認してください。

### 2.1. ソフトウェア要件

- **Python**: 3.9以上
- **pip**: Pythonパッケージマネージャー
- **Git**: バージョン管理システム
- **Heroku CLI**: Herokuへのデプロイに必要（オプション）
- **PostgreSQL**: 本番環境で使用（開発環境ではSQLiteも可）

### 2.2. 必要な知識

- Flaskフレームワークの基本的な理解
- SQLAlchemyを使用したデータベース操作
- Jinja2テンプレートエンジンの使用方法
- Blueprintによるモジュール化の概念

---

## 3. 移植手順

### 3.1. プロジェクトのコピー

まず、`login-system-app` ディレクトリを新しいプロジェクト名でコピーします。ここでは、`survey-system-app` という名前で新しいアプリケーションを作成する例を示します。

```bash
# login-system-appをsurvey-system-appとしてコピー
cp -r login-system-app/ survey-system-app

# 新しいディレクトリに移動
cd survey-system-app
```

### 3.2. Gitリポジトリの初期化

既存のGit履歴を削除し、新しいリポジトリとして初期化します。

```bash
# 既存の.gitディレクトリを削除
rm -rf .git

# 新しいGitリポジトリを初期化
git init

# 全てのファイルをステージング
git add .

# 初回コミット
git commit -m "Initial commit: Copied from login-system-app"
```

### 3.3. GitHubリポジトリの作成とプッシュ

GitHub上に新しいリポジトリを作成し、ローカルリポジトリをプッシュします。

```bash
# GitHubに新しいリポジトリを作成（GitHub CLIを使用）
gh repo create system-asayama/survey-system-app --private

# リモートリポジトリを追加
git remote add origin https://github.com/system-asayama/survey-system-app.git

# mainブランチにプッシュ
git push -u origin main
```

### 3.4. 仮想環境の作成とパッケージのインストール

Pythonの仮想環境を作成し、必要なパッケージをインストールします。

```bash
# 仮想環境を作成
python3 -m venv venv

# 仮想環境を有効化（Linux/Mac）
source venv/bin/activate

# 仮想環境を有効化（Windows）
# venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt
```

### 3.5. 環境変数の設定

`.env` ファイルを作成し、アプリケーションの設定を行います。

```bash
# .envファイルを作成
touch .env
```

`.env` ファイルに以下の内容を記述します。

```env
# Flask設定
FLASK_APP=app.py
FLASK_ENV=development

# データベース設定（開発環境）
DATABASE_URL=sqlite:///project.db

# セキュリティ設定
SECRET_KEY=your-secret-key-here

# ライセンス管理（利用可能なアプリケーション）
LICENSED_APPS=survey,invoice,quote
```

**注意**: `SECRET_KEY` は、以下のコマンドで生成できます。

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3.6. データベースの初期化

Flask-Migrateを使用してデータベースを初期化します。

```bash
# マイグレーションディレクトリを作成（初回のみ）
flask db init

# マイグレーションファイルを生成
flask db migrate -m "Initial migration"

# データベースにマイグレーションを適用
flask db upgrade
```

### 3.7. 初期データの投入

システム管理者やテナントなどの初期データを投入します。`seed_data.py` スクリプトが用意されている場合は、以下のコマンドで実行します。

```bash
python seed_data.py
```

### 3.8. ローカルでの動作確認

開発サーバーを起動し、ブラウザで動作を確認します。

```bash
flask run
```

ブラウザで `http://localhost:5000` にアクセスし、ログイン画面が表示されることを確認します。

---

## 4. Herokuへのデプロイ

### 4.1. Herokuアプリケーションの作成

Heroku CLIを使用して新しいアプリケーションを作成します。

```bash
heroku create survey-system-app-unique-name
```

### 4.2. PostgreSQLアドオンの追加

本番環境ではPostgreSQLを使用します。

```bash
heroku addons:create heroku-postgresql:essential-0
```

### 4.3. 環境変数の設定

Heroku上で環境変数を設定します。

```bash
heroku config:set FLASK_APP=app.py
heroku config:set FLASK_ENV=production
heroku config:set SECRET_KEY=your-production-secret-key
heroku config:set LICENSED_APPS=survey,invoice
```

### 4.4. デプロイ

Gitを使用してHerokuにデプロイします。

```bash
git push heroku main
```

### 4.5. データベースのマイグレーション

Heroku上でデータベースのマイグレーションを実行します。

```bash
heroku run flask db upgrade
```

### 4.6. 初期データの投入

Heroku上で初期データを投入します。

```bash
heroku run python seed_data.py
```

### 4.7. 動作確認

ブラウザでHerokuアプリケーションのURLにアクセスし、正常に動作することを確認します。

```bash
heroku open
```

---

## 5. アプリケーション固有の機能追加

移植が完了したら、新しいビジネスロジックを追加します。

### 5.1. 新しいBlueprintの作成

例えば、アンケート機能を追加する場合、`app/blueprints/survey.py` を作成します。

```python
from flask import Blueprint, render_template
from app.utils.decorators import require_app_enabled

survey_bp = Blueprint('survey', __name__, url_prefix='/survey')

@survey_bp.route('/')
@require_app_enabled('survey')
def index():
    return render_template('survey_index.html')
```

### 5.2. Blueprintの登録

`app/__init__.py` で新しいBlueprintを登録します。

```python
from app.blueprints.survey import survey_bp

def create_app():
    app = Flask(__name__)
    # ... 他の設定 ...
    
    app.register_blueprint(survey_bp)
    
    return app
```

### 5.3. AVAILABLE_APPSへの追加

`app/blueprints/system_admin.py` および `app/blueprints/tenant_admin.py` の `AVAILABLE_APPS` リストに新しいアプリケーションを追加します。詳細は「AVAILABLE_APPSの定義方法」ドキュメントを参照してください。

---

## 6. データベーステーブルの追加

新しい機能に必要なテーブルを追加します。

### 6.1. モデルの作成

`app/models.py` に新しいモデルを追加します。

```python
class Survey(db.Model):
    __tablename__ = 'T_アンケート'
    
    id = db.Column(db.Integer, primary_key=True)
    店舗ID = db.Column(db.Integer, db.ForeignKey('T_店舗.id'), nullable=False)
    タイトル = db.Column(db.String(200), nullable=False)
    説明 = db.Column(db.Text)
    作成日時 = db.Column(db.DateTime, default=datetime.utcnow)
```

### 6.2. マイグレーションの実行

```bash
flask db migrate -m "Add Survey table"
flask db upgrade
```

---

## 7. テストとデバッグ

### 7.1. ユニットテストの作成

`tests/` ディレクトリにテストファイルを作成します。

```python
import unittest
from app import create_app, db

class SurveyTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        
    def test_survey_index(self):
        response = self.client.get('/survey/')
        self.assertEqual(response.status_code, 302)  # リダイレクト
```

### 7.2. テストの実行

```bash
python -m unittest discover tests
```

---

## 8. まとめ

本ガイドに従うことで、`login-system-app` を基盤として新しいビジネスアプリケーションを迅速に構築できます。認証・権限管理の基盤が整っているため、開発者はビジネスロジックの実装に集中できます。

### 8.1. 次のステップ

- `AVAILABLE_APPS` の定義方法を学び、アプリケーションを追加する
- UIのカスタマイズを行い、ブランディングを適用する
- APIエンドポイントを追加し、外部システムとの連携を実現する

---

## 9. トラブルシューティング

### 9.1. データベース接続エラー

**症状**: `OperationalError: unable to open database file`

**解決策**: `DATABASE_URL` が正しく設定されているか確認してください。

### 9.2. マイグレーションエラー

**症状**: `alembic.util.exc.CommandError: Can't locate revision identified by 'xxxxx'`

**解決策**: マイグレーション履歴をリセットし、再度マイグレーションを実行してください。

```bash
rm -rf migrations/
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

### 9.3. Herokuデプロイエラー

**症状**: `Error: Failed to push some refs to 'https://git.heroku.com/xxx.git'`

**解決策**: Herokuのリモートリポジトリが正しく設定されているか確認してください。

```bash
git remote -v
```

---

## 10. 参考資料

- [Flask公式ドキュメント](https://flask.palletsprojects.com/)
- [Flask-SQLAlchemy公式ドキュメント](https://flask-sqlalchemy.palletsprojects.com/)
- [Heroku公式ドキュメント](https://devcenter.heroku.com/)
