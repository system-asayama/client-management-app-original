# -*- coding: utf-8 -*-
"""
e-Tax 納付情報登録依頼 サービス層

RPAワーカーの呼び出し、DBの更新、PDFのストレージ保存を担当する。
FlaskエンドポイントおよびバッチスクリプトからこのServiceを呼び出す。
"""

import os
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


def execute_etax_request(request_id: int) -> dict:
    """
    TEtaxRequest.id を受け取り、RPAを実行してDBを更新する。

    Args:
        request_id: TEtaxRequest.id

    Returns:
        dict: {"status": "completed"|"error", "message": str}
    """
    from app.db import SessionLocal
    from app.models_clients import TEtaxRequest, TClient

    db = SessionLocal()
    try:
        req = db.query(TEtaxRequest).filter(TEtaxRequest.id == request_id).first()
        if not req:
            return {"status": "error", "message": f"request_id={request_id} が見つかりません"}

        if req.status not in ("pending", "error"):
            return {"status": "skipped", "message": f"ステータスが {req.status} のためスキップ"}

        # ステータスを「処理中」に更新
        req.status = "processing"
        req.updated_at = datetime.utcnow()
        db.commit()

        # 顧問先の認証情報を取得
        client = db.query(TClient).filter(TClient.id == req.client_id).first()
        if not client:
            _mark_error(db, req, "顧問先が見つかりません")
            return {"status": "error", "message": "顧問先が見つかりません"}

        if not client.etax_user_id or not client.etax_password:
            _mark_error(db, req, "e-Tax 利用者識別番号または暗証番号が未登録です")
            return {"status": "error", "message": "e-Tax 認証情報が未登録です"}

        # RPAワーカーを実行
        from app.utils.etax.rpa_worker import run_etax_payment_request
        result = run_etax_payment_request(
            etax_user_id=client.etax_user_id,
            etax_password=client.etax_password,
            tax_type=req.tax_type or "",
            filing_type=req.filing_type or "",
            fiscal_year=req.fiscal_year or 0,
            fiscal_end_month=req.fiscal_end_month or 0,
            amount=req.amount or 0,
            tax_office_name=req.tax_office_name or "",
            request_id=request_id,
        )

        if result["status"] == "completed":
            # PDFをストレージにアップロード
            pdf_url = None
            if result.get("pdf_path") and os.path.exists(result["pdf_path"]):
                pdf_url = _upload_pdf_to_storage(
                    pdf_path=result["pdf_path"],
                    client_id=req.client_id,
                    request_id=request_id,
                )

            # DBを完了状態に更新
            req.status = "completed"
            req.payment_code = result.get("payment_code")
            req.pdf_file_url = pdf_url
            req.error_message = None
            req.updated_at = datetime.utcnow()
            db.commit()

            logger.info(f"[Service] request_id={request_id} 完了: payment_code={req.payment_code}")
            return {"status": "completed", "message": "納付情報登録依頼が完了しました", "payment_code": req.payment_code}

        else:
            req.retry_count = (req.retry_count or 0) + 1
            _mark_error(db, req, result.get("error_message", "不明なエラー"))
            return {"status": "error", "message": result.get("error_message", "不明なエラー")}

    except Exception as e:
        logger.error(f"[Service] request_id={request_id} 予期しないエラー: {e}", exc_info=True)
        try:
            req = db.query(TEtaxRequest).filter(TEtaxRequest.id == request_id).first()
            if req:
                _mark_error(db, req, str(e))
        except Exception:
            pass
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def create_manual_request(
    client_id: int,
    tenant_id: int,
    tax_record_id: Optional[int],
    tax_type: str,
    filing_type: str,
    fiscal_year: int,
    fiscal_end_month: int,
    amount: int,
    tax_office_name: str,
) -> int:
    """
    手動送信用のTEtaxRequestレコードを作成してIDを返す。

    Returns:
        int: 作成したTEtaxRequest.id
    """
    from app.db import SessionLocal
    from app.models_clients import TEtaxRequest

    db = SessionLocal()
    try:
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
        return req.id
    finally:
        db.close()


