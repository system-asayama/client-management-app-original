# T0-4: 監査ログ Hash チェーン規約

**Status:** 承認済み  
**Date:** 2026-04-13  
**Ticket:** [P0][T0-4]  
**Depends on:** T0-2 (docs/spec_t0_2_api_contract.md)  

---

## 1. 目的

電子契約の証拠能力を担保するため、監査ログ（`contract_audit_logs` テーブル）に対して SHA-256 ハッシュチェーンを実装する。  
ログ1件でも改ざんされた場合、`verify` APIが検出できることを保証する。

---

## 2. ハッシュチェーン構造

### 2.1 概念図

```
log[1]:  prev_hash=""      hash=SHA256(canonical(log[1]))
log[2]:  prev_hash=log[1].hash  hash=SHA256(canonical(log[2]))
log[3]:  prev_hash=log[2].hash  hash=SHA256(canonical(log[3]))
  ...
log[N]:  prev_hash=log[N-1].hash hash=SHA256(canonical(log[N]))
```

### 2.2 各フィールドの役割

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `seq` | integer | 契約内連番（1始まり、欠番禁止）|
| `prev_hash` | varchar(64) | 直前ログの `hash` 値（最初のログは空文字列）|
| `hash` | varchar(64) | 本レコードのSHA-256ハッシュ（hex64文字）|
| `canonical_json` | text | ハッシュ計算の元データ（永久保存） |

---

## 3. Canonical JSON 規約

### 3.1 定義

ハッシュ計算に使用するJSONは以下のルールで生成する。

1. **キー順**: アルファベット昇順（再帰的にソート）
2. **空白なし**: separators=(',', ':')
3. **文字コード**: UTF-8
4. **Null許容**: null値はJSONのnullで表現（Pythonの`None`をそのまま）
5. **日時**: ISO 8601 文字列（タイムゾーンはUTC、末尾Zあり）

### 3.2 Python実装例

```python
import json
import hashlib

def canonical_json(data: dict) -> str:
    """dict を canonical JSON 文字列に変換する"""
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def compute_hash(log_data: dict) -> str:
    """log_data の SHA-256 ハッシュを hex 文字列で返す"""
    canonical = canonical_json(log_data)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

### 3.3 ハッシュ計算に含めるフィールド（凍結）

```json
{
  "action": "string",
  "actor_id": "integer | null",
  "actor_type": "string",
  "contract_id": "uuid-string",
  "created_at": "ISO8601Z",
  "detail": {},
  "prev_hash": "hex64 | ''",
  "seq": "integer"
}
```

> **注意:** `hash` フィールド自体はハッシュ計算に含めない（循環回避）。  
> `log_id` もハッシュ計算に含めない（DBが採番するため）。

---

## 4. アクション定義（凍結）

| action 値 | 説明 | actor_type |
|-----------|------|-----------|
| `contract_created` | 契約作成 | user |
| `contract_dispatched` | 署名URL送付 | user |
| `signer_token_issued` | 署名URL発行 | system |
| `kyc_completed` | KYC完了 | signer |
| `consent_recorded` | 同意記録 | signer |
| `signature_applied` | 署名実行 | signer |
| `business_signed` | 事業者署名（KMS）| system |
| `timestamp_applied` | RFC3161タイムスタンプ付与 | system |
| `contract_finalized` | 契約確定 | system |
| `audit_verified` | 監査ログ整合性検証 | user |

---

## 5. 検証（verify）ロジック

### 5.1 全件検証アルゴリズム

```python
# 擬似コード
def verify_audit_chain(contract_id: str) -> (bool, int | None):
    logs = fetch_logs_ordered_by_seq(contract_id)
    expected_prev_hash = ""
    for log in logs:
        # prev_hash チェック
        if log.prev_hash != expected_prev_hash:
            return False, log.seq
        # hash 再計算
        recomputed = compute_hash({
            "action": log.action,
            "actor_id": log.actor_id,
            "actor_type": log.actor_type,
            "contract_id": str(log.contract_id),
            "created_at": log.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "detail": log.detail,
            "prev_hash": log.prev_hash,
            "seq": log.seq,
        })
        if recomputed != log.hash:
            return False, log.seq
        expected_prev_hash = log.hash
    return True, None
```

### 5.2 検証失敗時の対応

- `verified=false` をレスポンスに含める
- `first_tampered_seq` に最初に不整合が検出されたseqを含める
- エスカレーション: 新規リリースを即停止し、原因解消まで凍結（リスクレジスタ R5）

---

## 6. DBルール

### 6.1 削除禁止

`contract_audit_logs` テーブルは **物理削除禁止**。  
アプリケーション層でのDELETE実行は禁止。DBユーザー権限でDELETE権限を剥奪する（本番）。

### 6.2 更新禁止

`hash` / `prev_hash` / `canonical_json` カラムは挿入後の UPDATE 禁止。  
アプリケーション層のロジックで保証する。

### 6.3 seq欠番禁止

`seq` は契約スコープで1始まりの連番。欠番が発生した場合はチェーン破損とみなす。

---

## 7. 承認証跡

| 項目 | 内容 |
|------|------|
| ドキュメント作成 | 2026-04-13 |
| レビュー完了 | 2026-04-13 |
| 凍結確定 | 2026-04-13 |

---

## 関連ファイル

- `docs/spec_t0_2_api_contract.md` — API契約（依存元）
- `docs/spec_t0_3_state_machine.md` — 状態遷移規約
