# -*- coding: utf-8 -*-
"""
骨董品店経営アプリ - メインブループリント
商品台帳・取引先・買取・販売・鑑定・ファイル管理
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from ..db import SessionLocal
from ..models_antiques import (
    TAntiqueTorihikisaki, TAntiqueShohin, TAntiqueKaitori,
    TAntiqueHanbai, TAntiqueKantei, TAntiqueFile
)
import datetime

bp = Blueprint('antiques', __name__, url_prefix='/antiques')

CATEGORY_LIST = ['陶磁器', '絵画・書', '茶道具', '古家具', '刀剣・甲冑', '古美術品', '工芸品', 'その他']
CONDITION_LIST = ['美品', '良好', '並', '難あり']
STATUS_LIST = ['在庫', '委託中', '売約済', '販売済']
PARTNER_TYPE_LIST = ['顧客', '仕入先', '両方']
KANTEI_RESULT_LIST = ['真作', '模写・複製', '時代相応', '要再鑑定', '不明']


def _get_tenant_id():
    return session.get('tenant_id')


def _get_user_id():
    return session.get('user_id')


def _parse_date(value):
    """ISO形式の日付文字列を date 型に変換（不正値・空値は None）"""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# ─── ダッシュボード ────────────────────────────────────────────────────────────

@bp.route('/dashboard')
def dashboard():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        tenant_id = _get_tenant_id()
        q = db.query(TAntiqueShohin)
        if tenant_id:
            q = q.filter(TAntiqueShohin.tenant_id == tenant_id)
        all_items = q.all()
        item_count = len(all_items)
        instock_count = sum(1 for i in all_items if i.status in ('在庫', '委託中'))
        sold_count = sum(1 for i in all_items if i.status == '販売済')
        inventory_value = sum(
            float(i.asking_price or 0) for i in all_items if i.status in ('在庫', '委託中', '売約済')
        )
        partner_count = db.query(TAntiqueTorihikisaki).filter(
            TAntiqueTorihikisaki.tenant_id == tenant_id if tenant_id else True
        ).count()
        sales_q = db.query(TAntiqueHanbai)
        if tenant_id:
            sales_q = sales_q.filter(TAntiqueHanbai.tenant_id == tenant_id)
        total_sales = sum(float(s.amount or 0) for s in sales_q.all())
        recent_items = q.order_by(TAntiqueShohin.created_at.desc()).limit(5).all()
    finally:
        db.close()
    return render_template('antiques/dashboard.html',
                           item_count=item_count,
                           instock_count=instock_count,
                           sold_count=sold_count,
                           inventory_value=inventory_value,
                           partner_count=partner_count,
                           total_sales=total_sales,
                           recent_items=recent_items)


# ─── 取引先管理 ───────────────────────────────────────────────────────────────

@bp.route('/partners')
def partners():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        tenant_id = _get_tenant_id()
        q = db.query(TAntiqueTorihikisaki)
        if tenant_id:
            q = q.filter(TAntiqueTorihikisaki.tenant_id == tenant_id)
        rows = q.order_by(TAntiqueTorihikisaki.created_at.desc()).all()
    finally:
        db.close()
    return render_template('antiques/partners.html', partners=rows)


@bp.route('/partners/new', methods=['GET', 'POST'])
def partner_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    if request.method == 'POST':
        db = SessionLocal()
        try:
            p = TAntiqueTorihikisaki(
                tenant_id=_get_tenant_id(),
                name=request.form.get('name', '').strip(),
                partner_type=request.form.get('partner_type', '顧客'),
                contact_name=request.form.get('contact_name', '').strip() or None,
                phone=request.form.get('phone', '').strip() or None,
                email=request.form.get('email', '').strip() or None,
                address=request.form.get('address', '').strip() or None,
                notes=request.form.get('notes', '').strip() or None,
                created_by=_get_user_id(),
            )
            db.add(p)
            db.commit()
            flash('取引先を登録しました', 'success')
        except Exception as e:
            db.rollback()
            flash(f'登録に失敗しました: {e}', 'danger')
        finally:
            db.close()
        return redirect(url_for('antiques.partners'))
    return render_template('antiques/partner_form.html',
                           partner=None, partner_type_list=PARTNER_TYPE_LIST)


@bp.route('/partners/<int:pid>/edit', methods=['GET', 'POST'])
def partner_edit(pid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        p = db.query(TAntiqueTorihikisaki).filter(TAntiqueTorihikisaki.id == pid).first()
        if not p:
            flash('取引先が見つかりません', 'danger')
            return redirect(url_for('antiques.partners'))
        if request.method == 'POST':
            p.name = request.form.get('name', '').strip()
            p.partner_type = request.form.get('partner_type', '顧客')
            p.contact_name = request.form.get('contact_name', '').strip() or None
            p.phone = request.form.get('phone', '').strip() or None
            p.email = request.form.get('email', '').strip() or None
            p.address = request.form.get('address', '').strip() or None
            p.notes = request.form.get('notes', '').strip() or None
            db.commit()
            flash('取引先情報を更新しました', 'success')
            return redirect(url_for('antiques.partners'))
        return render_template('antiques/partner_form.html',
                               partner=p, partner_type_list=PARTNER_TYPE_LIST)
    except Exception as e:
        db.rollback()
        flash(f'更新に失敗しました: {e}', 'danger')
        return redirect(url_for('antiques.partners'))
    finally:
        db.close()


@bp.route('/partners/<int:pid>/delete', methods=['POST'])
def partner_delete(pid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        p = db.query(TAntiqueTorihikisaki).filter(TAntiqueTorihikisaki.id == pid).first()
        if p:
            db.delete(p)
            db.commit()
            flash('取引先を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('antiques.partners'))


# ─── 商品台帳（在庫） ─────────────────────────────────────────────────────────

@bp.route('/items')
def items():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        tenant_id = _get_tenant_id()
        rows = db.query(TAntiqueShohin, TAntiqueTorihikisaki).outerjoin(
            TAntiqueTorihikisaki, TAntiqueShohin.supplier_id == TAntiqueTorihikisaki.id
        )
        if tenant_id:
            rows = rows.filter(TAntiqueShohin.tenant_id == tenant_id)
        rows = rows.order_by(TAntiqueShohin.created_at.desc()).all()
    finally:
        db.close()
    return render_template('antiques/items.html', rows=rows, status_list=STATUS_LIST)


@bp.route('/items/new', methods=['GET', 'POST'])
def item_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        suppliers = db.query(TAntiqueTorihikisaki).all()
        if request.method == 'POST':
            i = TAntiqueShohin(
                tenant_id=_get_tenant_id(),
                management_no=request.form.get('management_no', '').strip() or None,
                name=request.form.get('name', '').strip(),
                category=request.form.get('category', '').strip() or None,
                era=request.form.get('era', '').strip() or None,
                condition=request.form.get('condition', '良好'),
                status=request.form.get('status', '在庫'),
                supplier_id=int(request.form['supplier_id']) if request.form.get('supplier_id') else None,
                acquisition_cost=request.form.get('acquisition_cost') or None,
                asking_price=request.form.get('asking_price') or None,
                description=request.form.get('description', '').strip() or None,
                created_by=_get_user_id(),
            )
            db.add(i)
            db.commit()
            flash('商品を登録しました', 'success')
            return redirect(url_for('antiques.items'))
        return render_template('antiques/item_form.html',
                               item=None, suppliers=suppliers,
                               category_list=CATEGORY_LIST,
                               condition_list=CONDITION_LIST,
                               status_list=STATUS_LIST)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('antiques.items'))
    finally:
        db.close()


@bp.route('/items/<int:iid>/edit', methods=['GET', 'POST'])
def item_edit(iid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        i = db.query(TAntiqueShohin).filter(TAntiqueShohin.id == iid).first()
        suppliers = db.query(TAntiqueTorihikisaki).all()
        if not i:
            flash('商品が見つかりません', 'danger')
            return redirect(url_for('antiques.items'))
        if request.method == 'POST':
            i.management_no = request.form.get('management_no', '').strip() or None
            i.name = request.form.get('name', '').strip()
            i.category = request.form.get('category', '').strip() or None
            i.era = request.form.get('era', '').strip() or None
            i.condition = request.form.get('condition', '良好')
            i.status = request.form.get('status', '在庫')
            i.supplier_id = int(request.form['supplier_id']) if request.form.get('supplier_id') else None
            i.acquisition_cost = request.form.get('acquisition_cost') or None
            i.asking_price = request.form.get('asking_price') or None
            i.description = request.form.get('description', '').strip() or None
            db.commit()
            flash('商品情報を更新しました', 'success')
            return redirect(url_for('antiques.items'))
        return render_template('antiques/item_form.html',
                               item=i, suppliers=suppliers,
                               category_list=CATEGORY_LIST,
                               condition_list=CONDITION_LIST,
                               status_list=STATUS_LIST)
    except Exception as e:
        db.rollback()
        flash(f'更新に失敗しました: {e}', 'danger')
        return redirect(url_for('antiques.items'))
    finally:
        db.close()


@bp.route('/items/<int:iid>/delete', methods=['POST'])
def item_delete(iid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        i = db.query(TAntiqueShohin).filter(TAntiqueShohin.id == iid).first()
        if i:
            db.delete(i)
            db.commit()
            flash('商品を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('antiques.items'))


# ─── 買取管理 ─────────────────────────────────────────────────────────────────

@bp.route('/purchases')
def purchases():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        rows = db.query(TAntiqueKaitori, TAntiqueShohin, TAntiqueTorihikisaki).outerjoin(
            TAntiqueShohin, TAntiqueKaitori.shohin_id == TAntiqueShohin.id
        ).outerjoin(
            TAntiqueTorihikisaki, TAntiqueKaitori.supplier_id == TAntiqueTorihikisaki.id
        ).order_by(TAntiqueKaitori.purchase_date.desc()).all()
    finally:
        db.close()
    return render_template('antiques/purchases.html', rows=rows)


@bp.route('/purchases/new', methods=['GET', 'POST'])
def purchase_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        items_list = db.query(TAntiqueShohin).all()
        suppliers = db.query(TAntiqueTorihikisaki).all()
        if request.method == 'POST':
            k = TAntiqueKaitori(
                tenant_id=_get_tenant_id(),
                shohin_id=int(request.form['shohin_id']) if request.form.get('shohin_id') else None,
                supplier_id=int(request.form['supplier_id']) if request.form.get('supplier_id') else None,
                purchase_date=_parse_date(request.form.get('purchase_date')),
                amount=request.form.get('amount') or None,
                payment_method=request.form.get('payment_method', '').strip() or None,
                notes=request.form.get('notes', '').strip() or None,
                created_by=_get_user_id(),
            )
            db.add(k)
            db.commit()
            flash('買取記録を登録しました', 'success')
            return redirect(url_for('antiques.purchases'))
        today = datetime.date.today().isoformat()
        return render_template('antiques/purchase_form.html',
                               purchase=None, items=items_list,
                               suppliers=suppliers, today=today)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('antiques.purchases'))
    finally:
        db.close()


@bp.route('/purchases/<int:kid>/delete', methods=['POST'])
def purchase_delete(kid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        k = db.query(TAntiqueKaitori).filter(TAntiqueKaitori.id == kid).first()
        if k:
            db.delete(k)
            db.commit()
            flash('買取記録を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('antiques.purchases'))


# ─── 販売管理 ─────────────────────────────────────────────────────────────────

@bp.route('/sales')
def sales():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        rows = db.query(TAntiqueHanbai, TAntiqueShohin, TAntiqueTorihikisaki).outerjoin(
            TAntiqueShohin, TAntiqueHanbai.shohin_id == TAntiqueShohin.id
        ).outerjoin(
            TAntiqueTorihikisaki, TAntiqueHanbai.customer_id == TAntiqueTorihikisaki.id
        ).order_by(TAntiqueHanbai.sale_date.desc()).all()
    finally:
        db.close()
    return render_template('antiques/sales.html', rows=rows)


@bp.route('/sales/new', methods=['GET', 'POST'])
def sale_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        items_list = db.query(TAntiqueShohin).all()
        customers = db.query(TAntiqueTorihikisaki).all()
        if request.method == 'POST':
            shohin_id = int(request.form['shohin_id']) if request.form.get('shohin_id') else None
            h = TAntiqueHanbai(
                tenant_id=_get_tenant_id(),
                shohin_id=shohin_id,
                customer_id=int(request.form['customer_id']) if request.form.get('customer_id') else None,
                sale_date=_parse_date(request.form.get('sale_date')),
                amount=request.form.get('amount') or None,
                payment_method=request.form.get('payment_method', '').strip() or None,
                notes=request.form.get('notes', '').strip() or None,
                created_by=_get_user_id(),
            )
            db.add(h)
            # 販売した商品は在庫ステータスを「販売済」に更新
            if shohin_id:
                item = db.query(TAntiqueShohin).filter(TAntiqueShohin.id == shohin_id).first()
                if item:
                    item.status = '販売済'
            db.commit()
            flash('販売記録を登録しました', 'success')
            return redirect(url_for('antiques.sales'))
        today = datetime.date.today().isoformat()
        return render_template('antiques/sale_form.html',
                               sale=None, items=items_list,
                               customers=customers, today=today)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('antiques.sales'))
    finally:
        db.close()


@bp.route('/sales/<int:hid>/delete', methods=['POST'])
def sale_delete(hid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        h = db.query(TAntiqueHanbai).filter(TAntiqueHanbai.id == hid).first()
        if h:
            db.delete(h)
            db.commit()
            flash('販売記録を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('antiques.sales'))


# ─── 鑑定記録 ─────────────────────────────────────────────────────────────────

@bp.route('/appraisals')
def appraisals():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        rows = db.query(TAntiqueKantei, TAntiqueShohin).outerjoin(
            TAntiqueShohin, TAntiqueKantei.shohin_id == TAntiqueShohin.id
        ).order_by(TAntiqueKantei.appraisal_date.desc()).all()
    finally:
        db.close()
    return render_template('antiques/appraisals.html', rows=rows)


@bp.route('/appraisals/new', methods=['GET', 'POST'])
def appraisal_new():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        items_list = db.query(TAntiqueShohin).all()
        if request.method == 'POST':
            a = TAntiqueKantei(
                tenant_id=_get_tenant_id(),
                shohin_id=int(request.form['shohin_id']) if request.form.get('shohin_id') else None,
                target_name=request.form.get('target_name', '').strip() or None,
                appraiser=request.form.get('appraiser', '').strip() or None,
                appraisal_date=_parse_date(request.form.get('appraisal_date')),
                appraised_value=request.form.get('appraised_value') or None,
                result=request.form.get('result', '不明'),
                comment=request.form.get('comment', '').strip() or None,
                created_by=_get_user_id(),
            )
            db.add(a)
            db.commit()
            flash('鑑定記録を登録しました', 'success')
            return redirect(url_for('antiques.appraisals'))
        today = datetime.date.today().isoformat()
        return render_template('antiques/appraisal_form.html',
                               appraisal=None, items=items_list,
                               result_list=KANTEI_RESULT_LIST, today=today)
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('antiques.appraisals'))
    finally:
        db.close()


@bp.route('/appraisals/<int:aid>/delete', methods=['POST'])
def appraisal_delete(aid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        a = db.query(TAntiqueKantei).filter(TAntiqueKantei.id == aid).first()
        if a:
            db.delete(a)
            db.commit()
            flash('鑑定記録を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('antiques.appraisals'))


# ─── ファイル管理 ─────────────────────────────────────────────────────────────

@bp.route('/files')
def files():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        items_list = db.query(TAntiqueShohin).all()
        shohin_id = request.args.get('shohin_id', type=int)
        file_rows = []
        if shohin_id:
            file_rows = db.query(TAntiqueFile).filter(
                TAntiqueFile.shohin_id == shohin_id
            ).order_by(TAntiqueFile.created_at.desc()).all()
    finally:
        db.close()
    return render_template('antiques/files.html',
                           items=items_list,
                           file_rows=file_rows,
                           selected_shohin_id=shohin_id)


@bp.route('/files/upload', methods=['POST'])
def file_upload():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    import uuid
    shohin_id = request.form.get('shohin_id', type=int)
    if not shohin_id:
        flash('商品を選択してください', 'danger')
        return redirect(url_for('antiques.files'))
    uploaded = request.files.getlist('files')
    db = SessionLocal()
    try:
        for f in uploaded:
            if not f or not f.filename:
                continue
            file_bytes = f.read()
            # S3アップロード（storage_adapterを利用）
            try:
                from ..utils.storage_adapter import upload_file_to_storage
                file_key = f'antiques/{shohin_id}/{uuid.uuid4().hex}_{f.filename}'
                file_url = upload_file_to_storage(file_key, file_bytes, f.content_type)
            except Exception:
                # S3未設定時はローカル保存パスをURLとして記録
                file_key = f'antiques/{shohin_id}/{f.filename}'
                file_url = f'/static/uploads/{file_key}'

            rec = TAntiqueFile(
                tenant_id=_get_tenant_id(),
                shohin_id=shohin_id,
                uploaded_by=_get_user_id(),
                file_name=f.filename,
                file_key=file_key,
                file_url=file_url,
                mime_type=f.content_type,
                file_size=len(file_bytes),
            )
            db.add(rec)
        db.commit()
        flash('ファイルをアップロードしました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'アップロードに失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('antiques.files', shohin_id=shohin_id))


@bp.route('/files/<int:fid>/delete', methods=['POST'])
def file_delete(fid):
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    db = SessionLocal()
    try:
        f = db.query(TAntiqueFile).filter(TAntiqueFile.id == fid).first()
        shohin_id = f.shohin_id if f else None
        if f:
            db.delete(f)
            db.commit()
            flash('ファイルを削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('antiques.files', shohin_id=shohin_id))
