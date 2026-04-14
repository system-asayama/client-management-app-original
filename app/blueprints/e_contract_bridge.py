from __future__ import annotations

import os
from urllib.parse import urljoin

from flask import Blueprint, redirect, session

from ..utils.decorators import ROLES, require_roles

bp = Blueprint("e_contract_bridge", __name__, url_prefix="/e-contract")


def _service_base_url() -> str:
    return os.environ.get("E_CONTRACT_SERVICE_URL", "http://localhost:5001").rstrip("/") + "/"


@bp.get("")
@bp.get("/")
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def index():
    # tenant context is kept in session; target service reads shared session cookie.
    return redirect(urljoin(_service_base_url(), "ui/contracts"))


@bp.get("/<path:subpath>")
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def forward(subpath: str):
    return redirect(urljoin(_service_base_url(), subpath))
