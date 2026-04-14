# E-Contract Service

このディレクトリは、将来的に別リポジトリへ切り出す前提の電子契約サービス雛形です。

現時点の実装範囲:
- T1-1 DBスキーマ
- T1-2 セッション共有前提の認可ミドルウェア
- T1-3 契約API（create/list/detail）

起動例:

```bash
export DATABASE_URL='postgresql://...'
export SECRET_KEY='existing-app-secret'
python -m e_contract_service.app
```

`DATABASE_URL` が未設定または空文字の場合は、
`e_contract_service/e_contract_local.db`（SQLite）を自動利用します。

主要エンドポイント:
- POST /api/contracts
- GET /api/contracts
- GET /api/contracts/<contract_id>
- GET /healthz