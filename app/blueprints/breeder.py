# -*- coding: utf-8 -*-
"""
ブリーダー管理システム Blueprint
全機能（ダッシュボード・生体・繁殖・販売・申請・健康・法規制・Todo・設定）を提供
"""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from sqlalchemy import func, and_, or_, desc, asc
from app.db import SessionLocal
from app.models_login import TKanrisha
from ..utils.decorators import require_roles, ROLES

bp = Blueprint('breeder', __name__, url_prefix='/breeder')

# ─── 認証ヘルパー ────────────────────────────────────────────
BREEDER_ROLES = (ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])

def _get_db():
    return SessionLocal()

def _require_login():
    """ログイン確認（デコレータの代わりに使用）"""
    if not session.get('user_id'):
        return redirect(url_for('auth.select_login'))
    return None


def _get_tenant_store():
    """ロールに応じてtenant_idとstore_idを返す。
    - system_admin: 両方None（全データ）
    - tenant_admin: tenant_idのみ（全店舗集計）、store_idはNone
    - admin/employee: tenant_id + store_id
    """
    role = session.get('role', '')
    if role == 'system_admin':
        return None, None
    tenant_id = session.get('tenant_id')
    if role == 'tenant_admin':
        return tenant_id, None  # 全店舗集計
    store_id = session.get('store_id')
    return tenant_id, store_id

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
        return render_template('breeder/dog_detail.html', dog=dog, heats=heats, weights=weights, vaccines=vaccines)
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
    from app.models_breeder import Heat, Dog
    db = _get_db()
    try:
        if request.method == 'POST':
            tenant_id, store_id = _get_tenant_store()
            heat = Heat(
                tenant_id=tenant_id,
                store_id=store_id,
                dog_id=int(request.form['dog_id']),
                start_date=_parse_date(request.form.get('start_date')),
                last_confirmed_date=_parse_date(request.form.get('last_confirmed_date')),
                next_predicted_date=_parse_date(request.form.get('next_predicted_date')),
                status=request.form.get('status', 'active'),
                notes=request.form.get('notes'),
            )
            db.add(heat)
            db.commit()
            flash('ヒートを登録しました', 'success')
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
        return render_template('breeder/document_scans.html', scans=scans, dogs=dogs, puppies=puppies)
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
    """OCR結果を元に犬の情報を更新する"""
    from app.models_breeder import DocumentScan, Dog, Puppy
    db = _get_db()
    try:
        scan = db.query(DocumentScan).get(scan_id)
        if not scan or not scan.result_json:
            flash('スキャンデータが見つかりません', 'error')
            return redirect(url_for('breeder.document_scans'))
        result = json.loads(scan.result_json)
        target_id = _int_or_none(request.form.get('target_id'))
        target_type = request.form.get('target_type', 'dog')
        if target_type == 'dog' and target_id:
            dog = db.query(Dog).get(target_id)
            if dog:
                if result.get('pedigree_number'):
                    dog.pedigree_number = result['pedigree_number']
                if result.get('microchip_number'):
                    dog.microchip_number = result['microchip_number']
                if result.get('registration_name'):
                    dog.registration_name = result['registration_name']
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
        return redirect(url_for('breeder.document_scans'))
    except Exception as e:
        db.rollback()
        flash(f'適用エラー: {e}', 'error')
        return redirect(url_for('breeder.document_scans'))
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
