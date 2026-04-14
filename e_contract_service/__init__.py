from __future__ import annotations

import os
import time
from flask import Flask, jsonify
from sqlalchemy import func

from .blueprints.contracts import bp as contracts_bp
from .blueprints.signing import bp as signing_bp
from .blueprints.finalize import bp as finalize_bp
from .blueprints.ui import bp as ui_bp
from .db import SessionLocal
from .migrations import run_migrations
from .models import AuditLog, Contract, Signer


_started_at = time.time()


def create_app() -> Flask:
    app = Flask(__name__)

    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    app.config.update(
        SESSION_COOKIE_NAME=os.environ.get("SESSION_COOKIE_NAME", "cm_session"),
        SESSION_COOKIE_DOMAIN=os.environ.get("SESSION_COOKIE_DOMAIN") or None,
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
        JSON_AS_ASCII=False,
    )

    run_migrations()
    app.register_blueprint(contracts_bp)
    app.register_blueprint(signing_bp)
    app.register_blueprint(finalize_bp)
    app.register_blueprint(ui_bp)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.get("/metrics")
    def metrics():
        db = SessionLocal()
        try:
            total_contracts = db.query(func.count(Contract.id)).scalar() or 0
            completed_contracts = db.query(func.count(Contract.id)).filter(Contract.status == "completed").scalar() or 0
            total_signers = db.query(func.count(Signer.id)).scalar() or 0
            signed_signers = db.query(func.count(Signer.id)).filter(Signer.status == "signed").scalar() or 0
            total_audit_logs = db.query(func.count(AuditLog.id)).scalar() or 0

            return jsonify(
                {
                    "uptime_seconds": int(time.time() - _started_at),
                    "contracts_total": total_contracts,
                    "contracts_completed": completed_contracts,
                    "signers_total": total_signers,
                    "signers_signed": signed_signers,
                    "audit_logs_total": total_audit_logs,
                }
            )
        finally:
            db.close()

    return app