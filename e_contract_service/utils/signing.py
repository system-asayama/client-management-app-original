"""T2-4/T2-5: 事業者署名 + RFC3161 タイムスタンプ

本番環境では以下の環境変数で本物の実装に切り替える:
  ENABLE_REAL_SIGNING=true   → cryptography ライブラリでRSA-PKCS#7署名
  ENABLE_REAL_TIMESTAMP=true → freetsa.org に RFC3161 リクエストを送信
  SIGNING_KEY_PEM=<PEM>      → 事業者秘密鍵（base64エンコード可）
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import urllib.request
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# T2-4: ドキュメントハッシュ + 事業者署名
# ---------------------------------------------------------------------------

def compute_document_hash(document_url: str) -> str:
    """ドキュメントURLをSHA-256でハッシュ化する（本番ではPDFバイナリをSHA-256）"""
    return hashlib.sha256(document_url.encode("utf-8")).hexdigest()


def sign_document_hash(hash_hex: str) -> str:
    """
    事業者秘密鍵でドキュメントハッシュに署名する。

    ENABLE_REAL_SIGNING=true かつ SIGNING_KEY_PEM が設定されている場合は
    cryptography ライブラリで RSA-PKCS#1v15 署名を行う。
    それ以外はHMAC-SHA256モックを返す（テスト用）。

    Returns:
        Base64エンコードされた署名バイト列
    """
    if os.environ.get("ENABLE_REAL_SIGNING", "").lower() == "true":
        return _real_pkcs7_sign(hash_hex)
    return _mock_sign(hash_hex)


def _mock_sign(hash_hex: str) -> str:
    """モック署名: HMAC-SHA256で決定論的なバイト列を返す"""
    key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production").encode()
    mac = hmac.new(key, msg=hash_hex.encode(), digestmod=hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def _real_pkcs7_sign(hash_hex: str) -> str:
    """本番署名: cryptography ライブラリを使用した RSA-PKCS#1v15 署名"""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        pem_b64 = os.environ.get("SIGNING_KEY_PEM", "")
        if not pem_b64:
            raise ValueError("SIGNING_KEY_PEM is not set")
        pem_data = base64.b64decode(pem_b64) if not pem_b64.startswith("-----") else pem_b64.encode()
        private_key = serialization.load_pem_private_key(pem_data, password=None)
        signature = private_key.sign(
            bytes.fromhex(hash_hex),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()
    except Exception as exc:
        raise RuntimeError(f"Real signing failed: {exc}") from exc


# ---------------------------------------------------------------------------
# T2-5: RFC3161 タイムスタンプ
# ---------------------------------------------------------------------------

def get_rfc3161_timestamp(hash_hex: str) -> str:
    """
    RFC3161 タイムスタンプトークンを取得する。

    ENABLE_REAL_TIMESTAMP=true の場合は freetsa.org に実際にリクエストを送信する。
    それ以外は基決定論的なモックトークン（テスト用）を返す。

    Returns:
        Base64エンコードされたタイムスタンプトークン
    """
    if os.environ.get("ENABLE_REAL_TIMESTAMP", "").lower() == "true":
        try:
            return _request_real_timestamp(hash_hex)
        except Exception:
            # 本番でも失敗時はモックにフォールバックしない → 例外を上位に伝播
            raise
    return _mock_timestamp(hash_hex)


def _mock_timestamp(hash_hex: str) -> str:
    """
    モックタイムスタンプ: 実際のDER構造を模したバイト列を返す。
    genTime(UTC) + messageImprint(SHA-256) を含む最小構造。
    """
    now = datetime.now(timezone.utc)
    gen_time_str = now.strftime("%Y%m%d%H%M%SZ").encode()
    hash_bytes = bytes.fromhex(hash_hex)

    # 最小限のASN.1風バイナリ（本番では実際のDER/CMS構造を使用のこと）
    payload = (
        b"\x30\x00"  # SEQUENCE placeholder
        + struct.pack(">H", len(gen_time_str)) + gen_time_str
        + b"\x02\x20" + hash_bytes  # INTEGER 32bytes = sha256
    )
    return base64.b64encode(payload).decode()


def _request_real_timestamp(hash_hex: str) -> str:
    """freetsa.org に RFC3161 リクエストを送信してタイムスタンプトークンを取得する"""
    hash_bytes = bytes.fromhex(hash_hex)

    # RFC3161 TimeStampReq の最小DER構造
    # SHA-256 OID: 2.16.840.1.101.3.4.2.1
    sha256_oid = bytes.fromhex("3031300d060960864801650304020105000420") + hash_bytes
    ts_req = (
        b"\x30"
        + _asn1_len(2 + len(sha256_oid))
        + b"\x02\x01\x01"  # version = 1
        + sha256_oid
    )

    req = urllib.request.Request(
        "https://freetsa.org/tsr",
        data=ts_req,
        method="POST",
        headers={"Content-Type": "application/timestamp-query"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        tsr_bytes = resp.read()

    return base64.b64encode(tsr_bytes).decode()


def _asn1_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    if n < 0x100:
        return bytes([0x81, n])
    return bytes([0x82, (n >> 8) & 0xFF, n & 0xFF])
