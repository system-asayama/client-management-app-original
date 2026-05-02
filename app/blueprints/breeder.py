# -*- coding: utf-8 -*-
"""
ブリーダー管理システム Blueprint
全機能（ダッシュボード・生体・繁殖・販売・申請・健康・法規制・Todo・設定）を提供
"""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, g
from sqlalchemy import func, and_, or_, desc, asc
from app.db import SessionLocal
from app.models_login import TKanrisha
from ..utils.decorators import require_roles, ROLES

bp = Blueprint('breeder', __name__, url_prefix='/breeder')

@bp.before_request
def load_bg_color():
    """全ページで背景色設定をgオブジェクトに読み込む"""
    try:
        from app.models_breeder import AppSetting
        db = SessionLocal()
        setting = db.query(AppSetting).filter(AppSetting.key == 'bg_color').first()
        g.bg_color = setting.value if setting and setting.value else '#0f0f13'
        db.close()
    except Exception:
        g.bg_color = '#0f0f13'

# ─── 認証ヘルパー ────────────────────────────────────────────
BREEDER_ROLES = (ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])

def _get_db():
    return SessionLocal()

def _require_login():
    """ログイン確認（デコレータの代わりに使用）"""
    if not session.get('user_id'):
        return redirect(url_for('auth.select_login'))
    return None


def _get_breeder_permission(admin_id, tenant_id):
    """admin_idがtenant_idに対して持つブリーダー権限レベルを返す。
    戻り値: 'operate'（操作権限）, 'view'（閲覧のみ）, None（権限なし）
    """
    if not admin_id or not tenant_id:
        return None
    try:
        from app.models_breeder import BreederPermission
        db = _get_db()
        perm = db.query(BreederPermission).filter(
            BreederPermission.admin_id == admin_id,
            BreederPermission.tenant_id == tenant_id
        ).first()
        db.close()
        return perm.permission_level if perm else None
    except Exception:
        return None


def _get_tenant_store():
    """ロールに応じてtenant_idとstore_idを返す。
    - system_admin: 両方None（全データ）
    - tenant_admin: tenant_idのみ（全店舗集計）、store_idはNone
    - admin: デフォルトは自店舗のみ。breeder_permissionsに権限があればテナント全体
    - employee: tenant_id + store_id（自店舗のみ）
    """
    role = session.get('role', '')
    if role == 'system_admin':
        return None, None
    tenant_id = session.get('tenant_id')
    if role == 'tenant_admin':
        return tenant_id, None  # 全店舗集計
    store_id = session.get('store_id')
    # admin の場合、権限チェック
    if role == 'admin':
        admin_id = session.get('user_id')
        perm = _get_breeder_permission(admin_id, tenant_id)
        if perm in ('view', 'operate'):
            return tenant_id, None  # テナント全体を参照
    return tenant_id, store_id


def _can_operate(tenant_id=None):
    """現在のユーザーがデータの追加・編集・削除（操作）を行えるか判定。
    - system_admin / tenant_admin: 常にTrue
    - admin: 自店舗データは常にTrue。テナント全体は 'operate' 権限が必要
    - employee: 自店舗データのみTrue
    """
    role = session.get('role', '')
    if role in ('system_admin', 'tenant_admin'):
        return True
    if role == 'admin':
        # テナント全体操作の場合は operate 権限が必要
        if tenant_id and session.get('tenant_id') == tenant_id:
            admin_id = session.get('user_id')
            perm = _get_breeder_permission(admin_id, tenant_id)
            if perm == 'operate':
                return True
        return True  # 自店舗データは常に操作可
    return role == 'employee'  # employee は自店舗のみ操作可

def _get_role():
    return session.get('role', '')

# ─── ダッシュボード ──────────────────────────────────────────
@bp.route('/')
@bp.route('/dashboard')
@require_roles(*BREEDER_ROLES)
def dashboard():
    from app.models_breeder import Dog, Puppy, Heat, Mating, Birth, Todo, Negotiation, PedigreeApplication
    db = _get_db()
    try:
        today = date.today()
        tenant_id, store_id = _get_tenant_store()
        def _tf(q, model):
            if tenant_id:
                q = q.filter(model.tenant_id == tenant_id)
            if store_id:
                q = q.filter(model.store_id == store_id)
            return q
        # 在舎頭数
        parent_count = _tf(db.query(func.count(Dog.id)).filter(Dog.status == 'active', Dog.dog_type == 'parent'), Dog).scalar() or 0
        puppy_count = _tf(db.query(func.count(Puppy.id)).filter(Puppy.status.in_(['available', 'reserved'])), Puppy).scalar() or 0
        # Todo未完了
        todo_pending = _tf(db.query(func.count(Todo.id)).filter(Todo.status == 'pending'), Todo).scalar() or 0
        todo_today = _tf(db.query(func.count(Todo.id)).filter(Todo.status == 'pending', Todo.due_date == today), Todo).scalar() or 0
        # ヒート中
        heat_active = _tf(db.query(func.count(Heat.id)).filter(Heat.status.in_(['active', 'imminent'])), Heat).scalar() or 0
        # 妊娠中
        pregnant = _tf(db.query(func.count(Mating.id)).filter(Mating.status == 'pregnant'), Mating).scalar() or 0
        # 今月の出産
        births_this_month = _tf(db.query(func.count(Birth.id)).filter(
            func.extract('year', Birth.birth_date) == today.year,
            func.extract('month', Birth.birth_date) == today.month
        ), Birth).scalar() or 0
        # 商談中
        negotiating = _tf(db.query(func.count(Negotiation.id)).filter(
            Negotiation.status.in_(['inquiry', 'negotiating', 'reserved'])
        ), Negotiation).scalar() or 0
        # 直近Todoリスト
        recent_todos = _tf(db.query(Todo).filter(
            Todo.status == 'pending'
        ), Todo).order_by(asc(Todo.due_date)).limit(5).all()
        # 最近の出産（月別統計 - 過去6ヶ月）
        birth_stats = []
        for i in range(5, -1, -1):
            d = today.replace(day=1) - timedelta(days=i * 30)
            cnt = db.query(func.count(Birth.id)).filter(
                func.extract('year', Birth.birth_date) == d.year,
                func.extract('month', Birth.birth_date) == d.month
            ).scalar() or 0
            birth_stats.append({'month': d.strftime('%Y/%m'), 'count': cnt})
        # 最近のヒート予定
        upcoming_heats = db.query(Heat, Dog).join(Dog, Heat.dog_id == Dog.id).filter(
            Heat.next_predicted_date >= today,
            Heat.next_predicted_date <= today + timedelta(days=30)
        ).order_by(asc(Heat.next_predicted_date)).limit(5).all()
        # 血統書申請未提出アラート（70日以内の出産で未申請の子犬）
        cutoff_70 = today - timedelta(days=70)
        unregistered_alert_count = 0
        unregistered_alert_puppies = []
        try:
            recent_births = db.query(Birth).filter(Birth.birth_date >= cutoff_70).all()
            for birth in recent_births:
                puppies_in_birth = db.query(Puppy).filter(Puppy.birth_id == birth.id).all()
                for puppy in puppies_in_birth:
                    has_app = db.query(PedigreeApplication).filter(
                        PedigreeApplication.puppy_id == puppy.id
                    ).first()
                    if not has_app:
                        unregistered_alert_count += 1
                        if len(unregistered_alert_puppies) < 5:
                            days_old = (today - birth.birth_date).days
                            unregistered_alert_puppies.append({
                                'puppy': puppy,
                                'birth_date': birth.birth_date,
                                'days_old': days_old,
                            })
        except Exception:
            pass
        role = _get_role()
        # テナント管理者・システム管理者の場合は店舗別集計も渡す
        store_stats = []
        if role in ('tenant_admin', 'system_admin'):
            from app.models_login import TTenpo
            sq = db.query(TTenpo)
            if tenant_id:
                sq = sq.filter(TTenpo.tenant_id == tenant_id)
            stores = sq.order_by(TTenpo.id).all()
            for store in stores:
                sid = store.id
                s_parents = db.query(func.count(Dog.id)).filter(
                    Dog.store_id == sid, Dog.status == 'active', Dog.dog_type == 'parent').scalar() or 0
                s_puppies = db.query(func.count(Puppy.id)).filter(
                    Puppy.store_id == sid, Puppy.status.in_(['available', 'reserved'])).scalar() or 0
                s_heats = db.query(func.count(Heat.id)).filter(
                    Heat.store_id == sid, Heat.status.in_(['active', 'imminent'])).scalar() or 0
                s_pregnant = db.query(func.count(Mating.id)).filter(
                    Mating.store_id == sid, Mating.status == 'pregnant').scalar() or 0
                s_todos = db.query(func.count(Todo.id)).filter(
                    Todo.store_id == sid, Todo.status == 'pending').scalar() or 0
                s_negotiations = db.query(func.count(Negotiation.id)).filter(
                    Negotiation.store_id == sid,
                    Negotiation.status.in_(['inquiry', 'negotiating', 'reserved'])).scalar() or 0
                store_stats.append({
                    'store': store,
                    'parents': s_parents,
                    'puppies': s_puppies,
                    'heats': s_heats,
                    'pregnant': s_pregnant,
                    'todos': s_todos,
                    'negotiations': s_negotiations,
                })

        # ── 年間売上予実管理（月別成約数・売上合計） ──
        annual_sales = []
        try:
            for m in range(1, 13):
                sold_cnt = _tf(db.query(func.count(Negotiation.id)).filter(
                    Negotiation.status == 'contracted',
                    func.extract('year', Negotiation.updated_at) == today.year,
                    func.extract('month', Negotiation.updated_at) == m,
                ), Negotiation).scalar() or 0
                sold_amt = _tf(db.query(func.coalesce(func.sum(Negotiation.sale_price), 0)).filter(
                    Negotiation.status == 'contracted',
                    func.extract('year', Negotiation.updated_at) == today.year,
                    func.extract('month', Negotiation.updated_at) == m,
                ), Negotiation).scalar() or 0
                annual_sales.append({'month': f'{m}月', 'count': sold_cnt, 'amount': int(sold_amt)})
        except Exception:
            annual_sales = [{'month': f'{m}月', 'count': 0, 'amount': 0} for m in range(1, 13)]

        # ── 遺伝疾患サマリー ──
        from app.models_breeder import GeneticTestResult
        gene_summary = []
        try:
            disease_rows = db.query(
                GeneticTestResult.disease_name,
                GeneticTestResult.result,
                func.count(GeneticTestResult.id)
            ).group_by(GeneticTestResult.disease_name, GeneticTestResult.result).all()
            disease_map = {}
            for row in disease_rows:
                d_name = row[0]
                if d_name not in disease_map:
                    disease_map[d_name] = {'clear': 0, 'carrier': 0, 'affected': 0, 'unknown': 0}
                disease_map[d_name][row[1]] = disease_map[d_name].get(row[1], 0) + row[2]
            for disease, counts in disease_map.items():
                gene_summary.append({'disease': disease, **counts})
        except Exception:
            pass

        # ── 繁忙予測（今後3ヶ月のヒート予測・出産予定） ──
        busy_forecast = []
        try:
            for i in range(3):
                d = today.replace(day=1) + timedelta(days=32 * i)
                d = d.replace(day=1)
                heat_cnt = db.query(func.count(Heat.id)).filter(
                    func.extract('year', Heat.next_predicted_date) == d.year,
                    func.extract('month', Heat.next_predicted_date) == d.month,
                ).scalar() or 0
                busy_forecast.append({'month': d.strftime('%Y/%m'), 'heats': heat_cnt, 'births': 0})
        except Exception:
            busy_forecast = []

        return render_template('breeder/dashboard.html',
            parent_count=parent_count,
            puppy_count=puppy_count,
            todo_pending=todo_pending,
            todo_today=todo_today,
            heat_active=heat_active,
            pregnant=pregnant,
            births_this_month=births_this_month,
            negotiating=negotiating,
            recent_todos=recent_todos,
            birth_stats=birth_stats,
            upcoming_heats=upcoming_heats,
            unregistered_alert_count=unregistered_alert_count,
            unregistered_alert_puppies=unregistered_alert_puppies,
            store_stats=store_stats,
            annual_sales=annual_sales,
            gene_summary=gene_summary,
            busy_forecast=busy_forecast,
        )
    finally:
        db.close()


# ─── 生体管理：親犬 ──────────────────────────────────────────
@bp.route('/dogs')
@require_roles(*BREEDER_ROLES)
def dogs_list():
    from app.models_breeder import Dog
    db = _get_db()
    try:
        dog_type = request.args.get('type', 'parent')
        status = request.args.get('status', '')
        q = request.args.get('q', '')
        tenant_id, store_id = _get_tenant_store()
        query = db.query(Dog).filter(Dog.dog_type == dog_type)
        if tenant_id:
            query = query.filter(Dog.tenant_id == tenant_id)
        if store_id:
            query = query.filter(Dog.store_id == store_id)
        if status:
            query = query.filter(Dog.status == status)
        if q:
            query = query.filter(or_(Dog.name.ilike(f'%{q}%'), Dog.breed.ilike(f'%{q}%')))
        dogs = query.order_by(desc(Dog.created_at)).all()
        return render_template('breeder/dogs_list.html', dogs=dogs, dog_type=dog_type, status=status, q=q)
    finally:
        db.close()

