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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["APP_MANAGER"])
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

        # 国税(national)/地方税(local)の別
        tax_system = (request.form.get('tax_system') or 'national').strip()
        if tax_system not in ('national', 'local'):
            tax_system = 'national'

        # 認証情報の確認（方式B: 担当税理士 > 方式A: 顧問先本人）
        # 担当税理士は 明示割当 > 同一店舗 > テナント内一意 で自動判定する
        from app.utils.etax.etax_service import resolve_tax_accountant
        ta = resolve_tax_accountant(db, client, tax_system)
        if tax_system == 'local':
            ta_has = bool(ta and ta.eltax_user_id and ta.eltax_password)
            cli_has = bool(client.eltax_user_id and client.eltax_password)
            if cli_has:
                pass  # 方式A（顧問先本人ログイン）を優先
            elif ta_has:
                if not client.eltax_user_id:
                    return jsonify({"error": "代理発行には顧問先のeLTAX利用者IDが必要です。税務申告基本情報ページで登録してください。"}), 400
            else:
                # どこが足りないか具体的に案内する（具体的な状況を優先）
                if client.eltax_user_id and not client.eltax_password:
                    msg = "顧問先のeLTAX暗証番号が未登録です。税務申告基本情報で登録してください。"
                elif ta and not (ta.eltax_user_id and ta.eltax_password):
                    msg = "担当税理士にeLTAXの利用者ID・暗証番号が登録されていません。税理士登録で登録してください。"
                elif client.tax_accountant_id and not ta:
                    msg = "割り当てられた担当税理士が見つかりません（無効化されている可能性）。顧問先編集で担当税理士を選び直してください。"
                elif not client.tax_accountant_id:
                    msg = "担当税理士が割り当てられておらず、顧問先自身のeLTAX認証情報もありません。顧問先編集で担当税理士を割り当てるか、税務申告基本情報でeLTAXの利用者ID・暗証番号を登録してください。"
                else:
                    msg = "eLTAX 認証情報が未登録です（担当税理士または顧問先）。"
                return jsonify({"error": msg}), 400
        else:
            ta_has = bool(ta and ta.etax_user_id and ta.etax_password)
            cli_has = bool(client.etax_user_id and client.etax_password)
            if cli_has:
                pass  # 方式A（顧問先本人ログイン）を優先
            elif ta_has:
                if not client.etax_user_id:
                    return jsonify({"error": "代理発行には顧問先のe-Tax利用者識別番号が必要です。税務申告基本情報ページで登録してください。"}), 400
            else:
                if client.etax_user_id and not client.etax_password:
                    msg = "顧問先のe-Tax暗証番号が未登録です。税務申告基本情報で登録してください。"
                elif ta and not (ta.etax_user_id and ta.etax_password):
                    msg = "担当税理士にe-Taxの利用者識別番号・暗証番号が登録されていません。税理士登録で登録してください。"
                elif client.tax_accountant_id and not ta:
                    msg = "割り当てられた担当税理士が見つかりません（無効化されている可能性）。顧問先編集で担当税理士を選び直してください。"
                elif not client.tax_accountant_id:
                    msg = "担当税理士が割り当てられておらず、顧問先自身のe-Tax認証情報もありません。顧問先編集で担当税理士を割り当てるか、税務申告基本情報でe-Taxの利用者識別番号・暗証番号を登録してください。"
                else:
                    msg = "e-Tax 認証情報が未登録です（担当税理士または顧問先）。"
                return jsonify({"error": msg}), 400

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

        # 申告先税務署を取得（国税のみ）
        tax_office_name = ""
        if tax_system == 'national':
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
            tax_system=tax_system,
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
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"], ROLES["APP_MANAGER"])
def get_status(request_id):
    """
    送信ステータスをJSONで返す（Ajax ポーリング用）。
    """
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        # 認証切れでもHTMLへリダイレクトせずJSONで返す（フロントのポーリング用）
        return jsonify({"status": "error", "error_message": "セッションが切れました。再ログインしてください。"}), 200
    db = SessionLocal()
    try:
        req = db.query(TEtaxRequest).filter(
            and_(TEtaxRequest.id == request_id, TEtaxRequest.tenant_id == tenant_id)
        ).first()
        if not req:
            return jsonify({"status": "error", "error_message": "リクエストが見つかりません"}), 200

        # ウォッチドッグ: processing のまま一定時間更新が無い場合は
        # ワーカーが落ちた（メモリ不足でDyno強制終了等）とみなしてエラー確定。
        # → 画面が「処理中」で永久に止まるのを防ぐ。
        if req.status == "processing" and req.updated_at:
            stalled = (datetime.utcnow() - req.updated_at).total_seconds()
            if stalled > 240:  # 4分
                req.status = "error"
                req.error_message = (
                    "処理がタイムアウトしました（自動ブラウザ処理が時間内に完了しませんでした）。"
                    "サーバのメモリ不足でブラウザが強制終了した可能性があります。"
                )
                req.updated_at = datetime.utcnow()
                db.commit()

        return jsonify({
            "id": req.id,
            "status": req.status,
            "payment_code": req.payment_code,
            "pdf_file_url": req.pdf_file_url,
            "error_message": req.error_message,
            "updated_at": req.updated_at.isoformat() if req.updated_at else None,
        })
    except Exception as e:
        # 予期しない例外でもHTML 500を返さずJSONにする（原因を画面で確認できるように）
        logger.error(f"[etax] get_status エラー: {e}", exc_info=True)
        return jsonify({"status": "error", "error_message": f"ステータス取得エラー: {str(e)[:160]}"}), 200
    finally:
        db.close()


