from __future__ import annotations

from flask import Blueprint, redirect

from ..utils.decorators import ROLES, require_roles

bp = Blueprint("e_contract_bridge", __name__, url_prefix="/e-contract")


@bp.get("")
@bp.get("/")
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def index():
    # Redirect to the integrated e-contract UI (same process, no separate service needed).
    return redirect("/e-contract/ui/contracts")
