# -*- coding: utf-8 -*-
"""
e-Tax 納付情報登録依頼 ブループリント

【エンドポイント一覧】
POST /etax/request/<client_id>          - 手動送信リクエスト作成＆実行
GET  /etax/status/<request_id>          - 送信ステータス確認（Ajax用）
GET  /etax/history/<client_id>          - 送信履歴一覧
GET  /etax/pdf/<request_id>             - PDFダウンロード（リダイレクト）
"""

import threading
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session, redirect, url_for, flash, render_template
from app.db import SessionLocal
from app.models_clients import TEtaxRequest, TClient, TTaxRecord, TFilingOfficeTaxOffice
from app.utils.decorators import require_roles, ROLES
from sqlalchemy import and_

logger = logging.getLogger(__name__)

bp = Blueprint('etax', __name__, url_prefix='/etax')


@bp.route('/request/<int:client_id>', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def create_request(client_id):
    """
    手動送信リクエストを作成してバックグラウンドでRPAを実行する。
    納税実績画面の「e-Tax送信」ボタンから呼び出される。
    """
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({"error": "テナントが選択されていません"}), 401

    db = SessionLocal()
    try:
        # 顧問先の存在確認
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            return jsonify({"error": "顧問先が見つかりません"}), 404

        # e-Tax認証情報の確認
        if not client.etax_user_id or not client.etax_password:
            return jsonify({
                "error": "e-Tax 利用者識別番号または暗証番号が未登録です。税務申告基本情報ページで登録してください。"
            }), 400

        # フォームデータの取得
        tax_record_id = request.form.get('tax_record_id', type=int)
        tax_type = request.form.get('tax_type', '').strip()
        filing_type = request.form.get('filing_type', '').strip()
        fiscal_year = request.form.get('fiscal_year', type=int)
        fiscal_end_month = request.form.get('fiscal_end_month', type=int)
        amount = request.form.get('amount', type=int)

        # バリデーション
        if not all([tax_type, filing_type, fiscal_year, fiscal_end_month, amount]):
            return jsonify({"error": "税目・申告区分・決算年度・決算月・金額は必須です"}), 400
        if amount <= 0:
            return jsonify({"error": "納付金額は1円以上を入力してください"}), 400

        # 申告先税務署を取得
        filing_office = db.query(TFilingOfficeTaxOffice).filter(
            TFilingOfficeTaxOffice.client_id == client_id
        ).first()
        tax_office_name = filing_office.tax_office_name if filing_office else ""

        # TEtaxRequestレコードを作成
        req = TEtaxRequest(
            client_id=client_id,
            tenant_id=tenant_id,
            tax_record_id=tax_record_id,
            request_type="manual",
            tax_type=tax_type,
            filing_type=filing_type,
            fiscal_year=fiscal_year,
            fiscal_end_month=fiscal_end_month,
            amount=amount,
            tax_office_name=tax_office_name,
            status="pending",
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        request_id = req.id

    finally:
        db.close()

    # バックグラウンドスレッドでRPAを実行（Heroku Dynoのリクエストタイムアウトを回避）
    def _run_in_background(req_id):
        try:
            from app.utils.etax.etax_service import execute_etax_request
            execute_etax_request(req_id)
        except Exception as e:
            logger.error(f"[etax] バックグラウンド実行エラー: {e}", exc_info=True)

    thread = threading.Thread(target=_run_in_background, args=(request_id,), daemon=True)
    thread.start()

    return jsonify({
        "status": "accepted",
        "request_id": request_id,
        "message": "e-Tax送信を受け付けました。処理完了後に結果が表示されます。",
    }), 202


@bp.route('/status/<int:request_id>', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def get_status(request_id):
    """
    送信ステータスをJSONで返す（Ajax ポーリング用）。
    """
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        req = db.query(TEtaxRequest).filter(
            and_(TEtaxRequest.id == request_id, TEtaxRequest.tenant_id == tenant_id)
        ).first()
        if not req:
            return jsonify({"error": "リクエストが見つかりません"}), 404

        return jsonify({
            "id": req.id,
            "status": req.status,
            "payment_code": req.payment_code,
            "pdf_file_url": req.pdf_file_url,
            "error_message": req.error_message,
            "updated_at": req.updated_at.isoformat() if req.updated_at else None,
        })
    finally:
        db.close()


@bp.route('/history/<int:client_id>', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def history(client_id):
    """
    顧問先のe-Tax送信履歴一覧を返す（JSON）。
    """
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            return jsonify({"error": "顧問先が見つかりません"}), 404

        requests = db.query(TEtaxRequest).filter(
            TEtaxRequest.client_id == client_id
        ).order_by(TEtaxRequest.created_at.desc()).limit(50).all()

        return jsonify({
            "requests": [
                {
                    "id": r.id,
                    "request_type": r.request_type,
                    "tax_type": r.tax_type,
                    "filing_type": r.filing_type,
                    "fiscal_year": r.fiscal_year,
                    "fiscal_end_month": r.fiscal_end_month,
                    "amount": r.amount,
                    "status": r.status,
                    "payment_code": r.payment_code,
                    "pdf_file_url": r.pdf_file_url,
                    "error_message": r.error_message,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in requests
            ]
        })
    finally:
        db.close()


@bp.route('/pdf/<int:request_id>', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def download_pdf(request_id):
    """
    納付区分番号通知PDFのURLにリダイレクトする。
    """
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        req = db.query(TEtaxRequest).filter(
            and_(TEtaxRequest.id == request_id, TEtaxRequest.tenant_id == tenant_id)
        ).first()
        if not req:
            flash("リクエストが見つかりません", "error")
            return redirect(url_for('clients.clients'))

        if not req.pdf_file_url:
            flash("PDFがまだ生成されていません", "warning")
            return redirect(url_for('clients.clients'))

        return redirect(req.pdf_file_url)
    finally:
        db.close()
