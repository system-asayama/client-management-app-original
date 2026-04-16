from __future__ import annotations

from flask import Blueprint, render_template

from ..auth import require_roles
from ..db import SessionLocal
from ..models import Contract, Signer

bp = Blueprint("e_contract_ui", __name__, url_prefix="/ui", template_folder="../templates")


@bp.get("/contracts")
@require_roles("system_admin", "tenant_admin", "admin")
def contracts_list_page():
    db = SessionLocal()
    try:
        contracts = db.query(Contract).order_by(Contract.created_at.desc()).limit(100).all()
        return render_template("e_contract_contracts.html", contracts=contracts)
    finally:
        db.close()


@bp.get("/contracts/create")
@require_roles("system_admin", "tenant_admin", "admin")
def contracts_create_page():
    return render_template("e_contract_create.html")


@bp.get("/contracts/<contract_id>")
@require_roles("system_admin", "tenant_admin", "admin")
def contracts_detail_page(contract_id: str):
    db = SessionLocal()
    try:
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        signers = db.query(Signer).filter(Signer.contract_id == contract_id).order_by(Signer.order_index.asc()).all()
        return render_template("e_contract_detail.html", contract=contract, signers=signers)
    finally:
        db.close()


@bp.get("/sign/<token>")
def signer_page(token: str):
    return render_template("e_contract_signer.html", token=token)


@bp.get("/contracts/<contract_id>/sign-fields")
@require_roles("system_admin", "tenant_admin", "admin")
def sign_fields_page(contract_id: str):
    return render_template("e_contract_sign_fields.html", contract_id=contract_id)


@bp.get("/contracts/<contract_id>/done")
@require_roles("system_admin", "tenant_admin", "admin")
def completed_page(contract_id: str):
    return render_template("e_contract_done.html", contract_id=contract_id)
