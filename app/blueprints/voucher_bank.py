# -*- coding: utf-8 -*-
"""
証憑データ化アプリ - 通帳モード Blueprint
通帳画像のアップロード、OCR処理（バックグラウンド）、一覧表示、CSV/Excel出力
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import os
import io
import csv
import threading
from datetime import datetime
from app.db import SessionLocal
from app.models_voucher import TBankStatement, TBankTransaction
from app.models_login import TTenpo, TTenant, TKanrisha
from app.utils.decorators import require_roles, ROLES
from app.utils.voucher.ocr import process_bank_statement_image, save_uploaded_file

bp = Blueprint('voucher_bank', __name__, url_prefix='/voucher/bank')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_session_info():
    tenpo_id = session.get('store_id') or session.get('tenpo_id')
    return {
        'tenant_id': session.get('tenant_id'),
        'tenpo_id': tenpo_id,
        'user_id': session.get('user_id'),
        'role': session.get('role'),
    }


def get_openai_api_key(tenant_id, tenpo_id):
    """店舗 → テナント → システム管理者の順でAPIキーを取得"""
    db = SessionLocal()
    try:
        if tenpo_id:
            tenpo = db.query(TTenpo).filter(TTenpo.id == tenpo_id).first()
            if tenpo and getattr(tenpo, 'openai_api_key', None):
                return tenpo.openai_api_key
        if tenant_id:
            tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            if tenant and getattr(tenant, 'openai_api_key', None):
                return tenant.openai_api_key
        sys_admin = db.query(TKanrisha).filter(
            TKanrisha.role == 'system_admin',
            TKanrisha.openai_api_key != None,
            TKanrisha.openai_api_key != ''
        ).first()
        if sys_admin:
            return sys_admin.openai_api_key
    except Exception:
        pass
    finally:
        db.close()
    return None


def _run_ocr_background(stmt_id, filepath, api_key, tenant_id):
    """バックグラウンドスレッドでOCR処理を実行してDBを更新する"""
    db = SessionLocal()
    try:
        stmt = db.query(TBankStatement).filter(TBankStatement.id == stmt_id).first()
        if not stmt:
            return
        stmt.ステータス = 'processing'
        db.commit()

        ocr_result = process_bank_statement_image(filepath, api_key=api_key)

        stmt = db.query(TBankStatement).filter(TBankStatement.id == stmt_id).first()
        if not stmt:
            return

        stmt.OCR結果_生データ = ocr_result.get('raw_text', '')
        stmt.銀行名 = ocr_result.get('bank_name')
        stmt.支店名 = ocr_result.get('branch_name')
        stmt.口座種別 = ocr_result.get('account_type')
        stmt.口座番号 = ocr_result.get('account_number')
        stmt.口座名義 = ocr_result.get('account_holder')
        stmt.期間_開始 = ocr_result.get('period_start')
        stmt.期間_終了 = ocr_result.get('period_end')
        stmt.ステータス = 'completed'
        db.flush()

        db.query(TBankTransaction).filter(TBankTransaction.statement_id == stmt_id).delete()

        for i, t in enumerate(ocr_result.get('transactions', []), 1):
            row = TBankTransaction(
                statement_id=stmt_id,
                tenant_id=tenant_id,
                日付=t.get('date'),
                摘要=t.get('description'),
                入金=t.get('deposit'),
                出金=t.get('withdrawal'),
                残高=t.get('balance'),
                備考=t.get('note'),
                行番号=i,
            )
            db.add(row)

        db.commit()

    except Exception as e:
        try:
            stmt = db.query(TBankStatement).filter(TBankStatement.id == stmt_id).first()
            if stmt:
                stmt.ステータス = 'error'
                stmt.OCR結果_生データ = f'OCRエラー: {str(e)}'
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ============================================================
# 通帳明細一覧
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
        q = db.query(TBankStatement).filter(TBankStatement.tenant_id == tenant_id)
        if role in (ROLES['ADMIN'], ROLES['EMPLOYEE']) and tenpo_id:
            q = q.filter(TBankStatement.tenpo_id == tenpo_id)
        statements = q.order_by(TBankStatement.created_at.desc()).all()
    finally:
        db.close()

    return render_template('voucher_bank_list.html', statements=statements)


# ============================================================
# 通帳アップロード（即時リダイレクト、OCRはバックグラウンド）
# ============================================================
@bp.route('/upload', methods=['GET', 'POST'])
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'], ROLES['EMPLOYEE'])
def upload():
    if request.method == 'GET':
        return render_template('voucher_bank_upload.html')

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
    if file.filename == '' or not allowed_file(file.filename):
        flash('ファイルが選択されていないか、許可されていない形式です（PNG/JPG/GIF/PDF）', 'error')
        return redirect(request.url)

    try:
        upload_dir = os.path.join('uploads', 'bank', str(tenant_id))
        filepath = save_uploaded_file(file, upload_dir)

        openai_api_key = get_openai_api_key(tenant_id, tenpo_id)

        db = SessionLocal()
        try:
            stmt = TBankStatement(
                tenant_id=tenant_id,
                tenpo_id=tenpo_id,
                uploaded_by=user_id,
                画像パス=filepath,
                ステータス='pending' if not openai_api_key else 'processing',
            )
            db.add(stmt)
            db.commit()
            stmt_id = stmt.id
        finally:
            db.close()

        if not openai_api_key:
            flash('OpenAI APIキーが未設定のため、OCR処理をスキップしました。', 'warning')
        else:
            t = threading.Thread(
                target=_run_ocr_background,
                args=(stmt_id, filepath, openai_api_key, tenant_id),
                daemon=True
            )
            t.start()
            flash('通帳をアップロードしました。OCR処理をバックグラウンドで実行中です...', 'success')

        return redirect(url_for('voucher_bank.detail', stmt_id=stmt_id))

    except Exception as e:
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(request.url)


# ============================================================
# OCRステータス確認API（詳細画面の自動リロード用）
# ============================================================
@bp.route('/<int:stmt_id>/status')
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'], ROLES['EMPLOYEE'])
def status(stmt_id):
    info = get_session_info()
    tenant_id = info['tenant_id']
    db = SessionLocal()
    try:
        stmt = db.query(TBankStatement).filter(
            TBankStatement.id == stmt_id,
            TBankStatement.tenant_id == tenant_id
        ).first()
        if not stmt:
            return jsonify({'status': 'error'})
        return jsonify({'status': stmt.ステータス or 'pending'})
    finally:
        db.close()


# ============================================================
# 通帳詳細
# ============================================================
@bp.route('/<int:stmt_id>')
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'], ROLES['EMPLOYEE'])
def detail(stmt_id):
    info = get_session_info()
    tenant_id = info['tenant_id']

    db = SessionLocal()
    try:
        stmt = db.query(TBankStatement).filter(
            TBankStatement.id == stmt_id,
            TBankStatement.tenant_id == tenant_id
        ).first()
        if not stmt:
            flash('明細が見つかりません', 'error')
            return redirect(url_for('voucher_bank.index'))
        transactions = db.query(TBankTransaction).filter(
            TBankTransaction.statement_id == stmt_id
        ).order_by(TBankTransaction.行番号).all()
    finally:
        db.close()

    return render_template('voucher_bank_detail.html', stmt=stmt, transactions=transactions)


# ============================================================
# CSV出力
# ============================================================
@bp.route('/<int:stmt_id>/csv')
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'], ROLES['EMPLOYEE'])
def export_csv(stmt_id):
    info = get_session_info()
    tenant_id = info['tenant_id']

    db = SessionLocal()
    try:
        stmt = db.query(TBankStatement).filter(
            TBankStatement.id == stmt_id,
            TBankStatement.tenant_id == tenant_id
        ).first()
        if not stmt:
            flash('明細が見つかりません', 'error')
            return redirect(url_for('voucher_bank.index'))
        transactions = db.query(TBankTransaction).filter(
            TBankTransaction.statement_id == stmt_id
        ).order_by(TBankTransaction.行番号).all()
    finally:
        db.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['銀行名', stmt.銀行名 or ''])
    writer.writerow(['支店名', stmt.支店名 or ''])
    writer.writerow(['口座種別', stmt.口座種別 or ''])
    writer.writerow(['口座番号', stmt.口座番号 or ''])
    writer.writerow(['口座名義', stmt.口座名義 or ''])
    writer.writerow(['期間', f"{stmt.期間_開始 or ''} ～ {stmt.期間_終了 or ''}"])
    writer.writerow([])
    writer.writerow(['日付', '摘要', '入金', '出金', '残高', '備考'])

    for t in transactions:
        writer.writerow([
            t.日付 or '',
            t.摘要 or '',
            int(t.入金) if t.入金 is not None else '',
            int(t.出金) if t.出金 is not None else '',
            int(t.残高) if t.残高 is not None else '',
            t.備考 or '',
        ])

    output.seek(0)
    bom = '\ufeff'
    csv_bytes = io.BytesIO((bom + output.getvalue()).encode('utf-8'))
    filename = f"通帳明細_{stmt.銀行名 or 'bank'}_{stmt_id}.csv"
    return send_file(csv_bytes, mimetype='text/csv; charset=utf-8',
                     as_attachment=True, download_name=filename)


# ============================================================
# Excel出力
# ============================================================
@bp.route('/<int:stmt_id>/excel')
@require_roles(ROLES['SYSTEM_ADMIN'], ROLES['TENANT_ADMIN'], ROLES['ADMIN'], ROLES['EMPLOYEE'])
def export_excel(stmt_id):
    info = get_session_info()
    tenant_id = info['tenant_id']

    db = SessionLocal()
    try:
        stmt = db.query(TBankStatement).filter(
            TBankStatement.id == stmt_id,
            TBankStatement.tenant_id == tenant_id
        ).first()
        if not stmt:
            flash('明細が見つかりません', 'error')
            return redirect(url_for('voucher_bank.index'))
        transactions = db.query(TBankTransaction).filter(
            TBankTransaction.statement_id == stmt_id
        ).order_by(TBankTransaction.行番号).all()
    finally:
        db.close()

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        flash('openpyxlがインストールされていません。CSVをご利用ください。', 'error')
        return redirect(url_for('voucher_bank.detail', stmt_id=stmt_id))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '通帳明細'

    header_fill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)
    info_fill = PatternFill(start_color='EFF6FF', end_color='EFF6FF', fill_type='solid')
    thin = Side(style='thin', color='D1D5DB')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    info_rows = [
        ('銀行名', stmt.銀行名 or ''),
        ('支店名', stmt.支店名 or ''),
        ('口座種別', stmt.口座種別 or ''),
        ('口座番号', stmt.口座番号 or ''),
        ('口座名義', stmt.口座名義 or ''),
        ('期間', f"{stmt.期間_開始 or ''} ～ {stmt.期間_終了 or ''}"),
    ]
    for r, (label, value) in enumerate(info_rows, 1):
        ws.cell(r, 1, label).fill = info_fill
        ws.cell(r, 1, label).font = Font(bold=True)
        ws.cell(r, 2, value)

    header_row = len(info_rows) + 2
    headers = ['日付', '摘要', '入金', '出金', '残高', '備考']
    for c, h in enumerate(headers, 1):
        cell = ws.cell(header_row, c, h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = border

    for i, t in enumerate(transactions):
        row = header_row + 1 + i
        values = [
            t.日付 or '',
            t.摘要 or '',
            int(t.入金) if t.入金 is not None else '',
            int(t.出金) if t.出金 is not None else '',
            int(t.残高) if t.残高 is not None else '',
            t.備考 or '',
        ]
        for c, v in enumerate(values, 1):
            cell = ws.cell(row, c, v)
            cell.border = border
            if c in (3, 4, 5) and v != '':
                cell.alignment = Alignment(horizontal='right')
                cell.number_format = '#,##0'

    ws.column_dimensions['A'].width = 14
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 14
    ws.column_dimensions['F'].width = 20

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"通帳明細_{stmt.銀行名 or 'bank'}_{stmt_id}.xlsx"
    return send_file(output,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)
