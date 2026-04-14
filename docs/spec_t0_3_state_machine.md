# T0-3: 状態遷移凍結（contract / signer）

**Status:** 承認済み  
**Date:** 2026-04-13  
**Ticket:** [P0][T0-3]  
**Depends on:** T0-2 (docs/spec_t0_2_api_contract.md)  

---

## 1. contract.status 状態遷移

### 1.1 定義済み状態

| 状態 | 説明 |
|------|------|
| `draft` | 契約作成済み・未送付 |
| `sent` | 署名URLを全署名者へ送付済み |
| `signing` | 1人以上が署名済み（進行中） |
| `completed` | 全署名者が署名し finalize 処理が完了 |

### 1.2 状態遷移図

```
draft ──────────────────→ sent
                           │
                           ↓（最初の署名者がsigned）
                        signing
                           │
                           ↓（全員signed + finalize完了）
                        completed
```

### 1.3 遷移ルール（凍結）

| From | To | トリガー | 禁止遷移 |
|------|----|----------|---------|
| `draft` | `sent` | `POST /dispatch` | draft→signing, draft→completed は禁止 |
| `sent` | `signing` | 最初のsigner.status=signed | sent→completed の直接遷移は禁止 |
| `signing` | `completed` | finalize処理完了（全員signed後）| signing→sent への逆遷移は禁止 |

### 1.4 逆遷移・中断の禁止

- **いかなる状態からも逆遷移なし**（completed/signing から draft/sent に戻ることは不可）
- `completed` は終端状態（以降の遷移は存在しない）
- キャンセル概念は本仕様スコープ外（必要時は別途 `cancelled` 状態を追加審議）

### 1.5 422エラーとなる操作

- `draft` 以外の契約への `dispatch`
- `signed` 済みまたは `signing` / `completed` 状態の契約への再 `dispatch`

---

## 2. signer.status 状態遷移

### 2.1 定義済み状態

| 状態 | 説明 |
|------|------|
| `pending` | 署名URL送付済み・KYC未完了 |
| `kyc_passed` | KYC成功済み・同意未完了 |
| `consented` | 同意記録済み・署名未完了 |
| `signed` | 署名完了 |

### 2.2 状態遷移図

```
pending ──→ kyc_passed ──→ consented ──→ signed
```

### 2.3 遷移ルール（凍結）

| From | To | トリガー | 条件 |
|------|----|----------|------|
| `pending` | `kyc_passed` | `POST /kyc` (result=success) | —— |
| `kyc_passed` | `consented` | `POST /consent` (agreed=true) | —— |
| `consented` | `signed` | `POST /sign` | 前の order_index の署名者が全員 `signed` |

### 2.4 禁止操作

- `kyc_passed` 未達で `/consent` の実行 → **422**
- `consented` 未達で `/sign` の実行 → **422**
- `signed` 済み署名者への `/sign` 再実行 → **409 TOKEN_ALREADY_USED**
- `order_index` 順守違反の署名実行 → **409 WRONG_SIGNER_ORDER**

### 2.5 KYC result=failed/pending の扱い

| result | signerの状態変化 | 次のアクション |
|--------|-----------------|--------------|
| `success` | pending → kyc_passed | /consent へ進む |
| `failed` | pending のまま（変化なし）| 再KYCまたは代替本人確認 |
| `pending` | pending のまま | webhook等で後日 success/failed を通知 |

---

## 3. 署名順制御ルール

### 3.1 order_index規約

- `order_index` は 1 始まりの連番
- 同一契約内で重複禁止（DBのUNIQUE制約で保証）
- `order_index=1` の署名者が最初

### 3.2 順番チェックロジック

```python
# 擬似コード: POST /sign/{token}/sign の前提チェック
def check_order(signer, contract):
    prev_signers = [s for s in contract.signers if s.order_index < signer.order_index]
    if any(s.status != "signed" for s in prev_signers):
        raise Error(409, "WRONG_SIGNER_ORDER")
```

---

## 4. contract←→signer 連動ルール

| signerイベント | contractへの影響 |
|---------------|----------------|
| 最初のsigner が signed | contract.status = signing |
| 最後のsigner が signed | finalize処理を起動 |
| finalize完了 | contract.status = completed |

---

## 5. 承認証跡

| 項目 | 内容 |
|------|------|
| ドキュメント作成 | 2026-04-13 |
| レビュー完了 | 2026-04-13 |
| 凍結確定 | 2026-04-13 |

---

## 関連ファイル

- `docs/spec_t0_2_api_contract.md` — API契約（依存元）
- `docs/spec_t0_4_audit_log.md` — 監査ログ規約
