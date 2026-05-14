# -*- coding: utf-8 -*-
"""
建設業運営アプリ - 拡張ブループリント (サクミル相当機能)

URLプレフィックス: /construction/ext

【機能】
  1. 写真管理         /construction/ext/photos
  2. 実行予算管理     /construction/ext/yosan
  3. 原価管理         /construction/ext/genka
  4. 工事台帳         /construction/ext/daicho
  5. 出面管理         /construction/ext/demen
  6. 仕入先マスタ     /construction/ext/shiiresaki
  7. 発注管理         /construction/ext/hacchu
  8. 入金管理         /construction/ext/nyukin
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import func as sqlfunc
from ..db import SessionLocal
from ..models_construction import TKokyaku, TAnken, TNippo, TMitsumori
from ..models_construction_ext import (
    TPhotoAlbum, TPhoto,
    TJikkouYosan, TGenka,
    TDemen,
    TShiiresaki, THacchu, THacchuMeisai,
    TNyukin,
)
import datetime
import uuid

bp = Blueprint('construction_ext', __name__, url_prefix='/construction/ext')


def _tenant_id():
    return session.get('tenant_id')


def _user_id():
    return session.get('user_id')


def _require_login():
    if not session.get('role'):
        return redirect(url_for('auth.select_login'))
    return None


# ════════════════════════════════════════════════════════════════════
# 1. 写真管理
# ════════════════════════════════════════════════════════════════════

@bp.route('/photos')
def photos():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        anken_id = request.args.get('anken_id', type=int)
        projects = db.query(TAnken).filter(
            TAnken.tenant_id == _tenant_id() if _tenant_id() else True
        ).all()
        albums, photos_list = [], []
        if anken_id:
            albums = db.query(TPhotoAlbum).filter(
                TPhotoAlbum.anken_id == anken_id
            ).order_by(TPhotoAlbum.created_at.desc()).all()
            photos_list = db.query(TPhoto).filter(
                TPhoto.anken_id == anken_id
            ).order_by(TPhoto.sort_order, TPhoto.taken_at.desc()).all()
    finally:
        db.close()
    return render_template('construction_ext/photos.html',
                           projects=projects, albums=albums,
                           photos=photos_list, selected_anken_id=anken_id)


@bp.route('/photos/album/new', methods=['POST'])
def album_new():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        anken_id = request.form.get('anken_id', type=int)
        album = TPhotoAlbum(
            tenant_id=_tenant_id(),
            anken_id=anken_id,
            title=request.form.get('title', '').strip() or '無題の台帳',
            description=request.form.get('description', '').strip() or None,
            created_by=_user_id(),
        )
        db.add(album)
        db.commit()
        flash('写真台帳を作成しました', 'success')
        return redirect(url_for('construction_ext.photos', anken_id=anken_id))
    except Exception as e:
        db.rollback()
        flash(f'作成に失敗しました: {e}', 'danger')
        return redirect(url_for('construction_ext.photos'))
    finally:
        db.close()


@bp.route('/photos/upload', methods=['POST'])
def photo_upload():
    redir = _require_login()
    if redir:
        return redir
    anken_id = request.form.get('anken_id', type=int)
    album_id = request.form.get('album_id', type=int)
    if not anken_id:
        flash('案件を選択してください', 'danger')
        return redirect(url_for('construction_ext.photos'))
    files = request.files.getlist('files')
    db = SessionLocal()
    try:
        for f in files:
            if not f or not f.filename:
                continue
            file_bytes = f.read()
            file_key = f'construction_photos/{anken_id}/{uuid.uuid4().hex}_{f.filename}'
            try:
                from ..utils.storage_adapter import upload_file_to_storage
                file_url = upload_file_to_storage(file_key, file_bytes, f.content_type)
            except Exception:
                file_url = f'/static/uploads/{file_key}'
            photo = TPhoto(
                tenant_id=_tenant_id(),
                album_id=album_id,
                anken_id=anken_id,
                taken_at=request.form.get('taken_at') or None,
                work_type=request.form.get('work_type', '').strip() or None,
                location=request.form.get('location', '').strip() or None,
                comment=request.form.get('comment', '').strip() or None,
                file_name=f.filename,
                file_key=file_key,
                file_url=file_url,
                mime_type=f.content_type,
                file_size=len(file_bytes),
                uploaded_by=_user_id(),
            )
            db.add(photo)
        db.commit()
        flash('写真をアップロードしました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'アップロードに失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.photos', anken_id=anken_id))


@bp.route('/photos/<int:pid>/delete', methods=['POST'])
def photo_delete(pid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        p = db.query(TPhoto).filter(TPhoto.id == pid).first()
        anken_id = p.anken_id if p else None
        if p:
            db.delete(p)
            db.commit()
            flash('写真を削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.photos', anken_id=anken_id))


# ════════════════════════════════════════════════════════════════════
# 2. 実行予算管理
# ════════════════════════════════════════════════════════════════════

YOSAN_CATEGORIES = ['資材費', '労務費', '外注費', '経費', 'その他']


@bp.route('/yosan')
def yosan_list():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        anken_id = request.args.get('anken_id', type=int)
        projects = db.query(TAnken).filter(
            TAnken.tenant_id == _tenant_id() if _tenant_id() else True
        ).all()
        rows, total_budget = [], 0
        if anken_id:
            rows = db.query(TJikkouYosan).filter(
                TJikkouYosan.anken_id == anken_id
            ).order_by(TJikkouYosan.category).all()
            total_budget = sum(float(r.budget_amount or 0) for r in rows)
    finally:
        db.close()
    return render_template('construction_ext/yosan.html',
                           projects=projects, rows=rows,
                           selected_anken_id=anken_id,
                           total_budget=total_budget,
                           categories=YOSAN_CATEGORIES)


@bp.route('/yosan/new', methods=['POST'])
def yosan_new():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        y = TJikkouYosan(
            tenant_id=_tenant_id(),
            anken_id=request.form.get('anken_id', type=int),
            category=request.form.get('category', '資材費'),
            item_name=request.form.get('item_name', '').strip() or None,
            budget_amount=request.form.get('budget_amount') or 0,
            notes=request.form.get('notes', '').strip() or None,
            created_by=_user_id(),
        )
        db.add(y)
        db.commit()
        flash('実行予算を登録しました', 'success')
        return redirect(url_for('construction_ext.yosan_list', anken_id=y.anken_id))
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('construction_ext.yosan_list'))
    finally:
        db.close()


@bp.route('/yosan/<int:yid>/delete', methods=['POST'])
def yosan_delete(yid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        y = db.query(TJikkouYosan).filter(TJikkouYosan.id == yid).first()
        anken_id = y.anken_id if y else None
        if y:
            db.delete(y)
            db.commit()
            flash('削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.yosan_list', anken_id=anken_id))


# ════════════════════════════════════════════════════════════════════
# 3. 原価管理
# ════════════════════════════════════════════════════════════════════

GENKA_CATEGORIES = ['資材費', '労務費', '外注費', '経費', 'その他']


@bp.route('/genka')
def genka_list():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        anken_id = request.args.get('anken_id', type=int)
        projects = db.query(TAnken).filter(
            TAnken.tenant_id == _tenant_id() if _tenant_id() else True
        ).all()
        shiiresakis = db.query(TShiiresaki).all()
        rows, total_cost = [], 0
        if anken_id:
            rows = db.query(TGenka).filter(
                TGenka.anken_id == anken_id
            ).order_by(TGenka.cost_date.desc()).all()
            total_cost = sum(float(r.amount or 0) for r in rows)
    finally:
        db.close()
    return render_template('construction_ext/genka.html',
                           projects=projects, rows=rows,
                           shiiresakis=shiiresakis,
                           selected_anken_id=anken_id,
                           total_cost=total_cost,
                           categories=GENKA_CATEGORIES)


@bp.route('/genka/new', methods=['POST'])
def genka_new():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        g = TGenka(
            tenant_id=_tenant_id(),
            anken_id=request.form.get('anken_id', type=int),
            category=request.form.get('category', '資材費'),
            item_name=request.form.get('item_name', '').strip() or None,
            cost_date=request.form.get('cost_date') or datetime.date.today().isoformat(),
            amount=request.form.get('amount') or 0,
            vendor_name=request.form.get('vendor_name', '').strip() or None,
            shiiresaki_id=request.form.get('shiiresaki_id', type=int) or None,
            notes=request.form.get('notes', '').strip() or None,
            created_by=_user_id(),
        )
        db.add(g)
        db.commit()
        flash('原価を登録しました', 'success')
        return redirect(url_for('construction_ext.genka_list', anken_id=g.anken_id))
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('construction_ext.genka_list'))
    finally:
        db.close()


@bp.route('/genka/<int:gid>/delete', methods=['POST'])
def genka_delete(gid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        g = db.query(TGenka).filter(TGenka.id == gid).first()
        anken_id = g.anken_id if g else None
        if g:
            db.delete(g)
            db.commit()
            flash('削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.genka_list', anken_id=anken_id))


# ════════════════════════════════════════════════════════════════════
# 4. 工事台帳(集計ビュー)
# ════════════════════════════════════════════════════════════════════

@bp.route('/daicho')
def daicho():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        tenant_id = _tenant_id()
        q = db.query(TAnken)
        if tenant_id:
            q = q.filter(TAnken.tenant_id == tenant_id)
        projects = q.order_by(TAnken.created_at.desc()).all()
        rows = []
        for p in projects:
            invoice_total = db.query(
                sqlfunc.coalesce(sqlfunc.sum(TMitsumori.total_amount), 0)
            ).filter(
                TMitsumori.anken_id == p.id,
                TMitsumori.doc_type == 'invoice'
            ).scalar() or 0
            contract = float(p.contract_amount or 0)
            uriage = max(contract, float(invoice_total))
            budget_total = db.query(
                sqlfunc.coalesce(sqlfunc.sum(TJikkouYosan.budget_amount), 0)
            ).filter(TJikkouYosan.anken_id == p.id).scalar() or 0
            cost_total = db.query(
                sqlfunc.coalesce(sqlfunc.sum(TGenka.amount), 0)
            ).filter(TGenka.anken_id == p.id).scalar() or 0
            nyukin_total = db.query(
                sqlfunc.coalesce(sqlfunc.sum(TNyukin.amount), 0)
            ).filter(TNyukin.anken_id == p.id).scalar() or 0
            profit = uriage - float(cost_total)
            margin = (profit / uriage * 100) if uriage else 0
            rows.append({
                'project': p,
                'uriage': uriage,
                'budget': float(budget_total),
                'cost': float(cost_total),
                'nyukin': float(nyukin_total),
                'mishu': uriage - float(nyukin_total),
                'profit': profit,
                'margin': round(margin, 1),
            })
    finally:
        db.close()
    return render_template('construction_ext/daicho.html', rows=rows)


@bp.route('/daicho/<int:pid>')
def daicho_detail(pid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        project = db.query(TAnken).filter(TAnken.id == pid).first()
        if not project:
            flash('案件が見つかりません', 'danger')
            return redirect(url_for('construction_ext.daicho'))
        budget_by_cat = {}
        for r in db.query(TJikkouYosan).filter(TJikkouYosan.anken_id == pid).all():
            budget_by_cat[r.category] = budget_by_cat.get(r.category, 0) + float(r.budget_amount or 0)
        cost_by_cat = {}
        for r in db.query(TGenka).filter(TGenka.anken_id == pid).all():
            cost_by_cat[r.category] = cost_by_cat.get(r.category, 0) + float(r.amount or 0)
        categories = sorted(set(list(budget_by_cat.keys()) + list(cost_by_cat.keys())))
        breakdown = [{
            'category': c,
            'budget': budget_by_cat.get(c, 0),
            'cost': cost_by_cat.get(c, 0),
            'diff': budget_by_cat.get(c, 0) - cost_by_cat.get(c, 0),
        } for c in categories]
    finally:
        db.close()
    return render_template('construction_ext/daicho_detail.html',
                           project=project, breakdown=breakdown)


# ════════════════════════════════════════════════════════════════════
# 5. 出面管理
# ════════════════════════════════════════════════════════════════════

@bp.route('/demen')
def demen_list():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        anken_id = request.args.get('anken_id', type=int)
        date_from = request.args.get('date_from') or None
        date_to = request.args.get('date_to') or None
        projects = db.query(TAnken).filter(
            TAnken.tenant_id == _tenant_id() if _tenant_id() else True
        ).all()
        q = db.query(TDemen)
        if anken_id:
            q = q.filter(TDemen.anken_id == anken_id)
        if date_from:
            q = q.filter(TDemen.work_date >= date_from)
        if date_to:
            q = q.filter(TDemen.work_date <= date_to)
        rows = q.order_by(TDemen.work_date.desc()).all()
        total_ninku = sum(float(r.ninku or 0) for r in rows)
        total_amount = sum(float(r.amount or 0) for r in rows)
    finally:
        db.close()
    return render_template('construction_ext/demen.html',
                           projects=projects, rows=rows,
                           selected_anken_id=anken_id,
                           date_from=date_from, date_to=date_to,
                           total_ninku=total_ninku,
                           total_amount=total_amount)


@bp.route('/demen/new', methods=['POST'])
def demen_new():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        ninku = request.form.get('ninku') or 1.0
        unit_price = request.form.get('unit_price') or None
        amount = None
        try:
            if unit_price:
                amount = float(ninku) * float(unit_price)
        except (ValueError, TypeError):
            amount = None
        d = TDemen(
            tenant_id=_tenant_id(),
            anken_id=request.form.get('anken_id', type=int),
            work_date=request.form.get('work_date') or datetime.date.today().isoformat(),
            employee_id=request.form.get('employee_id', type=int) or None,
            worker_name=request.form.get('worker_name', '').strip() or None,
            worker_type=request.form.get('worker_type', '自社'),
            ninku=ninku,
            unit_price=unit_price,
            amount=amount,
            notes=request.form.get('notes', '').strip() or None,
            created_by=_user_id(),
        )
        db.add(d)
        db.commit()
        flash('出面を登録しました', 'success')
        return redirect(url_for('construction_ext.demen_list', anken_id=d.anken_id))
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('construction_ext.demen_list'))
    finally:
        db.close()


@bp.route('/demen/<int:did>/delete', methods=['POST'])
def demen_delete(did):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        d = db.query(TDemen).filter(TDemen.id == did).first()
        anken_id = d.anken_id if d else None
        if d:
            db.delete(d)
            db.commit()
            flash('削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.demen_list', anken_id=anken_id))


# ════════════════════════════════════════════════════════════════════
# 6. 仕入先マスタ
# ════════════════════════════════════════════════════════════════════

@bp.route('/shiiresaki')
def shiiresaki_list():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        rows = db.query(TShiiresaki).filter(
            TShiiresaki.tenant_id == _tenant_id() if _tenant_id() else True
        ).order_by(TShiiresaki.created_at.desc()).all()
    finally:
        db.close()
    return render_template('construction_ext/shiiresaki.html', rows=rows)


@bp.route('/shiiresaki/new', methods=['POST'])
def shiiresaki_new():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        s = TShiiresaki(
            tenant_id=_tenant_id(),
            company_name=request.form.get('company_name', '').strip(),
            contact_name=request.form.get('contact_name', '').strip() or None,
            phone=request.form.get('phone', '').strip() or None,
            email=request.form.get('email', '').strip() or None,
            address=request.form.get('address', '').strip() or None,
            category=request.form.get('category', '資材'),
            payment_terms=request.form.get('payment_terms', '').strip() or None,
            notes=request.form.get('notes', '').strip() or None,
            created_by=_user_id(),
        )
        db.add(s)
        db.commit()
        flash('仕入先を登録しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.shiiresaki_list'))


@bp.route('/shiiresaki/<int:sid>/delete', methods=['POST'])
def shiiresaki_delete(sid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        s = db.query(TShiiresaki).filter(TShiiresaki.id == sid).first()
        if s:
            db.delete(s)
            db.commit()
            flash('削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.shiiresaki_list'))


# ════════════════════════════════════════════════════════════════════
# 7. 発注管理
# ════════════════════════════════════════════════════════════════════

HACCHU_STATUS_LABELS = {
    'draft': '下書き', 'sent': '発注済', 'received': '納品済',
    'paid': '支払済', 'cancelled': '取消'
}


@bp.route('/hacchu')
def hacchu_list():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        rows = db.query(THacchu, TAnken, TShiiresaki).outerjoin(
            TAnken, THacchu.anken_id == TAnken.id
        ).outerjoin(
            TShiiresaki, THacchu.shiiresaki_id == TShiiresaki.id
        ).order_by(THacchu.created_at.desc()).all()
        projects = db.query(TAnken).all()
        shiiresakis = db.query(TShiiresaki).all()
    finally:
        db.close()
    return render_template('construction_ext/hacchu.html',
                           rows=rows, projects=projects,
                           shiiresakis=shiiresakis,
                           status_labels=HACCHU_STATUS_LABELS)


@bp.route('/hacchu/new', methods=['GET', 'POST'])
def hacchu_new():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        projects = db.query(TAnken).all()
        shiiresakis = db.query(TShiiresaki).all()
        if request.method == 'POST':
            h = THacchu(
                tenant_id=_tenant_id(),
                anken_id=request.form.get('anken_id', type=int),
                shiiresaki_id=request.form.get('shiiresaki_id', type=int) or None,
                order_no=request.form.get('order_no', '').strip() or None,
                order_date=request.form.get('order_date') or None,
                delivery_date=request.form.get('delivery_date') or None,
                status=request.form.get('status', 'draft'),
                total_amount=request.form.get('total_amount') or None,
                notes=request.form.get('notes', '').strip() or None,
                created_by=_user_id(),
            )
            db.add(h)
            db.flush()
            descs = request.form.getlist('item_description[]')
            qtys = request.form.getlist('item_quantity[]')
            units = request.form.getlist('item_unit[]')
            prices = request.form.getlist('item_unit_price[]')
            amounts = request.form.getlist('item_amount[]')
            for i, desc in enumerate(descs):
                if not desc.strip():
                    continue
                item = THacchuMeisai(
                    hacchu_id=h.id,
                    description=desc.strip(),
                    quantity=qtys[i] if i < len(qtys) and qtys[i] else None,
                    unit=units[i] if i < len(units) and units[i] else None,
                    unit_price=prices[i] if i < len(prices) and prices[i] else None,
                    amount=amounts[i] if i < len(amounts) and amounts[i] else None,
                    sort_order=i,
                )
                db.add(item)
            db.commit()
            flash('発注を登録しました', 'success')
            return redirect(url_for('construction_ext.hacchu_list'))
        return render_template('construction_ext/hacchu_form.html',
                               hacchu=None, projects=projects,
                               shiiresakis=shiiresakis,
                               today=datetime.date.today().isoformat())
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
        return redirect(url_for('construction_ext.hacchu_list'))
    finally:
        db.close()


@bp.route('/hacchu/<int:hid>/delete', methods=['POST'])
def hacchu_delete(hid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        db.query(THacchuMeisai).filter(THacchuMeisai.hacchu_id == hid).delete()
        h = db.query(THacchu).filter(THacchu.id == hid).first()
        if h:
            db.delete(h)
        db.commit()
        flash('削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.hacchu_list'))


# ════════════════════════════════════════════════════════════════════
# 8. 入金管理
# ════════════════════════════════════════════════════════════════════

NYUKIN_METHODS = ['振込', '現金', '小切手', '手形', 'その他']


@bp.route('/nyukin')
def nyukin_list():
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        invoices = db.query(TMitsumori, TAnken).outerjoin(
            TAnken, TMitsumori.anken_id == TAnken.id
        ).filter(TMitsumori.doc_type == 'invoice').order_by(
            TMitsumori.issue_date.desc()
        ).all()
        rows = []
        for inv, project in invoices:
            paid_total = db.query(
                sqlfunc.coalesce(sqlfunc.sum(TNyukin.amount), 0)
            ).filter(TNyukin.mitsumori_id == inv.id).scalar() or 0
            invoice_amount = float(inv.total_amount or 0)
            rows.append({
                'invoice': inv,
                'project': project,
                'invoice_amount': invoice_amount,
                'paid': float(paid_total),
                'remaining': invoice_amount - float(paid_total),
            })
    finally:
        db.close()
    return render_template('construction_ext/nyukin.html', rows=rows)


@bp.route('/nyukin/<int:mid>/detail')
def nyukin_detail(mid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        invoice = db.query(TMitsumori).filter(TMitsumori.id == mid).first()
        if not invoice:
            flash('請求書が見つかりません', 'danger')
            return redirect(url_for('construction_ext.nyukin_list'))
        project = db.query(TAnken).filter(TAnken.id == invoice.anken_id).first() if invoice.anken_id else None
        payments = db.query(TNyukin).filter(
            TNyukin.mitsumori_id == mid
        ).order_by(TNyukin.payment_date.desc()).all()
        paid_total = sum(float(p.amount or 0) for p in payments)
        invoice_amount = float(invoice.total_amount or 0)
    finally:
        db.close()
    return render_template('construction_ext/nyukin_detail.html',
                           invoice=invoice, project=project,
                           payments=payments,
                           paid_total=paid_total,
                           invoice_amount=invoice_amount,
                           remaining=invoice_amount - paid_total,
                           methods=NYUKIN_METHODS)


@bp.route('/nyukin/<int:mid>/new', methods=['POST'])
def nyukin_new(mid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        invoice = db.query(TMitsumori).filter(TMitsumori.id == mid).first()
        n = TNyukin(
            tenant_id=_tenant_id(),
            mitsumori_id=mid,
            anken_id=invoice.anken_id if invoice else None,
            payment_date=request.form.get('payment_date') or datetime.date.today().isoformat(),
            amount=request.form.get('amount') or 0,
            method=request.form.get('method', '振込'),
            bank_name=request.form.get('bank_name', '').strip() or None,
            notes=request.form.get('notes', '').strip() or None,
            created_by=_user_id(),
        )
        db.add(n)
        if invoice:
            paid_total = db.query(
                sqlfunc.coalesce(sqlfunc.sum(TNyukin.amount), 0)
            ).filter(TNyukin.mitsumori_id == mid).scalar() or 0
            paid_total = float(paid_total) + float(n.amount or 0)
            if paid_total >= float(invoice.total_amount or 0):
                invoice.status = 'paid'
        db.commit()
        flash('入金を登録しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'登録に失敗しました: {e}', 'danger')
    finally:
        db.close()
    return redirect(url_for('construction_ext.nyukin_detail', mid=mid))


@bp.route('/nyukin/<int:nid>/delete', methods=['POST'])
def nyukin_delete(nid):
    redir = _require_login()
    if redir:
        return redir
    db = SessionLocal()
    try:
        n = db.query(TNyukin).filter(TNyukin.id == nid).first()
        mid = n.mitsumori_id if n else None
        if n:
            db.delete(n)
            db.commit()
            flash('削除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'削除に失敗しました: {e}', 'danger')
    finally:
        db.close()
    if mid:
        return redirect(url_for('construction_ext.nyukin_detail', mid=mid))
    return redirect(url_for('construction_ext.nyukin_list'))
