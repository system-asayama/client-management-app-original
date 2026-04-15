from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from .db import Base


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(Integer, nullable=False, index=True)
    created_by = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    document_url = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="draft")
    hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class Signer(Base):
    __tablename__ = "signers"
    __table_args__ = (
        UniqueConstraint("contract_id", "order_index", name="uq_signers_contract_order"),
        UniqueConstraint("access_token_hash", name="uq_signers_access_token_hash"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    order_index = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    kyc_status = Column(String(32), nullable=False, default="pending")
    signed_at = Column(DateTime, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    access_token_hash = Column(String(64), nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    token_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class Signature(Base):
    __tablename__ = "signatures"

    id = Column(String(36), primary_key=True, default=_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_id = Column(String(36), ForeignKey("signers.id", ondelete="SET NULL"), nullable=True)
    signature_data = Column(Text, nullable=True)
    timestamp_token = Column(Text, nullable=True)
    signed_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "contract_audit_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_id = Column(String(36), ForeignKey("signers.id", ondelete="SET NULL"), nullable=True)
    seq = Column(Integer, nullable=False)
    action = Column(String(64), nullable=False)
    actor_id = Column(Integer, nullable=True)
    actor_type = Column(String(32), nullable=False)
    metadata_json = Column(Text, nullable=False)
    canonical_json = Column(Text, nullable=False)
    prev_hash = Column(String(64), nullable=False, default="")
    hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
