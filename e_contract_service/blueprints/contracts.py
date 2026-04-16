from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from ..auth import require_roles
from ..db import SessionLocal
from ..models import AuditLog, Contract, Signer


bp = Blueprint("e_contract_contracts", __name__, url_prefix="/api/contracts")


def _canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _append_audit_log(db, contract_id: str, action: str, actor_id: int, actor_type: str, metadata: dict) -> None:
    max_seq = db.query(func.max(AuditLog.seq)).filter(AuditLog.contract_id == contract_id).scalar()
    next_seq = (max_seq or 0) + 1
    previous = (
        db.query(AuditLog)
        .filter(AuditLog.contract_id == contract_id)
        .order_by(AuditLog.seq.desc())
        .first()
    )
    prev_hash = previous.hash if previous else ""
    created_at = _utcnow()
    payload = {
        "action": action,
        "actor_id": actor_id,
        "actor_type": actor_type,
        "contract_id": contract_id,
        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "detail": metadata,
        "prev_hash": prev_hash,
        "seq": next_seq,
    }
    canonical = _canonical_json(payload)
    db.add(
        AuditLog(
            contract_id=contract_id,
            seq=next_seq,
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            metadata_json=_canonical_json(metadata),
            canonical_json=canonical,
            prev_hash=prev_hash,
            hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            created_at=created_at,
        )
    )
    # Ensure subsequent log writes in the same transaction see the new seq.
    db.flush()


def _serialize_signer(signer: Signer) -> dict:
    return {
        "signer_id": signer.id,
        "name": signer.name,
        "email": signer.email,
        "order_index": signer.order_index,
        "status": signer.status,
        "face_auth_status": signer.face_auth_status,
        "signed_at": signer.signed_at.isoformat() if signer.signed_at else None,
    }


def _authorize_contract_query(db, contract_id: str):
    query = db.query(Contract).filter(Contract.id == contract_id)
    if g.auth.role != "system_admin":
        query = query.filter(Contract.tenant_id == g.auth.tenant_id)
    return query


def _serialize_audit_log(log: AuditLog) -> dict:
    return {
        "log_id": log.id,
        "seq": log.seq,
        "action": log.action,
        "actor_id": log.actor_id,
        "actor_type": log.actor_type,
        "detail": json.loads(log.metadata_json),
        "prev_hash": log.prev_hash,
        "hash": log.hash,
        "created_at": log.created_at.isoformat(),
    }


def _verify_audit_chain(logs: list[AuditLog]) -> tuple[bool, int | None]:
    expected_prev_hash = ""
    for log in logs:
        if log.prev_hash != expected_prev_hash:
            return False, log.seq
        payload = {
            "action": log.action,
            "actor_id": log.actor_id,
            "actor_type": log.actor_type,
            "contract_id": log.contract_id,
            "created_at": log.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "detail": json.loads(log.metadata_json),
            "prev_hash": log.prev_hash,
            "seq": log.seq,
        }
        canonical = _canonical_json(payload)
        recalculated = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if recalculated != log.hash:
            return False, log.seq
        expected_prev_hash = log.hash
    return True, None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@bp.post("")
