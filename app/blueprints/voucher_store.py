# -*- coding: utf-8 -*-
"""
証憑データ化アプリ - 店舗アプリ Blueprint
レシート・領収書のアップロード、OCR処理、一覧表示
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import io
import csv
from datetime import datetime
from app.db import SessionLocal
from app.models_voucher import TVoucher, TCompany
from app.utils.decorators import require_roles, ROLES
from app.utils.voucher.ocr import process_receipt_image, save_uploaded_file
from app.utils.voucher.nta_api import NTAInvoiceAPI
from app.utils.voucher.nta_api_enhanced import search_corporate_number_by_contact

bp = Blueprint('voucher_store', __name__, url_prefix='/voucher')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_session_info():
    """セッションからテナントID・店舗ID・ユーザーIDを取得"""
    return {
        'tenant_id': session.get('tenant_id'),
        'tenpo_id': session.get('tenpo_id'),
        'user_id': session.get('user_id'),
        'role': session.get('role'),
    }


# ============================================================
# 証憑一覧
# ============================================================
@bp.route('/')
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'], ROLES['EMPLOYEE'])
def index():
    info = get_session_info()
    tenant_id = info['tenant_id']
    tenpo_id = info['tenpo_id']
    role = info['role']

    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('auth.select_login'))

    db = SessionLocal()
    try:
        q = db.query(TVoucher).filter(TVoucher.tenant_id == tenant_id)
        # 店舗管理者・従業員は自店舗の証憑のみ
        if role in (ROLES['ADMIN'], ROLES['EMPLOYEE']) and tenpo_id:
            q = q.filter(TVoucher.tenpo_id == tenpo_id)
        vouchers = q.order_by(TVoucher.created_at.desc()).all()
    finally:
        db.close()

    return render_template('voucher_store_list.html', vouchers=vouchers)


# ============================================================
# 証憑アップロード
# ============================================================
@bp.route('/upload', methods=['GET', 'POST'])
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'], ROLES['EMPLOYEE'])
def upload():
    if request.method == 'GET':
        return render_template('voucher_store_upload.html')

    info = get_session_info()
    tenant_id = info['tenant_id']
    tenpo_id = info['tenpo_id']
    user_id = info['user_id']

    if not tenant_id or not user_id:
        flash('セッション情報が不正です', 'error')
        return redirect(url_for('auth.select_login'))

    if 'file' not in request.files:
        flash('ファイルが選択されていません', 'error')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('ファイルが選択されていません', 'error')
        return redirect(request.url)

    if not allowed_file(file.filename):
        flash('許可されていないファイル形式です（PNG/JPG/GIF/PDF）', 'error')
        return redirect(request.url)

    try:
        # ファイル保存
        upload_dir = os.path.join('uploads', 'vouchers', str(tenant_id))
        filepath = save_uploaded_file(file, upload_dir)

        # OCR処理
        ocr_result = process_receipt_image(filepath)

        # 電話番号・住所から法人番号検索（NTA API）
        company_id = None
        corporate_number = ocr_result.get('corporate_number')
        phone = None
        address = None

        if ocr_result.get('phone_numbers'):
            phone = ocr_result['phone_numbers'][0]
        if ocr_result.get('addresses'):
            address = ocr_result['addresses'][0]

        # 法人番号が取れていない場合は電話番号・住所から検索
        if not corporate_number and (phone or address or ocr_result.get('company_name')):
            try:
                result = search_corporate_number_by_contact(
                    phone_number=phone,
                    address=address,
                    company_name=ocr_result.get('company_name')
                )
                if result and result.get('corporate_number'):
                    corporate_number = result['corporate_number']
            except Exception:
                pass

        # 取引先会社の登録・取得
        if ocr_result.get('company_name') or corporate_number:
            db = SessionLocal()
            try:
                company = None
                if corporate_number:
                    company = db.query(TCompany).filter(
                        TCompany.法人番号 == corporate_number,
                        TCompany.tenant_id == tenant_id
                    ).first()
                if not company and ocr_result.get('company_name'):
                    company = db.query(TCompany).filter(
                        TCompany.会社名 == ocr_result['company_name'],
                        TCompany.tenant_id == tenant_id
                    ).first()
                if not company:
                    company = TCompany(
                        tenant_id=tenant_id,
                        会社名=ocr_result.get('company_name', ''),
                        法人番号=corporate_number,
                        電話番号=phone,
                        住所=address,
                    )
                    db.add(company)
                    db.flush()
                company_id = company.id
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()

        # 証憑レコード保存
        db = SessionLocal()
        try:
            voucher = TVoucher(
                tenant_id=tenant_id,
                tenpo_id=tenpo_id,
                uploaded_by=user_id,
                company_id=company_id,
                画像パス=filepath,
                OCR結果_生データ=ocr_result.get('raw_text', ''),
                電話番号=phone,
                住所=address,
                郵便番号=ocr_result.get('postal_code'),
                会社名=ocr_result.get('company_name'),
                金額=ocr_result.get('amount'),
                日付=ocr_result.get('date'),
                インボイス番号=ocr_result.get('invoice_number'),
                法人番号=corporate_number,
                ステータス='pending',
            )
            db.add(voucher)
            db.commit()
            voucher_id = voucher.id
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

        flash('証憑をアップロードしました。OCR結果を確認してください。', 'success')
        return redirect(url_for('voucher_store.detail', voucher_id=voucher_id))

    except Exception as e:
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(request.url)


# ============================================================
# 証憑詳細
# ============================================================
@bp.route('/<int:voucher_id>')
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'], ROLES['EMPLOYEE'])
def detail(voucher_id):
    info = get_session_info()
    tenant_id = info['tenant_id']

    db = SessionLocal()
    try:
        voucher = db.query(TVoucher).filter(
            TVoucher.id == voucher_id,
            TVoucher.tenant_id == tenant_id
        ).first()
    finally:
        db.close()

    if not voucher:
        flash('証憑が見つかりません', 'error')
        return redirect(url_for('voucher_store.index'))

    return render_template('voucher_store_detail.html', voucher=voucher)


# ============================================================
# 証憑編集
# ============================================================
@bp.route('/<int:voucher_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'])
def edit(voucher_id):
    info = get_session_info()
    tenant_id = info['tenant_id']

    db = SessionLocal()
    try:
        voucher = db.query(TVoucher).filter(
            TVoucher.id == voucher_id,
            TVoucher.tenant_id == tenant_id
        ).first()

        if not voucher:
            flash('証憑が見つかりません', 'error')
            return redirect(url_for('voucher_store.index'))

        if request.method == 'GET':
            return render_template('voucher_store_edit.html', voucher=voucher)

        # POST: 更新
        voucher.電話番号 = request.form.get('phone')
        voucher.住所 = request.form.get('address')
        voucher.会社名 = request.form.get('company_name')
        voucher.金額 = request.form.get('amount') or None
        voucher.日付 = request.form.get('date')
        voucher.インボイス番号 = request.form.get('invoice_number')
        voucher.法人番号 = request.form.get('corporate_number')
        voucher.摘要 = request.form.get('description')
        voucher.ステータス = request.form.get('status', 'pending')
        db.commit()
        flash('証憑を更新しました', 'success')
        return redirect(url_for('voucher_store.detail', voucher_id=voucher_id))

    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(request.url)
    finally:
        db.close()


# ============================================================
# 証憑削除
# ============================================================
@bp.route('/<int:voucher_id>/delete', methods=['POST'])
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'])
def delete(voucher_id):
    info = get_session_info()
    tenant_id = info['tenant_id']

    db = SessionLocal()
    try:
        voucher = db.query(TVoucher).filter(
            TVoucher.id == voucher_id,
            TVoucher.tenant_id == tenant_id
        ).first()

        if voucher:
            filepath = voucher.画像パス
            db.delete(voucher)
            db.commit()
            # ファイル削除
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            flash('証憑を削除しました', 'success')
        else:
            flash('証憑が見つかりません', 'error')
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
    finally:
        db.close()

    return redirect(url_for('voucher_store.index'))


# ============================================================
# CSVエクスポート
# ============================================================
@bp.route('/export/csv')
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'])
def export_csv():
    info = get_session_info()
    tenant_id = info['tenant_id']
    tenpo_id = info['tenpo_id']
    role = info['role']

    db = SessionLocal()
    try:
        q = db.query(TVoucher).filter(TVoucher.tenant_id == tenant_id)
        if role in (ROLES['ADMIN'],) and tenpo_id:
            q = q.filter(TVoucher.tenpo_id == tenpo_id)
        vouchers = q.order_by(TVoucher.日付.desc()).all()
    finally:
        db.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', '日付', '会社名', '金額', '摘要', '電話番号', '住所', 'インボイス番号', '法人番号', 'ステータス', '登録日時'])
    for v in vouchers:
        writer.writerow([
            v.id, v.日付, v.会社名 or '', v.金額 or '',
            v.摘要 or '', v.電話番号 or '', v.住所 or '',
            v.インボイス番号 or '', v.法人番号 or '',
            v.ステータス, v.created_at
        ])

    output.seek(0)
    filename = f"vouchers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )
