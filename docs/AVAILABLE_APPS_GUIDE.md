# AVAILABLE_APPSの定義方法ガイド

**著者**: Manus AI  
**作成日**: 2025年12月29日  
**バージョン**: 1.0

---

## 1. はじめに

本ガイドは、`login-system-app` に新しいビジネスアプリケーションを追加する際に、`AVAILABLE_APPS` リストをどのように定義・利用するかを詳細に説明します。`AVAILABLE_APPS` は、システムで利用可能なアプリケーションのメタデータを管理する中心的な仕組みであり、テナント管理者や店舗管理者がアプリケーションの有効化・無効化を制御するための基盤となります。

### 1.1. 対象読者

本ガイドは、以下の読者を対象としています。

- `login-system-app` を基盤として新しいアプリケーションを開発する開発者
- アプリケーションの追加・管理方法を理解したい方
- マルチテナント・マルチストアのアーキテクチャに興味がある方

---

## 2. AVAILABLE_APPSとは

`AVAILABLE_APPS` は、システムで利用可能なアプリケーションのメタデータを定義するPythonのリストです。このリストは以下のファイルに存在します。

- `app/blueprints/system_admin.py`（システム管理者用）
- `app/blueprints/tenant_admin.py`（テナント管理者用）

各アプリケーションは辞書（`dict`）として定義され、以下のキーを持ちます。

### 2.1. アプリケーション定義の構造

| キー             | 型      | 必須 | 説明                                                                 |
| ---------------- | ------- | ---- | -------------------------------------------------------------------- |
| `name`           | `str`   | ✓    | アプリケーションの一意な識別子（例: `survey`）                       |
| `display_name`   | `str`   | ✓    | UIに表示される名前（例: `アンケート`）                               |
| `description`    | `str`   | ✓    | アプリケーションの簡単な説明                                         |
| `scope`          | `str`   | ✓    | アプリケーションのスコープ（`store` または `tenant`）                 |
| `url`            | `str`   | ✓    | アプリケーションのエンドポイント（例: `survey.index`）                |
| `icon`           | `str`   | ✓    | Font Awesomeのアイコンクラス名（例: `fas fa-poll`）                  |
| `color`          | `str`   | ✓    | アイコンの背景色（例: `bg-primary`、`bg-success`）                   |

### 2.2. スコープについて

**スコープ**は、アプリケーションがどのレベルで管理されるかを示します。

- **`store`**: 店舗レベルで管理されるアプリケーション（例: アンケート、在庫管理）
- **`tenant`**: テナントレベルで管理されるアプリケーション（例: 請求書、会計システム）

店舗レベルのアプリケーションは、各店舗で個別に有効化・無効化できます。テナントレベルのアプリケーションは、テナント全体で一括管理されます。

---

## 3. AVAILABLE_APPSの定義例

以下は、`survey-app`（アンケート）と`invoice-app`（請求書）を追加する場合の `AVAILABLE_APPS` の定義例です。

### 3.1. システム管理者用（`app/blueprints/system_admin.py`）

```python
AVAILABLE_APPS = [
    {
        'name': 'survey',
        'display_name': 'アンケート',
        'description': '顧客満足度調査や市場調査を実施します。',
        'scope': 'store',
        'url': 'survey.index',
        'icon': 'fas fa-poll',
        'color': 'bg-success'
    },
    {
        'name': 'invoice',
        'display_name': '請求書',
        'description': '請求書を作成・管理します。',
        'scope': 'tenant',
        'url': 'invoice.index',
        'icon': 'fas fa-file-invoice-dollar',
        'color': 'bg-info'
    },
    {
        'name': 'quote',
        'display_name': '見積書',
        'description': '見積書を作成・管理します。',
        'scope': 'store',
        'url': 'quote.index',
        'icon': 'fas fa-file-alt',
        'color': 'bg-warning'
    },
    {
        'name': 'decision',
        'display_name': '意思決定支援',
        'description': 'データに基づく意思決定を支援します。',
        'scope': 'tenant',
        'url': 'decision.index',
        'icon': 'fas fa-chart-line',
        'color': 'bg-danger'
    }
]
```

### 3.2. テナント管理者用（`app/blueprints/tenant_admin.py`）

テナント管理者用の `AVAILABLE_APPS` も同様に定義します。通常は、システム管理者用と同じ定義を使用しますが、テナント管理者には表示しないアプリケーションがある場合は、フィルタリングを行います。

---

## 4. ライセンス管理

環境変数 `LICENSED_APPS` を使用して、特定のインスタンスで有効になるアプリケーションを制御します。これにより、コンサルタントや会計士ごとに異なるアプリケーションセットを提供できます。

### 4.1. 環境変数の設定

`.env` ファイルまたはHerokuの環境変数に以下のように設定します。

```env
LICENSED_APPS=survey,invoice,quote
```

この設定により、`survey`、`invoice`、`quote` のみがシステムで利用可能になります。`decision` は表示されません。

### 4.2. ライセンスチェックのロジック