@bp.route('/dogs/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def dog_new():
    from app.models_breeder import Dog
    if request.method == 'POST':
        db = _get_db()
        try:
            tenant_id, store_id = _get_tenant_store()
            dog = Dog(
                tenant_id=tenant_id,
                store_id=store_id,
                name=request.form['name'],
                registration_name=request.form.get('registration_name'),
                breed=request.form['breed'],
                gender=request.form['gender'],
                birth_date=_parse_date(request.form.get('birth_date')),
                color=request.form.get('color'),
                microchip_number=request.form.get('microchip_number'),
                pedigree_number=request.form.get('pedigree_number'),
                dog_type=request.form.get('dog_type', 'parent'),
                status=request.form.get('status', 'active'),
                notes=request.form.get('notes'),
            )
            db.add(dog)
            db.commit()
            flash('犬を登録しました', 'success')
            return redirect(url_for('breeder.dogs_list'))
        except Exception as e:
            db.rollback()
            flash(f'登録エラー: {e}', 'error')
        finally:
            db.close()
    return render_template('breeder/dog_form.html', dog=None)

@bp.route('/dogs/<int:dog_id>/edit', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def dog_edit(dog_id):
    from app.models_breeder import Dog
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        q = db.query(Dog).filter(Dog.id == dog_id)
        if tenant_id:
            q = q.filter(Dog.tenant_id == tenant_id)
        dog = q.first()
        if not dog:
            flash('犬が見つかりません', 'error')
            return redirect(url_for('breeder.dogs_list'))
        if request.method == 'POST':
            dog.name = request.form['name']
            dog.registration_name = request.form.get('registration_name')
            dog.breed = request.form['breed']
            dog.gender = request.form['gender']
            dog.birth_date = _parse_date(request.form.get('birth_date'))
            dog.color = request.form.get('color')
            dog.microchip_number = request.form.get('microchip_number')
            dog.pedigree_number = request.form.get('pedigree_number')
            dog.dog_type = request.form.get('dog_type', 'parent')
            dog.status = request.form.get('status', 'active')
            dog.notes = request.form.get('notes')
            db.commit()
            flash('更新しました', 'success')
            return redirect(url_for('breeder.dog_detail', dog_id=dog_id))
        return render_template('breeder/dog_form.html', dog=dog)
    except Exception as e:
        db.rollback()
        flash(f'更新エラー: {e}', 'error')
        return redirect(url_for('breeder.dogs_list'))
    finally:
        db.close()

@bp.route('/dogs/<int:dog_id>/delete', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def dog_delete(dog_id):
    from app.models_breeder import Dog, PedigreeAncestor
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        q = db.query(Dog).filter(Dog.id == dog_id)
        if tenant_id:
            q = q.filter(Dog.tenant_id == tenant_id)
        dog = q.first()
        if not dog:
            flash('犬が見つかりません', 'error')
            return redirect(url_for('breeder.dogs_list'))
        dog_name = dog.name
        # 祖先情報も削除
        try:
            db.query(PedigreeAncestor).filter(PedigreeAncestor.dog_id == dog_id).delete()
        except Exception:
            pass
        db.delete(dog)
        db.commit()
        flash(f'「{dog_name}」を削除しました', 'success')
        return redirect(url_for('breeder.dogs_list'))
    except Exception as e:
        db.rollback()
        flash(f'削除エラー: {e}', 'error')
        return redirect(url_for('breeder.dog_edit', dog_id=dog_id))
    finally:
        db.close()


@bp.route('/dogs/<int:dog_id>')
@require_roles(*BREEDER_ROLES)
def dog_detail(dog_id):
    from app.models_breeder import Dog, Heat, Mating, WeightRecord, VaccineRecord, HealthCheckRecord, MedicationRecord, MedicalHistory, FoodRecord
    db = _get_db()
    try:
        dog = db.query(Dog).filter(Dog.id == dog_id).first()
        if not dog:
            flash('犬が見つかりません', 'error')
            return redirect(url_for('breeder.dogs_list'))
        heats = db.query(Heat).filter(Heat.dog_id == dog_id).order_by(desc(Heat.created_at)).limit(5).all()
        weights = db.query(WeightRecord).filter(WeightRecord.dog_id == dog_id).order_by(desc(WeightRecord.recorded_at)).limit(10).all()
        vaccines = db.query(VaccineRecord).filter(VaccineRecord.dog_id == dog_id).order_by(desc(VaccineRecord.administered_at)).all()
        # 家系図データ構築（3世代）
        def build_tree(did, depth=3):
            if did is None or depth == 0:
                return None
            d = db.query(Dog).filter(Dog.id == did).first()
            if not d:
                return None
            return {
                'id': d.id,
                'name': d.name,
                'breed': d.breed or '',
                'gender': d.gender or '',
                'reg_no': d.registration_name or d.pedigree_number or '',
                'sire': build_tree(d.father_id, depth - 1),
                'dam':  build_tree(d.mother_id, depth - 1),
            }
        tree = build_tree(dog_id)
        try:
            coi = _calc_coi(dog_id, db)
        except Exception:
            coi = 0.0
        return render_template('breeder/dog_detail.html', dog=dog, heats=heats, weights=weights, vaccines=vaccines, tree=tree, coi=coi)
    finally:
        db.close()


# ─── 生体管理：子犬 ──────────────────────────────────────────
@bp.route('/puppies')
@require_roles(*BREEDER_ROLES)
def puppies_list():
    from app.models_breeder import Puppy, Dog
    db = _get_db()
    try:
        status = request.args.get('status', '')
        q = request.args.get('q', '')
        tenant_id, store_id = _get_tenant_store()
        query = db.query(Puppy)
        if tenant_id:
            query = query.filter(Puppy.tenant_id == tenant_id)
        if store_id:
            query = query.filter(Puppy.store_id == store_id)
        if status:
            query = query.filter(Puppy.status == status)
        if q:
            query = query.filter(or_(Puppy.name.ilike(f'%{q}%'), Puppy.breed.ilike(f'%{q}%')))
        puppies = query.order_by(desc(Puppy.created_at)).all()
        return render_template('breeder/puppies_list.html', puppies=puppies, status=status, q=q)
    finally:
        db.close()

@bp.route('/puppies/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def puppy_new():
    from app.models_breeder import Puppy, Dog, Birth
    db = _get_db()
    try:
        if request.method == 'POST':
            tenant_id, store_id = _get_tenant_store()
            puppy = Puppy(
                tenant_id=tenant_id,
                store_id=store_id,
                name=request.form.get('name'),
                breed=request.form['breed'],
                gender=request.form['gender'],
                birth_date=_parse_date(request.form.get('birth_date')),
                color=request.form.get('color'),
                microchip_number=request.form.get('microchip_number'),
                birth_id=_int_or_none(request.form.get('birth_id')),
                mother_id=_int_or_none(request.form.get('mother_id')),
                father_id=_int_or_none(request.form.get('father_id')),
                status=request.form.get('status', 'available'),
                price=_decimal_or_none(request.form.get('price')),
                notes=request.form.get('notes'),
            )
            db.add(puppy)
            db.commit()
            flash('子犬を登録しました', 'success')
            return redirect(url_for('breeder.puppies_list'))
        dogs = db.query(Dog).filter(Dog.dog_type == 'parent', Dog.status == 'active').all()
        births = db.query(Birth).order_by(desc(Birth.birth_date)).limit(20).all()
        return render_template('breeder/puppy_form.html', puppy=None, dogs=dogs, births=births)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return render_template('breeder/puppy_form.html', puppy=None, dogs=[], births=[])
    finally:
        db.close()

@bp.route('/puppies/<int:puppy_id>/edit', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def puppy_edit(puppy_id):
    from app.models_breeder import Puppy, Dog, Birth
    db = _get_db()
    try:
        puppy = db.query(Puppy).filter(Puppy.id == puppy_id).first()
        if not puppy:
            flash('子犬が見つかりません', 'error')
            return redirect(url_for('breeder.puppies_list'))
        if request.method == 'POST':
            puppy.name = request.form.get('name')
            puppy.breed = request.form['breed']
            puppy.gender = request.form['gender']
            puppy.birth_date = _parse_date(request.form.get('birth_date'))
            puppy.color = request.form.get('color')
            puppy.microchip_number = request.form.get('microchip_number')
            puppy.mother_id = _int_or_none(request.form.get('mother_id'))
            puppy.father_id = _int_or_none(request.form.get('father_id'))
            puppy.status = request.form.get('status', 'available')
            puppy.price = _decimal_or_none(request.form.get('price'))
            puppy.notes = request.form.get('notes')
            db.commit()
            flash('更新しました', 'success')
            return redirect(url_for('breeder.puppies_list'))
        dogs = db.query(Dog).filter(Dog.dog_type == 'parent', Dog.status == 'active').all()
        births = db.query(Birth).order_by(desc(Birth.birth_date)).limit(20).all()
        return render_template('breeder/puppy_form.html', puppy=puppy, dogs=dogs, births=births)
    except Exception as e:
        db.rollback()
        flash(f'更新エラー: {e}', 'error')
        return redirect(url_for('breeder.puppies_list'))
    finally:
        db.close()


# ─── 繁殖管理：ヒート ────────────────────────────────────────
@bp.route('/heats')
@require_roles(*BREEDER_ROLES)
def heats_list():
    from app.models_breeder import Heat, Dog
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        q = db.query(Heat, Dog).join(Dog, Heat.dog_id == Dog.id)
        if tenant_id:
            q = q.filter(Heat.tenant_id == tenant_id)
        if store_id:
            q = q.filter(Heat.store_id == store_id)
        heats = q.order_by(desc(Heat.created_at)).all()
        return render_template('breeder/heats_list.html', heats=heats)
    finally:
        db.close()

@bp.route('/heats/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def heat_new():
    from app.models_breeder import Heat, Dog, AppSetting
    from datetime import timedelta
    db = _get_db()
    try:
        if request.method == 'POST':
            tenant_id, store_id = _get_tenant_store()
            start_date = _parse_date(request.form.get('start_date'))
            # 次回予測日: フォームに入力があればそれを使い、なければ開始日 + ヒートサイクル日数で自動計算
            next_predicted_date = _parse_date(request.form.get('next_predicted_date'))
            if not next_predicted_date and start_date:
                # AppSettingからデフォルトヒートサイクル日数を取得（デフォルト180日）
                cycle_days = 180
                try:
                    setting_q = db.query(AppSetting)
                    if tenant_id:
                        setting_q = setting_q.filter(AppSetting.tenant_id == tenant_id)
                    setting = setting_q.first()
                    if setting and getattr(setting, 'default_heat_cycle_days', None):
                        cycle_days = int(setting.default_heat_cycle_days)
                except Exception:
                    pass
                next_predicted_date = start_date + timedelta(days=cycle_days)
            heat = Heat(
                tenant_id=tenant_id,
                store_id=store_id,
                dog_id=int(request.form['dog_id']),
                start_date=start_date,
                last_confirmed_date=_parse_date(request.form.get('last_confirmed_date')),
                next_predicted_date=next_predicted_date,
                status=request.form.get('status', 'active'),
                notes=request.form.get('notes'),
            )
            db.add(heat)
            db.commit()
            flash('ヒートを登録しました（次回予測日: {}）'.format(
                next_predicted_date.strftime('%Y/%m/%d') if next_predicted_date else '未設定'
            ), 'success')
            return redirect(url_for('breeder.heats_list'))
        dogs = db.query(Dog).filter(Dog.dog_type == 'parent', Dog.gender == 'female', Dog.status == 'active').all()
        return render_template('breeder/heat_form.html', heat=None, dogs=dogs)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.heats_list'))
    finally:
        db.close()


# ─── 繁殖管理：交配・出産 ────────────────────────────────────
@bp.route('/matings')
@require_roles(*BREEDER_ROLES)
def matings_list():
    from app.models_breeder import Mating, Dog
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        mq = db.query(Mating)
        if tenant_id:
            mq = mq.filter(Mating.tenant_id == tenant_id)
        if store_id:
            mq = mq.filter(Mating.store_id == store_id)
        matings = mq.order_by(desc(Mating.mating_date)).all()
        dq = db.query(Dog)
        if tenant_id:
            dq = dq.filter(Dog.tenant_id == tenant_id)
        if store_id:
            dq = dq.filter(Dog.store_id == store_id)
        dogs = {d.id: d for d in dq.all()}
        return render_template('breeder/matings_list.html', matings=matings, dogs=dogs)
    finally:
        db.close()

@bp.route('/matings/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def mating_new():
    from app.models_breeder import Mating, Dog, Heat
    db = _get_db()
    try:
        if request.method == 'POST':
            mating_date = _parse_date(request.form.get('mating_date'))
            expected = mating_date + timedelta(days=63) if mating_date else None
            tenant_id, store_id = _get_tenant_store()
            mating = Mating(
                tenant_id=tenant_id,
                store_id=store_id,
                mother_id=int(request.form['mother_id']),
                father_id=int(request.form['father_id']),
                heat_id=_int_or_none(request.form.get('heat_id')),
                mating_date=mating_date,
                method=request.form.get('method', 'natural'),
                expected_birth_date=expected,
                status='mated',
                notes=request.form.get('notes'),
            )
            db.add(mating)
            db.commit()
            flash('交配を登録しました', 'success')
            return redirect(url_for('breeder.matings_list'))
        mothers = db.query(Dog).filter(Dog.gender == 'female', Dog.status == 'active').all()
        fathers = db.query(Dog).filter(Dog.gender == 'male', Dog.status == 'active').all()
        return render_template('breeder/mating_form.html', mating=None, mothers=mothers, fathers=fathers)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.matings_list'))
    finally:
        db.close()

@bp.route('/births')
@require_roles(*BREEDER_ROLES)
def births_list():
    from app.models_breeder import Birth, Dog
    db = _get_db()
    try:
        births = db.query(Birth).order_by(desc(Birth.birth_date)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        return render_template('breeder/births_list.html', births=births, dogs=dogs)
    finally:
        db.close()

@bp.route('/births/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def birth_new():
    from app.models_breeder import Birth, Dog, Mating
    db = _get_db()
    try:
        if request.method == 'POST':
            birth = Birth(
                mating_id=_int_or_none(request.form.get('mating_id')),
                mother_id=int(request.form['mother_id']),
                father_id=_int_or_none(request.form.get('father_id')),
                birth_date=_parse_date(request.form['birth_date']),
                total_count=int(request.form.get('total_count', 0)),
                alive_count=int(request.form.get('alive_count', 0)),
                male_count=int(request.form.get('male_count', 0)),
                female_count=int(request.form.get('female_count', 0)),
                notes=request.form.get('notes'),
            )
            db.add(birth)
            db.commit()
            flash('出産を登録しました', 'success')
            return redirect(url_for('breeder.births_list'))
        dogs = db.query(Dog).filter(Dog.status == 'active').all()
        matings = db.query(Mating).filter(Mating.status.in_(['mated', 'pregnant'])).order_by(desc(Mating.mating_date)).all()
        return render_template('breeder/birth_form.html', birth=None, dogs=dogs, matings=matings)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.births_list'))
    finally:
        db.close()


# ─── 販売管理 ────────────────────────────────────────────────
@bp.route('/contacts')
@require_roles(*BREEDER_ROLES)
def contacts_list():
    from app.models_breeder import Contact
    db = _get_db()
    try:
        q = request.args.get('q', '')
        query = db.query(Contact)
        if q:
            query = query.filter(or_(Contact.name.ilike(f'%{q}%'), Contact.email.ilike(f'%{q}%'), Contact.phone.ilike(f'%{q}%')))
        contacts = query.order_by(desc(Contact.created_at)).all()
        return render_template('breeder/contacts_list.html', contacts=contacts, q=q)
    finally:
        db.close()

@bp.route('/contacts/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def contact_new():
    from app.models_breeder import Contact
    if request.method == 'POST':
        db = _get_db()
        try:
            contact = Contact(
                name=request.form['name'],
                email=request.form.get('email'),
                phone=request.form.get('phone'),
                address=request.form.get('address'),
                notes=request.form.get('notes'),
            )
            db.add(contact)
            db.commit()
            flash('コンタクトを登録しました', 'success')
            return redirect(url_for('breeder.contacts_list'))
        except Exception as e:
            db.rollback()
            flash(f'登録エラー: {e}', 'error')
        finally:
            db.close()
    return render_template('breeder/contact_form.html', contact=None)

@bp.route('/negotiations')
@require_roles(*BREEDER_ROLES)
def negotiations_list():
    from app.models_breeder import Negotiation, Contact, Puppy
    db = _get_db()
    try:
        status = request.args.get('status', '')
        query = db.query(Negotiation)
        if status:
            query = query.filter(Negotiation.status == status)
        negotiations = query.order_by(desc(Negotiation.created_at)).all()
        contacts = {c.id: c for c in db.query(Contact).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/negotiations_list.html', negotiations=negotiations, contacts=contacts, puppies=puppies, status=status)
    finally:
        db.close()

@bp.route('/negotiations/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def negotiation_new():
    from app.models_breeder import Negotiation, Contact, Puppy
    db = _get_db()
    try:
        if request.method == 'POST':
            neg = Negotiation(
                contact_id=_int_or_none(request.form.get('contact_id')),
                puppy_id=_int_or_none(request.form.get('puppy_id')),
                status=request.form.get('status', 'inquiry'),
                price=_decimal_or_none(request.form.get('price')),
                notes=request.form.get('notes'),
            )
            db.add(neg)
            db.commit()
            flash('商談を登録しました', 'success')
            return redirect(url_for('breeder.negotiations_list'))
        contacts = db.query(Contact).order_by(Contact.name).all()
        puppies = db.query(Puppy).filter(Puppy.status.in_(['available', 'reserved'])).all()
        return render_template('breeder/negotiation_form.html', negotiation=None, contacts=contacts, puppies=puppies)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.negotiations_list'))
    finally:
        db.close()

@bp.route('/life-logs')
@require_roles(*BREEDER_ROLES)
def life_logs_list():
    from app.models_breeder import LifeLog, Dog, Puppy, Contact
    db = _get_db()
    try:
        logs = db.query(LifeLog).order_by(desc(LifeLog.logged_at)).limit(100).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        contacts = {c.id: c for c in db.query(Contact).all()}
        return render_template('breeder/life_logs_list.html', logs=logs, dogs=dogs, puppies=puppies, contacts=contacts)
    finally:
        db.close()


# ─── 申請管理 ────────────────────────────────────────────────
@bp.route('/applications/pedigree')
@require_roles(*BREEDER_ROLES)
def pedigree_applications():
    from app.models_breeder import PedigreeApplication, Puppy, Dog
    db = _get_db()
    try:
        apps = db.query(PedigreeApplication).order_by(desc(PedigreeApplication.created_at)).all()
        puppies = {p.id: p for p in db.query(Puppy).all()}
        dogs = {d.id: d for d in db.query(Dog).all()}
        return render_template('breeder/pedigree_applications.html', apps=apps, puppies=puppies, dogs=dogs)
    finally:
        db.close()

@bp.route('/applications/pedigree/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def pedigree_application_new():
    from app.models_breeder import PedigreeApplication, Puppy, Dog
    db = _get_db()
    try:
        if request.method == 'POST':
            app_obj = PedigreeApplication(
                puppy_id=_int_or_none(request.form.get('puppy_id')),
                dog_id=_int_or_none(request.form.get('dog_id')),
                application_date=_parse_date(request.form.get('application_date')),
                status=request.form.get('status', 'pending'),
                pedigree_number=request.form.get('pedigree_number'),
                notes=request.form.get('notes'),
            )
            db.add(app_obj)
            db.commit()
            flash('血統書申請を登録しました', 'success')
            return redirect(url_for('breeder.pedigree_applications'))
        puppies = db.query(Puppy).all()
        dogs = db.query(Dog).all()
        return render_template('breeder/pedigree_application_form.html', app=None, puppies=puppies, dogs=dogs)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.pedigree_applications'))
    finally:
        db.close()

@bp.route('/applications/chip')
@require_roles(*BREEDER_ROLES)
def chip_applications():
    from app.models_breeder import ChipApplication, Puppy, Dog
    db = _get_db()
    try:
        apps = db.query(ChipApplication).order_by(desc(ChipApplication.created_at)).all()
        puppies = {p.id: p for p in db.query(Puppy).all()}
        dogs = {d.id: d for d in db.query(Dog).all()}
        return render_template('breeder/chip_applications.html', apps=apps, puppies=puppies, dogs=dogs)
    finally:
        db.close()

@bp.route('/applications/chip/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def chip_application_new():
    from app.models_breeder import ChipApplication, Puppy, Dog
    db = _get_db()
    try:
        if request.method == 'POST':
            app_obj = ChipApplication(
                puppy_id=_int_or_none(request.form.get('puppy_id')),
                dog_id=_int_or_none(request.form.get('dog_id')),
                application_date=_parse_date(request.form.get('application_date')),
                status=request.form.get('status', 'pending'),
                chip_number=request.form.get('chip_number'),
                notes=request.form.get('notes'),
            )
            db.add(app_obj)
            db.commit()
            flash('チップ申請を登録しました', 'success')
            return redirect(url_for('breeder.chip_applications'))
        puppies = db.query(Puppy).all()
        dogs = db.query(Dog).all()
        return render_template('breeder/chip_application_form.html', app=None, puppies=puppies, dogs=dogs)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.chip_applications'))
    finally:
        db.close()

@bp.route('/applications/pedigree/<int:app_id>/edit', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def pedigree_application_edit(app_id):
    from app.models_breeder import PedigreeApplication, Puppy, Dog
    db = _get_db()
    try:
        app_obj = db.query(PedigreeApplication).get(app_id)
        if not app_obj:
            flash('血統書申請が見つかりません', 'error')
            return redirect(url_for('breeder.pedigree_applications'))
        if request.method == 'POST':
            app_obj.puppy_id = _int_or_none(request.form.get('puppy_id'))
            app_obj.dog_id = _int_or_none(request.form.get('dog_id'))
            app_obj.application_date = _parse_date(request.form.get('application_date'))
            app_obj.status = request.form.get('status', app_obj.status)
            app_obj.pedigree_number = request.form.get('pedigree_number')
            app_obj.notes = request.form.get('notes')
            db.commit()
            flash('血統書申請を更新しました', 'success')
            return redirect(url_for('breeder.pedigree_applications'))
        puppies = db.query(Puppy).all()
        dogs = db.query(Dog).all()
        return render_template('breeder/pedigree_application_form.html', app=app_obj, puppies=puppies, dogs=dogs)
    except Exception as e:
        db.rollback()
        flash(f'更新エラー: {e}', 'error')
        return redirect(url_for('breeder.pedigree_applications'))
    finally:
        db.close()

@bp.route('/applications/pedigree/<int:app_id>/delete', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def pedigree_application_delete(app_id):
    from app.models_breeder import PedigreeApplication
    db = _get_db()
    try:
        app_obj = db.query(PedigreeApplication).get(app_id)
        if app_obj:
            db.delete(app_obj)
            db.commit()
            flash('血統書申請を削除しました', 'success')
        return redirect(url_for('breeder.pedigree_applications'))
    except Exception as e:
        db.rollback()
        flash(f'削除エラー: {e}', 'error')
        return redirect(url_for('breeder.pedigree_applications'))
    finally:
        db.close()

@bp.route('/applications/chip/<int:app_id>/edit', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def chip_application_edit(app_id):
    from app.models_breeder import ChipApplication, Puppy, Dog
    db = _get_db()
    try:
        app_obj = db.query(ChipApplication).get(app_id)
        if not app_obj:
            flash('チップ申請が見つかりません', 'error')
            return redirect(url_for('breeder.chip_applications'))
        if request.method == 'POST':
            app_obj.puppy_id = _int_or_none(request.form.get('puppy_id'))
            app_obj.dog_id = _int_or_none(request.form.get('dog_id'))
            app_obj.application_date = _parse_date(request.form.get('application_date'))
            app_obj.status = request.form.get('status', app_obj.status)
            app_obj.chip_number = request.form.get('chip_number')
            app_obj.notes = request.form.get('notes')
            db.commit()
            flash('チップ申請を更新しました', 'success')
            return redirect(url_for('breeder.chip_applications'))
        puppies = db.query(Puppy).all()
        dogs = db.query(Dog).all()
        return render_template('breeder/chip_application_form.html', app=app_obj, puppies=puppies, dogs=dogs)
    except Exception as e:
        db.rollback()
        flash(f'更新エラー: {e}', 'error')
        return redirect(url_for('breeder.chip_applications'))
    finally:
        db.close()

@bp.route('/applications/chip/<int:app_id>/delete', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def chip_application_delete(app_id):
    from app.models_breeder import ChipApplication
    db = _get_db()
    try:
        app_obj = db.query(ChipApplication).get(app_id)
        if app_obj:
            db.delete(app_obj)
            db.commit()
            flash('チップ申請を削除しました', 'success')
        return redirect(url_for('breeder.chip_applications'))
    except Exception as e:
        db.rollback()
        flash(f'削除エラー: {e}', 'error')
        return redirect(url_for('breeder.chip_applications'))
    finally:
        db.close()

@bp.route('/applications/auto-generate', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def auto_generate_applications():
    """出産データから血統書申請・チップ申請を自動生成する"""
    from app.models_breeder import Birth, Puppy, PedigreeApplication, ChipApplication
    db = _get_db()
    try:
        today = date.today()
        cutoff = today - timedelta(days=70)
        births = db.query(Birth).filter(Birth.birth_date >= cutoff).all()
        pedigree_created = 0
        chip_created = 0
        for birth in births:
            puppies = db.query(Puppy).filter(Puppy.birth_id == birth.id).all()
            for puppy in puppies:
                existing_p = db.query(PedigreeApplication).filter(
                    PedigreeApplication.puppy_id == puppy.id
                ).first()
                if not existing_p:
                    db.add(PedigreeApplication(
                        puppy_id=puppy.id,
                        application_date=today,
                        status='pending',
                        notes=f'出産日{birth.birth_date}から自動生成',
                    ))
                    pedigree_created += 1
                if puppy.microchip_number:
                    existing_c = db.query(ChipApplication).filter(
                        ChipApplication.puppy_id == puppy.id
                    ).first()
                    if not existing_c:
                        db.add(ChipApplication(
                            puppy_id=puppy.id,
                            application_date=today,
                            status='pending',
                            chip_number=puppy.microchip_number,
                            notes=f'出産日{birth.birth_date}から自動生成',
                        ))
                        chip_created += 1
        db.commit()
        flash(f'自動生成完了：血統書申請 {pedigree_created}件、チップ申請 {chip_created}件を生成しました', 'success')
        return redirect(url_for('breeder.pedigree_applications'))
    except Exception as e:
        db.rollback()
        flash(f'自動生成エラー: {e}', 'error')
        return redirect(url_for('breeder.pedigree_applications'))
    finally:
        db.close()

@bp.route('/applications/scans')
@require_roles(*BREEDER_ROLES)
def document_scans():
    from app.models_breeder import DocumentScan, Dog, Puppy
    db = _get_db()
    try:
        scans = db.query(DocumentScan).order_by(desc(DocumentScan.created_at)).limit(50).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        # result_jsonを辞書に変換してテンプレートに渡す
        scan_results = {}
        for scan in scans:
            if scan.result_json:
                try:
                    scan_results[scan.id] = json.loads(scan.result_json)
                except Exception:
                    scan_results[scan.id] = {}
            else:
                scan_results[scan.id] = {}
            # 画像URLをscan_resultsに追加
            scan_results[scan.id]['_image_url'] = url_for('breeder.document_scan_image', scan_id=scan.id)
        return render_template('breeder/document_scans.html', scans=scans, dogs=dogs, puppies=puppies, scan_results=scan_results)
    finally:
        db.close()

@bp.route('/applications/scans/upload', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def document_scan_upload():
    """血統書PDF/画像をアップロードしてOCRで情報を抽出する"""
    import os
    from app.models_breeder import DocumentScan
    db = _get_db()
    try:
        f = request.files.get('file')
        if not f or not f.filename:
            flash('ファイルを選択してください', 'error')
            return redirect(url_for('breeder.document_scans'))
        scan_type = request.form.get('scan_type', 'pedigree')
        upload_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'uploads', 'scans')
        os.makedirs(upload_dir, exist_ok=True)
        filename = f'{date.today().strftime("%Y%m%d")}_{f.filename}'
        filepath = os.path.join(upload_dir, filename)
        f.save(filepath)
        result_json = None
        error_msg = None
        status_val = 'success'
        try:
            from app.utils.ocr import extract_pedigree_info
            result = extract_pedigree_info(filepath, scan_type)
            result_json = json.dumps(result, ensure_ascii=False)
        except Exception as ocr_err:
            error_msg = str(ocr_err)
            status_val = 'failed'
        scan = DocumentScan(
            filename=f.filename,
            scan_type=scan_type,
            status=status_val,
            result_json=result_json,
            error_message=error_msg,
            file_path=filepath,
        )
        db.add(scan)
        db.commit()
        if status_val == 'success' and result_json:
            flash('OCR取り込み完了！データを確認してください', 'success')
        else:
            flash(f'OCR処理中にエラーが発生しました: {error_msg}', 'warning')
        return redirect(url_for('breeder.document_scans'))
    except Exception as e:
        db.rollback()
        flash(f'アップロードエラー: {e}', 'error')
        return redirect(url_for('breeder.document_scans'))
    finally:
        db.close()

@bp.route('/applications/scans/<int:scan_id>/apply', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def document_scan_apply(scan_id):
    """
    OCR結果を元に犬の情報を更新する。
    血統書 / チップ / 遺伝疾患検査 / 股関節評価 の4種に対応。
    """
    from app.models_breeder import DocumentScan, Dog, Puppy, GeneticTestResult
    db = _get_db()
    try:
        scan = db.query(DocumentScan).get(scan_id)
        if not scan or not scan.result_json:
            flash('スキャンデータが見つかりません', 'error')
            return redirect(url_for('breeder.document_scans'))

        result = json.loads(scan.result_json)
        # genderを小文字に正規化（MALE→male, FEMALE→female, DISSE MALE→male等）
        if result.get('gender'):
            _g = result['gender'].lower().strip()
            if 'female' in _g:
                result['gender'] = 'female'
            elif 'male' in _g:
                result['gender'] = 'male'
            else:
                result['gender'] = _g
        target_id   = _int_or_none(request.form.get('target_id'))
        target_type = request.form.get('target_type', 'dog')
        scan_type   = scan.scan_type or 'pedigree'

        if target_type == 'dog' and target_id:
            dog = db.query(Dog).get(target_id)
            if dog:
                if scan_type == 'pedigree':
                    if result.get('pedigree_number'):
                        dog.pedigree_number = result['pedigree_number']
                    if result.get('microchip_number'):
                        dog.microchip_number = result['microchip_number']
                    if result.get('registration_name'):
                        dog.registration_name = result['registration_name']
                    if result.get('birth_date') and not dog.birth_date:
                        try:
                            from datetime import date as _date
                            y, mo, d = result['birth_date'].split('-')
                            dog.birth_date = _date(int(y), int(mo), int(d))
                        except Exception:
                            pass
                    if result.get('gender') and not dog.gender:
                        dog.gender = result['gender']
                elif scan_type == 'chip':
                    if result.get('microchip_number'):
                        dog.microchip_number = result['microchip_number']
                elif scan_type == 'genetic':
                    # 遺伝疾患検査結果を GeneticTestResult テーブルに登録（重複時は上書き）
                    for item in result.get('results', []):
                        disease = item.get('disease_name')
                        res_val = item.get('result')
                        if not disease or not res_val:
                            continue
                        existing = db.query(GeneticTestResult).filter(
                            GeneticTestResult.dog_id == dog.id,
                            GeneticTestResult.disease_name == disease
                        ).first()
                        if existing:
                            existing.result = res_val
                            if result.get('test_date'):
                                existing.tested_at = result['test_date']
                            if result.get('lab_name'):
                                existing.lab_name = result['lab_name']
                        else:
                            db.add(GeneticTestResult(
                                dog_id=dog.id,
                                disease_name=disease,
                                result=res_val,
                                tested_at=result.get('test_date'),
                                lab_name=result.get('lab_name'),
                            ))
                elif scan_type == 'hip':
                    # 股関節評価結果を notes に追記
                    hip_note = (
                        f"股関節評価: "
                        f"左={result.get('left_score','不明')} "
                        f"右={result.get('right_score','不明')} "
                        f"総合={result.get('overall_grade','不明')} "
                        f"評価機関={result.get('evaluator','不明')} "
                        f"評価日={result.get('evaluation_date','不明')}"
                    )
                    dog.notes = ((dog.notes or '') + '\n' + hip_note).strip()
                scan.dog_id = dog.id
                db.commit()
                flash(f'「{dog.name}」にデータを適用しました', 'success')

        elif target_type == 'puppy' and target_id:
            puppy = db.query(Puppy).get(target_id)
            if puppy:
                if result.get('pedigree_number'):
                    puppy.pedigree_number = result['pedigree_number']
                if result.get('microchip_number'):
                    puppy.microchip_number = result['microchip_number']
                scan.puppy_id = puppy.id
                db.commit()
                flash(f'子犬「{puppy.name or puppy.id}」にデータを適用しました', 'success')
        elif target_type == 'new_dog' and scan_type == 'pedigree':
            # 血統書スキャンから新規親犬を自動登録
            tenant_id, store_id = _get_tenant_store()
            new_name = result.get('registration_name') or '血統書取込犬'
            new_dog = Dog(
                tenant_id=tenant_id,
                store_id=store_id,
                name=new_name,
                dog_type='parent',
                breed=result.get('breed') or None,
                gender=result.get('gender') or None,
                pedigree_number=result.get('pedigree_number') or None,
                microchip_number=result.get('microchip_number') or None,
                registration_name=result.get('registration_name') or None,
                status='active',
            )
            if result.get('birth_date'):
                try:
                    from datetime import date as _date
                    y, mo, d = result['birth_date'].split('-')
                    new_dog.birth_date = _date(int(y), int(mo), int(d))
                except Exception:
                    pass
            db.add(new_dog)
            db.flush()  # IDを確定
            # 父・母（sire/dam）を外部犬として登録し、father_id/mother_idをリンク
            try:
                ancestors = result.get('ancestors', []) or []
                def _get_or_create_ancestor_dog(anc_name, anc_reg, anc_breed, anc_color, anc_gender, t_id, s_id):
                    """血統書番号またはname一致で既存犬を探し、なければ外部犬として作成"""
                    existing = None
                    if anc_reg:
                        existing = db.query(Dog).filter(
                            Dog.pedigree_number == anc_reg,
                            Dog.tenant_id == t_id
                        ).first()
                    if not existing and anc_name:
                        existing = db.query(Dog).filter(
                            Dog.name == anc_name,
                            Dog.tenant_id == t_id
                        ).first()
                    if not existing:
                        existing = Dog(
                            tenant_id=t_id,
                            store_id=s_id,
                            name=anc_name,
                            dog_type='external',
                            breed=anc_breed or None,
                            gender=anc_gender or None,
                            pedigree_number=anc_reg or None,
                            registration_name=anc_name,
                            color=anc_color or None,
                            status='active',
                        )
                        db.add(existing)
                        db.flush()
                    return existing
                # positionをキーにした辞書を作成
                anc_map = {}
                for anc in ancestors:
                    pos = anc.get('position', '')
                    if pos and anc.get('name'):
                        anc_map[pos] = anc

                # 父（sire）
                sire_dog = None
                if 'sire' in anc_map:
                    a = anc_map['sire']
                    sire_dog = _get_or_create_ancestor_dog(
                        a['name'], a.get('registration_number'),
                        a.get('breed'), a.get('color'), 'male',
                        tenant_id, store_id
                    )
                    new_dog.father_id = sire_dog.id

                # 母（dam）
                dam_dog = None
                if 'dam' in anc_map:
                    a = anc_map['dam']
                    dam_dog = _get_or_create_ancestor_dog(
                        a['name'], a.get('registration_number'),
                        a.get('breed'), a.get('color'), 'female',
                        tenant_id, store_id
                    )
                    new_dog.mother_id = dam_dog.id

                # 父方祖父（sire_sire）
                if 'sire_sire' in anc_map and sire_dog:
                    a = anc_map['sire_sire']
                    g = _get_or_create_ancestor_dog(
                        a['name'], a.get('registration_number'),
                        a.get('breed'), a.get('color'), 'male',
                        tenant_id, store_id
                    )
                    sire_dog.father_id = g.id

                # 父方祖母（sire_dam）
                if 'sire_dam' in anc_map and sire_dog:
                    a = anc_map['sire_dam']
                    g = _get_or_create_ancestor_dog(
                        a['name'], a.get('registration_number'),
                        a.get('breed'), a.get('color'), 'female',
                        tenant_id, store_id
                    )
                    sire_dog.mother_id = g.id

                # 母方祖父（dam_sire）
                if 'dam_sire' in anc_map and dam_dog:
                    a = anc_map['dam_sire']
                    g = _get_or_create_ancestor_dog(
                        a['name'], a.get('registration_number'),
                        a.get('breed'), a.get('color'), 'male',
                        tenant_id, store_id
                    )
                    dam_dog.father_id = g.id

                # 母方祖母（dam_dam）
                if 'dam_dam' in anc_map and dam_dog:
                    a = anc_map['dam_dam']
                    g = _get_or_create_ancestor_dog(
                        a['name'], a.get('registration_number'),
                        a.get('breed'), a.get('color'), 'female',
                        tenant_id, store_id
                    )
                    dam_dog.mother_id = g.id
            except Exception as parent_e:
                import logging
                logging.getLogger(__name__).warning(f'父母リンクエラー: {parent_e}')
            # 4代分の祖先情報を保存
            try:
                from app.models_breeder import PedigreeAncestor
                ancestors = result.get('ancestors', []) or []
                for anc in ancestors:
                    if not anc.get('name'):
                        continue
                    pa = PedigreeAncestor(
                        dog_id=new_dog.id,
                        generation=anc.get('generation', 1),
                        position=anc.get('position', ''),
                        name=anc.get('name'),
                        registration_number=anc.get('registration_number'),
                        breed=anc.get('breed'),
                        color=anc.get('color'),
                    )
                    db.add(pa)
            except Exception as anc_e:
                import logging
                logging.getLogger(__name__).warning(f'祖先情報保存エラー: {anc_e}')
            scan.dog_id = new_dog.id
            db.commit()
            flash(f'新規親犬「{new_name}」を血統書から登録しました（父・母・4代分の祖先情報も取込み）', 'success')
        return redirect(url_for('breeder.document_scans'))
    except Exception as e:
        db.rollback()
        flash(f'適用エラー: {e}', 'error')
        return redirect(url_for('breeder.document_scans'))
    finally:
        db.close()


@bp.route('/applications/scans/<int:scan_id>/delete', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def document_scan_delete(scan_id):
    """書類スキャン履歴を削除する"""
    from app.models_breeder import DocumentScan
    db = _get_db()
    try:
        scan = db.query(DocumentScan).get(scan_id)
        if not scan:
            flash('スキャン履歴が見つかりません', 'error')
            return redirect(url_for('breeder.document_scans'))
        db.delete(scan)
        db.commit()
        flash('スキャン履歴を削除しました', 'success')
        return redirect(url_for('breeder.document_scans'))
    except Exception as e:
        db.rollback()
        flash(f'削除エラー: {e}', 'error')
        return redirect(url_for('breeder.document_scans'))
    finally:
        db.close()
@bp.route('/applications/scans/<int:scan_id>/image')
@require_roles(*BREEDER_ROLES)
def document_scan_image(scan_id):
    """スキャン画像を配信する"""
    import os
    from flask import send_file, abort
    from app.models_breeder import DocumentScan
    db = _get_db()
    try:
        scan = db.query(DocumentScan).get(scan_id)
        if not scan or not scan.file_path:
            abort(404)
        if not os.path.exists(scan.file_path):
            abort(404)
        return send_file(scan.file_path)
    finally:
        db.close()

# ─── 健康管理 ────────────────────────────────────────────────
@bp.route('/health/weight')
@require_roles(*BREEDER_ROLES)
def weight_records():
    from app.models_breeder import WeightRecord, Dog, Puppy
    db = _get_db()
    try:
        records = db.query(WeightRecord).order_by(desc(WeightRecord.recorded_at)).limit(100).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/weight_records.html', records=records, dogs=dogs, puppies=puppies)
    finally:
        db.close()

@bp.route('/health/weight/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def weight_record_new():
    from app.models_breeder import WeightRecord, Dog, Puppy
    db = _get_db()
    try:
        if request.method == 'POST':
            rec = WeightRecord(
                dog_id=_int_or_none(request.form.get('dog_id')),
                puppy_id=_int_or_none(request.form.get('puppy_id')),
                weight=float(request.form['weight']),
                recorded_at=_parse_date(request.form['recorded_at']),
                notes=request.form.get('notes'),
            )
            db.add(rec)
            db.commit()
            flash('体重を記録しました', 'success')
            return redirect(url_for('breeder.weight_records'))
        dogs = db.query(Dog).filter(Dog.status == 'active').all()
        puppies = db.query(Puppy).filter(Puppy.status.in_(['available', 'reserved'])).all()
        return render_template('breeder/weight_record_form.html', dogs=dogs, puppies=puppies)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.weight_records'))
    finally:
        db.close()

@bp.route('/health/vaccines')
@require_roles(*BREEDER_ROLES)
def vaccine_records():
    from app.models_breeder import VaccineRecord, Dog, Puppy
    db = _get_db()
    try:
        records = db.query(VaccineRecord).order_by(desc(VaccineRecord.administered_at)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/vaccine_records.html', records=records, dogs=dogs, puppies=puppies)
    finally:
        db.close()

@bp.route('/health/vaccines/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def vaccine_record_new():
    from app.models_breeder import VaccineRecord, Dog, Puppy
    db = _get_db()
    try:
        if request.method == 'POST':
            rec = VaccineRecord(
                dog_id=_int_or_none(request.form.get('dog_id')),
                puppy_id=_int_or_none(request.form.get('puppy_id')),
                vaccine_name=request.form['vaccine_name'],
                administered_at=_parse_date(request.form['administered_at']),
                next_due_at=_parse_date(request.form.get('next_due_at')),
                clinic=request.form.get('clinic'),
                notes=request.form.get('notes'),
            )
            db.add(rec)
            db.commit()
            flash('ワクチンを記録しました', 'success')
            return redirect(url_for('breeder.vaccine_records'))
        dogs = db.query(Dog).filter(Dog.status == 'active').all()
        puppies = db.query(Puppy).filter(Puppy.status.in_(['available', 'reserved'])).all()
        return render_template('breeder/vaccine_record_form.html', dogs=dogs, puppies=puppies)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.vaccine_records'))
    finally:
        db.close()

@bp.route('/health/checkups')
@require_roles(*BREEDER_ROLES)
def health_checkups():
    from app.models_breeder import HealthCheckRecord, Dog, Puppy
    db = _get_db()
    try:
        records = db.query(HealthCheckRecord).order_by(desc(HealthCheckRecord.checked_at)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/health_checkups.html', records=records, dogs=dogs, puppies=puppies)
    finally:
        db.close()

@bp.route('/health/medications')
@require_roles(*BREEDER_ROLES)
def medication_records():
    from app.models_breeder import MedicationRecord, Dog, Puppy
    db = _get_db()
    try:
        records = db.query(MedicationRecord).order_by(desc(MedicationRecord.start_date)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/medication_records.html', records=records, dogs=dogs, puppies=puppies)
    finally:
        db.close()

@bp.route('/health/medical-history')
@require_roles(*BREEDER_ROLES)
def medical_histories():
    from app.models_breeder import MedicalHistory, Dog, Puppy
    db = _get_db()
    try:
        records = db.query(MedicalHistory).order_by(desc(MedicalHistory.diagnosed_at)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/medical_histories.html', records=records, dogs=dogs, puppies=puppies)
    finally:
        db.close()

@bp.route('/health/food')
@require_roles(*BREEDER_ROLES)
def food_records():
    from app.models_breeder import FoodRecord, Dog, Puppy
    db = _get_db()
    try:
        records = db.query(FoodRecord).order_by(desc(FoodRecord.start_date)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/food_records.html', records=records, dogs=dogs, puppies=puppies)
    finally:
        db.close()


# ─── 法規制対応：台帳 ────────────────────────────────────────
@bp.route('/ledger')
@require_roles(*BREEDER_ROLES)
def ledger():
    from app.models_breeder import LedgerEntry, Dog, Puppy
    db = _get_db()
    try:
        entries = db.query(LedgerEntry).order_by(desc(LedgerEntry.entry_date)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/ledger.html', entries=entries, dogs=dogs, puppies=puppies)
    finally:
        db.close()

@bp.route('/ledger/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def ledger_new():
    from app.models_breeder import LedgerEntry, Dog, Puppy
    db = _get_db()
    try:
        if request.method == 'POST':
            entry = LedgerEntry(
                entry_date=_parse_date(request.form['entry_date']),
                entry_type=request.form['entry_type'],
                dog_id=_int_or_none(request.form.get('dog_id')),
                puppy_id=_int_or_none(request.form.get('puppy_id')),
                description=request.form.get('description'),
                notes=request.form.get('notes'),
            )
            db.add(entry)
            db.commit()
            flash('台帳に記録しました', 'success')
            return redirect(url_for('breeder.ledger'))
        dogs = db.query(Dog).all()
        puppies = db.query(Puppy).all()
        return render_template('breeder/ledger_form.html', entry=None, dogs=dogs, puppies=puppies)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.ledger'))
    finally:
        db.close()


# ─── Todo管理 ────────────────────────────────────────────────
@bp.route('/todos')
@require_roles(*BREEDER_ROLES)
def todos_list():
    from app.models_breeder import Todo, Dog, Puppy
    db = _get_db()
    try:
        today = date.today()
        tab = request.args.get('tab', 'pending')
        status = 'pending' if tab == 'pending' else 'completed'
        todos = db.query(Todo).filter(Todo.status == status).order_by(asc(Todo.due_date)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        puppies = {p.id: p for p in db.query(Puppy).all()}
        return render_template('breeder/todos_list.html', todos=todos, dogs=dogs, puppies=puppies, tab=tab, today=today)
    finally:
        db.close()

@bp.route('/todos/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def todo_new():
    from app.models_breeder import Todo, Dog, Puppy
    db = _get_db()
    try:
        if request.method == 'POST':
            todo = Todo(
                title=request.form['title'],
                description=request.form.get('description'),
                due_date=_parse_date(request.form.get('due_date')),
                status='pending',
                category=request.form.get('category'),
                dog_id=_int_or_none(request.form.get('dog_id')),
                puppy_id=_int_or_none(request.form.get('puppy_id')),
            )
            db.add(todo)
            db.commit()
            flash('Todoを追加しました', 'success')
            return redirect(url_for('breeder.todos_list'))
        dogs = db.query(Dog).filter(Dog.status == 'active').all()
        puppies = db.query(Puppy).filter(Puppy.status.in_(['available', 'reserved'])).all()
        return render_template('breeder/todo_form.html', todo=None, dogs=dogs, puppies=puppies)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.todos_list'))
    finally:
        db.close()

@bp.route('/todos/<int:todo_id>/complete', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def todo_complete(todo_id):
    from app.models_breeder import Todo
    db = _get_db()
    try:
        todo = db.query(Todo).filter(Todo.id == todo_id).first()
        if todo:
            todo.status = 'completed'
            db.commit()
            flash('完了にしました', 'success')
    finally:
        db.close()
    return redirect(url_for('breeder.todos_list'))


# ─── 設定 ────────────────────────────────────────────────────
@bp.route('/settings')
@require_roles(*BREEDER_ROLES)
def settings():
    from app.models_breeder import AppSetting, EventPreset
    db = _get_db()
    try:
        settings_list = db.query(AppSetting).all()
        settings_dict = {s.key: s.value for s in settings_list}
        presets = db.query(EventPreset).order_by(EventPreset.category, EventPreset.name).all()
        return render_template('breeder/settings.html', settings=settings_dict, presets=presets)
    finally:
        db.close()

@bp.route('/settings/save', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def settings_save():
    from app.models_breeder import AppSetting
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        for key, value in request.form.items():
            q = db.query(AppSetting).filter(AppSetting.key == key)
            if tenant_id:
                q = q.filter(AppSetting.tenant_id == tenant_id)
            if store_id:
                q = q.filter(AppSetting.store_id == store_id)
            existing = q.first()
            if existing:
                existing.value = value
            else:
                db.add(AppSetting(key=key, value=value, tenant_id=tenant_id, store_id=store_id))
        db.commit()
        flash('設定を保存しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'保存エラー: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('breeder.settings'))



# ─── テナント管理者向け全店舗集計 ──────────────────────────────
@bp.route('/tenant_summary')
@require_roles(*BREEDER_ROLES)
def tenant_summary():
    """テナント管理者・システム管理者向け：全店舗の集計ダッシュボード"""
    from app.models_breeder import Dog, Puppy, Heat, Mating, Birth, Todo, Negotiation
    from app.models_login import TTenpo, TTenant
    db = _get_db()
    try:
        role = _get_role()
        tenant_id = session.get('tenant_id')
        today = date.today()

        # 店舗一覧取得
        sq = db.query(TTenpo)
        if role != 'system_admin' and tenant_id:
            sq = sq.filter(TTenpo.tenant_id == tenant_id)
        stores = sq.order_by(TTenpo.id).all()

        # テナント名取得
        tenant_name = None
        if tenant_id:
            t = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            tenant_name = t.名称 if t else None

        # 店舗別集計
        store_stats = []
        for store in stores:
            sid = store.id
            parents = db.query(func.count(Dog.id)).filter(
                Dog.store_id == sid, Dog.status == 'active', Dog.dog_type == 'parent').scalar() or 0
            puppies = db.query(func.count(Puppy.id)).filter(
                Puppy.store_id == sid, Puppy.status.in_(['available', 'reserved'])).scalar() or 0
            heats = db.query(func.count(Heat.id)).filter(
                Heat.store_id == sid, Heat.status.in_(['active', 'imminent'])).scalar() or 0
            pregnant = db.query(func.count(Mating.id)).filter(
                Mating.store_id == sid, Mating.status == 'pregnant').scalar() or 0
            todos = db.query(func.count(Todo.id)).filter(
                Todo.store_id == sid, Todo.status == 'pending').scalar() or 0
            negotiations = db.query(func.count(Negotiation.id)).filter(
                Negotiation.store_id == sid,
                Negotiation.status.in_(['inquiry', 'negotiating', 'reserved'])).scalar() or 0
            store_stats.append({
                'store': store,
                'parents': parents,
                'puppies': puppies,
                'heats': heats,
                'pregnant': pregnant,
                'todos': todos,
                'negotiations': negotiations,
            })

        # 全体合計
        totals = {
            'parents': sum(s['parents'] for s in store_stats),
            'puppies': sum(s['puppies'] for s in store_stats),
            'heats': sum(s['heats'] for s in store_stats),
            'pregnant': sum(s['pregnant'] for s in store_stats),
            'todos': sum(s['todos'] for s in store_stats),
            'negotiations': sum(s['negotiations'] for s in store_stats),
        }

        return render_template('breeder/tenant_summary.html',
            store_stats=store_stats,
            totals=totals,
            tenant_name=tenant_name,
            role=role,
            today=today,
        )
    finally:
        db.close()


@bp.route('/select_store', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def select_store():
    """店舗切り替え"""
    from app.models_login import TTenpo
    db = _get_db()
    try:
        tenant_id = session.get('tenant_id')
        role = _get_role()
        sq = db.query(TTenpo)
        if role != 'system_admin' and tenant_id:
            sq = sq.filter(TTenpo.tenant_id == tenant_id)
        stores = sq.order_by(TTenpo.id).all()

        if request.method == 'POST':
            store_id = request.form.get('store_id')
            if store_id == 'all':
                session['store_id'] = None
            else:
                session['store_id'] = int(store_id) if store_id else None
            return redirect(request.form.get('next') or url_for('breeder.dashboard'))

        return render_template('breeder/select_store.html', stores=stores,
                               current_store_id=session.get('store_id'))
    finally:
        db.close()

# ─── 権限管理 ──────────────────────────────────────────────
@bp.route('/permissions')
@require_roles(ROLES["TENANT_ADMIN"])
def permissions():
    """権限管理ページ（テナント管理者のみ）"""
    from app.models_breeder import BreederPermission
    from app.models_login import TKanrisha, TTenpo
    db = _get_db()
    try:
        tenant_id = session.get('tenant_id')
        role = _get_role()

        # テナント内の全admin一覧
        admins_q = db.query(TKanrisha).filter(
            TKanrisha.role == 'admin',
            TKanrisha.active == 1
        )
        if tenant_id:
            admins_q = admins_q.filter(TKanrisha.tenant_id == tenant_id)
        admins = admins_q.order_by(TKanrisha.name).all()

        # 既存の権限一覧
        perms_q = db.query(BreederPermission)
        if tenant_id:
            perms_q = perms_q.filter(BreederPermission.tenant_id == tenant_id)
        perms = {p.admin_id: p for p in perms_q.all()}

        return render_template('breeder/permissions.html',
            admins=admins,
            perms=perms,
            role=role,
        )
    finally:
        db.close()


@bp.route('/permissions/set', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"])
def permissions_set():
    """権限付与・変更・剥奪（テナント管理者のみ）"""
    from app.models_breeder import BreederPermission
    db = _get_db()
    try:
        tenant_id = session.get('tenant_id')
        granted_by = session.get('user_id')
        admin_id = request.form.get('admin_id', type=int)
        permission_level = request.form.get('permission_level', '')  # 'view', 'operate', '' (剥奪)

        if not admin_id or not tenant_id:
            flash('パラメータが不正です', 'error')
            return redirect(url_for('breeder.permissions'))

        existing = db.query(BreederPermission).filter(
            BreederPermission.admin_id == admin_id,
            BreederPermission.tenant_id == tenant_id
        ).first()

        if permission_level in ('view', 'operate'):
            if existing:
                existing.permission_level = permission_level
                existing.granted_by = granted_by
                existing.updated_at = datetime.now()
                flash('権限を更新しました', 'success')
            else:
                new_perm = BreederPermission(
                    admin_id=admin_id,
                    tenant_id=tenant_id,
                    permission_level=permission_level,
                    granted_by=granted_by
                )
                db.add(new_perm)
                flash('権限を付与しました', 'success')
        else:
            # 剥奪
            if existing:
                db.delete(existing)
                flash('権限を剥奪しました', 'success')
            else:
                flash('対象の権限が見つかりません', 'warning')

        db.commit()
        return redirect(url_for('breeder.permissions'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {e}', 'error')
        return redirect(url_for('breeder.permissions'))
    finally:
        db.close()


# ─── ユーティリティ ──────────────────────────────────────────
def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except Exception:
        return None

def _int_or_none(s):
    try:
        return int(s) if s else None
    except Exception:
        return None

def _decimal_or_none(s):
    try:
        from decimal import Decimal
        return Decimal(s) if s else None
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════════
# 交配シミュレーション（Churupi相当）
# ═══════════════════════════════════════════════════════════════════

def _calc_coi(dog_id, db, depth=4):
    """
    Wright係数法によるCOI（近交係数）の簡易計算。
    depth世代分の祖先を遡り、共通祖先が存在する場合に係数を加算する。
    """
    from app.models_breeder import Dog

    def get_ancestors(did, gen, memo=None):
        if memo is None:
            memo = {}
        if gen == 0 or did is None:
            return memo
        if did in memo:
            memo[did].append(gen)
        else:
            memo[did] = [gen]
        d = db.query(Dog).filter(Dog.id == did).first()
        if d:
            get_ancestors(d.mother_id, gen - 1, memo)
            get_ancestors(d.father_id, gen - 1, memo)
        return memo

    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if not dog:
        return 0.0

    sire_anc = get_ancestors(dog.father_id, depth)
    dam_anc  = get_ancestors(dog.mother_id, depth)

    common = set(sire_anc.keys()) & set(dam_anc.keys())
    coi = 0.0
    for anc_id in common:
        for n1 in sire_anc[anc_id]:
            for n2 in dam_anc[anc_id]:
                coi += (0.5 ** (n1 + n2 + 1))
    return round(coi * 100, 2)


def _get_ancestors_from_pedigree_table(dog_id, db):
    """
    pedigree_ancestorsテーブルから祖先情報を取得し、
    {generation: [{name, registration_number}]} 形式で返す。
    """
    try:
        from app.models_breeder import PedigreeAncestor
        rows = db.query(PedigreeAncestor).filter(PedigreeAncestor.dog_id == dog_id).all()
        result = {}
        for row in rows:
            gen = row.generation
            if gen not in result:
                result[gen] = []
            result[gen].append({
                'name': (row.name or '').strip().upper(),
                'registration_number': (row.registration_number or '').strip().upper(),
            })
        return result
    except Exception:
        return {}


def _calc_coi_pair(sire_id, dam_id, db, depth=4):
    """
    仮想子犬のCOIを計算する（シミュレーション用）。
    pedigree_ancestorsテーブルが利用可能な場合は名前ベースの共通祖先照合を併用。
    """
    from app.models_breeder import Dog
    def get_ancestors(did, gen, memo=None):
        if memo is None:
            memo = {}
        if gen == 0 or did is None:
            return memo
        if did in memo:
            memo[did].append(gen)
        else:
            memo[did] = [gen]
        d = db.query(Dog).filter(Dog.id == did).first()
        if d:
            get_ancestors(d.mother_id, gen - 1, memo)
            get_ancestors(d.father_id, gen - 1, memo)
        return memo
    sire_anc = get_ancestors(sire_id, depth)
    dam_anc  = get_ancestors(dam_id, depth)
    common = set(sire_anc.keys()) & set(dam_anc.keys())
    coi = 0.0
    for anc_id in common:
        for n1 in sire_anc[anc_id]:
            for n2 in dam_anc[anc_id]:
                coi += (0.5 ** (n1 + n2 + 1))
    # pedigree_ancestorsテーブルを使った名前ベースCOI補完
    try:
        sire_ped = _get_ancestors_from_pedigree_table(sire_id, db)
        dam_ped  = _get_ancestors_from_pedigree_table(dam_id, db)
        if sire_ped and dam_ped:
            # 全世代の祖先名セットを作成（名前 or 登録番号で照合）
            def _anc_keys(ped_dict):
                """世代 -> [(key, gen_weight)] のリストを返す"""
                result = []
                for gen, ancs in ped_dict.items():
                    for a in ancs:
                        key = a['registration_number'] if a['registration_number'] else a['name']
                        if key:
                            result.append((key, gen + 1))  # gen+1: pedigree_ancestorsのgenerationは1始まり
                return result
            sire_keys = _anc_keys(sire_ped)
            dam_keys  = _anc_keys(dam_ped)
            sire_key_map = {}
            for key, gen in sire_keys:
                if key not in sire_key_map:
                    sire_key_map[key] = []
                sire_key_map[key].append(gen)
            dam_key_map = {}
            for key, gen in dam_keys:
                if key not in dam_key_map:
                    dam_key_map[key] = []
                dam_key_map[key].append(gen)
            common_keys = set(sire_key_map.keys()) & set(dam_key_map.keys())
            for key in common_keys:
                for n1 in sire_key_map[key]:
                    for n2 in dam_key_map[key]:
                        coi += (0.5 ** (n1 + n2 + 1))
    except Exception:
        pass
    return round(coi * 100, 2)


@bp.route('/simulation', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def simulation():
    """交配シミュレーションページ"""
    from app.models_breeder import Dog
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()

    def _tf(q):
        if tenant_id:
            q = q.filter(Dog.tenant_id == tenant_id)
        if store_id:
            q = q.filter(Dog.store_id == store_id)
        return q

    males   = _tf(db.query(Dog).filter(Dog.status == 'active', Dog.gender == 'male')).all()
    females = _tf(db.query(Dog).filter(Dog.status == 'active', Dog.gender == 'female')).all()

    result = None
    sire_id = dam_id = None
    max_depth = 5
    if request.method == 'POST':
        sire_id   = request.form.get('sire_id',   type=int)
        dam_id    = request.form.get('dam_id',    type=int)
        max_depth = request.form.get('max_depth', type=int, default=5) or 5
        if sire_id and dam_id:
            try:
                from app.services.breeding_logic import evaluate_mating_compatibility
                from app.models_breeder import MatingEvaluation
                result = evaluate_mating_compatibility(
                    sire_id, dam_id, max_depth=max_depth, db=db, use_ai_comment=True
                )
                # 評価結果を DB に保存
                try:
                    eval_rec = MatingEvaluation(
                        tenant_id=tenant_id,
                        store_id=store_id,
                        sire_id=sire_id,
                        dam_id=dam_id,
                        coi=result['coi'],
                        coi_percent=result['coi_percent'],
                        rank=result['rank'],
                        recommendation=result['recommendation'],
                        result_json=json.dumps(result, ensure_ascii=False, default=str),
                        max_depth=max_depth,
                    )
                    db.add(eval_rec)
                    db.commit()
                except Exception:
                    db.rollback()
            except Exception as e:
                result = {'error': str(e)}

    return render_template('breeder/simulation.html',
                           males=males, females=females,
                           result=result, sire_id=sire_id, dam_id=dam_id,
                           max_depth=max_depth)


# ═══════════════════════════════════════════════════════════════════
# 相性一括チェック（Churupi相当）
# ═══════════════════════════════════════════════════════════════════

@bp.route('/mating-bulk')
@require_roles(*BREEDER_ROLES)
def mating_bulk():
    """相性一括チェックページ"""
    from app.models_breeder import Dog
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()

    def _tf(q):
        if tenant_id:
            q = q.filter(Dog.tenant_id == tenant_id)
        if store_id:
            q = q.filter(Dog.store_id == store_id)
        return q

    males   = _tf(db.query(Dog).filter(Dog.status == 'active', Dog.gender == 'male')).all()
    females = _tf(db.query(Dog).filter(Dog.status == 'active', Dog.gender == 'female')).all()

    # 全ペアのCOIを breeding_logic で計算（数式ロジック）
    from app.services.breeding_logic import calculate_coi, get_coi_rank
    matrix = []
    for dam in females:
        row = {'dam': dam, 'pairs': []}
        for sire in males:
            try:
                coi_result = calculate_coi(sire.id, dam.id, max_depth=5, db=db)
                coi_pct = coi_result['coi_percent']
                rank_info = get_coi_rank(coi_pct)
                row['pairs'].append({
                    'sire': sire,
                    'coi': coi_pct,
                    'rank': rank_info['rank'],
                    'risk_level': rank_info['risk_level'],
                    'level': 'low' if coi_pct < 5 else ('medium' if coi_pct < 10 else 'high'),
                })
            except Exception:
                row['pairs'].append({'sire': sire, 'coi': None, 'rank': '-', 'risk_level': '-', 'level': 'unknown'})
        matrix.append(row)

    return render_template('breeder/mating_bulk.html',
                           males=males, females=females, matrix=matrix)


# ═══════════════════════════════════════════════════════════════════
# 遺伝疾患検査結果管理（Churupi相当）
# ═══════════════════════════════════════════════════════════════════

@bp.route('/dogs/<int:dog_id>/genetic-tests', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def genetic_tests(dog_id):
    from app.models_breeder import Dog, GeneticTestResult
    db = _get_db()
    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if not dog:
        flash('犬が見つかりません', 'error')
        return redirect(url_for('breeder.dogs_list'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            rec = GeneticTestResult(
                tenant_id=dog.tenant_id,
                store_id=dog.store_id,
                dog_id=dog_id,
                disease_name=request.form.get('disease_name', ''),
                result=request.form.get('result', 'unknown'),
                tested_at=request.form.get('tested_at') or None,
                lab_name=request.form.get('lab_name') or None,
                notes=request.form.get('notes') or None,
            )
            db.add(rec)
            db.commit()
            flash('遺伝疾患検査結果を登録しました', 'success')
        elif action == 'delete':
            rec_id = request.form.get('rec_id', type=int)
            rec = db.query(GeneticTestResult).filter(GeneticTestResult.id == rec_id).first()
            if rec:
                db.delete(rec)
                db.commit()
                flash('削除しました', 'success')
        return redirect(url_for('breeder.genetic_tests', dog_id=dog_id))

    tests = db.query(GeneticTestResult).filter(GeneticTestResult.dog_id == dog_id).order_by(GeneticTestResult.tested_at.desc()).all()
    return render_template('breeder/genetic_tests.html', dog=dog, tests=tests)


# ═══════════════════════════════════════════════════════════════════
# ショー記録管理（Churupi相当）
# ═══════════════════════════════════════════════════════════════════

@bp.route('/dogs/<int:dog_id>/show-records', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def show_records_dog(dog_id):
    from app.models_breeder import Dog, ShowRecord
    db = _get_db()
    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if not dog:
        flash('犬が見つかりません', 'error')
        return redirect(url_for('breeder.dogs_list'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            rec = ShowRecord(
                tenant_id=dog.tenant_id,
                store_id=dog.store_id,
                dog_id=dog_id,
                show_name=request.form.get('show_name', ''),
                show_date=request.form.get('show_date'),
                location=request.form.get('location') or None,
                title_earned=request.form.get('title_earned') or None,
                placement=request.form.get('placement') or None,
                judge_name=request.form.get('judge_name') or None,
                notes=request.form.get('notes') or None,
            )
            db.add(rec)
            db.commit()
            flash('ショー記録を登録しました', 'success')
        elif action == 'delete':
            rec_id = request.form.get('rec_id', type=int)
            rec = db.query(ShowRecord).filter(ShowRecord.id == rec_id).first()
            if rec:
                db.delete(rec)
                db.commit()
                flash('削除しました', 'success')
        return redirect(url_for('breeder.show_records_dog', dog_id=dog_id))

    records = db.query(ShowRecord).filter(ShowRecord.dog_id == dog_id).order_by(ShowRecord.show_date.desc()).all()
    return render_template('breeder/show_records.html', dog=dog, records=records)


# ═══════════════════════════════════════════════════════════════════
# 家系図（Churupi相当）
# ═══════════════════════════════════════════════════════════════════

@bp.route('/dogs/<int:dog_id>/pedigree-tree')
@require_roles(*BREEDER_ROLES)
def pedigree_tree(dog_id):
    from app.models_breeder import Dog
    db = _get_db()
    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if not dog:
        flash('犬が見つかりません', 'error')
        return redirect(url_for('breeder.dogs_list'))

    def build_tree(did, depth=3):
        if did is None or depth == 0:
            return None
        d = db.query(Dog).filter(Dog.id == did).first()
        if not d:
            return None
        return {
            'id': d.id,
            'name': d.name,
            'breed': d.breed or '',
            'gender': d.gender or '',
            'reg_no': d.pedigree_number or '',
            'sire': build_tree(d.father_id, depth - 1),
            'dam':  build_tree(d.mother_id, depth - 1),
        }

    tree = build_tree(dog_id)
    coi = _calc_coi(dog_id, db)
    return render_template('breeder/pedigree_tree.html', dog=dog, tree=tree, coi=coi)


# ═══════════════════════════════════════════════════════════════════
# 公開カルテ（Churupi相当）
# ═══════════════════════════════════════════════════════════════════

@bp.route('/dogs/<int:dog_id>/public-carte', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def public_carte_manage(dog_id):
    import secrets as _secrets
    from app.models_breeder import Dog, PublicCarte, GeneticTestResult, ShowRecord
    db = _get_db()
    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if not dog:
        flash('犬が見つかりません', 'error')
        return redirect(url_for('breeder.dogs_list'))

    carte = db.query(PublicCarte).filter(PublicCarte.dog_id == dog_id).first()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create' and not carte:
            carte = PublicCarte(
                tenant_id=dog.tenant_id,
                store_id=dog.store_id,
                dog_id=dog_id,
                public_token=_secrets.token_urlsafe(32),
                is_published=0,
                intro_text=request.form.get('intro_text') or None,
            )
            db.add(carte)
            db.commit()
            flash('公開カルテを作成しました', 'success')
        elif action == 'update' and carte:
            carte.is_published = int(request.form.get('is_published', 0))
            carte.intro_text = request.form.get('intro_text') or None
            db.commit()
            flash('公開カルテを更新しました', 'success')
        return redirect(url_for('breeder.public_carte_manage', dog_id=dog_id))

    gene_tests = db.query(GeneticTestResult).filter(GeneticTestResult.dog_id == dog_id).all()
    show_recs  = db.query(ShowRecord).filter(ShowRecord.dog_id == dog_id).all()
    return render_template('breeder/public_carte_manage.html',
                           dog=dog, carte=carte,
                           gene_tests=gene_tests, show_recs=show_recs)


@bp.route('/carte/<token>')
def public_carte_view(token):
    """認証不要の公開カルテビュー"""
    from app.models_breeder import PublicCarte, Dog, GeneticTestResult, ShowRecord, WeightRecord, VaccineRecord
    db = _get_db()
    carte = db.query(PublicCarte).filter(PublicCarte.public_token == token).first()
    if not carte or not carte.is_published:
        return render_template('breeder/public_carte_404.html'), 404

    # 閲覧数カウント
    carte.view_count = (carte.view_count or 0) + 1
    db.commit()

    dog = db.query(Dog).filter(Dog.id == carte.dog_id).first()
    gene_tests = db.query(GeneticTestResult).filter(GeneticTestResult.dog_id == carte.dog_id).all()
    show_recs  = db.query(ShowRecord).filter(ShowRecord.dog_id == carte.dog_id).all()
    weights    = db.query(WeightRecord).filter(WeightRecord.dog_id == carte.dog_id).order_by(WeightRecord.measured_at.desc()).limit(10).all()
    vaccines   = db.query(VaccineRecord).filter(VaccineRecord.dog_id == carte.dog_id).order_by(VaccineRecord.vaccinated_at.desc()).all()
    coi = _calc_coi(carte.dog_id, db)

    return render_template('breeder/public_carte_view.html',
                           dog=dog, carte=carte,
                           gene_tests=gene_tests, show_recs=show_recs,
                           weights=weights, vaccines=vaccines, coi=coi)



# ─── 販売管理：カンバンボード（Churupi相当） ──────────────────────────
@bp.route('/negotiations/kanban')
@require_roles(*BREEDER_ROLES)
def negotiations_kanban():
    """カンバンボード形式の商談管理（Churupiのdealsページ相当）"""
    from app.models_breeder import Negotiation, Contact, Puppy
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        query = db.query(Negotiation)
        if tenant_id:
            query = query.filter(Negotiation.tenant_id == tenant_id)
        if store_id:
            query = query.filter(Negotiation.store_id == store_id)
        all_negs = query.order_by(asc(Negotiation.created_at)).all()
        contacts = {c.id: c for c in db.query(Contact).all()}
        puppies  = {p.id: p for p in db.query(Puppy).all()}
        # カンバンカラム定義（Churupiと同等）
        columns = [
            {'key': 'inquiry',     'label': '問い合わせ',  'color': '#6366f1'},
            {'key': 'negotiating', 'label': '商談中',       'color': '#f59e0b'},
            {'key': 'reserved',    'label': '予約済み',     'color': '#3b82f6'},
            {'key': 'contracted',  'label': '成約',         'color': '#10b981'},
            {'key': 'cancelled',   'label': 'キャンセル',   'color': '#ef4444'},
        ]
        kanban = {col['key']: [] for col in columns}
        for neg in all_negs:
            col_key = neg.status if neg.status in kanban else 'inquiry'
            kanban[col_key].append(neg)
        return render_template('breeder/negotiations_kanban.html',
                               columns=columns, kanban=kanban,
                               contacts=contacts, puppies=puppies)
    finally:
        db.close()


@bp.route('/negotiations/<int:neg_id>/move', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def negotiation_move(neg_id):
    """カンバンカードのステータス変更（ドラッグ&ドロップ対応）"""
    from app.models_breeder import Negotiation
    db = _get_db()
    try:
        neg = db.query(Negotiation).filter(Negotiation.id == neg_id).first()
        if not neg:
            return jsonify({'error': 'not found'}), 404
        new_status = request.json.get('status') if request.is_json else request.form.get('status')
        valid_statuses = ['inquiry', 'negotiating', 'reserved', 'contracted', 'cancelled']
        if new_status not in valid_statuses:
            return jsonify({'error': 'invalid status'}), 400
        neg.status = new_status
        neg.updated_at = datetime.utcnow()
        db.commit()
        return jsonify({'success': True, 'status': new_status})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ─── CSVエクスポート（Churupi相当） ──────────────────────────────────
@bp.route('/export')
@require_roles(*BREEDER_ROLES)
def export_page():
    """エクスポートページ（Churupiのexportsページ相当）"""
    return render_template('breeder/export.html')


@bp.route('/export/download')
@require_roles(*BREEDER_ROLES)
def export_download():
    """CSVエクスポート実行"""
    import csv
    import io
    from flask import Response
    from app.models_breeder import Dog, Puppy, Negotiation, Contact, Heat, Birth, PedigreeApplication

    target = request.args.get('target', 'dogs')
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        output = io.StringIO()
        writer = csv.writer(output)

        if target == 'dogs':
            writer.writerow(['ID', '犬名', '犬種', '性別', '生年月日', '毛色', '登録番号', 'ステータス', '備考'])
            query = db.query(Dog)
            if tenant_id:
                query = query.filter(Dog.tenant_id == tenant_id)
            for d in query.all():
                writer.writerow([d.id, d.name, d.breed or '', d.gender or '', d.birth_date or '',
                                  d.color or '', d.pedigree_number or '', d.status or '', d.notes or ''])

        elif target == 'puppies':
            writer.writerow(['ID', '子犬名', '犬種', '性別', '生年月日', '毛色', 'ステータス', '販売価格'])
            query = db.query(Puppy)
            if tenant_id:
                query = query.filter(Puppy.tenant_id == tenant_id)
            for p in query.all():
                writer.writerow([p.id, p.name or '', p.breed or '', p.gender or '', p.birth_date or '',
                                  p.color or '', p.status or '', p.price or ''])

        elif target == 'negotiations':
            writer.writerow(['ID', 'ステータス', '顧客名', '子犬名', '成約価格', '作成日', '更新日'])
            query = db.query(Negotiation)
            if tenant_id:
                query = query.filter(Negotiation.tenant_id == tenant_id)
            contacts = {c.id: c for c in db.query(Contact).all()}
            puppies  = {p.id: p for p in db.query(Puppy).all()}
            for n in query.all():
                contact_name = contacts[n.contact_id].name if n.contact_id and n.contact_id in contacts else ''
                puppy_name   = puppies[n.puppy_id].name if n.puppy_id and n.puppy_id in puppies else ''
                writer.writerow([n.id, n.status or '', contact_name, puppy_name,
                                  n.sale_price or '', n.created_at or '', n.updated_at or ''])

        elif target == 'contacts':
            writer.writerow(['ID', '氏名', '電話番号', 'メールアドレス', '住所', '備考'])
            query = db.query(Contact)
            if tenant_id:
                query = query.filter(Contact.tenant_id == tenant_id)
            for c in query.all():
                writer.writerow([c.id, c.name or '', c.phone or '', c.email or '',
                                  c.address or '', c.notes or ''])

        elif target == 'heats':
            writer.writerow(['ID', '犬名', '開始日', '終了日', 'ステータス', '次回予測日'])
            query = db.query(Heat)
            if tenant_id:
                query = query.filter(Heat.tenant_id == tenant_id)
            dogs = {d.id: d for d in db.query(Dog).all()}
            for h in query.all():
                dog_name = dogs[h.dog_id].name if h.dog_id and h.dog_id in dogs else ''
                writer.writerow([h.id, dog_name, h.start_date or '', h.end_date or '',
                                  h.status or '', h.next_predicted_date or ''])

        elif target == 'births':
            writer.writerow(['ID', '出産日', '総頭数', '生存頭数', '備考'])
            query = db.query(Birth)
            if tenant_id:
                query = query.filter(Birth.tenant_id == tenant_id)
            for b in query.all():
                writer.writerow([b.id, b.birth_date or '', b.total_count or 0,
                                  b.alive_count or 0, b.notes or ''])

        elif target == 'pedigree_applications':
            writer.writerow(['ID', '子犬名', '申請日', 'ステータス', '申請番号'])
            query = db.query(PedigreeApplication)
            if tenant_id:
                query = query.filter(PedigreeApplication.tenant_id == tenant_id)
            puppies = {p.id: p for p in db.query(Puppy).all()}
            for a in query.all():
                puppy_name = puppies[a.puppy_id].name if a.puppy_id and a.puppy_id in puppies else ''
                writer.writerow([a.id, puppy_name, a.applied_at or '', a.status or '', a.application_number or ''])

        output.seek(0)
        filename = f'breeder_{target}_{date.today().strftime("%Y%m%d")}.csv'
        return Response(
            '\ufeff' + output.getvalue(),  # BOM付きUTF-8（Excel対応）
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    finally:
        db.close()


# ─── 設定：細分化タブ（Churupi相当） ──────────────────────────────────
@bp.route('/settings/advanced')
@require_roles(*BREEDER_ROLES)
def settings_advanced():
    """詳細設定ページ（Churupiの設定タブ細分化相当）"""
    from app.models_breeder import AppSetting
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        query = db.query(AppSetting)
        if tenant_id:
            query = query.filter(AppSetting.tenant_id == tenant_id)
        if store_id:
            query = query.filter(AppSetting.store_id == store_id)
        setting = query.first()
        return render_template('breeder/settings_advanced.html', setting=setting)
    finally:
        db.close()


@bp.route('/settings/advanced/save', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def settings_advanced_save():
    """詳細設定の保存"""
    from app.models_breeder import AppSetting
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        query = db.query(AppSetting)
        if tenant_id:
            query = query.filter(AppSetting.tenant_id == tenant_id)
        if store_id:
            query = query.filter(AppSetting.store_id == store_id)
        setting = query.first()
        if not setting:
            setting = AppSetting(tenant_id=tenant_id, store_id=store_id)
            db.add(setting)

        block = request.form.get('block', 'general')

        if block == 'animal':
            # 生体設定
            setting.default_breed = request.form.get('default_breed', '')
            setting.default_heat_cycle_days = int(request.form.get('default_heat_cycle_days') or 180)
            setting.default_gestation_days  = int(request.form.get('default_gestation_days') or 63)

        elif block == 'deal':
            # 商談設定
            setting.deal_default_view = request.form.get('deal_default_view', 'list')
            setting.deal_auto_archive_days = int(request.form.get('deal_auto_archive_days') or 90)

        elif block == 'application':
            # 申請設定
            setting.pedigree_alert_days = int(request.form.get('pedigree_alert_days') or 60)
            setting.chip_alert_days     = int(request.form.get('chip_alert_days') or 90)

        elif block == 'carte':
            # カルテ設定
            setting.carte_show_weight    = request.form.get('carte_show_weight') == '1'
            setting.carte_show_vaccine   = request.form.get('carte_show_vaccine') == '1'
            setting.carte_show_gene      = request.form.get('carte_show_gene') == '1'
            setting.carte_show_show_rec  = request.form.get('carte_show_show_rec') == '1'

        db.commit()
        flash('設定を保存しました', 'success')
        return redirect(url_for('breeder.settings_advanced') + f'?block={block}')
    except Exception as e:
        db.rollback()
        flash(f'保存エラー: {e}', 'error')
        return redirect(url_for('breeder.settings_advanced'))
    finally:
        db.close()


# ─── 遺伝疾患検査・ショー記録の一覧ページ ──────────────────────────────
@bp.route('/genetic-tests')
@require_roles(*BREEDER_ROLES)
def genetic_tests_list():
    """遺伝疾患検査結果の一覧（全犬）"""
    from app.models_breeder import GeneticTestResult, Dog
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        query = db.query(GeneticTestResult)
        if tenant_id:
            query = query.filter(GeneticTestResult.tenant_id == tenant_id)
        tests = query.order_by(desc(GeneticTestResult.tested_at)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        return render_template('breeder/genetic_tests.html', tests=tests, dogs=dogs, dog=None, dog_id=None)
    finally:
        db.close()


@bp.route('/show-records')
@require_roles(*BREEDER_ROLES)
def show_records_list():
    """ショー記録の一覧（全犬）"""
    from app.models_breeder import ShowRecord, Dog
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        query = db.query(ShowRecord)
        if tenant_id:
            query = query.filter(ShowRecord.tenant_id == tenant_id)
        records = query.order_by(desc(ShowRecord.show_date)).all()
        dogs = {d.id: d for d in db.query(Dog).all()}
        return render_template('breeder/show_records.html', records=records, dogs=dogs, dog=None, dog_id=None)
    finally:
        db.close()


# ─── イベントプリセット一覧ページ ──────────────────────────────────────
@bp.route('/presets')
@require_roles(*BREEDER_ROLES)
def presets_list():
    """イベントプリセット一覧（Churupiのpresetsページ相当）"""
    from app.models_breeder import EventPreset
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        query = db.query(EventPreset)
        if tenant_id:
            query = query.filter(EventPreset.tenant_id == tenant_id)
        presets = query.order_by(EventPreset.category, EventPreset.name).all()
        return render_template('breeder/presets_list.html', presets=presets)
    finally:
        db.close()


@bp.route('/presets/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def preset_new():
    """イベントプリセット新規作成"""
    from app.models_breeder import EventPreset
    db = _get_db()
    try:
        if request.method == 'POST':
            tenant_id, store_id = _get_tenant_store()
            preset = EventPreset(
                tenant_id=tenant_id,
                store_id=store_id,
                name=request.form.get('name', ''),
                category=request.form.get('category', 'general'),
                days_offset=int(request.form.get('days_offset') or 0),
                notes=request.form.get('notes', ''),
            )
            db.add(preset)
            db.commit()
            flash('プリセットを登録しました', 'success')
            return redirect(url_for('breeder.presets_list'))
        return render_template('breeder/preset_form.html', preset=None)
    except Exception as e:
        db.rollback()
        flash(f'登録エラー: {e}', 'error')
        return redirect(url_for('breeder.presets_list'))
    finally:
        db.close()


@bp.route('/presets/<int:preset_id>/edit', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def preset_edit(preset_id):
    """イベントプリセット編集"""
    from app.models_breeder import EventPreset
    db = _get_db()
    try:
        preset = db.query(EventPreset).filter(EventPreset.id == preset_id).first()
        if not preset:
            flash('プリセットが見つかりません', 'error')
            return redirect(url_for('breeder.presets_list'))
        if request.method == 'POST':
            preset.name        = request.form.get('name', preset.name)
            preset.category    = request.form.get('category', preset.category)
            preset.days_offset = int(request.form.get('days_offset') or 0)
            preset.notes       = request.form.get('notes', '')
            db.commit()
            flash('プリセットを更新しました', 'success')
            return redirect(url_for('breeder.presets_list'))
        return render_template('breeder/preset_form.html', preset=preset)
    except Exception as e:
        db.rollback()
        flash(f'更新エラー: {e}', 'error')
        return redirect(url_for('breeder.presets_list'))
    finally:
        db.close()


@bp.route('/presets/<int:preset_id>/delete', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def preset_delete(preset_id):
    """イベントプリセット削除"""
    from app.models_breeder import EventPreset
    db = _get_db()
    try:
        preset = db.query(EventPreset).filter(EventPreset.id == preset_id).first()
        if preset:
            db.delete(preset)
            db.commit()
            flash('プリセットを削除しました', 'success')
        return redirect(url_for('breeder.presets_list'))
    except Exception as e:
        db.rollback()
        flash(f'削除エラー: {e}', 'error')
        return redirect(url_for('breeder.presets_list'))
    finally:
        db.close()


# ─── JKCドッグショースケジュール取得API ────────────────────────────────────────
@bp.route('/api/jkc-shows')
def api_jkc_shows():
    """JKC公式サイトからドッグショースケジュールをスクレイピングして返す"""
    import requests as req
    from bs4 import BeautifulSoup
    import re
    from datetime import datetime, timedelta

    try:
        today = datetime.today()
        start = today.strftime('%Y%m%d')
        end = (today + timedelta(days=180)).strftime('%Y%m%d')
        url = f'https://www.jkc.or.jp/events/event_schedule/?_sfm_acf_ev_date={start}+{end}'
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; BreederApp/1.0)'}
        resp = req.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        events = []
        # JKCサイトの構造: 各イベントは .p-schedule__item 内に日付・タイトル・会場がある
        # 日付は .p-schedule__date, タイトルは .p-schedule__title, 会場は .p-schedule__place
        items = soup.select('.p-schedule__item')
        if not items:
            # 別のセレクタを試す
            items = soup.select('.p-event-list__item, .p-schedule-list__item, article')

        current_date = None
        # 日付ヘッダーとイベントのペアを解析
        for elem in soup.find_all(['h4', 'h3', 'div'], recursive=True):
            text = elem.get_text(strip=True)
            # 日付パターン: 2026年5月2日(土) など
            date_match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
            if date_match:
                y, m, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                try:
                    current_date = datetime(y, m, d).strftime('%Y-%m-%d')
                except Exception:
                    pass

        # より確実な方法: テキスト全体から日付+イベント名+会場を抽出
        events = []
        full_text = resp.text
        # 日付ブロックを正規表現で抽出
        # パターン: 開催日 → 日付 → 種別 → タイトル → 会場
        date_pattern = re.compile(
            r'(\d{4})年(\d{1,2})月(\d{1,2})日[^<]*?(?:水|木|金|土|日|月|火|祝|･)*\)'
        )
        
        # BeautifulSoupで構造的に解析
        # スケジュールコンテナを探す
        schedule_container = soup.find(id='schedule-list') or soup.find(class_='p-schedule') or soup.find(class_='p-event-list')
        
        # テキストベースで解析
        raw_text = soup.get_text(separator='\n')
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        
        i = 0
        current_date_str = None
        while i < len(lines):
            line = lines[i]
            dm = re.match(r'^(\d{4})年(\d{1,2})月(\d{1,2})日', line)
            if dm:
                y, m, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                try:
                    current_date_str = datetime(y, m, d).strftime('%Y-%m-%d')
                except Exception:
                    current_date_str = None
                i += 1
                continue
            
            if current_date_str:
                # ドッグショーのイベント名を探す（「展」「クラブ」「ショー」を含む行）
                if re.search(r'展\[|展（|クラブ展|ショー展|部会展|連合会展|インターナショナル', line):
                    title = line
                    # 次の行が会場名の可能性
                    venue = ''
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        # 会場名っぽい行（市・町・区・都・道・府・県・施設・公園・広場を含む）
                        if re.search(r'市|町|区|都|道|府|県|施設|公園|広場|センター|ホール|アリーナ', next_line):
                            venue = next_line
                    
                    events.append({
                        'title': f'🐕 {title}',
                        'start': current_date_str,
                        'venue': venue,
                        'color': '#2e7d32',
                        'textColor': '#ffffff',
                        'url': 'https://www.jkc.or.jp/events/event_schedule/',
                        'extendedProps': {
                            'venue': venue,
                            'type': 'jkc_show'
                        }
                    })
            i += 1
        
        # 重複除去（同日同タイトル）
        seen = set()
        unique_events = []
        for ev in events:
            key = (ev['start'], ev['title'])
            if key not in seen:
                seen.add(key)
                unique_events.append(ev)
        
        return {'events': unique_events, 'count': len(unique_events)}
    
    except Exception as e:
        return {'events': [], 'error': str(e)}, 200


# ===========================================================================
# 繁殖意思決定支援システム - 拡張ルート
# ===========================================================================

# ---------------------------------------------------------------------------
# 健康履歴登録画面
# ---------------------------------------------------------------------------

@bp.route('/dogs/<int:dog_id>/health-records', methods=['GET', 'POST'])
def health_records(dog_id):
    """健康履歴登録・一覧画面"""
    from app.models_breeder import Dog, DogHealthRecord
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()

    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if not dog:
        return '犬が見つかりません', 404

    if request.method == 'POST':
        record = DogHealthRecord(
            dog_id=dog_id,
            record_date=request.form.get('record_date') or None,
            category=request.form.get('category') or None,
            title=request.form.get('title', ''),
            severity=request.form.get('severity') or None,
            description=request.form.get('description') or None,
            diagnosed_by_vet=1 if request.form.get('diagnosed_by_vet') else 0,
            resolved=1 if request.form.get('resolved') else 0,
            notes=request.form.get('notes') or None,
        )
        db.add(record)
        db.commit()
        return redirect(url_for('breeder.health_records', dog_id=dog_id))

    records = db.query(DogHealthRecord).filter(DogHealthRecord.dog_id == dog_id).order_by(DogHealthRecord.record_date.desc()).all()
    return render_template('breeder/health_records.html', dog=dog, records=records)


@bp.route('/dogs/<int:dog_id>/health-records/<int:record_id>/delete', methods=['POST'])
def health_record_delete(dog_id, record_id):
    from app.models_breeder import DogHealthRecord
    db = _get_db()
    r = db.query(DogHealthRecord).filter(DogHealthRecord.id == record_id, DogHealthRecord.dog_id == dog_id).first()
    if r:
        db.delete(r)
        db.commit()
    return redirect(url_for('breeder.health_records', dog_id=dog_id))


# ---------------------------------------------------------------------------
# 繁殖履歴登録画面
# ---------------------------------------------------------------------------

@bp.route('/breeding-histories', methods=['GET', 'POST'])
def breeding_histories():
    """繁殖履歴一覧・登録画面"""
    from app.models_breeder import Dog, BreedingHistory
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()

    if request.method == 'POST':
        bh = BreedingHistory(
            tenant_id=tenant_id,
            store_id=store_id,
            sire_id=int(request.form.get('sire_id')),
            dam_id=int(request.form.get('dam_id')),
            mating_date=request.form.get('mating_date') or None,
            birth_date=request.form.get('birth_date') or None,
            pregnancy_result=request.form.get('pregnancy_result') or None,
            puppy_count=int(request.form.get('puppy_count') or 0) or None,
            live_birth_count=int(request.form.get('live_birth_count') or 0) or None,
            stillbirth_count=int(request.form.get('stillbirth_count') or 0) or None,
            c_section=1 if request.form.get('c_section') else 0,
            complications=request.form.get('complications') or None,
            notes=request.form.get('notes') or None,
        )
        db.add(bh)
        db.commit()
        return redirect(url_for('breeder.breeding_histories'))

    histories = db.query(BreedingHistory).filter(
        BreedingHistory.tenant_id == tenant_id
    ).order_by(BreedingHistory.mating_date.desc()).all()

    dogs = db.query(Dog).filter(Dog.tenant_id == tenant_id).all()
    return render_template('breeder/breeding_histories.html', histories=histories, dogs=dogs)


# ---------------------------------------------------------------------------
# 産子登録画面
# ---------------------------------------------------------------------------

@bp.route('/breeding-histories/<int:history_id>/puppies', methods=['GET', 'POST'])
def puppy_records(history_id):
    """産子記録一覧・登録画面"""
    from app.models_breeder import BreedingHistory, PuppyRecord, Dog
    db = _get_db()

    history = db.query(BreedingHistory).filter(BreedingHistory.id == history_id).first()
    if not history:
        return '繁殖履歴が見つかりません', 404

    if request.method == 'POST':
        pr = PuppyRecord(
            breeding_history_id=history_id,
            puppy_id=int(request.form.get('puppy_id') or 0) or None,
            sex=request.form.get('sex') or None,
            birth_weight=float(request.form.get('birth_weight') or 0) or None,
            survived=1 if request.form.get('survived') else 0,
            death_date=request.form.get('death_date') or None,
            death_age_days=int(request.form.get('death_age_days') or 0) or None,
            health_status=request.form.get('health_status') or None,
            defects=request.form.get('defects') or None,
            notes=request.form.get('notes') or None,
        )
        db.add(pr)
        db.commit()
        return redirect(url_for('breeder.puppy_records', history_id=history_id))

    puppies = db.query(PuppyRecord).filter(PuppyRecord.breeding_history_id == history_id).all()
    dogs = db.query(Dog).all()
    return render_template('breeder/puppy_records.html', history=history, puppies=puppies, dogs=dogs)


# ---------------------------------------------------------------------------
# 産子フォローアップ画面
# ---------------------------------------------------------------------------

@bp.route('/puppy-records/<int:puppy_id>/followups', methods=['GET', 'POST'])
def puppy_followups(puppy_id):
    """産子フォローアップ一覧・登録画面"""
    from app.models_breeder import PuppyRecord, PuppyFollowUp
    db = _get_db()

    puppy = db.query(PuppyRecord).filter(PuppyRecord.id == puppy_id).first()
    if not puppy:
        return '産子記録が見つかりません', 404

    if request.method == 'POST':
        fu = PuppyFollowUp(
            puppy_id=puppy_id,
            followup_date=request.form.get('followup_date') or None,
            age_months=int(request.form.get('age_months') or 0) or None,
            weight=float(request.form.get('weight') or 0) or None,
            health_status=request.form.get('health_status') or None,
            disease_found=1 if request.form.get('disease_found') else 0,
            disease_name=request.form.get('disease_name') or None,
            temperament=request.form.get('temperament') or None,
            owner_reported=1 if request.form.get('owner_reported') else 0,
            notes=request.form.get('notes') or None,
        )
        db.add(fu)
        db.commit()
        return redirect(url_for('breeder.puppy_followups', puppy_id=puppy_id))

    followups = db.query(PuppyFollowUp).filter(PuppyFollowUp.puppy_id == puppy_id).order_by(PuppyFollowUp.followup_date.desc()).all()
    return render_template('breeder/puppy_followups.html', puppy=puppy, followups=followups)


# ---------------------------------------------------------------------------
# 候補比較画面
# ---------------------------------------------------------------------------

@bp.route('/mating-compare', methods=['GET', 'POST'])
def mating_compare():
    """交配候補比較画面"""
    from app.models_breeder import Dog
    from app.services.breeding_logic import compare_mating_candidates
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()

    dogs = db.query(Dog).filter(Dog.tenant_id == tenant_id).all()
    results = None
    fixed_dog = None
    fixed_role = 'dam'
    error = None

    if request.method == 'POST':
        try:
            fixed_dog_id = int(request.form.get('fixed_dog_id', 0))
            fixed_role   = request.form.get('fixed_role', 'dam')
            candidate_ids_raw = request.form.getlist('candidate_ids')
            candidate_ids = [int(x) for x in candidate_ids_raw if x]
            max_depth = int(request.form.get('max_depth', 5))

            if not fixed_dog_id or not candidate_ids:
                error = '固定する犬と候補犬を選択してください。'
            else:
                fixed_dog = db.query(Dog).filter(Dog.id == fixed_dog_id).first()
                results = compare_mating_candidates(
                    fixed_dog_id=fixed_dog_id,
                    fixed_role=fixed_role,
                    candidate_ids=candidate_ids,
                    max_depth=max_depth,
                    db=db,
                    use_ai_comment=False,
                )
        except Exception as e:
            error = f'比較中にエラーが発生しました: {e}'

    return render_template('breeder/mating_compare.html',
                           dogs=dogs, results=results, fixed_dog=fixed_dog,
                           fixed_role=fixed_role, error=error)


# ---------------------------------------------------------------------------
# 総合レポート画面
# ---------------------------------------------------------------------------

@bp.route('/mating-report/<int:evaluation_id>')
def mating_report(evaluation_id):
    """交配評価レポート画面"""
    import json as _json
    from app.models_breeder import MatingEvaluation, Dog
    from app.services.comment_generator import generate_ai_report_text
    db = _get_db()

    ev = db.query(MatingEvaluation).filter(MatingEvaluation.id == evaluation_id).first()
    if not ev:
        return '評価が見つかりません', 404

    result = _json.loads(ev.result_json) if ev.result_json else {}
    sire = db.query(Dog).filter(Dog.id == ev.sire_id).first()
    dam  = db.query(Dog).filter(Dog.id == ev.dam_id).first()

    report_text = generate_ai_report_text(result)

    return render_template('breeder/mating_report.html',
                           evaluation=ev, result=result,
                           sire=sire, dam=dam,
                           report_text=report_text)


@bp.route('/mating-report/<int:evaluation_id>/pdf')
def mating_report_pdf(evaluation_id):
    """交配評価レポートPDF出力"""
    import json as _json
    import subprocess, tempfile, os
    from flask import send_file
    from app.models_breeder import MatingEvaluation, Dog
    from app.services.comment_generator import generate_ai_report_text
    db = _get_db()

    ev = db.query(MatingEvaluation).filter(MatingEvaluation.id == evaluation_id).first()
    if not ev:
        return '評価が見つかりません', 404

    result = _json.loads(ev.result_json) if ev.result_json else {}
    sire = db.query(Dog).filter(Dog.id == ev.sire_id).first()
    dam  = db.query(Dog).filter(Dog.id == ev.dam_id).first()
    report_text = generate_ai_report_text(result)

    html_content = render_template('breeder/mating_report_pdf.html',
                                   evaluation=ev, result=result,
                                   sire=sire, dam=dam,
                                   report_text=report_text)

    with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as f:
        f.write(html_content)
        html_path = f.name

    pdf_path = html_path.replace('.html', '.pdf')
    try:
        subprocess.run(['manus-md-to-pdf', html_path, pdf_path], check=False, timeout=30)
        if not os.path.exists(pdf_path):
            # weasyprint フォールバック
            from weasyprint import HTML
            HTML(filename=html_path).write_pdf(pdf_path)
        return send_file(pdf_path, as_attachment=True,
                         download_name=f'mating_report_{evaluation_id}.pdf',
                         mimetype='application/pdf')
    finally:
        try:
            os.unlink(html_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 犬種別リスクマスタ管理画面
# ---------------------------------------------------------------------------

@bp.route('/breed-risks', methods=['GET', 'POST'])
def breed_risks():
    """犬種別リスクマスタ管理画面"""
    from app.models_breeder import BreedRiskMaster
    db = _get_db()

    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'add':
            risk = BreedRiskMaster(
                breed=request.form.get('breed', ''),
                risk_name=request.form.get('risk_name', ''),
                risk_category=request.form.get('risk_category') or None,
                severity=request.form.get('severity') or None,
                description=request.form.get('description') or None,
                recommended_test=request.form.get('recommended_test') or None,
                notes=request.form.get('notes') or None,
            )
            db.add(risk)
            db.commit()
        elif action == 'delete':
            risk_id = int(request.form.get('risk_id', 0))
            r = db.query(BreedRiskMaster).filter(BreedRiskMaster.id == risk_id).first()
            if r:
                db.delete(r)
                db.commit()
        return redirect(url_for('breeder.breed_risks'))

    risks = db.query(BreedRiskMaster).order_by(BreedRiskMaster.breed, BreedRiskMaster.risk_name).all()
    return render_template('breeder/breed_risks.html', risks=risks)


# ---------------------------------------------------------------------------
# API エンドポイント
# ---------------------------------------------------------------------------

@bp.route('/api/dogs', methods=['GET'])
def api_dogs_list():
    """GET /api/dogs - 犬一覧API"""
    from app.models_breeder import Dog
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()
    dogs = db.query(Dog).filter(Dog.tenant_id == tenant_id).all()
    return jsonify([{
        'id': d.id, 'name': d.name, 'breed': d.breed,
        'sex': d.sex, 'birth_date': str(d.birth_date) if d.birth_date else None,
    } for d in dogs])


@bp.route('/api/dogs', methods=['POST'])
def api_dog_create():
    """POST /api/dogs - 犬登録API"""
    from app.models_breeder import Dog
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()
    data = request.get_json() or {}
    dog = Dog(
        tenant_id=tenant_id, store_id=store_id,
        name=data.get('name', ''),
        breed=data.get('breed'),
        sex=data.get('sex'),
        birth_date=data.get('birth_date'),
    )
    db.add(dog)
    db.commit()
    return jsonify({'id': dog.id, 'name': dog.name}), 201


@bp.route('/api/dogs/<int:dog_id>', methods=['GET'])
def api_dog_detail(dog_id):
    """GET /api/dogs/{dog_id} - 犬詳細API"""
    from app.models_breeder import Dog
    db = _get_db()
    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if not dog:
        return jsonify({'error': 'not found'}), 404
    return jsonify({
        'id': dog.id, 'name': dog.name, 'breed': dog.breed,
        'sex': dog.sex, 'birth_date': str(dog.birth_date) if dog.birth_date else None,
    })


@bp.route('/api/health-records', methods=['POST'])
def api_health_record_create():
    """POST /api/health-records - 健康履歴登録API"""
    from app.models_breeder import DogHealthRecord
    db = _get_db()
    data = request.get_json() or {}
    r = DogHealthRecord(
        dog_id=data.get('dog_id'),
        record_date=data.get('record_date'),
        category=data.get('category'),
        title=data.get('title', ''),
        severity=data.get('severity'),
        description=data.get('description'),
        diagnosed_by_vet=data.get('diagnosed_by_vet', 0),
        resolved=data.get('resolved', 0),
        notes=data.get('notes'),
    )
    db.add(r)
    db.commit()
    return jsonify({'id': r.id}), 201


@bp.route('/api/breeding-histories', methods=['POST'])
def api_breeding_history_create():
    """POST /api/breeding-histories - 繁殖履歴登録API"""
    from app.models_breeder import BreedingHistory
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()
    data = request.get_json() or {}
    bh = BreedingHistory(
        tenant_id=tenant_id, store_id=store_id,
        sire_id=data.get('sire_id'),
        dam_id=data.get('dam_id'),
        mating_date=data.get('mating_date'),
        birth_date=data.get('birth_date'),
        pregnancy_result=data.get('pregnancy_result'),
        puppy_count=data.get('puppy_count'),
        live_birth_count=data.get('live_birth_count'),
        stillbirth_count=data.get('stillbirth_count'),
        c_section=data.get('c_section', 0),
        complications=data.get('complications'),
        notes=data.get('notes'),
    )
    db.add(bh)
    db.commit()
    return jsonify({'id': bh.id}), 201


@bp.route('/api/puppy-records', methods=['POST'])
def api_puppy_record_create():
    """POST /api/puppy-records - 産子記録登録API"""
    from app.models_breeder import PuppyRecord
    db = _get_db()
    data = request.get_json() or {}
    pr = PuppyRecord(
        breeding_history_id=data.get('breeding_history_id'),
        puppy_id=data.get('puppy_id'),
        sex=data.get('sex'),
        birth_weight=data.get('birth_weight'),
        survived=data.get('survived', 1),
        death_date=data.get('death_date'),
        death_age_days=data.get('death_age_days'),
        health_status=data.get('health_status'),
        defects=data.get('defects'),
        notes=data.get('notes'),
    )
    db.add(pr)
    db.commit()
    return jsonify({'id': pr.id}), 201


@bp.route('/api/puppy-followups', methods=['POST'])
def api_puppy_followup_create():
    """POST /api/puppy-followups - 産子フォローアップ登録API"""
    from app.models_breeder import PuppyFollowUp
    db = _get_db()
    data = request.get_json() or {}
    fu = PuppyFollowUp(
        puppy_id=data.get('puppy_id'),
        followup_date=data.get('followup_date'),
        age_months=data.get('age_months'),
        weight=data.get('weight'),
        health_status=data.get('health_status'),
        disease_found=data.get('disease_found', 0),
        disease_name=data.get('disease_name'),
        temperament=data.get('temperament'),
        owner_reported=data.get('owner_reported', 0),
        notes=data.get('notes'),
    )
    db.add(fu)
    db.commit()
    return jsonify({'id': fu.id}), 201


@bp.route('/api/mating/evaluate', methods=['POST'])
def api_mating_evaluate():
    """POST /api/mating/evaluate - 交配総合評価API"""
    import json as _json
    from app.models_breeder import Dog, MatingEvaluation
    from app.services.breeding_logic import evaluate_mating_compatibility_full
    db = _get_db()
    tenant_id, store_id = _get_tenant_store()
    data = request.get_json() or {}

    sire_id   = data.get('sire_id')
    dam_id    = data.get('dam_id')
    max_depth = data.get('max_depth', 5)
    use_ai    = data.get('use_ai_comment', False)

    if not sire_id or not dam_id:
        return jsonify({'error': 'sire_id と dam_id は必須です'}), 400

    sire = db.query(Dog).filter(Dog.id == sire_id).first()
    dam  = db.query(Dog).filter(Dog.id == dam_id).first()

    result = evaluate_mating_compatibility_full(
        sire_id=sire_id, dam_id=dam_id,
        max_depth=max_depth, db=db,
        use_ai_comment=use_ai,
        sire_breed=sire.breed if sire else None,
        dam_breed=dam.breed if dam else None,
    )

    ev = MatingEvaluation(
        tenant_id=tenant_id, store_id=store_id,
        sire_id=sire_id, dam_id=dam_id,
        coi=result.get('coi', 0),
        coi_percent=result.get('coi_percent', 0),
        rank=result.get('rank', ''),
        recommendation=result.get('judgment', ''),
        result_json=_json.dumps(result, ensure_ascii=False),
        max_depth=max_depth,
    )
    db.add(ev)
    db.commit()

    result['evaluation_id'] = ev.id
    return jsonify(result)


@bp.route('/api/mating/compare-candidates', methods=['POST'])
def api_mating_compare():
    """POST /api/mating/compare-candidates - 候補比較API"""
    from app.models_breeder import Dog
    from app.services.breeding_logic import compare_mating_candidates
    db = _get_db()
    data = request.get_json() or {}

    fixed_dog_id  = data.get('fixed_dog_id')
    fixed_role    = data.get('fixed_role', 'dam')
    candidate_ids = data.get('candidate_ids', [])
    max_depth     = data.get('max_depth', 5)

    if not fixed_dog_id or not candidate_ids:
        return jsonify({'error': 'fixed_dog_id と candidate_ids は必須です'}), 400

    results = compare_mating_candidates(
        fixed_dog_id=fixed_dog_id,
        fixed_role=fixed_role,
        candidate_ids=candidate_ids,
        max_depth=max_depth,
        db=db,
    )
    return jsonify({'candidate_rankings': results})


@bp.route('/api/mating/evaluations/<int:evaluation_id>', methods=['GET'])
def api_mating_evaluation_get(evaluation_id):
    """GET /api/mating/evaluations/{evaluation_id} - 評価取得API"""
    import json as _json
    from app.models_breeder import MatingEvaluation
    db = _get_db()
    ev = db.query(MatingEvaluation).filter(MatingEvaluation.id == evaluation_id).first()
    if not ev:
        return jsonify({'error': 'not found'}), 404
    result = _json.loads(ev.result_json) if ev.result_json else {}
    result['evaluation_id'] = ev.id
    return jsonify(result)


@bp.route('/api/mating/evaluations/<int:evaluation_id>/report', methods=['GET'])
def api_mating_evaluation_report(evaluation_id):
    """GET /api/mating/evaluations/{evaluation_id}/report - レポートJSON取得API"""
    import json as _json
    from app.models_breeder import MatingEvaluation, Dog
    from app.services.comment_generator import generate_ai_report_text
    db = _get_db()
    ev = db.query(MatingEvaluation).filter(MatingEvaluation.id == evaluation_id).first()
    if not ev:
        return jsonify({'error': 'not found'}), 404
    result = _json.loads(ev.result_json) if ev.result_json else {}
    sire = db.query(Dog).filter(Dog.id == ev.sire_id).first()
    dam  = db.query(Dog).filter(Dog.id == ev.dam_id).first()
    report_text = generate_ai_report_text(result)
    return jsonify({
        'evaluation_id': ev.id,
        'sire': {'id': sire.id, 'name': sire.name} if sire else None,
        'dam':  {'id': dam.id,  'name': dam.name}  if dam  else None,
        'report': report_text,
        'result': result,
    })


@bp.route('/api/breed-risks', methods=['GET'])
def api_breed_risks_list():
    """GET /api/breed-risks - 犬種別リスクマスタ一覧API"""
    from app.models_breeder import BreedRiskMaster
    db = _get_db()
    risks = db.query(BreedRiskMaster).all()
    return jsonify([{
        'id': r.id, 'breed': r.breed, 'risk_name': r.risk_name,
        'risk_category': r.risk_category, 'severity': r.severity,
        'description': r.description, 'recommended_test': r.recommended_test,
    } for r in risks])


@bp.route('/api/breed-risks', methods=['POST'])
def api_breed_risk_create():
    """POST /api/breed-risks - 犬種別リスクマスタ登録API"""
    from app.models_breeder import BreedRiskMaster
    db = _get_db()
    data = request.get_json() or {}
    r = BreedRiskMaster(
        breed=data.get('breed', ''),
        risk_name=data.get('risk_name', ''),
        risk_category=data.get('risk_category'),
        severity=data.get('severity'),
        description=data.get('description'),
        recommended_test=data.get('recommended_test'),
        notes=data.get('notes'),
    )
    db.add(r)
    db.commit()
    return jsonify({'id': r.id}), 201


# ═══════════════════════════════════════════════════════════════
# 飼い主アプリ連携 API（Owner / OwnerDog / HealthLog / MedicalEvent / LifeStatus / DeathInfo）
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# POST /api/owners  飼い主登録
# ─────────────────────────────────────────────
@bp.route('/api/owners', methods=['POST'])
def api_owner_create():
    """POST /api/owners - 飼い主登録API"""
    from app.models_breeder import Owner
    db = _get_db()
    data = request.get_json() or {}
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    o = Owner(
        tenant_id=tenant_id,
        store_id=store_id,
        name=data.get('name', ''),
        email=data.get('email'),
        phone=data.get('phone'),
        notes=data.get('notes'),
    )
    db.add(o)
    db.commit()
    return jsonify({'id': o.id, 'name': o.name}), 201


@bp.route('/api/owners', methods=['GET'])
def api_owners_list():
    """GET /api/owners - 飼い主一覧API"""
    from app.models_breeder import Owner
    db = _get_db()
    tenant_id = session.get('tenant_id')
    q = db.query(Owner)
    if tenant_id:
        q = q.filter(Owner.tenant_id == tenant_id)
    owners = q.order_by(Owner.created_at.desc()).all()
    return jsonify([{
        'id': o.id, 'name': o.name, 'email': o.email,
        'phone': o.phone, 'created_at': str(o.created_at),
    } for o in owners])


# ─────────────────────────────────────────────
# POST /api/owner-dogs  飼い主×犬紐付け登録
# ─────────────────────────────────────────────
@bp.route('/api/owner-dogs', methods=['POST'])
def api_owner_dog_create():
    """POST /api/owner-dogs - 飼い主×犬紐付け登録API"""
    from app.models_breeder import OwnerDog
    db = _get_db()
    data = request.get_json() or {}
    od = OwnerDog(
        owner_id=data.get('owner_id'),
        dog_id=data.get('dog_id'),
        nickname=data.get('nickname'),
        acquired_date=data.get('acquired_date'),
        breeder_id=data.get('breeder_id'),
        share_health_data=int(data.get('share_health_data', 0)),
        share_followup_data=int(data.get('share_followup_data', 0)),
    )
    db.add(od)
    db.commit()
    return jsonify({'id': od.id}), 201


# ─────────────────────────────────────────────
# POST /api/health-logs  健康ログ記録
# ─────────────────────────────────────────────
@bp.route('/api/health-logs', methods=['POST'])
def api_health_log_create():
    """POST /api/health-logs - 健康ログ記録API（体重・食欲・活動量など）"""
    from app.models_breeder import HealthLog
    from datetime import date as _date
    db = _get_db()
    data = request.get_json() or {}
    log = HealthLog(
        owner_dog_id=data.get('owner_dog_id'),
        log_date=data.get('log_date') or str(_date.today()),
        weight=data.get('weight'),
        food_type=data.get('food_type'),
        activity_level=data.get('activity_level'),
        appetite=data.get('appetite'),
        stool_condition=data.get('stool_condition'),
        notes=data.get('notes'),
    )
    db.add(log)
    db.commit()
    return jsonify({'id': log.id}), 201


@bp.route('/api/health-logs/<int:owner_dog_id>', methods=['GET'])
def api_health_logs_list(owner_dog_id):
    """GET /api/health-logs/{owner_dog_id} - 健康ログ一覧API"""
    from app.models_breeder import HealthLog
    db = _get_db()
    logs = db.query(HealthLog).filter(
        HealthLog.owner_dog_id == owner_dog_id
    ).order_by(HealthLog.log_date.desc()).all()
    return jsonify([{
        'id': l.id, 'log_date': str(l.log_date), 'weight': float(l.weight) if l.weight else None,
        'food_type': l.food_type, 'activity_level': l.activity_level,
        'appetite': l.appetite, 'stool_condition': l.stool_condition, 'notes': l.notes,
    } for l in logs])


# ─────────────────────────────────────────────
# POST /api/medical-events  医療イベント記録
# ─────────────────────────────────────────────
@bp.route('/api/medical-events', methods=['POST'])
def api_medical_event_create():
    """POST /api/medical-events - 通院・病気・ワクチン等の医療イベント記録API"""
    from app.models_breeder import MedicalEvent
    from datetime import date as _date
    db = _get_db()
    data = request.get_json() or {}
    ev = MedicalEvent(
        owner_dog_id=data.get('owner_dog_id'),
        event_date=data.get('event_date') or str(_date.today()),
        category=data.get('category', 'other'),
        title=data.get('title', ''),
        severity=data.get('severity'),
        diagnosed_by_vet=int(data.get('diagnosed_by_vet', 0)),
        treatment=data.get('treatment'),
        resolved=int(data.get('resolved', 0)),
        notes=data.get('notes'),
    )
    db.add(ev)
    db.commit()
    return jsonify({'id': ev.id}), 201


@bp.route('/api/medical-events/<int:owner_dog_id>', methods=['GET'])
def api_medical_events_list(owner_dog_id):
    """GET /api/medical-events/{owner_dog_id} - 医療イベント一覧API"""
    from app.models_breeder import MedicalEvent
    db = _get_db()
    events = db.query(MedicalEvent).filter(
        MedicalEvent.owner_dog_id == owner_dog_id
    ).order_by(MedicalEvent.event_date.desc()).all()
    return jsonify([{
        'id': e.id, 'event_date': str(e.event_date), 'category': e.category,
        'title': e.title, 'severity': e.severity,
        'diagnosed_by_vet': bool(e.diagnosed_by_vet),
        'treatment': e.treatment, 'resolved': bool(e.resolved), 'notes': e.notes,
    } for e in events])


# ─────────────────────────────────────────────
# POST /api/life-status  生活ステータス変更
# ─────────────────────────────────────────────
@bp.route('/api/life-status', methods=['POST'])
def api_life_status_create():
    """
    POST /api/life-status - ステータス変更API
    設計思想：「死亡しましたか？」と直接聞かず、
    「現在の状態を教えてください」として状態遷移で取得する。
    """
    from app.models_breeder import LifeStatus
    from datetime import date as _date
    db = _get_db()
    data = request.get_json() or {}
    ls = LifeStatus(
        owner_dog_id=data.get('owner_dog_id'),
        status=data.get('status', 'healthy'),
        status_date=data.get('status_date') or str(_date.today()),
        age_months=data.get('age_months'),
        notes=data.get('notes'),
    )
    db.add(ls)
    db.commit()
    return jsonify({'id': ls.id, 'status': ls.status}), 201


@bp.route('/api/life-status/<int:owner_dog_id>', methods=['GET'])
def api_life_status_list(owner_dog_id):
    """GET /api/life-status/{owner_dog_id} - ステータス履歴一覧API"""
    from app.models_breeder import LifeStatus
    db = _get_db()
    statuses = db.query(LifeStatus).filter(
        LifeStatus.owner_dog_id == owner_dog_id
    ).order_by(LifeStatus.status_date.desc()).all()
    return jsonify([{
        'id': s.id, 'status': s.status, 'status_date': str(s.status_date),
        'age_months': s.age_months, 'notes': s.notes,
    } for s in statuses])


# ─────────────────────────────────────────────
# POST /api/death-info  死亡情報登録（選択式・センシティブ設計）
# ─────────────────────────────────────────────
@bp.route('/api/death-info', methods=['POST'])
def api_death_info_create():
    """
    POST /api/death-info - 死亡情報登録API
    設計思想：年齢を直接入力させず選択式（age_range）で取得する。
    個人情報は一切収集しない。
    """
    from app.models_breeder import DeathInfo
    db = _get_db()
    data = request.get_json() or {}
    di = DeathInfo(
        owner_dog_id=data.get('owner_dog_id'),
        estimated_age_range=data.get('estimated_age_range'),
        cause_category=data.get('cause_category', 'unknown'),
        notes=data.get('notes'),
    )
    db.add(di)
    db.commit()
    return jsonify({'id': di.id}), 201


# ─────────────────────────────────────────────
# GET /api/owner-dogs/{id}/dashboard  飼い主ダッシュボード
# ─────────────────────────────────────────────
@bp.route('/api/owner-dogs/<int:owner_dog_id>/dashboard', methods=['GET'])
def api_owner_dog_dashboard(owner_dog_id):
    """
    GET /api/owner-dogs/{id}/dashboard - 飼い主向け健康ダッシュボードAPI
    体重推移・医療イベント・ワクチンアラート・シニア通知を一括返却する。
    """
    from app.models_breeder import (
        OwnerDog, Dog, HealthLog, MedicalEvent, LifeStatus, VaccineSchedule
    )
    from app.services.survival_analysis import (
        analyze_weight_trend, generate_vaccine_alerts, check_senior_notification
    )
    from datetime import date as _date
    db = _get_db()

    od = db.query(OwnerDog).filter(OwnerDog.id == owner_dog_id).first()
    if not od:
        return jsonify({'error': 'Not found'}), 404

    dog = db.query(Dog).filter(Dog.id == od.dog_id).first()

    # 健康ログ（直近90件）
    logs = db.query(HealthLog).filter(
        HealthLog.owner_dog_id == owner_dog_id
    ).order_by(HealthLog.log_date.desc()).limit(90).all()

    log_dicts = [{'log_date': l.log_date, 'weight': l.weight} for l in logs]
    weight_trend = analyze_weight_trend(log_dicts)

    # 医療イベント（直近10件）
    events = db.query(MedicalEvent).filter(
        MedicalEvent.owner_dog_id == owner_dog_id
    ).order_by(MedicalEvent.event_date.desc()).limit(10).all()

    # 現在のステータス
    latest_status = db.query(LifeStatus).filter(
        LifeStatus.owner_dog_id == owner_dog_id
    ).order_by(LifeStatus.status_date.desc()).first()

    # ワクチンアラート
    schedules = db.query(VaccineSchedule).filter(
        VaccineSchedule.owner_dog_id == owner_dog_id
    ).all()
    schedule_dicts = [{
        'id': s.id, 'vaccine_type': s.vaccine_type,
        'scheduled_date': s.scheduled_date, 'is_completed': s.is_completed,
    } for s in schedules]
    vaccine_alerts = generate_vaccine_alerts(schedule_dicts)

    # シニア通知
    birth_date = dog.birth_date if dog else None
    senior_info = check_senior_notification(birth_date)

    return jsonify({
        'owner_dog_id': owner_dog_id,
        'dog': {
            'id': dog.id if dog else None,
            'name': dog.name if dog else None,
            'nickname': od.nickname,
            'breed': dog.breed if dog else None,
            'birth_date': str(dog.birth_date) if dog and dog.birth_date else None,
        },
        'current_status': latest_status.status if latest_status else 'healthy',
        'weight_trend': weight_trend,
        'recent_medical_events': [{
            'id': e.id, 'event_date': str(e.event_date), 'category': e.category,
            'title': e.title, 'severity': e.severity, 'resolved': bool(e.resolved),
        } for e in events],
        'vaccine_alerts': vaccine_alerts,
        'senior_info': senior_info,
    })


# ─────────────────────────────────────────────
# GET /api/analytics/survival  生存分析API
# ─────────────────────────────────────────────
@bp.route('/api/analytics/survival', methods=['GET'])
def api_analytics_survival():
    """
    GET /api/analytics/survival - カプランマイヤー生存分析API
    クエリパラメータ: breed（犬種）, tenant_id（テナント）
    """
    from app.models_breeder import OwnerDog, Dog, LifeStatus, DeathInfo
    from app.services.survival_analysis import (
        kaplan_meier_estimate, make_survival_record,
        greenwood_confidence_interval
    )
    db = _get_db()
    breed_filter = request.args.get('breed')
    tenant_id = session.get('tenant_id')

    # share_health_data=1 の OwnerDog のみ対象（プライバシー設計）
    q = db.query(OwnerDog).filter(OwnerDog.share_health_data == 1)
    if tenant_id:
        # breeder_id でフィルタ（ブリーダーは自分のテナントのデータのみ）
        q = q.filter(OwnerDog.breeder_id == tenant_id)
    owner_dogs = q.all()

    records = []
    for od in owner_dogs:
        dog = db.query(Dog).filter(Dog.id == od.dog_id).first()
        if not dog:
            continue
        if breed_filter and dog.breed != breed_filter:
            continue

        # 最新ステータスを確認
        latest_status = db.query(LifeStatus).filter(
            LifeStatus.owner_dog_id == od.id
        ).order_by(LifeStatus.status_date.desc()).first()

        is_deceased = latest_status and latest_status.status == 'deceased'

        # 死亡情報（選択式年齢帯）
        death_info = db.query(DeathInfo).filter(
            DeathInfo.owner_dog_id == od.id
        ).first()

        age_months = None
        age_range = None
        if is_deceased:
            if latest_status and latest_status.age_months:
                age_months = latest_status.age_months
            elif death_info:
                age_range = death_info.estimated_age_range
        else:
            # 生存中: 現在の月齢を計算
            if dog.birth_date:
                from datetime import date as _date
                today = _date.today()
                age_months = (today.year - dog.birth_date.year) * 12 + (
                    today.month - dog.birth_date.month
                )

        rec = make_survival_record(
            dog_id=dog.id,
            age_months=age_months,
            is_deceased=is_deceased,
            age_range=age_range,
        )
        records.append(rec)

    from app.services.survival_analysis import kaplan_meier_estimate, greenwood_confidence_interval
    km = kaplan_meier_estimate(records)
    curve_with_ci = greenwood_confidence_interval(km['survival_curve'])
    km['survival_curve'] = curve_with_ci

    return jsonify({
        'breed': breed_filter or 'all',
        'survival_analysis': km,
    })


# ─────────────────────────────────────────────
# GET /api/analytics/line-performance  ライン別分析API
# ─────────────────────────────────────────────
@bp.route('/api/analytics/line-performance', methods=['GET'])
def api_analytics_line_performance():
    """
    GET /api/analytics/line-performance - ライン別パフォーマンス分析API
    クエリパラメータ: ancestor_id（祖先犬ID）
    """
    from app.models_breeder import (
        Dog, OwnerDog, LifeStatus, DeathInfo, MedicalEvent, PuppyRecord
    )
    from app.services.survival_analysis import (
        make_survival_record, analyze_line_performance
    )
    from app.services.breeding_logic import get_ancestors
    db = _get_db()

    ancestor_id = request.args.get('ancestor_id', type=int)
    if not ancestor_id:
        return jsonify({'error': 'ancestor_id is required'}), 400

    ancestor = db.query(Dog).filter(Dog.id == ancestor_id).first()
    if not ancestor:
        return jsonify({'error': 'Ancestor not found'}), 404

    # 祖先の子孫を取得（breeding_logicのget_ancestorsを逆引き）
    # 全犬の祖先を調べて ancestor_id が含まれるものを子孫とする
    all_dogs = db.query(Dog).filter(Dog.id != ancestor_id).all()
    descendant_ids = []
    for dog in all_dogs:
        ancestors = get_ancestors(db, dog.id, max_depth=5)
        if ancestor_id in ancestors:
            descendant_ids.append(dog.id)

    # 子孫の生存レコードを作成
    survival_records = []
    for dog_id in descendant_ids:
        od = db.query(OwnerDog).filter(
            OwnerDog.dog_id == dog_id,
            OwnerDog.share_health_data == 1
        ).first()
        if not od:
            continue

        latest_status = db.query(LifeStatus).filter(
            LifeStatus.owner_dog_id == od.id
        ).order_by(LifeStatus.status_date.desc()).first()

        is_deceased = latest_status and latest_status.status == 'deceased'
        death_info = db.query(DeathInfo).filter(
            DeathInfo.owner_dog_id == od.id
        ).first()

        dog = db.query(Dog).filter(Dog.id == dog_id).first()
        age_months = None
        age_range = None
        if is_deceased:
            if latest_status and latest_status.age_months:
                age_months = latest_status.age_months
            elif death_info:
                age_range = death_info.estimated_age_range
        else:
            if dog and dog.birth_date:
                from datetime import date as _date
                today = _date.today()
                age_months = (today.year - dog.birth_date.year) * 12 + (
                    today.month - dog.birth_date.month
                )

        survival_records.append(make_survival_record(
            dog_id=dog_id,
            age_months=age_months,
            is_deceased=is_deceased,
            age_range=age_range,
        ))

    # 医療イベント
    medical_events = []
    for dog_id in descendant_ids:
        od = db.query(OwnerDog).filter(
            OwnerDog.dog_id == dog_id,
            OwnerDog.share_health_data == 1
        ).first()
        if not od:
            continue
        events = db.query(MedicalEvent).filter(
            MedicalEvent.owner_dog_id == od.id
        ).all()
        for e in events:
            medical_events.append({
                'dog_id': dog_id,
                'title': e.title,
                'category': e.category,
                'severity': e.severity,
            })

    # 繁殖結果
    breeding_results = []
    puppies = db.query(PuppyRecord).filter(
        PuppyRecord.dog_id.in_(descendant_ids)
    ).all() if descendant_ids else []
    # litter_id でグループ化
    litter_map = {}
    for p in puppies:
        lid = p.litter_id or p.id
        if lid not in litter_map:
            litter_map[lid] = {'litter_id': lid, 'puppy_count': 0, 'survival_count': 0}
        litter_map[lid]['puppy_count'] += 1
        if p.status not in ('deceased', 'stillborn'):
            litter_map[lid]['survival_count'] += 1
    breeding_results = list(litter_map.values())

    result = analyze_line_performance(
        ancestor_id=ancestor_id,
        ancestor_name=ancestor.name,
        descendant_records=survival_records,
        medical_events=medical_events,
        breeding_results=breeding_results,
    )

    return jsonify({'line_analysis': result})


# ─────────────────────────────────────────────
# ワクチンスケジュール管理
# ─────────────────────────────────────────────
@bp.route('/api/vaccine-schedules', methods=['POST'])
def api_vaccine_schedule_create():
    """POST /api/vaccine-schedules - ワクチン・予防薬スケジュール登録API"""
    from app.models_breeder import VaccineSchedule
    db = _get_db()
    data = request.get_json() or {}
    vs = VaccineSchedule(
        owner_dog_id=data.get('owner_dog_id'),
        vaccine_type=data.get('vaccine_type', ''),
        scheduled_date=data.get('scheduled_date'),
        completed_date=data.get('completed_date'),
        is_completed=int(data.get('is_completed', 0)),
        notes=data.get('notes'),
    )
    db.add(vs)
    db.commit()
    return jsonify({'id': vs.id}), 201


@bp.route('/api/vaccine-schedules/<int:owner_dog_id>', methods=['GET'])
def api_vaccine_schedules_list(owner_dog_id):
    """GET /api/vaccine-schedules/{owner_dog_id} - ワクチンスケジュール一覧API"""
    from app.models_breeder import VaccineSchedule
    from app.services.survival_analysis import generate_vaccine_alerts
    db = _get_db()
    schedules = db.query(VaccineSchedule).filter(
        VaccineSchedule.owner_dog_id == owner_dog_id
    ).order_by(VaccineSchedule.scheduled_date).all()

    schedule_dicts = [{
        'id': s.id, 'vaccine_type': s.vaccine_type,
        'scheduled_date': s.scheduled_date, 'is_completed': s.is_completed,
    } for s in schedules]
    alerts = generate_vaccine_alerts(schedule_dicts)

    return jsonify({
        'schedules': [{
            'id': s.id, 'vaccine_type': s.vaccine_type,
            'scheduled_date': str(s.scheduled_date),
            'completed_date': str(s.completed_date) if s.completed_date else None,
            'is_completed': bool(s.is_completed), 'notes': s.notes,
        } for s in schedules],
        'alerts': alerts,
    })


# ═══════════════════════════════════════════════════════════════
# 飼い主向けUIルート
# ═══════════════════════════════════════════════════════════════

@bp.route('/owner/<int:owner_dog_id>/dashboard')
def owner_dashboard(owner_dog_id):
    """飼い主向け健康ダッシュボード"""
    from app.models_breeder import OwnerDog, Dog, HealthLog, MedicalEvent, LifeStatus, VaccineSchedule
    from app.services.survival_analysis import (
        analyze_weight_trend, generate_vaccine_alerts, check_senior_notification
    )
    from datetime import date as _date
    db = _get_db()

    od = db.query(OwnerDog).filter(OwnerDog.id == owner_dog_id).first()
    if not od:
        return "Not found", 404

    dog = db.query(Dog).filter(Dog.id == od.dog_id).first()

    logs = db.query(HealthLog).filter(
        HealthLog.owner_dog_id == owner_dog_id
    ).order_by(HealthLog.log_date.desc()).limit(90).all()
    log_dicts = [{'log_date': l.log_date, 'weight': l.weight} for l in logs]
    weight_trend = analyze_weight_trend(log_dicts)

    events = db.query(MedicalEvent).filter(
        MedicalEvent.owner_dog_id == owner_dog_id
    ).order_by(MedicalEvent.event_date.desc()).limit(10).all()

    latest_status = db.query(LifeStatus).filter(
        LifeStatus.owner_dog_id == owner_dog_id
    ).order_by(LifeStatus.status_date.desc()).first()

    schedules = db.query(VaccineSchedule).filter(
        VaccineSchedule.owner_dog_id == owner_dog_id
    ).all()
    schedule_dicts = [{
        'id': s.id, 'vaccine_type': s.vaccine_type,
        'scheduled_date': s.scheduled_date, 'is_completed': s.is_completed,
    } for s in schedules]
    vaccine_alerts = generate_vaccine_alerts(schedule_dicts)

    birth_date = dog.birth_date if dog else None
    senior_info = check_senior_notification(birth_date)

    return render_template('owner/owner_dashboard.html',
        owner_dog_id=owner_dog_id,
        dog={
            'id': dog.id if dog else None,
            'name': dog.name if dog else '不明',
            'nickname': od.nickname,
            'breed': dog.breed if dog else None,
            'birth_date': str(dog.birth_date) if dog and dog.birth_date else None,
        },
        current_status=latest_status.status if latest_status else 'healthy',
        weight_trend=weight_trend,
        recent_medical_events=[{
            'id': e.id, 'event_date': str(e.event_date), 'category': e.category,
            'title': e.title, 'severity': e.severity, 'resolved': bool(e.resolved),
        } for e in events],
        vaccine_alerts=vaccine_alerts,
        senior_info=senior_info,
    )


@bp.route('/owner/<int:owner_dog_id>/health-log/new')
def owner_health_log_new(owner_dog_id):
    """健康ログ記録フォーム"""
    from app.models_breeder import OwnerDog, Dog
    from datetime import date as _date
    db = _get_db()
    od = db.query(OwnerDog).filter(OwnerDog.id == owner_dog_id).first()
    dog = db.query(Dog).filter(Dog.id == od.dog_id).first() if od else None
    return render_template('owner/owner_health_log_form.html',
        owner_dog_id=owner_dog_id,
        dog={'name': dog.name if dog else '不明', 'nickname': od.nickname if od else None},
        today=str(_date.today()),
    )


@bp.route('/owner/<int:owner_dog_id>/health-log', methods=['POST'])
def owner_health_log_create(owner_dog_id):
    """健康ログ記録処理"""
    from app.models_breeder import HealthLog
    db = _get_db()
    data = request.form
    log = HealthLog(
        owner_dog_id=owner_dog_id,
        log_date=data.get('log_date'),
        weight=data.get('weight') or None,
        food_type=data.get('food_type'),
        activity_level=data.get('activity_level'),
        appetite=data.get('appetite'),
        stool_condition=data.get('stool_condition'),
        notes=data.get('notes'),
    )
    db.add(log)
    db.commit()
    return redirect(url_for('breeder.owner_dashboard', owner_dog_id=owner_dog_id))


@bp.route('/owner/<int:owner_dog_id>/status')
def owner_status_update(owner_dog_id):
    """状態更新フォーム"""
    from app.models_breeder import OwnerDog, Dog, LifeStatus
    from datetime import date as _date
    db = _get_db()
    od = db.query(OwnerDog).filter(OwnerDog.id == owner_dog_id).first()
    dog = db.query(Dog).filter(Dog.id == od.dog_id).first() if od else None
    latest = db.query(LifeStatus).filter(
        LifeStatus.owner_dog_id == owner_dog_id
    ).order_by(LifeStatus.status_date.desc()).first()
    return render_template('owner/owner_status_update.html',
        owner_dog_id=owner_dog_id,
        dog={'name': dog.name if dog else '不明', 'nickname': od.nickname if od else None},
        current_status=latest.status if latest else 'healthy',
        today=str(_date.today()),
    )


@bp.route('/owner/<int:owner_dog_id>/status', methods=['POST'])
def owner_status_update_create(owner_dog_id):
    """状態更新処理（死亡情報も同時登録）"""
    from app.models_breeder import LifeStatus, DeathInfo
    db = _get_db()
    data = request.form
    status = data.get('status', 'healthy')

    ls = LifeStatus(
        owner_dog_id=owner_dog_id,
        status=status,
        status_date=data.get('status_date'),
        notes=data.get('notes'),
    )
    db.add(ls)

    if status == 'deceased' and data.get('estimated_age_range'):
        di = DeathInfo(
            owner_dog_id=owner_dog_id,
            estimated_age_range=data.get('estimated_age_range'),
            cause_category=data.get('cause_category', 'unknown'),
            notes=data.get('notes'),
        )
        db.add(di)

    db.commit()
    return redirect(url_for('breeder.owner_dashboard', owner_dog_id=owner_dog_id))


@bp.route('/owner/<int:owner_dog_id>/medical-events')
def owner_medical_event_list(owner_dog_id):
    """通院履歴一覧"""
    from app.models_breeder import OwnerDog, Dog, MedicalEvent
    db = _get_db()
    od = db.query(OwnerDog).filter(OwnerDog.id == owner_dog_id).first()
    dog = db.query(Dog).filter(Dog.id == od.dog_id).first() if od else None
    events = db.query(MedicalEvent).filter(
        MedicalEvent.owner_dog_id == owner_dog_id
    ).order_by(MedicalEvent.event_date.desc()).all()
    return render_template('owner/owner_medical_event_form.html',
        owner_dog_id=owner_dog_id,
        dog={'name': dog.name if dog else '不明', 'nickname': od.nickname if od else None},
        events=events,
        today=str(__import__('datetime').date.today()),
    )


@bp.route('/owner/<int:owner_dog_id>/medical-events/new')
def owner_medical_event_new(owner_dog_id):
    """医療イベント記録フォーム"""
    from app.models_breeder import OwnerDog, Dog
    from datetime import date as _date
    db = _get_db()
    od = db.query(OwnerDog).filter(OwnerDog.id == owner_dog_id).first()
    dog = db.query(Dog).filter(Dog.id == od.dog_id).first() if od else None
    return render_template('owner/owner_medical_event_form.html',
        owner_dog_id=owner_dog_id,
        dog={'name': dog.name if dog else '不明', 'nickname': od.nickname if od else None},
        today=str(_date.today()),
    )


@bp.route('/owner/<int:owner_dog_id>/medical-events', methods=['POST'])
def owner_medical_event_create(owner_dog_id):
    """医療イベント記録処理"""
    from app.models_breeder import MedicalEvent
    db = _get_db()
    data = request.form
    ev = MedicalEvent(
        owner_dog_id=owner_dog_id,
        event_date=data.get('event_date'),
        category=data.get('category', 'other'),
        title=data.get('title', ''),
        severity=data.get('severity') or None,
        diagnosed_by_vet=int('diagnosed_by_vet' in data),
        treatment=data.get('treatment'),
        resolved=int('resolved' in data),
        notes=data.get('notes'),
    )
    db.add(ev)
    db.commit()
    return redirect(url_for('breeder.owner_dashboard', owner_dog_id=owner_dog_id))


@bp.route('/owner/<int:owner_dog_id>/vaccines')
def owner_vaccine_list(owner_dog_id):
    """ワクチン・予防スケジュール一覧"""
    from app.models_breeder import OwnerDog, Dog, VaccineSchedule
    from app.services.survival_analysis import generate_vaccine_alerts
    db = _get_db()
    od = db.query(OwnerDog).filter(OwnerDog.id == owner_dog_id).first()
    dog = db.query(Dog).filter(Dog.id == od.dog_id).first() if od else None
    schedules = db.query(VaccineSchedule).filter(
        VaccineSchedule.owner_dog_id == owner_dog_id
    ).order_by(VaccineSchedule.scheduled_date).all()
    schedule_dicts = [{
        'id': s.id, 'vaccine_type': s.vaccine_type,
        'scheduled_date': s.scheduled_date, 'is_completed': s.is_completed,
    } for s in schedules]
    alerts = generate_vaccine_alerts(schedule_dicts)
    return render_template('owner/owner_dashboard.html',
        owner_dog_id=owner_dog_id,
        dog={'name': dog.name if dog else '不明', 'nickname': od.nickname if od else None},
        vaccine_alerts=alerts,
        schedules=schedules,
        current_status='healthy',
        weight_trend={'current_weight': None, 'trend': 'unknown', 'data_points': []},
        recent_medical_events=[],
        senior_info=None,
    )


@bp.route('/analytics/survival')
@require_roles(*BREEDER_ROLES)
def survival_report():
    """生存分析レポート（ブリーダー向け）"""
    from app.models_breeder import OwnerDog, Dog, LifeStatus, DeathInfo
    from app.services.survival_analysis import (
        kaplan_meier_estimate, make_survival_record, greenwood_confidence_interval
    )
    from datetime import date as _date
    db = _get_db()
    breed_filter = request.args.get('breed')
    tenant_id = session.get('tenant_id')

    q = db.query(OwnerDog).filter(OwnerDog.share_health_data == 1)
    if tenant_id:
        q = q.filter(OwnerDog.breeder_id == tenant_id)
    owner_dogs = q.all()

    records = []
    for od in owner_dogs:
        dog = db.query(Dog).filter(Dog.id == od.dog_id).first()
        if not dog:
            continue
        if breed_filter and dog.breed != breed_filter:
            continue
        latest_status = db.query(LifeStatus).filter(
            LifeStatus.owner_dog_id == od.id
        ).order_by(LifeStatus.status_date.desc()).first()
        is_deceased = latest_status and latest_status.status == 'deceased'
        death_info = db.query(DeathInfo).filter(DeathInfo.owner_dog_id == od.id).first()
        age_months = None
        age_range = None
        if is_deceased:
            if latest_status and latest_status.age_months:
                age_months = latest_status.age_months
            elif death_info:
                age_range = death_info.estimated_age_range
        else:
            if dog.birth_date:
                today = _date.today()
                age_months = (today.year - dog.birth_date.year) * 12 + (
                    today.month - dog.birth_date.month
                )
        records.append(make_survival_record(
            dog_id=dog.id, age_months=age_months,
            is_deceased=is_deceased, age_range=age_range,
        ))

    km = kaplan_meier_estimate(records)
    km['survival_curve'] = greenwood_confidence_interval(km['survival_curve'])

    return render_template('owner/survival_report.html',
        km=km,
        breed=breed_filter,
    )


# ─── 飼い主管理（ブリーダー側） ─────────────────────────────────
@bp.route('/owners')
@require_roles(*BREEDER_ROLES)
def owner_list():
    """飼い主一覧"""
    db = _get_db()
    from app.models_breeder import Owner, OwnerDog, Dog
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()
        q = db.query(Owner)
        if tenant_id:
            q = q.filter(Owner.tenant_id == tenant_id)
        owners = q.order_by(Owner.created_at.desc()).all()

        # 各飼い主の犬一覧を取得
        owner_data = []
        for owner in owners:
            dogs = db.query(OwnerDog, Dog).join(
                Dog, OwnerDog.dog_id == Dog.id
            ).filter(OwnerDog.owner_id == owner.id).all()
            owner_data.append({
                'owner': owner,
                'dogs': dogs,
                'dog_count': len(dogs),
            })

        return render_template('breeder/owner_list.html', owner_data=owner_data)
    finally:
        db.close()


@bp.route('/owners/new', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def owner_new():
    """飼い主新規登録（招待URL発行）"""
    db = _get_db()
    from app.models_breeder import Owner, OwnerDog, Dog
    import secrets
    from datetime import datetime, timedelta
    db = _get_db()
    try:
        tenant_id, store_id = _get_tenant_store()

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            dog_id = request.form.get('dog_id')
            nickname = request.form.get('nickname', '').strip()
            notes = request.form.get('notes', '').strip()

            if not name:
                flash('飼い主名は必須です。', 'error')
                dogs = _get_available_dogs(db, tenant_id, store_id)
                return render_template('breeder/owner_new.html', dogs=dogs)

            # 招待トークン生成（72時間有効）
            token = secrets.token_urlsafe(32)
            expires = datetime.now() + timedelta(hours=72)

            owner = Owner(
                tenant_id=tenant_id,
                store_id=store_id,
                name=name,
                email=email if email else None,
                phone=phone if phone else None,
                notes=notes if notes else None,
                invite_token=token,
                invite_token_expires=expires,
                is_active=0,
            )
            db.add(owner)
            db.flush()  # owner.id を取得

            # 犬との紐付け
            if dog_id:
                od = OwnerDog(
                    owner_id=owner.id,
                    dog_id=int(dog_id),
                    nickname=nickname if nickname else None,
                    acquired_date=request.form.get('acquired_date') or None,
                    breeder_id=tenant_id,
                    share_health_data=0,
                    share_followup_data=0,
                )
                db.add(od)

            db.commit()
            flash(f'飼い主を登録しました。招待URLを共有してください。', 'success')
            return redirect(url_for('breeder.owner_invite_url', owner_id=owner.id))

        dogs = _get_available_dogs(db, tenant_id, store_id)
        return render_template('breeder/owner_new.html', dogs=dogs)
    except Exception as e:
        db.rollback()
        flash(f'登録中にエラーが発生しました: {e}', 'error')
        return redirect(url_for('breeder.owner_list'))
    finally:
        db.close()


def _get_available_dogs(db, tenant_id, store_id):
    """販売済み・譲渡済みの犬一覧を取得"""
    from app.models_breeder import Dog, Puppy
    dogs = []
    # 親犬
    q = db.query(Dog)
    if tenant_id:
        q = q.filter(Dog.tenant_id == tenant_id)
    dogs += q.all()
    return dogs


@bp.route('/owners/<int:owner_id>/invite-url')
@require_roles(*BREEDER_ROLES)
def owner_invite_url(owner_id: int):
    """招待URL表示ページ"""
    db = _get_db()
    from app.models_breeder import Owner
    from flask import request as req
    db = _get_db()
    try:
        owner = db.query(Owner).filter(Owner.id == owner_id).first()
        if not owner:
            flash('飼い主が見つかりません。', 'error')
            return redirect(url_for('breeder.owner_list'))

        # 招待URLを生成
        base_url = req.host_url.rstrip('/')
        if owner.invite_token:
            invite_url = f"{base_url}/owner/invite/{owner.invite_token}"
        else:
            invite_url = None

        return render_template('breeder/owner_invite_url.html', owner=owner, invite_url=invite_url)
    finally:
        db.close()


@bp.route('/owners/<int:owner_id>/reinvite', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def owner_reinvite(owner_id: int):
    """招待URL再発行"""
    db = _get_db()
    from app.models_breeder import Owner
    import secrets
    from datetime import datetime, timedelta
    db = _get_db()
    try:
        owner = db.query(Owner).filter(Owner.id == owner_id).first()
        if not owner:
            flash('飼い主が見つかりません。', 'error')
            return redirect(url_for('breeder.owner_list'))

        token = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(hours=72)
        owner.invite_token = token
        owner.invite_token_expires = expires
        owner.is_active = 0  # 再登録を促す
        db.commit()

        flash('招待URLを再発行しました。', 'success')
        return redirect(url_for('breeder.owner_invite_url', owner_id=owner_id))
    except Exception as e:
        db.rollback()
        flash(f'再発行中にエラーが発生しました: {e}', 'error')
        return redirect(url_for('breeder.owner_list'))
    finally:
        db.close()


@bp.route('/owners/<int:owner_id>/add-dog', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def owner_add_dog(owner_id: int):
    """飼い主に犬を追加紐付け"""
    from app.models_breeder import Owner, OwnerDog
    db = _get_db()
    try:
        owner = db.query(Owner).filter(Owner.id == owner_id).first()
        if not owner:
            return jsonify({'error': 'not found'}), 404

        dog_id = request.form.get('dog_id')
        nickname = request.form.get('nickname', '').strip()
        if not dog_id:
            return jsonify({'error': 'dog_id required'}), 400

        # 重複チェック
        existing = db.query(OwnerDog).filter(
            OwnerDog.owner_id == owner_id,
            OwnerDog.dog_id == int(dog_id)
        ).first()
        if existing:
            flash('この犬はすでに登録されています。', 'error')
            return redirect(url_for('breeder.owner_invite_url', owner_id=owner_id))

        od = OwnerDog(
            owner_id=owner_id,
            dog_id=int(dog_id),
            nickname=nickname if nickname else None,
            acquired_date=request.form.get('acquired_date') or None,
            breeder_id=owner.tenant_id,
            share_health_data=0,
            share_followup_data=0,
        )
        db.add(od)
        db.commit()
        flash('犬を追加しました。', 'success')
        return redirect(url_for('breeder.owner_invite_url', owner_id=owner_id))
    except Exception as e:
        db.rollback()
        flash(f'追加中にエラーが発生しました: {e}', 'error')
        return redirect(url_for('breeder.owner_invite_url', owner_id=owner_id))
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# プラットフォーム機能: ブリーダープロフィール・評価スコア・検索・プラン
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# ブリーダープロフィール
# ─────────────────────────────────────────────

@bp.route('/profile', methods=['GET', 'POST'])
@require_roles(*BREEDER_ROLES)
def breeder_profile():
    """ブリーダープロフィール編集"""
    db = _get_db()
    from app.models_breeder import BreederProfile
    from app.services.plan_guard import get_plan_context

    tenant_id = session.get('tenant_id')
    profile = db.query(BreederProfile).filter_by(tenant_id=tenant_id).first()

    if request.method == 'POST':
        data = request.form
        if not profile:
            profile = BreederProfile(tenant_id=tenant_id)
            db.add(profile)
        profile.kennel_name = data.get('kennel_name', '')
        profile.location_prefecture = data.get('location_prefecture', '')
        profile.location_city = data.get('location_city', '')
        profile.website = data.get('website', '')
        profile.description = data.get('description', '')
        profile.is_public = 1 if data.get('is_public') else 0
        profile.years_experience = int(data.get('years_experience') or 0)
        breeds_raw = data.get('main_breeds', '')
        profile.main_breeds = [b.strip() for b in breeds_raw.split(',') if b.strip()]
        db.commit()
        flash('プロフィールを更新しました', 'success')
        return redirect(url_for('breeder.breeder_profile'))

    plan_ctx = get_plan_context(db, tenant_id)
    return render_template('breeder/breeder_profile.html',
                           profile=profile, **plan_ctx)


@bp.route('/profile/public/<int:tenant_id>')
def public_breeder_profile(tenant_id):
    """ブリーダー公開プロフィールページ（ログイン不要）"""
    db = _get_db()
    from app.models_breeder import BreederProfile, BreederScore

    profile = db.query(BreederProfile).filter_by(
        tenant_id=tenant_id, is_public=1).first()
    if not profile:
        abort(404)

    latest_score = db.query(BreederScore).filter_by(
        tenant_id=tenant_id).order_by(BreederScore.calculated_at.desc()).first()

    return render_template('breeder/public_profile.html',
                           profile=profile, score=latest_score)


# ─────────────────────────────────────────────
# ブリーダー評価スコア
# ─────────────────────────────────────────────

@bp.route('/score')
@require_roles(*BREEDER_ROLES)
def breeder_score_page():
    """ブリーダー評価スコアページ"""
    db = _get_db()
    from app.models_breeder import BreederScore
    from app.services.breeder_score import calculate_and_save_breeder_score
    from app.services.plan_guard import get_plan_context, can_use_feature, get_tenant_plan

    tenant_id = session.get('tenant_id')
    plan_name = get_tenant_plan(db, tenant_id)

    if not can_use_feature(plan_name, 'breeder_score'):
        flash('ブリーダー評価スコアはプロプラン以上でご利用いただけます', 'warning')
        return redirect(url_for('breeder.plan_upgrade'))

    latest_score = db.query(BreederScore).filter_by(
        tenant_id=tenant_id).order_by(BreederScore.calculated_at.desc()).first()

    plan_ctx = get_plan_context(db, tenant_id)
    return render_template('breeder/breeder_score.html',
                           score=latest_score, **plan_ctx)


@bp.route('/api/score/recalculate', methods=['POST'])
@require_roles(*BREEDER_ROLES)
def api_recalculate_score():
    """評価スコアを再計算するAPI"""
    db = _get_db()
    from app.services.breeder_score import calculate_and_save_breeder_score
    from app.services.plan_guard import can_use_feature, get_tenant_plan

    tenant_id = session.get('tenant_id')
    plan_name = get_tenant_plan(db, tenant_id)

    if not can_use_feature(plan_name, 'breeder_score'):
        return jsonify({'error': 'plan_limit', 'message': 'プロプラン以上が必要です'}), 403

    result = calculate_and_save_breeder_score(db, tenant_id)
    return jsonify(result)


# ─────────────────────────────────────────────
# ブリーダー検索（公開）
# ─────────────────────────────────────────────

@bp.route('/search')
def breeder_search():
    """ブリーダー検索ページ（ログイン不要）"""
    db = _get_db()
    from app.models_breeder import BreederProfile, BreederScore

    prefecture = request.args.get('prefecture', '')
    breed = request.args.get('breed', '')
    keyword = request.args.get('q', '')

    query = db.query(BreederProfile).filter_by(is_public=1)

    if prefecture:
        query = query.filter(BreederProfile.location_prefecture == prefecture)
    if keyword:
        query = query.filter(BreederProfile.kennel_name.contains(keyword))

    profiles = query.order_by(BreederProfile.is_verified.desc()).limit(50).all()

    # 各プロフィールに最新スコアを付与
    results = []
    for p in profiles:
        score = db.query(BreederScore).filter_by(
            tenant_id=p.tenant_id).order_by(BreederScore.calculated_at.desc()).first()
        results.append({'profile': p, 'score': score})

    # 都道府県リスト
    prefectures = [
        '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
        '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
        '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県',
        '岐阜県', '静岡県', '愛知県', '三重県',
        '滋賀県', '京都府', '大阪府', '兵庫県', '奈良県', '和歌山県',
        '鳥取県', '島根県', '岡山県', '広島県', '山口県',
        '徳島県', '香川県', '愛媛県', '高知県',
        '福岡県', '佐賀県', '長崎県', '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県',
    ]

    return render_template('breeder/breeder_search.html',
                           results=results, prefectures=prefectures,
                           prefecture=prefecture, breed=breed, keyword=keyword)


# ─────────────────────────────────────────────
# プラン管理・アップグレード
# ─────────────────────────────────────────────

@bp.route('/plan')
@require_roles(*BREEDER_ROLES)
def plan_upgrade():
    """プランアップグレードページ"""
    db = _get_db()
    from app.models_breeder import Subscription, Plan
    from app.services.plan_guard import get_plan_context, PLAN_FEATURES

    tenant_id = session.get('tenant_id')
    plan_ctx = get_plan_context(db, tenant_id)

    subscription = db.query(Subscription).filter_by(
        tenant_id=tenant_id).order_by(Subscription.id.desc()).first()

    return render_template('breeder/plan_upgrade.html',
                           subscription=subscription,
                           **plan_ctx)


@bp.route('/api/plan/current')
@require_roles(*BREEDER_ROLES)
def api_current_plan():
    """現在のプラン情報を返すAPI"""
    db = _get_db()
    from app.services.plan_guard import get_plan_context

    tenant_id = session.get('tenant_id')
    ctx = get_plan_context(db, tenant_id)
    return jsonify({
        'plan': ctx['current_plan'],
        'display_name': ctx['current_plan_display'],
        'features': ctx['available_features'],
    })


# ─────────────────────────────────────────────
# 管理者ダッシュボード（KPI）
# ─────────────────────────────────────────────

@bp.route('/admin/kpi')
@require_roles('owner', 'system_admin', 'tenant_admin')
def admin_kpi_dashboard():
    """管理者向けKPIダッシュボード"""
    db = _get_db()
    from app.models_breeder import KpiSnapshot
    from sqlalchemy import text

    # 最新KPIスナップショット（過去30日）
    snapshots = db.query(KpiSnapshot).order_by(
        KpiSnapshot.snapshot_date.desc()).limit(30).all()

    # リアルタイム集計
    try:
        rt = {}
        rt['total_tenants'] = db.execute(text("SELECT COUNT(*) FROM tenants")).fetchone()[0]
        rt['active_breeders'] = db.execute(text(
            "SELECT COUNT(DISTINCT tenant_id) FROM dogs WHERE is_deleted = 0"
        )).fetchone()[0]
        rt['total_dogs'] = db.execute(text(
            "SELECT COUNT(*) FROM dogs WHERE is_deleted = 0"
        )).fetchone()[0]
        rt['total_owners'] = db.execute(text("SELECT COUNT(*) FROM owners")).fetchone()[0]
        rt['total_health_logs'] = db.execute(text("SELECT COUNT(*) FROM health_logs")).fetchone()[0]
        rt['total_coi_calcs'] = db.execute(text(
            "SELECT COUNT(*) FROM feature_usages WHERE feature_key = 'advanced_coi'"
        )).fetchone()[0]
        rt['paying_tenants'] = db.execute(text(
            "SELECT COUNT(DISTINCT tenant_id) FROM subscriptions WHERE status = 'active'"
        )).fetchone()[0]
    except Exception:
        rt = {}

    return render_template('breeder/admin_kpi.html',
                           snapshots=snapshots, rt=rt)


@bp.route('/api/admin/kpi/snapshot', methods=['POST'])
@require_roles('owner', 'system_admin', 'tenant_admin')
def api_create_kpi_snapshot():
    """KPIスナップショットを手動作成するAPI"""
    db = _get_db()
    from app.models_breeder import KpiSnapshot
    from sqlalchemy import text
    from datetime import date

    today = date.today()
    existing = db.query(KpiSnapshot).filter_by(snapshot_date=today).first()
    if existing:
        return jsonify({'message': '本日のスナップショットは既に存在します'}), 200

    def safe_count(query_str):
        try:
            return db.execute(text(query_str)).fetchone()[0] or 0
        except Exception:
            db.rollback()
            return 0
    try:
        snap = KpiSnapshot(snapshot_date=today)
        snap.active_breeders = safe_count(
            "SELECT COUNT(DISTINCT tenant_id) FROM dogs WHERE is_deleted = 0")
        snap.active_owners = safe_count(
            "SELECT COUNT(*) FROM owners WHERE is_active = 1")
        snap.total_dogs = safe_count(
            "SELECT COUNT(*) FROM dogs WHERE is_deleted = 0")
        snap.total_health_logs = safe_count(
            "SELECT COUNT(*) FROM health_logs")
        snap.total_coi_calcs = safe_count(
            "SELECT COUNT(*) FROM feature_usages WHERE feature_key = 'advanced_coi'")
        snap.paying_tenants = safe_count(
            "SELECT COUNT(DISTINCT tenant_id) FROM subscriptions WHERE status = 'active'")
        db.add(snap)
        db.commit()
        return jsonify({'message': 'スナップショット作成完了', 'date': str(today)})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/admin/kpi/summary')
@require_roles('owner', 'system_admin', 'tenant_admin')
def api_kpi_summary():
    """KPIサマリーを返すAPI"""
    db = _get_db()
    from app.models_breeder import KpiSnapshot

    snapshots = db.query(KpiSnapshot).order_by(
        KpiSnapshot.snapshot_date.desc()).limit(30).all()

    return jsonify([{
        'date': str(s.snapshot_date),
        'active_breeders': s.active_breeders,
        'active_owners': s.active_owners,
        'total_dogs': s.total_dogs,
        'total_health_logs': s.total_health_logs,
        'total_coi_calcs': s.total_coi_calcs,
        'paying_tenants': s.paying_tenants,
        'mrr': s.mrr,
    } for s in snapshots])
