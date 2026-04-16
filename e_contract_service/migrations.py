from __future__ import annotations

from sqlalchemy import text

from .db import Base, engine
from . import models  # noqa: F401


def _column_exists(conn, table: str, column: str) -> bool:
    """DBに依存しないカラム存在チェック。"""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result)
    elif dialect in ("mysql", "mariadb"):
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ),
            {"t": table, "c": column},
        )
        return bool(result.scalar())
    elif dialect == "postgresql":
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
        return bool(result.scalar())
    # fallback: assume not exists
    return False


def run_migrations() -> None:
    # 新規テーブルを作成
    Base.metadata.create_all(bind=engine)

    # 既存テーブルへのカラム追加マイグレーション
    with engine.begin() as conn:
        dialect = conn.dialect.name

        # contracts.require_face_auth
        if not _column_exists(conn, "contracts", "require_face_auth"):
            conn.execute(
                text("ALTER TABLE contracts ADD COLUMN require_face_auth INTEGER NOT NULL DEFAULT 0")
            )

        # signers.face_auth_status
        if not _column_exists(conn, "signers", "face_auth_status"):
            if dialect == "sqlite":
                conn.execute(
                    text("ALTER TABLE signers ADD COLUMN face_auth_status VARCHAR(32) NOT NULL DEFAULT 'not_required'")
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE signers ADD COLUMN face_auth_status VARCHAR(32) NOT NULL DEFAULT 'not_required'"
                    )
                )

        # contracts.sign_fields (署名欄位置情報 JSON)
        if not _column_exists(conn, "contracts", "sign_fields"):
            conn.execute(
                text("ALTER TABLE contracts ADD COLUMN sign_fields TEXT")
            )

        # signatures.signature_data (手書きサイン画像 Base64)
        if not _column_exists(conn, "signatures", "signature_data"):
            conn.execute(
                text("ALTER TABLE signatures ADD COLUMN signature_data TEXT")
            )
