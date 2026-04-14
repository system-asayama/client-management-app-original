from __future__ import annotations

import os
import unittest


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-change-in-production")

from e_contract_service import create_app  # noqa: E402


class ContractsApiTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def _login(self, role: str = "tenant_admin", tenant_id: int = 10):
        with self.client.session_transaction() as session:
            session["user_id"] = 999
            session["user_name"] = "tester"
            session["role"] = role
            session["tenant_id"] = tenant_id
            session["is_owner"] = True

    def test_requires_authentication(self):
        response = self.client.get("/api/contracts")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "AUTH_REQUIRED")

    def test_create_contract(self):
        self._login()
        response = self.client.post(
            "/api/contracts",
            json={
                "title": "基本契約書",
                "document_url": "https://example.com/doc.pdf",
                "signers": [
                    {"name": "署名者A", "email": "a@example.com", "order_index": 1},
                    {"name": "署名者B", "email": "b@example.com", "order_index": 2},
                ],
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(len(payload["signers"]), 2)

    def test_list_and_detail_contracts_with_tenant_scope(self):
        self._login(tenant_id=55)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "業務委託契約書",
                "document_url": "https://example.com/contract.pdf",
                "signers": [{"name": "署名者A", "email": "a@example.com", "order_index": 1}],
            },
        )
        self.assertEqual(create.status_code, 201)
        contract_id = create.get_json()["contract_id"]

        listed = self.client.get("/api/contracts")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.get_json()["total"], 1)

        detail = self.client.get(f"/api/contracts/{contract_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["tenant_id"], 55)

    def test_dispatch_contract_and_verify_token(self):
        self._login(tenant_id=77)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "秘密保持契約書",
                "document_url": "https://example.com/nda.pdf",
                "signers": [{"name": "署名者A", "email": "a@example.com", "order_index": 1}],
            },
        )
        contract_id = create.get_json()["contract_id"]

        dispatch = self.client.post(f"/api/contracts/{contract_id}/dispatch", json={})
        self.assertEqual(dispatch.status_code, 200)
        dispatch_payload = dispatch.get_json()
        self.assertEqual(dispatch_payload["status"], "sent")
        self.assertEqual(dispatch_payload["signer_count"], 1)
        sign_url = dispatch_payload["signing_links"][0]["sign_url"]

        token_path = sign_url.split("/api/sign/", 1)[1]
        verified = self.client.get(f"/api/sign/{token_path}")
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.get_json()["contract_id"], contract_id)

    def test_audit_log_list_and_verify(self):
        self._login(role="tenant_admin", tenant_id=88)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "監査対象契約",
                "document_url": "https://example.com/audit.pdf",
                "signers": [{"name": "署名者A", "email": "a@example.com", "order_index": 1}],
            },
        )
        contract_id = create.get_json()["contract_id"]

        audit = self.client.get(f"/api/contracts/{contract_id}/audit")
        self.assertEqual(audit.status_code, 200)
        self.assertGreaterEqual(audit.get_json()["total"], 1)

        verified = self.client.post(f"/api/contracts/{contract_id}/verify", json={})
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.get_json()["verified"])

    def test_kyc_consent_and_sign_flow(self):
        self._login(tenant_id=91)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "発注基本契約書",
                "document_url": "https://example.com/base.pdf",
                "signers": [
                    {"name": "署名者A", "email": "a@example.com", "order_index": 1},
                    {"name": "署名者B", "email": "b@example.com", "order_index": 2},
                ],
            },
        )
        contract_id = create.get_json()["contract_id"]
        dispatch = self.client.post(f"/api/contracts/{contract_id}/dispatch", json={})
        links = dispatch.get_json()["signing_links"]
        token1 = links[0]["sign_url"].split("/api/sign/", 1)[1]
        token2 = links[1]["sign_url"].split("/api/sign/", 1)[1]

        wrong_order = self.client.post(f"/api/sign/{token2}/sign", json={})
        self.assertEqual(wrong_order.status_code, 422)

        kyc = self.client.post(
            f"/api/sign/{token1}/kyc",
            json={"kyc_provider": "mock", "kyc_session_id": "sess-1", "result": "success"},
        )
        self.assertEqual(kyc.status_code, 200)
        consent = self.client.post(f"/api/sign/{token1}/consent", json={"agreed": True})
        self.assertEqual(consent.status_code, 200)
        sign = self.client.post(f"/api/sign/{token1}/sign", json={})
        self.assertEqual(sign.status_code, 200)

        second_kyc = self.client.post(
            f"/api/sign/{token2}/kyc",
            json={"kyc_provider": "mock", "kyc_session_id": "sess-2", "result": "success"},
        )
        self.assertEqual(second_kyc.status_code, 200)
        second_consent = self.client.post(f"/api/sign/{token2}/consent", json={"agreed": True})
        self.assertEqual(second_consent.status_code, 200)
        second_sign = self.client.post(f"/api/sign/{token2}/sign", json={})
        self.assertEqual(second_sign.status_code, 200)

    def test_wrong_signer_order_returns_409_after_consent(self):
        self._login(tenant_id=92)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "順番検証契約",
                "document_url": "https://example.com/order.pdf",
                "signers": [
                    {"name": "署名者A", "email": "a@example.com", "order_index": 1},
                    {"name": "署名者B", "email": "b@example.com", "order_index": 2},
                ],
            },
        )
        contract_id = create.get_json()["contract_id"]
        dispatch = self.client.post(f"/api/contracts/{contract_id}/dispatch", json={})
        token2 = dispatch.get_json()["signing_links"][1]["sign_url"].split("/api/sign/", 1)[1]

        self.client.post(
            f"/api/sign/{token2}/kyc",
            json={"kyc_provider": "mock", "kyc_session_id": "sess-3", "result": "success"},
        )
        self.client.post(f"/api/sign/{token2}/consent", json={"agreed": True})
        sign = self.client.post(f"/api/sign/{token2}/sign", json={})
        self.assertEqual(sign.status_code, 409)
        self.assertEqual(sign.get_json()["code"], "WRONG_SIGNER_ORDER")

    def _complete_all_signing(self, contract_id: str):
        """全署名者のKYC→同意→署名を完了するヘルパー"""
        dispatch = self.client.post(f"/api/contracts/{contract_id}/dispatch", json={})
        links = dispatch.get_json()["signing_links"]
        for link in links:
            token = link["sign_url"].split("/api/sign/", 1)[1]
            self.client.post(
                f"/api/sign/{token}/kyc",
                json={"kyc_provider": "mock", "kyc_session_id": f"sess-{token[:8]}", "result": "success"},
            )
            self.client.post(f"/api/sign/{token}/consent", json={"agreed": True})
            self.client.post(f"/api/sign/{token}/sign", json={})

    def test_finalize_contract(self):
        self._login(role="tenant_admin", tenant_id=20)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "業務委託契約（finalize検証）",
                "document_url": "https://example.com/final.pdf",
                "signers": [{"name": "署名者A", "email": "a@example.com", "order_index": 1}],
            },
        )
        self.assertEqual(create.status_code, 201)
        contract_id = create.get_json()["contract_id"]

        self._complete_all_signing(contract_id)

        resp = self.client.post(f"/api/contracts/{contract_id}/finalize", json={})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["status"], "completed")
        self.assertIsNotNone(payload["document_hash"])
        self.assertEqual(len(payload["document_hash"]), 64)
        self.assertIsNotNone(payload["signature_id"])
        self.assertIsNotNone(payload["timestamp_token"])
        self.assertIsNotNone(payload["finalized_at"])

    def test_finalize_returns_409_if_already_completed(self):
        self._login(role="tenant_admin", tenant_id=21)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "重複finalize検証",
                "document_url": "https://example.com/dup.pdf",
                "signers": [{"name": "署名者A", "email": "a@example.com", "order_index": 1}],
            },
        )
        contract_id = create.get_json()["contract_id"]
        self._complete_all_signing(contract_id)

        first = self.client.post(f"/api/contracts/{contract_id}/finalize", json={})
        self.assertEqual(first.status_code, 200)
        second = self.client.post(f"/api/contracts/{contract_id}/finalize", json={})
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.get_json()["code"], "ALREADY_COMPLETED")

    def test_finalize_returns_422_if_unsigned_signers_remain(self):
        self._login(role="tenant_admin", tenant_id=22)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "未署名finalize検証",
                "document_url": "https://example.com/unfinished.pdf",
                "signers": [
                    {"name": "署名者A", "email": "a@example.com", "order_index": 1},
                    {"name": "署名者B", "email": "b@example.com", "order_index": 2},
                ],
            },
        )
        contract_id = create.get_json()["contract_id"]
        self.client.post(f"/api/contracts/{contract_id}/dispatch", json={})

        resp = self.client.post(f"/api/contracts/{contract_id}/finalize", json={})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()["code"], "UNPROCESSABLE")

    def test_get_certificate_after_finalize(self):
        self._login(role="tenant_admin", tenant_id=23)
        create = self.client.post(
            "/api/contracts",
            json={
                "title": "証明書取得検証",
                "document_url": "https://example.com/cert.pdf",
                "signers": [{"name": "署名者A", "email": "a@example.com", "order_index": 1}],
            },
        )
        contract_id = create.get_json()["contract_id"]
        self._complete_all_signing(contract_id)
        self.client.post(f"/api/contracts/{contract_id}/finalize", json={})

        cert = self.client.get(f"/api/contracts/{contract_id}/certificate")
        self.assertEqual(cert.status_code, 200)
        payload = cert.get_json()
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["audit_chain_valid"])
        self.assertGreaterEqual(payload["audit_log_count"], 2)
        self.assertIsNotNone(payload["document_hash"])


if __name__ == "__main__":
    unittest.main()