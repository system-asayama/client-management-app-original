# -*- coding: utf-8 -*-
"""
機微情報（顧問先の e-Tax / eLTAX 暗証番号など）の保管時暗号化ユーティリティ。

- Fernet（AES128-CBC + HMAC）で暗号化する。
- 暗号鍵は環境変数から導出する:
    1. CREDENTIAL_ENCRYPTION_KEY（推奨。任意文字列でも有効なFernet鍵でも可）
    2. 無ければ SECRET_KEY をSHA-256でハッシュして鍵に使う（フォールバック）
- 暗号文には "enc:v1:" プレフィックスを付与し、平文との区別を可能にする。
- 復号できない値・プレフィックスの無い値（旧データの平文）はそのまま返す
  （後方互換。段階的に暗号化へ移行できる）。

SQLAlchemyの EncryptedString 型を使うと、カラム読み書き時に透過的に
暗号化/復号されるため、既存の参照・保存・表示コードを変更する必要がない。
"""
import os
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import TypeDecorator, String

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"
_fernet_cache = None


def _build_fernet():
    """環境変数から Fernet インスタンスを構築（プロセス内でキャッシュ）。"""
    key_env = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
    if key_env:
        # 既に有効な Fernet 鍵（44文字の urlsafe base64）ならそのまま使う
        try:
            return Fernet(key_env.encode("ascii"))
        except Exception:
            raw = key_env.encode("utf-8")
    else:
        raw = os.environ.get(
            "SECRET_KEY", "dev-secret-key-change-in-production"
        ).encode("utf-8")
    # 任意文字列 → SHA-256(32byte) → urlsafe base64 で Fernet 鍵化
    fkey = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(fkey)


def _fernet():
    global _fernet_cache
    if _fernet_cache is None:
        _fernet_cache = _build_fernet()
    return _fernet_cache


def encrypt_secret(plaintext):
    """平文を暗号化して 'enc:v1:...' 形式の文字列を返す。None/空はそのまま。"""
    if plaintext is None:
        return None
    s = str(plaintext)
    if s == "":
        return ""
    if s.startswith(_PREFIX):
        return s  # 二重暗号化を防止
    try:
        token = _fernet().encrypt(s.encode("utf-8")).decode("ascii")
        return _PREFIX + token
    except Exception as e:  # 暗号化失敗時は保存を止めない（可用性優先）
        logger.error("encrypt_secret 失敗: %s", e)
        return s


def decrypt_secret(value):
    """'enc:v1:...' を復号して平文を返す。プレフィックスの無い値はそのまま返す。"""
    if value is None:
        return None
    s = str(value)
    if not s.startswith(_PREFIX):
        return s  # 旧データ（平文）はそのまま
    token = s[len(_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("decrypt_secret: 復号失敗（鍵不一致の可能性）")
        return s
    except Exception as e:
        logger.error("decrypt_secret 失敗: %s", e)
        return s


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(_PREFIX)


class EncryptedString(TypeDecorator):
    """保存時に暗号化・取得時に復号する透過的な文字列カラム型。"""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_secret(value)

    def process_result_value(self, value, dialect):
        return decrypt_secret(value)


def encrypt_existing_tax_credentials():
    """既存の平文で保存された e-Tax / eLTAX 暗証番号を一度だけ暗号化する。

    生SQLで 'enc:v1:' プレフィックスの無い値のみ対象にするため冪等。
    EncryptedString型を経由すると読取り時に復号されてしまうので、
    ここでは text() の生SQLで raw 値を読み書きする。
    """
    from sqlalchemy import text
    from app.db import SessionLocal

    columns = ("etax_password", "eltax_password")
    db = SessionLocal()
    updated = 0
    try:
        for col in columns:
            rows = db.execute(text(
                f'SELECT id, "{col}" FROM "T_顧問先" '
                f'WHERE "{col}" IS NOT NULL AND "{col}" <> \'\' '
                f'AND "{col}" NOT LIKE :pfx'
            ), {"pfx": _PREFIX + "%"}).fetchall()
            for rid, raw in rows:
                enc = encrypt_secret(raw)
                db.execute(text(
                    f'UPDATE "T_顧問先" SET "{col}" = :v WHERE id = :id'
                ), {"v": enc, "id": rid})
                updated += 1
        db.commit()
        if updated:
            logger.info("既存の税認証情報を暗号化しました: %d件", updated)
        return updated
    except Exception as e:
        db.rollback()
        logger.error("encrypt_existing_tax_credentials 失敗: %s", e)
        return 0
    finally:
        db.close()