@require_roles("system_admin", "tenant_admin", "admin")
def create_contract():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    document_url = (payload.get("document_url") or "").strip()
    signers = payload.get("signers") or []
    require_face_auth = 1 if payload.get("require_face_auth") else 0

    if not title or len(title) > 255 or not document_url or not isinstance(signers, list) or not signers:
        return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR"}), 400

    seen_orders = set()
    cleaned_signers = []
    for signer in signers:
        name = (signer.get("name") or "").strip()
        email = (signer.get("email") or "").strip()
        order_index = signer.get("order_index")
        if not name or not email or "@" not in email or not isinstance(order_index, int) or order_index < 1:
            return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR"}), 400
        if order_index in seen_orders:
            return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR", "detail": "duplicate order_index"}), 400
        seen_orders.add(order_index)
        cleaned_signers.append({"name": name, "email": email, "order_index": order_index})

    db = SessionLocal()
    try:
        contract = Contract(
            tenant_id=g.auth.tenant_id or 0,
            created_by=g.auth.user_id,
            title=title,
            document_url=document_url,
            status="draft",
            require_face_auth=require_face_auth,
        )
        db.add(contract)
        db.flush()

        signer_rows = []
        for signer in sorted(cleaned_signers, key=lambda item: item["order_index"]):
            face_auth_status = "pending" if require_face_auth else "not_required"
            row = Signer(contract_id=contract.id, face_auth_status=face_auth_status, **signer)
            db.add(row)
            signer_rows.append(row)

        _append_audit_log(
            db,
            contract_id=contract.id,
            action="contract_created",
            actor_id=g.auth.user_id,
            actor_type="user",
            metadata={"title": title, "signer_count": len(signer_rows)},
        )
        db.commit()

        return jsonify(
            {
                "contract_id": contract.id,
                "title": contract.title,
                "status": contract.status,
                "tenant_id": contract.tenant_id,
                "created_by": contract.created_by,
                "created_at": contract.created_at.isoformat(),
                "signers": [_serialize_signer(signer) for signer in signer_rows],
            }
        ), 201
    finally:
        db.close()


