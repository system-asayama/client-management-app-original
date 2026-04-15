# T0-1: 認証共有仕様（Cookie/Session）凍結

**Status:** 承認済み  
**Date:** 2026-04-13  
**Ticket:** [P0][T0-1]  
**Author:** system-asayama  

---

## 1. 目的

既存クライアント管理アプリ（client-management-app-original）のログインセッションを、電子契約サービス側で安全に共有・利用するための仕様を確定する。

---

## 2. セッションキー契約（Session Key Contract）

電子契約サービスは以下のセッションキーを読み取り専用で参照する。

| キー | 型 | 説明 | 欠損時の挙動 |
|------|-----|------|-------------|
| `user_id` | `int` | ユーザーID | 401 Unauthorized |
| `user_name` | `str` | ユーザー表示名 | 401 Unauthorized |
| `role` | `str` | ロール文字列（下表参照） | 401 Unauthorized |
| `tenant_id` | `int \| None` | テナントID（system_adminはNone可） | 403 Forbidden（system_admin除く）|
| `is_employee` | `bool` | 従業員フラグ | 401 Unauthorized |
| `store_id` | `int \| None` | 店舗ID（任意） | チェックなし（情報用） |
| `is_owner` | `bool \| None` | オーナーフラグ（任意） | チェックなし（情報用） |
| `csrf_token` | `str` | CSRFトークン | 電子契約側で独自生成 |

### 2.1 ロール定義

| role 値 | 説明 | tenant_id |
|---------|------|-----------|
| `system_admin` | 全テナント横断管理者 | `None`可 |
| `tenant_admin` | テナント単位管理者 | 必須 |
| `admin` | 店舗・拠点管理者 | 必須 |
| `employee` | 従業員 | 必須 |
| `client_admin` | クライアント管理者 | 必須 |
| `client_employee` | クライアント従業員 | 必須 |

### 2.2 電子契約サービスで使用可能なロール

電子契約サービスは以下のロールのみアクセスを許可する。

| ロール | 権限 |
|--------|------|
| `system_admin` | 全テナントの契約管理 |
| `tenant_admin` | 自テナントの契約管理 |
| `admin` | 自テナントの契約参照 |
| `employee` | 自テナントの契約参照 |

`client_admin` / `client_employee` は電子契約管理UIへのアクセス不可（署名者フローは別途signing URLで制御）。

---

## 3. Cookie設定

### 3.1 セッションCookie属性

| 属性 | 値 | 理由 |
|------|-----|------|
| `SESSION_COOKIE_NAME` | `cm_session` | 両サービスで統一 |
| `SESSION_COOKIE_DOMAIN` | `.example.com`（本番） / `localhost`（開発） | サブドメイン共有 |
| `SESSION_COOKIE_SECURE` | `True`（本番） / `False`（HTTP開発環境） | HTTPS強制 |
| `SESSION_COOKIE_HTTPONLY` | `True` | XSS対策 |
| `SESSION_COOKIE_SAMESITE` | `Lax` | CSRF基本防御 |
| `PERMANENT_SESSION_LIFETIME` | `28800`秒（8時間） | 業務時間内持続 |

### 3.2 環境変数設定（電子契約サービス側）

```bash
# 必須
SECRET_KEY=<既存アプリと同一の値>  # セッション復号に使用
SESSION_COOKIE_NAME=cm_session
SESSION_COOKIE_DOMAIN=.example.com   # 本番のみ

# 本番
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
PERMANENT_SESSION_LIFETIME=28800

# 開発用（HTTP可）
SESSION_COOKIE_SECURE=false
```

> **重要:** `SECRET_KEY` は両サービスで同一でなければセッション復号に失敗する。  
> 本番環境では `heroku config:set SECRET_KEY=...` で統一すること。

---

## 4. 認証・認可ミドルウェア仕様

### 4.1 認証チェック（401判定ルール）

下記のいずれかに該当する場合 `HTTP 401 Unauthorized` を返す。

1. `session.get("user_id")` が `None`または空
2. `session.get("role")` が `None`または空
3. `session.get("is_employee")` が `None`（欠損）

```python
# 擬似コード
def require_auth():
    if not session.get("user_id") or not session.get("role"):
        return {"error": "Unauthorized"}, 401
    if session.get("is_employee") is None:
        return {"error": "Unauthorized"}, 401
```

### 4.2 テナント強制フィルター（403判定ルール）

`system_admin` 以外は `tenant_id` が必須。

```python
# 擬似コード
def require_tenant():
    role = session.get("role")
    tenant_id = session.get("tenant_id")
    if role != "system_admin" and not tenant_id:
        return {"error": "Forbidden: tenant_id missing"}, 403
```

### 4.3 ロール権限チェック（403判定ルール）

```python
# 擬似コード
def require_roles(*allowed_roles):
    role = session.get("role")
    if role not in allowed_roles:
        return {"error": "Forbidden: insufficient role"}, 403
```

### 4.4 テナント境界フィルター

`system_admin` は全テナントにアクセス可。それ以外は `tenant_id` でフィルタ。

```python
# 擬似コード
def tenant_filter():
    role = session.get("role")
    tenant_id = session.get("tenant_id")
    if role == "system_admin":
        return None  # フィルタなし
    return tenant_id  # WHERE tenant_id = ?
```

---

## 5. エラーレスポンス形式

```json
// 401
{"error": "Unauthorized", "code": "AUTH_REQUIRED"}

// 403 (権限不足)
{"error": "Forbidden", "code": "INSUFFICIENT_ROLE"}

// 403 (テナント不一致)
{"error": "Forbidden", "code": "TENANT_MISMATCH"}
```

---

## 6. 非適用事項（スコープ外）

- JWT-SSOへの移行（Cookie共有失敗時は別途 T0-1-B として評価）
- session書き込み・ユーザー作成（電子契約側は読み取り専用）
- クライアント（署名者）のセッション管理（signing URL tokenで独立管理）

---

## 7. リスクと対応方針

| リスク | 影響 | 対応 |
|--------|------|------|
| Cookie共有失敗（ドメイン不一致） | 全フロー停止 | JWT-SSO代替案（RFC 7519）へ切替 |
| SECRET_KEY不一致 | セッション復号失敗 | 環境変数確認・統一手順書整備 |
| SameSite=Laxでのクロスサイトリダイレクト | 一部フロー失敗 | 必要ならStrictまたはNoneへ変更（HTTPS必須）|

---

## 8. 承認証跡

| 項目 | 内容 |
|------|------|
| ドキュメント作成 | 2026-04-13 |
| レビュー完了 | 2026-04-13 |
| 凍結確定 | 2026-04-13 |
| 次アクション | Issue #2 (T0-2) API契約凍結に着手 |

---

## 関連ファイル

- `app/utils/security.py` — `login_user()` セッションキー設定元
- `app/utils/decorators.py` — `require_roles()`, `current_tenant_filter_sql()`
- `app/__init__.py` — `SECRET_KEY` 設定参照
- `docs/spec_t0_2_api_contract.md` — 依存仕様（T0-2）
