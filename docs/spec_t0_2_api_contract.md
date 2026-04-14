# T0-2: API契約凍結

**Status:** 承認済み  
**Date:** 2026-04-13  
**Ticket:** [P0][T0-2]  
**Depends on:** T0-1 (docs/spec_t0_1_session_auth.md)  

---

## 1. 目的

電子契約サービスの全APIエンドポイントについて、request/response/error を確定し「API契約」として凍結する。  
実装者はこの文書を唯一の真実の源（Single Source of Truth）として実装する。

---

## 2. 共通仕様

### 2.1 認証

全APIは `docs/spec_t0_1_session_auth.md` のセッション認証が必要。  
未認証時は一律 **401** を返す。

### 2.2 Content-Type

- Request: `application/json`
- Response: `application/json`

### 2.3 共通レスポンスヘッダー

```
Content-Type: application/json
X-Request-ID: <uuid>      # トレーサビリティ用（ログ相関）
```

### 2.4 共通エラーフォーマット

```json
{
  "error": "エラー概要",
  "code": "ERROR_CODE",
  "detail": "詳細説明（任意）"
}
```

### 2.5 エラーコード一覧（凍結）

| HTTP | code | 意味 |
|------|------|------|
| 400 | `VALIDATION_ERROR` | リクエストパラメータ不正 |
| 401 | `AUTH_REQUIRED` | 未認証 |
| 403 | `INSUFFICIENT_ROLE` | ロール権限不足 |
| 403 | `TENANT_MISMATCH` | テナント不一致 |
| 404 | `NOT_FOUND` | リソース未存在 |
| 409 | `TOKEN_ALREADY_USED` | 署名URLの再利用 |
| 409 | `WRONG_SIGNER_ORDER` | 署名順序違反 |
| 410 | `TOKEN_EXPIRED` | 署名URL期限切れ |
| 422 | `UNPROCESSABLE` | 業務ルール違反（状態遷移不正等） |
| 502 | `EXTERNAL_ERROR` | 外部サービス（KMS/TSA/KYC）障害 |
| 503 | `SERVICE_UNAVAILABLE` | サービス一時停止 |

---

## 3. API一覧

| # | メソッド | パス | 説明 | 必要ロール |
|---|---------|------|------|-----------|
| 1 | POST | `/api/contracts` | 契約作成 | tenant_admin, admin, system_admin |
| 2 | GET | `/api/contracts` | 契約一覧 | tenant_admin, admin, employee, system_admin |
| 3 | GET | `/api/contracts/{contract_id}` | 契約詳細 | tenant_admin, admin, employee, system_admin |
| 4 | POST | `/api/contracts/{contract_id}/dispatch` | 署名者へURL送付 | tenant_admin, admin, system_admin |
| 5 | GET | `/api/sign/{token}` | 署名URL認証・契約内容取得 | 不要（tokenで認証）|
| 6 | POST | `/api/sign/{token}/kyc` | KYC完了通知 | 不要（tokenで認証）|
| 7 | POST | `/api/sign/{token}/consent` | 同意記録 | 不要（tokenで認証）|
| 8 | POST | `/api/sign/{token}/sign` | 署名実行 | 不要（tokenで認証）|
| 9 | GET | `/api/contracts/{contract_id}/audit` | 監査ログ取得 | tenant_admin, system_admin |
| 10 | POST | `/api/contracts/{contract_id}/verify` | 監査ログ整合性検証 | tenant_admin, system_admin |

---

## 4. 詳細API仕様

---

### 4.1 POST /api/contracts — 契約作成

**Request Body**

```json
{
  "title": "string (必須, max:255)",
  "document_url": "string (必須, URL)",
  "signers": [
    {
      "name": "string (必須)",
      "email": "string (必須, email形式)",
      "order_index": "integer (必須, 1始まり, 重複不可)"
    }
  ]
}
```

**Response 201 Created**

