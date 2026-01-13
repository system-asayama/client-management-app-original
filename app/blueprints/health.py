from flask import Blueprint, jsonify, current_app

bp = Blueprint("health", __name__)

@bp.get("/healthz")
def healthz():
    """
    アプリケーションの状態を返します。
    ok=True のとき正常稼働です。
    """
    return jsonify(
        ok=True,
        env=current_app.config.get("ENVIRONMENT"),
        version=current_app.config.get("VERSION"),
    )
