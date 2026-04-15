from __future__ import annotations

from dataclasses import dataclass
from functools import wraps

from flask import g, jsonify, session


ALLOWED_ROLES = {"system_admin", "tenant_admin", "admin", "employee"}


@dataclass
class AuthContext:
    user_id: int
    user_name: str | None
    role: str
    tenant_id: int | None
    store_id: int | None
    is_owner: bool


def get_auth_context() -> AuthContext:
    role = session.get("role")
    user_id = session.get("user_id")
    user_name = session.get("user_name")
    tenant_id = session.get("tenant_id")
    store_id = session.get("store_id")
    is_owner = bool(session.get("is_owner", False))

    if not role or not user_id:
        raise PermissionError("AUTH_REQUIRED")
    if role not in ALLOWED_ROLES:
        raise PermissionError("INSUFFICIENT_ROLE")
    if role != "system_admin" and not tenant_id:
        raise LookupError("TENANT_MISMATCH")

    return AuthContext(
        user_id=int(user_id),
        user_name=user_name,
        role=role,
        tenant_id=tenant_id,
        store_id=store_id,
        is_owner=is_owner,
    )


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            g.auth = get_auth_context()
        except PermissionError as exc:
            code = str(exc)
            status = 401 if code == "AUTH_REQUIRED" else 403
            return jsonify({"error": "Unauthorized" if status == 401 else "Forbidden", "code": code}), status
        except LookupError as exc:
            return jsonify({"error": "Forbidden", "code": str(exc)}), 403
        return view(*args, **kwargs)

    return wrapped


def require_roles(*roles: str):
    def decorator(view):
        @wraps(view)
        @require_auth
        def wrapped(*args, **kwargs):
            if g.auth.role not in roles:
                return jsonify({"error": "Forbidden", "code": "INSUFFICIENT_ROLE"}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator