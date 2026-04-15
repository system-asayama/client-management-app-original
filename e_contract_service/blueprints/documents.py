from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from ..auth import require_roles

bp = Blueprint("e_contract_documents", __name__, url_prefix="/api/documents")

ALLOWED_EXTENSIONS = {"pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _upload_dir() -> str:
    """アップロードディレクトリを返す（環境変数 E_CONTRACT_UPLOAD_DIR 優先）。"""
    base = os.environ.get(
        "E_CONTRACT_UPLOAD_DIR",
        os.path.join(os.getcwd(), "uploads", "e_contracts"),
    )
    os.makedirs(base, exist_ok=True)
    return base


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@bp.post("/upload")
@require_roles("system_admin", "tenant_admin", "admin")
def upload_document():
    """
    契約書PDFをアップロードしてURLを返す。

    Request: multipart/form-data  field name = "file"
    Response: { "document_url": "/e-contract/api/documents/files/<filename>" }
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part", "code": "VALIDATION_ERROR"}), 400

    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "No file selected", "code": "VALIDATION_ERROR"}), 400

    if not _allowed(f.filename):
        return jsonify({"error": "Only PDF files are allowed", "code": "VALIDATION_ERROR"}), 400

    # ファイルサイズチェック（ストリームを読み切る前にContent-Lengthで確認）
    content_length = request.content_length
    if content_length and content_length > MAX_FILE_SIZE:
        return jsonify({"error": "File too large (max 20MB)", "code": "FILE_TOO_LARGE"}), 413

    # ユニークなファイル名を生成（タイムスタンプ + ランダム8文字 + 元のファイル名）
    original = secure_filename(f.filename)
    ts = _utcnow().strftime("%Y%m%d%H%M%S")
    rand = secrets.token_hex(4)
    saved_name = f"{ts}_{rand}_{original}"

    upload_dir = _upload_dir()
    save_path = os.path.join(upload_dir, saved_name)

    # ストリームを読み込んでサイズチェック
    data = f.read()
    if len(data) > MAX_FILE_SIZE:
        return jsonify({"error": "File too large (max 20MB)", "code": "FILE_TOO_LARGE"}), 413
    if len(data) == 0:
        return jsonify({"error": "Empty file", "code": "VALIDATION_ERROR"}), 400

    with open(save_path, "wb") as fp:
        fp.write(data)

    document_url = f"/e-contract/api/documents/files/{saved_name}"
    return jsonify({"document_url": document_url, "filename": original, "size": len(data)}), 201


@bp.get("/files/<path:filename>")
def serve_document(filename: str):
    """
    アップロード済みPDFを配信する。
    署名者ページからも参照されるため認証不要。
    ファイル名にパストラバーサルが含まれる場合は 404 を返す。
    """
    # パストラバーサル防止
    safe = secure_filename(filename)
    if safe != filename or ".." in filename or "/" in filename:
        return jsonify({"error": "Not found"}), 404

    upload_dir = _upload_dir()
    return send_from_directory(upload_dir, safe)