`admin.py` の `store_apps()` 関数内で、以下のようにライセンスチェックが行われます。

```python
import os

# 環境変数からライセンス情報を取得
licensed_apps = os.getenv('LICENSED_APPS', '').split(',')
licensed_apps = [app.strip() for app in licensed_apps if app.strip()]

# AVAILABLE_APPSをフィルタリング
available_apps = [app for app in AVAILABLE_APPS if app['name'] in licensed_apps]
```

このロジックにより、ライセンスされていないアプリケーションは表示されません。

---

## 5. データベーステーブルとの連携

アプリケーションの有効化・無効化は、以下の2つのテーブルで管理されます。

### 5.1. テナントレベルのアプリ設定（`T_テナントアプリ設定`）

| カラム名       | 型          | 説明                                   |
| -------------- | ----------- | -------------------------------------- |
| `id`           | `Integer`   | プライマリキー                         |
| `テナントID`   | `Integer`   | テナントID（外部キー）                 |
| `アプリ名`     | `String`    | アプリケーション名（`name`に対応）     |
| `有効フラグ`   | `Boolean`   | 有効化されているか（`True`/`False`）   |
| `作成日時`     | `DateTime`  | レコード作成日時                       |
| `更新日時`     | `DateTime`  | レコード更新日時                       |

### 5.2. 店舗レベルのアプリ設定（`T_店舗アプリ設定`）

| カラム名       | 型          | 説明                                   |
| -------------- | ----------- | -------------------------------------- |
| `id`           | `Integer`   | プライマリキー                         |
| `店舗ID`       | `Integer`   | 店舗ID（外部キー）                     |
| `アプリ名`     | `String`    | アプリケーション名（`name`に対応）     |
| `有効フラグ`   | `Boolean`   | 有効化されているか（`True`/`False`）   |
| `作成日時`     | `DateTime`  | レコード作成日時                       |
| `更新日時`     | `DateTime`  | レコード更新日時                       |

### 5.3. アプリ表示のロジック

店舗管理者がアプリ一覧を表示する際、以下の条件を満たすアプリケーションのみが表示されます。

1. **ライセンスチェック**: `LICENSED_APPS` に含まれている
2. **テナントレベルチェック**: `T_テナントアプリ設定` で有効化されている
3. **店舗レベルチェック**: `T_店舗アプリ設定` で有効化されている

これらのチェックは、`admin.py` の `store_apps()` 関数で実装されています。

---

## 6. アクセス制御デコレータ

`@require_app_enabled()` デコレータを使用して、無効化されたアプリケーションへのアクセスを防ぎます。

### 6.1. デコレータの使用例

```python
from app.utils.decorators import require_app_enabled

@survey_bp.route('/')
@require_app_enabled('survey')
def index():
    return render_template('survey_index.html')
```

このデコレータは、以下のチェックを行います。

1. ユーザーがログインしているか
2. アプリケーションがライセンスされているか
3. テナントレベルで有効化されているか
4. 店舗レベルで有効化されているか（店舗スコープの場合）

いずれかの条件を満たさない場合、403エラーが返されます。

### 6.2. デコレータの実装

`app/utils/decorators.py` に実装されています。

```python
from functools import wraps
from flask import session, abort
import os
from app.models import TenantAppSetting, StoreAppSetting

def require_app_enabled(app_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # ライセンスチェック
            licensed_apps = os.getenv('LICENSED_APPS', '').split(',')
            if app_name not in licensed_apps:
                abort(403)
            
            # テナントレベルチェック
            tenant_id = session.get('tenant_id')
            tenant_app = TenantAppSetting.query.filter_by(
                テナントID=tenant_id,
                アプリ名=app_name
            ).first()
            if not tenant_app or not tenant_app.有効フラグ:
                abort(403)
            
            # 店舗レベルチェック（店舗スコープの場合）
            store_id = session.get('store_id')
            if store_id:
                store_app = StoreAppSetting.query.filter_by(
                    店舗ID=store_id,
                    アプリ名=app_name
                ).first()
                if not store_app or not store_app.有効フラグ:
                    abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

---

## 7. UIへの統合

定義されたアプリケーションは、`admin_store_apps.html` テンプレートでカード形式で表示されます。

### 7.1. テンプレートの構造

```html
{% for app in apps %}
<div class="col-md-4 mb-4">
    <div class="card">
        <div class="card-body">
            <div class="d-flex align-items-center mb-3">
                <div class="icon-box {{ app.color }} text-white rounded-circle p-3 me-3">
                    <i class="{{ app.icon }} fa-2x"></i>
                </div>
                <div>
                    <h5 class="card-title mb-0">{{ app.display_name }}</h5>
                </div>
            </div>
            <p class="card-text">{{ app.description }}</p>
            <a href="{{ url_for(app.url) }}" class="btn btn-primary">開く</a>
        </div>
    </div>
