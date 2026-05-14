# -*- coding: utf-8 -*-
"""
建設業運営アプリ - メインブループリント
案件・顧客・日報・スケジュール・見積請求・ファイル管理
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from ..utils import get_db, _sql, require_roles, ROLES
from ..db import SessionLocal
from ..models_construction import (
    TKokyaku, TAnken, TNippo, TSchedule, TMitsumori, TMitsumoriMeisai, TAnkenFile
)
import datetime

bp = Blueprint('construction', __name__, url_prefix='/construction')

ALLOWED_ROLES = [ROLES.get('SYSTEM_ADMIN', 'system_admin'),
                 ROLES.get('TENANT_ADMIN', 'tenant_admin'),
                 ROLES.get('ADMIN', 'admin'),
                 ROLES.get('EMPLOYEE', 'employee')]


def _get_tenant_id():
    return session.get('tenant_id')


def _get_user_id():
    return session.get('user_id')


# ─── ダッシュボード ────────────────────────────────────────────────────────────

@bp.route('/dashboard')
def dashboard():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        tenant_id = _get_tenant_id()
        q = db.query(TAnken)
        if tenant_id:
            q = q.filter(TAnken.tenant_id == tenant_id)
        all_projects = q.all()
        project_count = len(all_projects)
        active_count = sum(1 for p in all_projects if p.status in ('受注', '施工中'))
        report_count = db.query(TNippo).count()
        total_amount = sum(float(p.contract_amount or 0) for p in all_projects)
        customer_count = db.query(TKokyaku).filter(
            TKokyaku.tenant_id == tenant_id if tenant_id else True
        ).count()
        recent_projects = q.order_by(TAnken.created_at.desc()).limit(5).all()
    finally:
        db.close()
    return render_template('construction/dashboard.html',
                           project_count=project_count,
                           active_count=active_count,
                           report_count=report_count,
                           total_amount=total_amount,
                           customer_count=customer_count,
                           recent_projects=recent_projects)


# ─── 顧客管理 ─────────────────────────────────────────────────────────────────

@bp.route('/customers')
def customers():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        tenant_id = _get_tenant_id()
        q = db.query(TKokyaku)
        if tenant_id:
            q = q.filter(TKokyaku.tenant_id == tenant_id)
        rows = q.order_by(TKokyaku.created_at.desc()).all()
    finally:
        db.close()
    return render_template('construction/customers.html', customers=rows)


@bp.route('/customers/new', methods=['GET', 'POST'])
def customer_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    if request.method == 'POST':
        db = SessionLocal()
        try:
            c = TKokyaku(
                tenant_id=_get_tenant_id(),
                company_name=request.form.get('company_name', '').strip(),
                contact_name=request.form.get('contact_name', '').strip() or None,
                phone=request.form.get('phone', '').strip() or None,
                email=request.form.get('email', '').strip() or None,
                address=request.form.get('address', '').strip() or None,
                notes=request.form.get('notes', '').strip() or None,
                created_by=_get_user_id(),
            )
            db.add(c)
            db.commit()
            flash('顧客を登録しました', 'success')
        except Exception as e:
            db.rollback()
            flash(f'登録に失敗しました: {e}', 'danger')
        finally:
            db.close()
        return redirect(url_for('construction.customers'))
    return render_template('construction/customer_form.html', customer=None)


@bp.route('/customers/<int:cid>/edit', methods=['GET', 'POST'])
def customer_edit(cid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        c = db.query(TKokyaku).filter(TKokyaku.id == cid).first()
        if not c:
            flash('顧客が見つかりません', 'danger')
            return redirect(url_for('construction.customers'))
        if request.method == 'POST':
            c.company_name = request.form.get('company_name', '').strip()
            c.contact_name = request.form.get('contact_name', '').strip() or None
            c.phone = request.form.get('phone', '').strip() or None
            c.email = request.form.get('email', '').strip() or None
            c.address = request.form.get('address', '').strip() or None
            c.notes = request.form.get('notes', '').strip() or None
            db.commit()
            flash('顧客情報を更新しました', 'success')
            return redirect(url_for('construction.customers'))
        return render_template('construction/customer_form.html', customer=c)
    except Exception as e:
        db.rollback()
        flash(f'更新に失敗しました: {e}', 'danger')
        return redirect(url_for('construction.customers'))
    finally:
        db.close()


@bp.route('/customers/<int:cid>/delete', methods=['POST'])
def customer_delete(cid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        c = db.query(TKokyaku).filter(TKokyaku.id == cid).first()
        if c:
            db.delete(c)
            db.commit()
            flash('顧客を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction.customers'))


# ─── 案件管理 ─────────────────────────────────────────────────────────────────

STATUS_LIST = ['見積中', '受注', '施工中', '完了', '請求済']


@bp.route('/projects')
def projects():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        tenant_id = _get_tenant_id()
        rows = db.query(TAnken, TKokyaku).outerjoin(
            TKokyaku, TAnken.customer_id == TKokyaku.id
        )
        if tenant_id:
            rows = rows.filter(TAnken.tenant_id == tenant_id)
        rows = rows.order_by(TAnken.created_at.desc()).all()
        customers = db.query(TKokyaku).all()
    finally:
        db.close()
    return render_template('construction/projects.html',
                           rows=rows, customers=customers,
                           status_list=STATUS_LIST)


@bp.route('/projects/new', methods=['GET', 'POST'])
def project_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        customers = db.query(TKokyaku).all()
        if request.method == 'POST':
            p = TAnken(
                tenant_id=_get_tenant_id(),
                name=request.form.get('name', '').strip(),
                customer_id=int(request.form['customer_id']) if request.form.get('customer_id') else None,
                status=request.form.get('status', '見積中'),
                start_date=request.form.get('start_date') or None,
                end_date=request.form.get('end_date') or None,
                assigned_to=request.form.get('assigned_to', '').strip() or None,
                description=request.form.get('description', '').strip() or None,
                contract_amount=request.form.get('contract_amount') or None,
                created_by=_get_user_id(),
            )
            db.add(p)
            db.commit()
            flash('案件を登録しました', 'success')
            return redirect(url_for('construction.projects'))
        return render_template('construction/project_form.html',
                               project=None, customers=customers,
                               status_list=STATUS_LIST)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('construction.projects'))
    finally:
        db.close()


@bp.route('/projects/<int:pid>/edit', methods=['GET', 'POST'])
def project_edit(pid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        p = db.query(TAnken).filter(TAnken.id == pid).first()
        customers = db.query(TKokyaku).all()
        if not p:
            flash('案件が見つかりません', 'danger')
            return redirect(url_for('construction.projects'))
        if request.method == 'POST':
            p.name = request.form.get('name', '').strip()
            p.customer_id = int(request.form['customer_id']) if request.form.get('customer_id') else None
            p.status = request.form.get('status', '見積中')
            p.start_date = request.form.get('start_date') or None
            p.end_date = request.form.get('end_date') or None
            p.assigned_to = request.form.get('assigned_to', '').strip() or None
            p.description = request.form.get('description', '').strip() or None
            p.contract_amount = request.form.get('contract_amount') or None
            db.commit()
            flash('案件を更新しました', 'success')
            return redirect(url_for('construction.projects'))
        return render_template('construction/project_form.html',
                               project=p, customers=customers,
                               status_list=STATUS_LIST)
    except Exception as e:
        db.rollback()
        flash(f'更新に失敗しました: {e}', 'danger')
        return redirect(url_for('construction.projects'))
    finally:
        db.close()


@bp.route('/projects/<int:pid>/delete', methods=['POST'])
def project_delete(pid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        p = db.query(TAnken).filter(TAnken.id == pid).first()
        if p:
            db.delete(p)
            db.commit()
            flash('案件を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction.projects'))


# ─── 作業日報 ─────────────────────────────────────────────────────────────────

@bp.route('/reports')
def reports():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        tenant_id = _get_tenant_id()
        rows = db.query(TNippo, TAnken).outerjoin(
            TAnken, TNippo.anken_id == TAnken.id
        ).order_by(TNippo.report_date.desc()).all()
        projects = db.query(TAnken).all()
    finally:
        db.close()
    return render_template('construction/reports.html', rows=rows, projects=projects)


@bp.route('/reports/new', methods=['GET', 'POST'])
def report_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        projects = db.query(TAnken).all()
        if request.method == 'POST':
            r = TNippo(
                tenant_id=_get_tenant_id(),
                anken_id=int(request.form['anken_id']) if request.form.get('anken_id') else None,
                user_id=_get_user_id(),
                report_date=request.form.get('report_date'),
                work_content=request.form.get('work_content', '').strip(),
                work_hours=request.form.get('work_hours') or None,
                notes=request.form.get('notes', '').strip() or None,
            )
            db.add(r)
            db.commit()
            flash('日報を登録しました', 'success')
            return redirect(url_for('construction.reports'))
        today = datetime.date.today().isoformat()
        return render_template('construction/report_form.html',
                               report=None, projects=projects, today=today)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('construction.reports'))
    finally:
        db.close()


@bp.route('/reports/<int:rid>/delete', methods=['POST'])
def report_delete(rid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        r = db.query(TNippo).filter(TNippo.id == rid).first()
        if r:
            db.delete(r)
            db.commit()
            flash('日報を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction.reports'))


# ─── スケジュール ─────────────────────────────────────────────────────────────

@bp.route('/schedules')
def schedules():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        rows = db.query(TSchedule, TAnken).outerjoin(
            TAnken, TSchedule.anken_id == TAnken.id
        ).order_by(TSchedule.start_at.asc()).all()
        projects = db.query(TAnken).all()
    finally:
        db.close()
    return render_template('construction/schedules.html', rows=rows, projects=projects)


@bp.route('/schedules/new', methods=['GET', 'POST'])
def schedule_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        projects = db.query(TAnken).all()
        if request.method == 'POST':
            s = TSchedule(
                tenant_id=_get_tenant_id(),
                anken_id=int(request.form['anken_id']) if request.form.get('anken_id') else None,
                user_id=_get_user_id(),
                title=request.form.get('title', '').strip(),
                start_at=request.form.get('start_at'),
                end_at=request.form.get('end_at') or None,
                all_day=1 if request.form.get('all_day') else 0,
                description=request.form.get('description', '').strip() or None,
            )
            db.add(s)
            db.commit()
            flash('予定を登録しました', 'success')
            return redirect(url_for('construction.schedules'))
        return render_template('construction/schedule_form.html',
                               schedule=None, projects=projects)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('construction.schedules'))
    finally:
        db.close()


@bp.route('/schedules/<int:sid>/delete', methods=['POST'])
def schedule_delete(sid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        s = db.query(TSchedule).filter(TSchedule.id == sid).first()
        if s:
            db.delete(s)
            db.commit()
            flash('予定を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction.schedules'))


# ─── 見積・請求管理 ───────────────────────────────────────────────────────────

DOC_TYPE_LABELS = {'estimate': '見積書', 'invoice': '請求書'}
MITSUMORI_STATUS_LABELS = {'draft': '下書き', 'sent': '送付済', 'accepted': '承認済', 'paid': '入金済'}


@bp.route('/estimates')
def estimates():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        rows = db.query(TMitsumori, TAnken).outerjoin(
            TAnken, TMitsumori.anken_id == TAnken.id
        ).order_by(TMitsumori.created_at.desc()).all()
        projects = db.query(TAnken).all()
    finally:
        db.close()
    return render_template('construction/estimates.html',
                           rows=rows, projects=projects,
                           doc_type_labels=DOC_TYPE_LABELS,
                           status_labels=MITSUMORI_STATUS_LABELS)


@bp.route('/estimates/new', methods=['GET', 'POST'])
def estimate_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        projects = db.query(TAnken).all()
        if request.method == 'POST':
            m = TMitsumori(
                tenant_id=_get_tenant_id(),
                anken_id=int(request.form['anken_id']) if request.form.get('anken_id') else None,
                doc_type=request.form.get('doc_type', 'estimate'),
                status=request.form.get('status', 'draft'),
                issue_date=request.form.get('issue_date') or None,
                due_date=request.form.get('due_date') or None,
                total_amount=request.form.get('total_amount') or None,
                notes=request.form.get('notes', '').strip() or None,
                created_by=_get_user_id(),
            )
            db.add(m)
            db.flush()
            # 明細行
            descs = request.form.getlist('item_description[]')
            qtys = request.form.getlist('item_quantity[]')
            prices = request.form.getlist('item_unit_price[]')
            amounts = request.form.getlist('item_amount[]')
            for i, desc in enumerate(descs):
                if not desc.strip():
                    continue
                item = TMitsumoriMeisai(
                    mitsumori_id=m.id,
                    description=desc.strip(),
                    quantity=qtys[i] if i < len(qtys) and qtys[i] else None,
                    unit_price=prices[i] if i < len(prices) and prices[i] else None,
                    amount=amounts[i] if i < len(amounts) and amounts[i] else None,
                    sort_order=i,
                )
                db.add(item)
            db.commit()
            flash('見積書を作成しました', 'success')
            return redirect(url_for('construction.estimates'))
        today = datetime.date.today().isoformat()
        return render_template('construction/estimate_form.html',
                               estimate=None, projects=projects, today=today)
    except Exception as e:
        db.rollback()
        flash(f'作成に失敗しました: {e}', 'danger')
        return redirect(url_for('construction.estimates'))
    finally:
        db.close()


@bp.route('/estimates/<int:mid>/delete', methods=['POST'])
def estimate_delete(mid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        db.query(TMitsumoriMeisai).filter(TMitsumoriMeisai.mitsumori_id == mid).delete()
        m = db.query(TMitsumori).filter(TMitsumori.id == mid).first()
        if m:
            db.delete(m)
        db.commit()
        flash('削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction.estimates'))


# ─── ファイル管理 ─────────────────────────────────────────────────────────────

@bp.route('/files')
def files():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        projects = db.query(TAnken).all()
        anken_id = request.args.get('anken_id', type=int)
        file_rows = []
        if anken_id:
            file_rows = db.query(TAnkenFile).filter(
                TAnkenFile.anken_id == anken_id
            ).order_by(TAnkenFile.created_at.desc()).all()
    finally:
        db.close()
    return render_template('construction/files.html',
                           projects=projects,
                           file_rows=file_rows,
                           selected_anken_id=anken_id)


@bp.route('/files/upload', methods=['POST'])
def file_upload():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    import os, uuid
    anken_id = request.form.get('anken_id', type=int)
    if not anken_id:
        flash('案件を選択してください', 'danger')
        return redirect(url_for('construction.files'))
    uploaded = request.files.getlist('files')
    db = SessionLocal()
    try:
        for f in uploaded:
            if not f or not f.filename:
                continue
            # S3アップロード（storage_adapterを利用）
            try:
                from ..utils.storage_adapter import upload_file_to_storage
                file_key = f'construction/{anken_id}/{uuid.uuid4().hex}_{f.filename}'
                file_bytes = f.read()
                file_url = upload_file_to_storage(file_key, file_bytes, f.content_type)
            except Exception:
                # S3未設定時はローカル保存パスをURLとして記録
                file_key = f'construction/{anken_id}/{f.filename}'
                file_url = f'/static/uploads/{file_key}'

            rec = TAnkenFile(
                tenant_id=_get_tenant_id(),
                anken_id=anken_id,
                uploaded_by=_get_user_id(),
                file_name=f.filename,
                file_key=file_key,
                file_url=file_url,
                mime_type=f.content_type,
                file_size=len(file_bytes) if 'file_bytes' in dir() else None,
            )
            db.add(rec)
        db.commit()
        flash('ファイルをアップロードしました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'アップロードに失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction.files', anken_id=anken_id))


@bp.route('/files/<int:fid>/delete', methods=['POST'])
def file_delete(fid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        f = db.query(TAnkenFile).filter(TAnkenFile.id == fid).first()
        anken_id = f.anken_id if f else None
        if f:
            db.delete(f)
            db.commit()
            flash('ファイルを削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction.files', anken_id=anken_id))