@bp.route('/history/<int:client_id>', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"], ROLES["APP_MANAGER"])
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


@bp.route('/national/login-test/<int:client_id>', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["APP_MANAGER"])
def national_login_test(client_id):
    """【国税・疎通テスト】e-Tax受付システムに『ログインのみ』を1回試す。

    A案（送受信モジュール相当の純Python実装）の核心＝拡張機能なしで
    認証が通るかを実証するための、安全に配慮したテスト専用エンドポイント。
    - データ送信は一切行わない（ログイン→結果確認→ログアウトのみ）。
    - 1回だけ・リトライなし（認証失敗連続によるアカウントロックを回避）。
    - 明示確認（confirm=1）が無ければ実行しない。
    - 認証情報は顧問先本人のe-Tax識別番号・暗証番号（方式A）を使用。
    """
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({"error": "テナントが選択されていません"}), 401
    if (request.form.get('confirm') or '') != '1':
        return jsonify({"error": "確認フラグ(confirm=1)が必要です。本番のe-Taxへログイン試行します。"}), 400

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            return jsonify({"error": "顧問先が見つかりません"}), 404
        uid = client.etax_user_id
        pwd = client.etax_password  # EncryptedString: 参照時に復号される
        if not uid or not pwd:
            return jsonify({"error": "顧問先のe-Tax利用者識別番号・暗証番号が未登録です。"
                                     "税務申告基本情報で登録してください。"}), 400
    finally:
        db.close()

    # 1回だけ本番ログインを試す（データ送信なし・リトライなし）
    from app.utils.etax.etax_web_client import EtaxWebClient
    result = EtaxWebClient.login_probe(uid, pwd)
    status_code = 200 if result.get("ok") else 502
    logger.info(f"[etax-web] 疎通テスト client_id={client_id} ok={result.get('ok')} "
                f"screen={result.get('screen_id')} err={result.get('error')}")
    return jsonify(result), status_code


@bp.route('/shot/<int:request_id>', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"], ROLES["APP_MANAGER"])
def error_shot(request_id):
    """
    RPAエラー時のスクリーンショット(PNG)を/tmpから直接配信する。
    ストレージ未設定でも診断画像を確認できるようにするフォールバック。
    （バックグラウンドスレッドは同一Dyno内で動くため/tmpを共有できる。
      Dyno再起動後は失効する）
    """
    import os as _os
    from flask import send_file, Response
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        req = db.query(TEtaxRequest).filter(
            and_(TEtaxRequest.id == request_id, TEtaxRequest.tenant_id == tenant_id)
        ).first()
        if not req:
            return Response("リクエストが見つかりません", status=404)
    finally:
        db.close()
    path = f"/tmp/eltax_error_{request_id}.png"
    if not _os.path.exists(path):
        return Response("スクリーンショットは失効しました（サーバ再起動後は保持されません）。再実行してください。",
                        status=404, mimetype="text/plain; charset=utf-8")
    return send_file(path, mimetype="image/png")


@bp.route('/pdf/<int:request_id>', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"], ROLES["APP_MANAGER"])
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