```json
{
  "contract_id": "uuid",
  "title": "string",
  "status": "draft",
  "tenant_id": "integer",
  "created_by": "integer",
  "created_at": "ISO8601",
  "signers": [
    {
      "signer_id": "uuid",
      "name": "string",
      "email": "string",
      "order_index": "integer",
      "status": "pending"
    }
  ]
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 400 | `VALIDATION_ERROR` | title/document_url欠損、signer email不正 |
| 400 | `VALIDATION_ERROR` | order_index重複 |
| 401 | `AUTH_REQUIRED` | 未認証 |
| 403 | `INSUFFICIENT_ROLE` | 対象外ロール |

---

### 4.2 GET /api/contracts — 契約一覧

**Query Parameters**

| パラメータ | 型 | 説明 | デフォルト |
|-----------|-----|------|----------|
| `status` | string | 絞り込み（draft/sent/signing/completed） | なし（全件）|
| `page` | integer | ページ番号（1始まり） | 1 |
| `per_page` | integer | 件数（max:100） | 20 |

**Response 200 OK**

```json
{
  "contracts": [
    {
      "contract_id": "uuid",
      "title": "string",
      "status": "draft|sent|signing|completed",
      "created_at": "ISO8601",
      "signer_count": "integer",
      "signed_count": "integer"
    }
  ],
  "total": "integer",
  "page": "integer",
  "per_page": "integer"
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 400 | `VALIDATION_ERROR` | status値が定義外 |
| 401 | `AUTH_REQUIRED` | 未認証 |

---

### 4.3 GET /api/contracts/{contract_id} — 契約詳細

**Response 200 OK**

```json
{
  "contract_id": "uuid",
  "title": "string",
  "document_url": "string",
  "status": "draft|sent|signing|completed",
  "tenant_id": "integer",
  "created_by": "integer",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "signers": [
    {
      "signer_id": "uuid",
      "name": "string",
      "email": "string",
      "order_index": "integer",
      "status": "pending|kyc_passed|consented|signed",
      "signed_at": "ISO8601 | null"
    }
  ]
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 401 | `AUTH_REQUIRED` | 未認証 |
| 403 | `TENANT_MISMATCH` | 他テナントの契約 |
| 404 | `NOT_FOUND` | contract_id 未存在 |

---

### 4.4 POST /api/contracts/{contract_id}/dispatch — 署名URL送付

**Request Body**

```json
{}
```
（本文なし、または空JSON）

**Response 200 OK**

```json
{
  "contract_id": "uuid",
  "status": "sent",
  "dispatched_at": "ISO8601",
  "signer_count": "integer"
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 401 | `AUTH_REQUIRED` | 未認証 |
| 403 | `INSUFFICIENT_ROLE` | employeeは不可 |
| 403 | `TENANT_MISMATCH` | 他テナント |
| 404 | `NOT_FOUND` | contract_id 未存在 |
| 422 | `UNPROCESSABLE` | draft以外からのdispatch |

---

### 4.5 GET /api/sign/{token} — 署名URL認証・契約内容取得

**パス変数**

| 変数 | 説明 |
|------|------|
| `token` | 署名URL発行時の平文token（32バイト urlsafe）|

**Response 200 OK**

```json
{
  "contract_id": "uuid",
  "title": "string",
  "document_url": "string",
  "signer": {
    "signer_id": "uuid",
    "name": "string",
    "order_index": "integer",
    "status": "pending|kyc_passed|consented"
  }
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 404 | `NOT_FOUND` | token対応レコード未存在 |
| 409 | `TOKEN_ALREADY_USED` | 既に使用済み（signed） |
| 410 | `TOKEN_EXPIRED` | 有効期限切れ |

---

### 4.6 POST /api/sign/{token}/kyc — KYC完了通知

**Request Body**

```json
{
  "kyc_provider": "string (必須)",
  "kyc_session_id": "string (必須)",
  "result": "success|failed|pending (必須)"
}
```

**Response 200 OK**

```json
{
  "signer_id": "uuid",
  "status": "kyc_passed",
  "kyc_recorded_at": "ISO8601"
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 400 | `VALIDATION_ERROR` | result値が定義外 |
| 404 | `NOT_FOUND` | token無効 |
| 410 | `TOKEN_EXPIRED` | 期限切れ |
| 422 | `UNPROCESSABLE` | kyc_passed/signed済みへの再実行 |
| 502 | `EXTERNAL_ERROR` | KYCプロバイダー障害 |

---

### 4.7 POST /api/sign/{token}/consent — 同意記録

**Request Body**

```json
{
  "agreed": true
}
```

**Response 200 OK**

```json
{
  "signer_id": "uuid",
  "status": "consented",
  "consented_at": "ISO8601",
  "ip_address": "string",
  "user_agent": "string"
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 400 | `VALIDATION_ERROR` | `agreed`がfalse（同意拒否） |
| 404 | `NOT_FOUND` | token無効 |
| 410 | `TOKEN_EXPIRED` | 期限切れ |
| 422 | `UNPROCESSABLE` | kyc_passed未完了または既にconsented |

---

### 4.8 POST /api/sign/{token}/sign — 署名実行

**Request Body**

```json
{}
```

**Response 200 OK**

```json
{
  "signer_id": "uuid",
  "status": "signed",
  "signed_at": "ISO8601",
  "signature_id": "uuid"
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 404 | `NOT_FOUND` | token無効 |
| 409 | `TOKEN_ALREADY_USED` | 署名済み |
| 409 | `WRONG_SIGNER_ORDER` | 前の署名者が未完了 |
| 410 | `TOKEN_EXPIRED` | 期限切れ |
| 422 | `UNPROCESSABLE` | consent未完了 |
| 502 | `EXTERNAL_ERROR` | KMS障害 |

---

### 4.9 GET /api/contracts/{contract_id}/audit — 監査ログ取得

**Query Parameters**

| パラメータ | 型 | 説明 |
|-----------|-----|------|
| `page` | integer | ページ番号（1始まり） |
| `per_page` | integer | 件数（max:100, default:50）|

**Response 200 OK**

```json
{
  "contract_id": "uuid",
  "logs": [
    {
      "log_id": "uuid",
      "seq": "integer",
      "action": "string",
      "actor_id": "integer | null",
      "actor_type": "user|signer|system",
      "detail": "object",
      "prev_hash": "string (sha256hex)",
      "hash": "string (sha256hex)",
      "created_at": "ISO8601"
    }
  ],
  "total": "integer"
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 401 | `AUTH_REQUIRED` | 未認証 |
| 403 | `INSUFFICIENT_ROLE` | admin/employee不可 |
| 403 | `TENANT_MISMATCH` | 他テナント |
| 404 | `NOT_FOUND` | contract_id未存在 |

---

### 4.10 POST /api/contracts/{contract_id}/verify — 監査ログ整合性検証

**Request Body**

```json
{}
```

**Response 200 OK**

```json
{
  "contract_id": "uuid",
  "verified": true,
  "log_count": "integer",
  "verified_at": "ISO8601"
}
```

**Response 200 OK（改ざん検知）**

```json
{
  "contract_id": "uuid",
  "verified": false,
  "first_tampered_seq": "integer",
  "verified_at": "ISO8601"
}
```

**Errors**

| Status | code | 条件 |
|--------|------|------|
| 401 | `AUTH_REQUIRED` | 未認証 |
| 403 | `INSUFFICIENT_ROLE` | admin/employee不可 |
| 404 | `NOT_FOUND` | contract_id未存在 |

---

## 5. 状態遷移（参照）

詳細は `docs/spec_t0_3_state_machine.md` に委譲。概要のみ掲載。

### 5.1 contract.status

```
draft → sent → signing → completed
```

| 遷移 | トリガーAPI |
|------|------------|
| draft → sent | POST /dispatch |
| sent → signing | 最初の署名者が署名実行 |
| signing → completed | 最後の署名者が署名 + finalize処理完了 |

### 5.2 signer.status

```
pending → kyc_passed → consented → signed
```

| 遷移 | トリガーAPI |
|------|------------|
| pending → kyc_passed | POST /kyc (result=success) |
| kyc_passed → consented | POST /consent |
| consented → signed | POST /sign |

---

## 6. 承認証跡

| 項目 | 内容 |
|------|------|
| ドキュメント作成 | 2026-04-13 |
| レビュー完了 | 2026-04-13 |
| 凍結確定 | 2026-04-13 |
| 次アクション | Issue #3 (T0-3) 状態遷移凍結 / Issue #4 (T0-4) 監査ログHash規約凍結 |

---

## 関連ファイル

- `docs/spec_t0_1_session_auth.md` — 認証仕様（依存元）
- `docs/spec_t0_3_state_machine.md` — 状態遷移詳細
- `docs/spec_t0_4_audit_log.md` — 監査ログHash規約