def get_pending_auto_requests_for_today() -> list:
    """
    本日実行すべき定期自動送信の対象顧問先を抽出して
    TEtaxRequestを作成（または既存のpendingを返す）する。

    「納付期限の1ヶ月前」= 今月の翌月末が納付期限の顧問先を対象とする。

    Returns:
        list[int]: 実行すべきTEtaxRequest.idのリスト
    """
    from app.db import SessionLocal
    from app.models_clients import TClient, TTaxRecord, TEtaxRequest, TFilingOfficeTaxOffice
    from sqlalchemy import and_

    today = date.today()
    # 「1ヶ月後の月末が納付期限」= 来月が納付期限月
    target_end_month = today.month + 1 if today.month < 12 else 1
    target_year_offset = 1 if today.month == 12 else 0

    db = SessionLocal()
    request_ids = []
    try:
        # 消費税課税事業者で、来月が決算月の翌月（中間申告期限）に当たる顧問先を抽出
        # 中間申告の期限: 決算月の翌月末（6ヶ月後）
        # ここでは簡易的に「決算月+6ヶ月 = 来月」の顧問先を対象とする
        clients = db.query(TClient).filter(
            and_(
                TClient.consumption_tax_payer == 1,  # 消費税課税事業者
                TClient.etax_user_id != None,         # e-Tax認証情報あり
                TClient.etax_password != None,
            )
        ).all()

        for client in clients:
            if not client.fiscal_year_end_month:
                continue

            # 中間申告期限の月を計算（決算月の6ヶ月後の翌月末）
            interim_due_month = ((client.fiscal_year_end_month + 6) % 12) or 12
            if interim_due_month != target_end_month:
                continue

            # 最新の納税実績を取得
            latest_record = db.query(TTaxRecord).filter(
                TTaxRecord.client_id == client.id
            ).order_by(TTaxRecord.fiscal_year.desc()).first()

            if not latest_record:
                logger.info(f"[Batch] client_id={client.id} 納税実績なし。スキップ。")
                continue

            # 中間納付額 = 前年確定消費税の半分
            prev_consumption = (latest_record.consumption_tax or 0) + (latest_record.local_consumption_tax or 0)
            interim_amount = prev_consumption // 2
            if interim_amount <= 0:
                logger.info(f"[Batch] client_id={client.id} 中間納付額が0円。スキップ。")
                continue

            # 対象決算年度
            target_fiscal_year = latest_record.fiscal_year + 1 + target_year_offset

            # 既に同一条件でpending/processing/completedのレコードがある場合はスキップ
            existing = db.query(TEtaxRequest).filter(
                and_(
                    TEtaxRequest.client_id == client.id,
                    TEtaxRequest.fiscal_year == target_fiscal_year,
                    TEtaxRequest.filing_type == "中間申告",
                    TEtaxRequest.tax_type == "消費税及地方消費税",
                    TEtaxRequest.status.in_(["pending", "processing", "completed"]),
                )
            ).first()
            if existing:
                logger.info(f"[Batch] client_id={client.id} 既存レコードあり（id={existing.id}）。スキップ。")
                continue

            # 申告先税務署を取得
            filing_office = db.query(TFilingOfficeTaxOffice).filter(
                TFilingOfficeTaxOffice.client_id == client.id
            ).first()
            tax_office_name = filing_office.tax_office_name if filing_office else ""

            # TEtaxRequestを作成
            req = TEtaxRequest(
                client_id=client.id,
                tenant_id=client.tenant_id,
                tax_record_id=latest_record.id,
                request_type="auto",
                tax_type="消費税及地方消費税",
                filing_type="中間申告",
                fiscal_year=target_fiscal_year,
                fiscal_end_month=client.fiscal_year_end_month,
                amount=interim_amount,
                tax_office_name=tax_office_name,
                status="pending",
            )
            db.add(req)
            db.commit()
            db.refresh(req)
            request_ids.append(req.id)
            logger.info(f"[Batch] client_id={client.id} 中間申告リクエスト作成: id={req.id} 金額={interim_amount:,}円")

    except Exception as e:
        logger.error(f"[Batch] 定期送信対象抽出中にエラー: {e}", exc_info=True)
    finally:
        db.close()

    return request_ids


def _mark_error(db, req, error_message: str):
    """TEtaxRequestをエラー状態に更新する"""
    req.status = "error"
    req.error_message = error_message
    req.updated_at = datetime.utcnow()
    db.commit()
    logger.error(f"[Service] request_id={req.id} エラー: {error_message}")


def _upload_pdf_to_storage(pdf_path: str, client_id: int, request_id: int) -> Optional[str]:
    """
    PDFをS3/Dropbox/ローカルにアップロードしてパブリックURLを返す。
    既存のStorageManagerを使用する。
    """
    try:
        from app.utils.storage import storage_manager
        import io

        filename = f"payment_notice_{client_id}_{request_id}.pdf"

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # StorageManagerはfile-like objectを期待するためBytesIOでラップ
        file_obj = io.BytesIO(pdf_bytes)
        file_obj.filename = filename
        file_obj.content_type = "application/pdf"

        result = storage_manager.upload_file(
            file_obj=file_obj,
            original_filename=filename,
            folder="etax",
        )
        if result.get("success"):
            url = result.get("url")
            logger.info(f"[Service] PDF アップロード完了: {url}")
            return url
        else:
            logger.warning(f"[Service] PDF アップロード失敗: {result.get('error')}")
            return None
    except Exception as e:
        logger.warning(f"[Service] PDF アップロード失敗（URLなしで継続）: {e}")
        return None
