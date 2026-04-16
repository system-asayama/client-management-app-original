from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from ..db import SessionLocal
from ..models import Contract, Signature, Signer
from .contracts import _append_audit_log


bp = Blueprint("e_contract_signing", __name__, url_prefix="/api/sign")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_signing_context(db, token: str):
    signer = db.query(Signer).filter(Signer.access_token_hash == _hash_token(token)).first()
    if not signer:
        return None, None, (jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404)
    if signer.token_expires_at and signer.token_expires_at < _utcnow():
        return None, None, (jsonify({"error": "Expired", "code": "TOKEN_EXPIRED"}), 410)
    if signer.token_used_at or signer.status == "signed":
        return None, None, (jsonify({"error": "Already used", "code": "TOKEN_ALREADY_USED"}), 409)

    contract = db.query(Contract).filter(Contract.id == signer.contract_id).first()
    if not contract:
        return None, None, (jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404)
    return signer, contract, None


@bp.get("/<token>")
def verify_signing_token(token: str):
    db = SessionLocal()
    try:
        signer, contract, error = _load_signing_context(db, token)
        if error:
            return error

        return jsonify(
            {
                "contract_id": contract.id,
                "title": contract.title,
                "document_url": contract.document_url,
                "require_face_auth": bool(contract.require_face_auth),
                "signer": {
                    "signer_id": signer.id,
                    "name": signer.name,
                    "order_index": signer.order_index,
                    "status": signer.status,
                    "face_auth_status": signer.face_auth_status,
                },
            }
        )
    finally:
        db.close()


@bp.post("/<token>/face-auth")
def record_face_auth(token: str):
    """ブラウザ側顔照合の結果を受け取り、face_auth_statusを更新する。
    passed=True の場合は自動的にKYCも通過させ、status=kyc_passed にする。
    """
    payload = request.get_json(silent=True) or {}
    passed = payload.get("passed")
    similarity = payload.get("similarity", 0)

    if not isinstance(passed, bool):
        return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR"}), 400

    db = SessionLocal()
    try:
        signer, contract, error = _load_signing_context(db, token)
        if error:
            return error

        if not contract.require_face_auth:
            return jsonify({"error": "Face auth not required", "code": "UNPROCESSABLE"}), 422

        if passed:
            signer.face_auth_status = "passed"
            signer.kyc_status = "success"
            signer.status = "kyc_passed"
        else:
            signer.face_auth_status = "failed"

        _append_audit_log(
            db,
            contract_id=contract.id,
            action="face_auth_completed",
            actor_id=None,
            actor_type="signer",
            metadata={
                "signer_id": signer.id,
                "passed": passed,
                "similarity": similarity,
                "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
            },
        )
        db.commit()
        return jsonify({
            "signer_id": signer.id,
            "face_auth_status": signer.face_auth_status,
            "status": signer.status,
            "passed": passed,
        })
    finally:
        db.close()


@bp.post("/<token>/kyc")
def record_kyc(token: str):
    payload = request.get_json(silent=True) or {}
    provider = (payload.get("kyc_provider") or "").strip()
    session_id = (payload.get("kyc_session_id") or "").strip()
    result = payload.get("result")

    if not provider or not session_id or result not in {"success", "failed", "pending"}:
        return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR"}), 400

    db = SessionLocal()
    try:
        signer, contract, error = _load_signing_context(db, token)
        if error:
            return error
        if signer.status in {"kyc_passed", "consented"} and result == "success":
            return jsonify({"error": "Unprocessable", "code": "UNPROCESSABLE"}), 422

        signer.kyc_status = result
        if result == "success":
            signer.status = "kyc_passed"

        _append_audit_log(
            db,
            contract_id=contract.id,
            action="kyc_completed",
            actor_id=None,
            actor_type="signer",
            metadata={"signer_id": signer.id, "provider": provider, "result": result, "kyc_session_id": session_id},
        )
        db.commit()

        if result != "success":
            return jsonify({"signer_id": signer.id, "status": signer.status, "kyc_status": signer.kyc_status}), 200
        return jsonify({"signer_id": signer.id, "status": signer.status, "kyc_recorded_at": _utcnow().isoformat()})
    finally:
        db.close()


@bp.post("/<token>/consent")
def record_consent(token: str):
    payload = request.get_json(silent=True) or {}
    if payload.get("agreed") is not True:
        return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR"}), 400

    db = SessionLocal()
    try:
        signer, contract, error = _load_signing_context(db, token)
        if error:
            return error
        if signer.status != "kyc_passed" or signer.kyc_status != "success":
            return jsonify({"error": "Unprocessable", "code": "UNPROCESSABLE"}), 422

        signer.status = "consented"
        signer.ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        signer.user_agent = request.headers.get("User-Agent")

        _append_audit_log(
            db,
            contract_id=contract.id,
            action="consent_recorded",
            actor_id=None,
            actor_type="signer",
            metadata={"signer_id": signer.id, "ip": signer.ip, "user_agent": signer.user_agent},
        )
        db.commit()
        return jsonify(
            {
                "signer_id": signer.id,
                "status": signer.status,
                "consented_at": _utcnow().isoformat(),
                "ip_address": signer.ip,
                "user_agent": signer.user_agent,
            }
        )
    finally:
        db.close()


@bp.post("/<token>/sign")
def sign_contract(token: str):
    db = SessionLocal()
    try:
        signer, contract, error = _load_signing_context(db, token)
        if error:
            return error
        if signer.status != "consented":
            return jsonify({"error": "Unprocessable", "code": "UNPROCESSABLE"}), 422

        previous_signers = (
            db.query(Signer)
            .filter(Signer.contract_id == contract.id, Signer.order_index < signer.order_index)
            .order_by(Signer.order_index.asc())
            .all()
        )
        if any(row.status != "signed" for row in previous_signers):
            return jsonify({"error": "Wrong signer order", "code": "WRONG_SIGNER_ORDER"}), 409

        signed_at = _utcnow()
        signer.status = "signed"
        signer.signed_at = signed_at
        signer.token_used_at = signed_at
        if contract.status == "sent":
            contract.status = "signing"

        # 全署名者が署名済みかチェックして契約を完了状態にする
        all_signers = db.query(Signer).filter(Signer.contract_id == contract.id).all()
        if all(s.status == "signed" or s.id == signer.id for s in all_signers):
            contract.status = "completed"
            _append_audit_log(
                db,
                contract_id=contract.id,
                action="contract_completed",
                actor_id=None,
                actor_type="system",
                metadata={"total_signers": len(all_signers)},
            )

        # リクエストボディからsignature_data（手書きサイン画像のBase64）を取得
        body = request.get_json(silent=True) or {}
        signature_data = body.get("signature_data")  # data:image/png;base64,...

        signature = Signature(
            contract_id=contract.id,
            signer_id=signer.id,
            signature_data=signature_data,
        )
        db.add(signature)
        _append_audit_log(
            db,
            contract_id=contract.id,
            action="signature_applied",
            actor_id=None,
            actor_type="signer",
            metadata={"signer_id": signer.id, "order_index": signer.order_index},
        )
        db.commit()
        return jsonify(
            {
                "signer_id": signer.id,
                "status": signer.status,
                "signed_at": signed_at.isoformat(),
                "signature_id": signature.id,
            }
        )
    finally:
        db.close()