@bp.get("")
@require_roles("system_admin", "tenant_admin", "admin", "employee")
def list_contracts():
    status = request.args.get("status")
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    allowed_statuses = {None, "draft", "sent", "signing", "completed"}
    if status not in allowed_statuses:
        return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR"}), 400

    db = SessionLocal()
    try:
        query = db.query(Contract)
        if g.auth.role != "system_admin":
            query = query.filter(Contract.tenant_id == g.auth.tenant_id)
        if status:
            query = query.filter(Contract.status == status)

        total = query.count()
        contracts = (
            query.order_by(Contract.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        items = []
        for contract in contracts:
            signer_count = db.query(func.count(Signer.id)).filter(Signer.contract_id == contract.id).scalar() or 0
            signed_count = (
                db.query(func.count(Signer.id))
                .filter(Signer.contract_id == contract.id, Signer.status == "signed")
                .scalar()
                or 0
            )
            items.append(
                {
                    "contract_id": contract.id,
                    "title": contract.title,
                    "status": contract.status,
                    "created_at": contract.created_at.isoformat(),
                    "signer_count": signer_count,
                    "signed_count": signed_count,
                }
            )

        return jsonify({"contracts": items, "total": total, "page": page, "per_page": per_page})
    finally:
        db.close()


@bp.get("/<contract_id>")
@require_roles("system_admin", "tenant_admin", "admin", "employee")
def get_contract(contract_id: str):
    db = SessionLocal()
    try:
        query = db.query(Contract).filter(Contract.id == contract_id)
        if g.auth.role != "system_admin":
            query = query.filter(Contract.tenant_id == g.auth.tenant_id)

        contract = query.first()
        if not contract:
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404

        signers = (
            db.query(Signer)
            .filter(Signer.contract_id == contract.id)
            .order_by(Signer.order_index.asc())
            .all()
        )
        return jsonify(
            {
                "contract_id": contract.id,
                "title": contract.title,
                "document_url": contract.document_url,
                "status": contract.status,
                "require_face_auth": bool(contract.require_face_auth),
                "tenant_id": contract.tenant_id,
                "created_by": contract.created_by,
                "created_at": contract.created_at.isoformat(),
                "updated_at": contract.updated_at.isoformat(),
                "signers": [_serialize_signer(signer) for signer in signers],
            }
        )
    finally:
        db.close()


@bp.post("/<contract_id>/dispatch")
@require_roles("system_admin", "tenant_admin", "admin")
def dispatch_contract(contract_id: str):
    db = SessionLocal()
    try:
        contract = _authorize_contract_query(db, contract_id).first()
        if not contract:
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404
        if contract.status != "draft":
            return jsonify({"error": "Unprocessable", "code": "UNPROCESSABLE"}), 422

        signers = db.query(Signer).filter(Signer.contract_id == contract.id).order_by(Signer.order_index.asc()).all()
        if not signers:
            return jsonify({"error": "Unprocessable", "code": "UNPROCESSABLE", "detail": "no signers"}), 422

        issued = []
        expires_at = _utcnow() + timedelta(days=7)
        for signer in signers:
            token = secrets.token_urlsafe(32)
            signer.access_token_hash = _hash_token(token)
            signer.token_expires_at = expires_at
            signer.token_used_at = None
            issued.append(
                {
                    "signer_id": signer.id,
                    "email": signer.email,
                    "sign_url": f"{request.url_root.rstrip('/')}/e-contract/ui/sign/{token}",
                    "expires_at": expires_at.isoformat(),
                }
            )
            _append_audit_log(
                db,
                contract_id=contract.id,
                action="signer_token_issued",
                actor_id=g.auth.user_id,
                actor_type="system",
                metadata={"signer_id": signer.id, "email": signer.email},
            )

        contract.status = "sent"
        _append_audit_log(
            db,
            contract_id=contract.id,
            action="contract_dispatched",
            actor_id=g.auth.user_id,
            actor_type="user",
            metadata={"signer_count": len(issued)},
        )
        db.commit()

        # 店舗SMTPで署名依頼メールを送信
        mail_results = []
        tenant_id = g.auth.tenant_id
        store_id = g.auth.store_id
        if tenant_id or store_id:
            try:
                from ..mailer import send_signing_request_email
                expires_str = expires_at.strftime('%Y年%m月%d日 %H:%M')
                for item in issued:
                    signer_obj = next((s for s in signers if s.id == item["signer_id"]), None)
                    signer_name = signer_obj.name if signer_obj else item["email"]
                    sent = send_signing_request_email(
                        tenant_id=tenant_id,
                        signer_name=signer_name,
                        signer_email=item["email"],
                        contract_title=contract.title,
                        sign_url=item["sign_url"],
                        expires_at=expires_str,
                        store_id=store_id,
                    )
                    mail_results.append({"email": item["email"], "sent": sent})
            except Exception as mail_err:
                import logging
                logging.getLogger(__name__).error(f"メール送信エラー: {mail_err}")

        return jsonify(
            {
                "contract_id": contract.id,
                "status": contract.status,
                "dispatched_at": _utcnow().isoformat(),
                "signer_count": len(issued),
                "signing_links": issued,
                "mail_results": mail_results,
            }
        )
    finally:
        db.close()


@bp.get("/<contract_id>/audit")
@require_roles("system_admin", "tenant_admin")
def get_audit_logs(contract_id: str):
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 50)), 1), 100)
    db = SessionLocal()
    try:
        contract = _authorize_contract_query(db, contract_id).first()
        if not contract:
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404

        query = db.query(AuditLog).filter(AuditLog.contract_id == contract_id).order_by(AuditLog.seq.asc())
        total = query.count()
        logs = query.offset((page - 1) * per_page).limit(per_page).all()
        return jsonify({"contract_id": contract_id, "logs": [_serialize_audit_log(log) for log in logs], "total": total})
    finally:
        db.close()


@bp.post("/<contract_id>/verify")
@require_roles("system_admin", "tenant_admin")
def verify_audit_logs(contract_id: str):
    db = SessionLocal()
    try:
        contract = _authorize_contract_query(db, contract_id).first()
        if not contract:
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404

        logs = db.query(AuditLog).filter(AuditLog.contract_id == contract_id).order_by(AuditLog.seq.asc()).all()
        verified, tampered_seq = _verify_audit_chain(logs)
        return jsonify(
            {
                "contract_id": contract_id,
                "verified": verified,
                "first_tampered_seq": tampered_seq,
                "verified_at": _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    finally:
        db.close()

@bp.delete("/<contract_id>")
@require_roles("system_admin", "tenant_admin", "admin")
def delete_contract(contract_id: str):
    db = SessionLocal()
    try:
        contract = _authorize_contract_query(db, contract_id).first()
        if not contract:
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404

        # 関連するSignerとAuditLogも削除
        db.query(Signer).filter(Signer.contract_id == contract_id).delete()
        db.query(AuditLog).filter(AuditLog.contract_id == contract_id).delete()
        db.delete(contract)
        db.commit()

        return jsonify({"message": "deleted", "contract_id": contract_id})
    finally:
        db.close()
