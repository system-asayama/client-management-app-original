from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-change-in-production")

from e_contract_service import create_app  # noqa: E402
from e_contract_service.db import SessionLocal  # noqa: E402
from e_contract_service.models import Signer  # noqa: E402


def _login(client, role: str = "tenant_admin", tenant_id: int = 200):
    with client.session_transaction() as session:
        session["user_id"] = 999
        session["user_name"] = "tester"
        session["role"] = role
        session["tenant_id"] = tenant_id
        session["is_owner"] = True


def test_full_e2e_flow_with_finalize_and_certificate():
    app = create_app()
    client = app.test_client()
    _login(client)

    # 1) 契約作成
    create = client.post(
        "/api/contracts",
        json={
            "title": "E2E検証契約",
            "document_url": "https://example.com/e2e.pdf",
            "signers": [
                {"name": "署名者A", "email": "a@example.com", "order_index": 1},
                {"name": "署名者B", "email": "b@example.com", "order_index": 2},
            ],
        },
    )
    assert create.status_code == 201
    contract_id = create.get_json()["contract_id"]

    # 2) 送信
    dispatch = client.post(f"/api/contracts/{contract_id}/dispatch", json={})
    assert dispatch.status_code == 200
    links = dispatch.get_json()["signing_links"]

    # 3) KYC
    # 4) 同意
    # 5) 署名
    for idx, link in enumerate(links, start=1):
        token = link["sign_url"].split("/api/sign/", 1)[1]
        kyc = client.post(
            f"/api/sign/{token}/kyc",
            json={
                "kyc_provider": "mock",
                "kyc_session_id": f"e2e-sess-{idx}",
                "result": "success",
            },
        )
        assert kyc.status_code == 200

        consent = client.post(f"/api/sign/{token}/consent", json={"agreed": True})
        assert consent.status_code == 200

        sign = client.post(f"/api/sign/{token}/sign", json={})
        assert sign.status_code == 200

    # 6) 電子署名付与 + 7) タイムスタンプ付与（finalize内）
    finalize = client.post(f"/api/contracts/{contract_id}/finalize", json={})
    assert finalize.status_code == 200
    finalize_payload = finalize.get_json()
    assert finalize_payload["status"] == "completed"
    assert finalize_payload["document_hash"]
    assert finalize_payload["timestamp_token"]

    # 証明書情報取得
    cert = client.get(f"/api/contracts/{contract_id}/certificate")
    assert cert.status_code == 200
    cert_payload = cert.get_json()
    assert cert_payload["status"] == "completed"
    assert cert_payload["audit_chain_valid"] is True


def test_abnormal_flow_expired_and_reuse_token():
    app = create_app()
    client = app.test_client()
    _login(client, tenant_id=201)

    create = client.post(
        "/api/contracts",
        json={
            "title": "異常系検証契約",
            "document_url": "https://example.com/abnormal.pdf",
            "signers": [{"name": "署名者A", "email": "a@example.com", "order_index": 1}],
        },
    )
    contract_id = create.get_json()["contract_id"]

    dispatch = client.post(f"/api/contracts/{contract_id}/dispatch", json={})
    token = dispatch.get_json()["signing_links"][0]["sign_url"].split("/api/sign/", 1)[1]

    # dispatch APIは固定7日有効なので、テストで明示的に期限切れへ更新
    db = SessionLocal()
    try:
        signer = db.query(Signer).filter(Signer.contract_id == contract_id).first()
        signer.token_expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    expired = client.get(f"/api/sign/{token}")
    assert expired.status_code == 410

    # 別契約でトークン再利用拒否を検証
    create2 = client.post(
        "/api/contracts",
        json={
            "title": "再利用検証契約",
            "document_url": "https://example.com/reuse.pdf",
            "signers": [{"name": "署名者A", "email": "a@example.com", "order_index": 1}],
        },
    )
    contract_id2 = create2.get_json()["contract_id"]
    dispatch2 = client.post(f"/api/contracts/{contract_id2}/dispatch", json={})
    token2 = dispatch2.get_json()["signing_links"][0]["sign_url"].split("/api/sign/", 1)[1]

    client.post(
        f"/api/sign/{token2}/kyc",
        json={"kyc_provider": "mock", "kyc_session_id": "sess-x", "result": "success"},
    )
    client.post(f"/api/sign/{token2}/consent", json={"agreed": True})
    first_sign = client.post(f"/api/sign/{token2}/sign", json={})
    assert first_sign.status_code == 200

    reuse = client.post(f"/api/sign/{token2}/sign", json={})
    assert reuse.status_code == 409