</div>
{% endfor %}
```

### 7.2. ダッシュボードへの統合

店舗管理者ダッシュボード（`admin_dashboard.html`）にも、利用可能なアプリケーションのリストが表示されます。

```html
<div class="row">
    <div class="col-12">
        <h3>利用可能なアプリ</h3>
    </div>
    {% for app in apps %}
    <div class="col-md-3 mb-3">
        <a href="{{ url_for(app.url) }}" class="text-decoration-none">
            <div class="card text-center">
                <div class="card-body">
                    <i class="{{ app.icon }} fa-3x {{ app.color }} mb-2"></i>
                    <h6>{{ app.display_name }}</h6>
                </div>
            </div>
        </a>
    </div>
    {% endfor %}
</div>
```

---

## 8. 新しいアプリケーションの追加手順

新しいアプリケーションを追加する際の手順を以下にまとめます。

### 8.1. ステップ1: Blueprintの作成

`app/blueprints/` ディレクトリに新しいBlueprintファイルを作成します。

```python
# app/blueprints/survey.py
from flask import Blueprint, render_template
from app.utils.decorators import require_app_enabled

survey_bp = Blueprint('survey', __name__, url_prefix='/survey')

@survey_bp.route('/')
@require_app_enabled('survey')
def index():
    return render_template('survey_index.html')
```

### 8.2. ステップ2: Blueprintの登録

`app/__init__.py` で新しいBlueprintを登録します。

```python
from app.blueprints.survey import survey_bp

def create_app():
    app = Flask(__name__)
    # ... 他の設定 ...
    
    app.register_blueprint(survey_bp)
    
    return app
```

### 8.3. ステップ3: AVAILABLE_APPSへの追加

`app/blueprints/system_admin.py` および `app/blueprints/tenant_admin.py` の `AVAILABLE_APPS` リストに新しいアプリケーションを追加します。

```python
AVAILABLE_APPS = [
    # ... 既存のアプリ ...
    {
        'name': 'survey',
        'display_name': 'アンケート',
        'description': '顧客満足度調査や市場調査を実施します。',
        'scope': 'store',
        'url': 'survey.index',
        'icon': 'fas fa-poll',
        'color': 'bg-success'
    }
]
```

### 8.4. ステップ4: 環境変数の更新

`.env` ファイルまたはHerokuの環境変数に新しいアプリケーションを追加します。

```env
LICENSED_APPS=survey,invoice,quote
```

### 8.5. ステップ5: データベースへの登録

テナント管理者またはシステム管理者が、管理画面から新しいアプリケーションを有効化します。これにより、`T_テナントアプリ設定` および `T_店舗アプリ設定` にレコードが作成されます。

---

## 9. Font Awesomeアイコンの選択

アプリケーションのアイコンは、Font Awesomeから選択できます。以下は推奨されるアイコンの例です。

| アプリケーション       | アイコンクラス                  | 説明                     |
| ---------------------- | ------------------------------- | ------------------------ |
| アンケート             | `fas fa-poll`                   | 投票・アンケート         |
| 請求書                 | `fas fa-file-invoice-dollar`    | 請求書                   |
| 見積書                 | `fas fa-file-alt`               | ドキュメント             |
| 意思決定支援           | `fas fa-chart-line`             | チャート・分析           |
| 在庫管理               | `fas fa-boxes`                  | 箱・在庫                 |
| 顧客管理               | `fas fa-users`                  | ユーザー・顧客           |
| レポート               | `fas fa-file-pdf`               | PDFレポート              |
| 設定                   | `fas fa-cog`                    | 設定・歯車               |

Font Awesomeの公式サイト（https://fontawesome.com/icons）で、さらに多くのアイコンを検索できます。

---

## 10. 背景色の選択

アイコンの背景色は、Bootstrapのユーティリティクラスを使用します。

| クラス名       | 色           | 用途                     |
| -------------- | ------------ | ------------------------ |
| `bg-primary`   | 青           | 主要な機能               |
| `bg-success`   | 緑           | 成功・完了               |
| `bg-info`      | 水色         | 情報・通知               |
| `bg-warning`   | 黄色         | 警告・注意               |
| `bg-danger`    | 赤           | エラー・削除             |
| `bg-secondary` | グレー       | 補助的な機能             |

---

## 11. まとめ

`AVAILABLE_APPS` の定義により、システムで利用可能なアプリケーションを柔軟に管理できます。ライセンス管理、テナントレベル・店舗レベルの有効化制御、アクセス制御デコレータを組み合わせることで、マルチテナント・マルチストアのアーキテクチャを実現しています。

新しいアプリケーションを追加する際は、本ガイドに従って `AVAILABLE_APPS` を定義し、Blueprintを作成し、環境変数を更新してください。これにより、迅速かつ一貫性のあるアプリケーション開発が可能になります。

---

## 12. 参考資料

- [Font Awesome公式サイト](https://fontawesome.com/)
- [Bootstrap公式ドキュメント](https://getbootstrap.com/)
- [Flask Blueprint公式ドキュメント](https://flask.palletsprojects.com/en/2.3.x/blueprints/)
