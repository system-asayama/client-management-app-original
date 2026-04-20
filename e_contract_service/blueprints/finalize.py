"""T2-6: finalize Blueprint — 全員署名後に事業者署名・タイムスタンプを付与して完了遷移"""

from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..auth import require_roles
from ..blueprints.contracts import _append_audit_log, _authorize_contract_query, _utcnow
from ..db import SessionLocal
from ..models import AuditLog, Contract, Signature, Signer
from ..utils.signing import compute_document_hash, get_rfc3161_timestamp, sign_document_hash

bp = Blueprint("e_contract_finalize", __name__, url_prefix="/api/contracts")


@bp.post("/<contract_id>/finalize")
@require_roles("system_admin", "tenant_admin", "admin", "app_manager")
def finalize_contract(contract_id: str):
    """
    全署名者の署名完了後、事業者署名とRFC3161タイムスタンプを付与して契約を完了状態に遷移する。

    Response:
      200 { contract_id, status, document_hash, signature_id, timestamp_token, finalized_at }
    Errors:
      404  契約が存在しない
      409  既にcompleted済み
      422  未署名の署名者が残っている
    """
    db = SessionLocal()
    try:
        contract = _authorize_contract_query(db, contract_id).first()
        if not contract:
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404

        if contract.status == "completed":
            return jsonify({"error": "Already completed", "code": "ALREADY_COMPLETED"}), 409

        signers = db.query(Signer).filter(Signer.contract_id == contract_id).all()
        if not signers:
            return jsonify({"error": "No signers", "code": "VALIDATION_ERROR"}), 422

        unsigned = [s for s in signers if s.status != "signed"]
        if unsigned:
            return jsonify({
                "error": "Unsigned signers remain",
                "code": "UNPROCESSABLE",
                "unsigned_signer_ids": [s.id for s in unsigned],
            }), 422

        # T2-4: ドキュメントハッシュ + 事業者署名
        doc_hash = compute_document_hash(contract.document_url)
        signature_data = sign_document_hash(doc_hash)

        # T2-5: RFC3161 タイムスタンプ
        timestamp_token = get_rfc3161_timestamp(doc_hash)

        finalized_at = _utcnow()

        # 事業者署名レコード（signer_id=None で区別）
        op_signature = Signature(
            contract_id=contract_id,
            signer_id=None,
            signed_hash=doc_hash,
            signature_data=signature_data,
            timestamp_token=timestamp_token,
            created_at=finalized_at,
        )
        db.add(op_signature)

        # T2-6: 完了遷移
        contract.status = "completed"
        contract.hash = doc_hash

        _append_audit_log(
            db,
            contract_id=contract_id,
            action="contract_finalized",
            actor_id=g.auth.user_id,
            actor_type="operator",
            metadata={
                "document_hash": doc_hash,
                "signed_by": g.auth.user_id,
                "signer_count": len(signers),
            },
        )

        db.commit()

        return jsonify({
            "contract_id": contract_id,
            "status": contract.status,
            "document_hash": doc_hash,
            "signature_id": op_signature.id,
            "timestamp_token": timestamp_token,
            "finalized_at": finalized_at.isoformat(),
        })
    finally:
        db.close()


@bp.get("/<contract_id>/certificate")
@require_roles("system_admin", "tenant_admin", "admin", "app_manager")
def get_certificate(contract_id: str):
    """
    完了済み契約の証明書情報（hashチェーン全体 + 最終タイムスタンプ）を返す。

    Response:
      200 { contract_id, status, document_hash, audit_log_count, audit_chain_valid, finalized_at }
    """
    db = SessionLocal()
    try:
        contract = _authorize_contract_query(db, contract_id).first()
        if not contract:
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404

        if contract.status != "completed":
            return jsonify({"error": "Not completed", "code": "UNPROCESSABLE"}), 422

        logs = (
            db.query(AuditLog)
            .filter(AuditLog.contract_id == contract_id)
            .order_by(AuditLog.seq.asc())
            .all()
        )

        # hashチェーン検証
        chain_valid = True
        prev_hash = ""
        for log in logs:
            if log.prev_hash != prev_hash:
                chain_valid = False
                break
            prev_hash = log.hash

        op_sig = (
            db.query(Signature)
            .filter(Signature.contract_id == contract_id, Signature.signer_id.is_(None))
            .order_by(Signature.created_at.desc())
            .first()
        )

        return jsonify({
            "contract_id": contract_id,
            "status": contract.status,
            "document_hash": contract.hash,
            "audit_log_count": len(logs),
            "audit_chain_valid": chain_valid,
            "timestamp_token": op_sig.timestamp_token if op_sig else None,
            "finalized_at": op_sig.created_at.isoformat() if op_sig else None,
        })
    finally:
        db.close()
