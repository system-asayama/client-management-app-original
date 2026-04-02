# -*- coding: utf-8 -*-
"""
店舗ダッシュボード（店舗ベースアーキテクチャ）
各店舗が独立した業務単位として機能するためのルート群
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.db import SessionLocal
from app.models_login import (
    TKanrisha, TJugyoin, TTenant, TTenpo,
    TKanrishaTenpo, TJugyoinTenpo, TAttendance
)
from app.models_clients import TClient
from sqlalchemy import func, and_, or_
from datetime import datetime, timezone, timedelta, date
from calendar import monthrange
from ..utils.decorators import ROLES, require_roles

bp = Blueprint('store_dashboard', __name__, url_prefix='/store')

PROFESSION_LABELS = {
    'tax': '税理士',
    'legal': '弁護士',
    'accounting': '公認会計士',
    'sr': '社労士',
}


def _get_store_or_404(db, store_id, tenant_id):
    """店舗を取得する。存在しない場合はNoneを返す"""
    return db.query(TTenpo).filter(
        and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
    ).first()


@bp.route('/<int:store_id>/dashboard')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["ADMIN"])
def dashboard(store_id):
    """店舗ダッシュボード"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        store = _get_store_or_404(db, store_id, tenant_id)
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.jimusho_dashboard'))

        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        profession = getattr(tenant, 'profession', None) or '' if tenant else ''

        # 顧問先統計（この店舗に属する顧問先）
        try:
            all_clients = db.query(TClient).filter(
                and_(TClient.tenant_id == tenant_id, TClient.store_id == store_id)
            ).all()
            client_count = len(all_clients)
            corp_count = sum(1 for c in all_clients if c.type == '法人')
            ind_count = sum(1 for c in all_clients if c.type == '個人')
        except Exception:
            client_count = corp_count = ind_count = 0

        # 従業員統計（この店舗に所属する従業員）
        try:
            employee_count = db.query(TJugyoin).join(
                TJugyoinTenpo, TJugyoin.id == TJugyoinTenpo.employee_id
            ).filter(
                and_(
                    TJugyoin.tenant_id == tenant_id,
                    TJugyoinTenpo.store_id == store_id,
                    TJugyoin.active == 1
                )
            ).count()
        except Exception:
            employee_count = 0

        # 管理者統計（この店舗に所属する管理者）
        try:
            admin_count = db.query(TKanrisha).join(
                TKanrishaTenpo, TKanrisha.id == TKanrishaTenpo.admin_id
            ).filter(
                and_(
                    TKanrisha.tenant_id == tenant_id,
                    TKanrishaTenpo.store_id == store_id,
                    TKanrisha.active == 1
                )
            ).count()
        except Exception:
            admin_count = 0

        # 今日の出勤中スタッフ数（この店舗）
        try:
            jst = timezone(timedelta(hours=9))
            today = datetime.now(jst).date()
            working_now = db.query(TAttendance).filter(
                and_(
                    TAttendance.tenant_id == tenant_id,
                    TAttendance.store_id == store_id,
                    TAttendance.work_date == today,
                    TAttendance.clock_in != None,
                    TAttendance.clock_out == None
                )
            ).count()
        except Exception:
            working_now = 0

        # 今月の勤怠サマリー（この店舗）
        try:
            jst = timezone(timedelta(hours=9))
            now = datetime.now(jst)
            _, last_day = monthrange(now.year, now.month)
            month_start = date(now.year, now.month, 1)
            month_end = date(now.year, now.month, last_day)
            month_attendance_count = db.query(TAttendance).filter(
                and_(
                    TAttendance.tenant_id == tenant_id,
                    TAttendance.store_id == store_id,
                    TAttendance.work_date >= month_start,
                    TAttendance.work_date <= month_end,
                    TAttendance.clock_in != None
                )
            ).count()
        except Exception:
            month_attendance_count = 0

        return render_template(
            'store_dashboard.html',
            store=store,
            store_id=store_id,
            tenant=tenant,
            tenant_id=tenant_id,
            profession=profession,
            profession_label=PROFESSION_LABELS.get(profession, ''),
            client_count=client_count,
            corp_count=corp_count,
            ind_count=ind_count,
            employee_count=employee_count,
            admin_count=admin_count,
            working_now=working_now,
            month_attendance_count=month_attendance_count,
        )
    finally:
        db.close()


@bp.route('/<int:store_id>/clients')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def clients(store_id):
    """店舗別顧問先一覧"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        store = _get_store_or_404(db, store_id, tenant_id)
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.jimusho_dashboard'))

        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        profession = getattr(tenant, 'profession', None) or '' if tenant else ''

        client_list = db.query(TClient).filter(
            and_(TClient.tenant_id == tenant_id, TClient.store_id == store_id)
        ).order_by(TClient.id.desc()).all()

        return render_template(
            'store_clients.html',
            store=store,
            store_id=store_id,
            clients=client_list,
            tenant=tenant,
            profession=profession,
            profession_label=PROFESSION_LABELS.get(profession, ''),
        )
    finally:
        db.close()


@bp.route('/<int:store_id>/employees')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["ADMIN"])
def employees(store_id):
    """店舗別従業員一覧"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        store = _get_store_or_404(db, store_id, tenant_id)
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.jimusho_dashboard'))

        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()

        # 従業員一覧（この店舗に所属）
        employee_list = db.query(TJugyoin).join(
            TJugyoinTenpo, TJugyoin.id == TJugyoinTenpo.employee_id
        ).filter(
            and_(
                TJugyoin.tenant_id == tenant_id,
                TJugyoinTenpo.store_id == store_id
            )
        ).order_by(TJugyoin.id).all()

        # 管理者一覧（この店舗に所属）
        admin_list = db.query(TKanrisha).join(
            TKanrishaTenpo, TKanrisha.id == TKanrishaTenpo.admin_id
        ).filter(
            and_(
                TKanrisha.tenant_id == tenant_id,
                TKanrishaTenpo.store_id == store_id
            )
        ).order_by(TKanrisha.id).all()

        return render_template(
            'store_employees.html',
            store=store,
            store_id=store_id,
            employees=employee_list,
            admins=admin_list,
            tenant=tenant,
        )
    finally:
        db.close()


@bp.route('/<int:store_id>/attendance')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["ADMIN"])
def attendance(store_id):
    """店舗別勤怠一覧"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        store = _get_store_or_404(db, store_id, tenant_id)
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.jimusho_dashboard'))

        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()

        jst = timezone(timedelta(hours=9))
        today = datetime.now(jst).date()

        # 月パラメータ処理
        month_str = request.args.get('month', today.strftime('%Y-%m'))
        try:
            year_m, mon_m = map(int, month_str.split('-'))
        except Exception:
            year_m, mon_m = today.year, today.month

        _, last_day = monthrange(year_m, mon_m)
        month_start = date(year_m, mon_m, 1)
        month_end = date(year_m, mon_m, last_day)

        # 前月・翌月の計算
        if mon_m == 1:
            prev_month = f'{year_m - 1}-12'
        else:
            prev_month = f'{year_m}-{mon_m - 1:02d}'
        if mon_m == 12:
            next_month = f'{year_m + 1}-01'
        else:
            next_month = f'{year_m}-{mon_m + 1:02d}'

        # スタッフ絞り込みフィルター
        staff_filter = request.args.get('staff_filter', '')

        # この店舗の勤怠レコードを取得
        query = db.query(TAttendance).filter(
            and_(
                TAttendance.tenant_id == tenant_id,
                TAttendance.store_id == store_id,
                TAttendance.work_date >= month_start,
                TAttendance.work_date <= month_end
            )
        )

        if staff_filter and '_' in staff_filter:
            parts = staff_filter.split('_', 1)
            filter_type = parts[0]
            try:
                filter_id = int(parts[1])
                query = query.filter(
                    and_(TAttendance.staff_type == filter_type,
                         TAttendance.staff_id == filter_id)
                )
            except (ValueError, IndexError):
                pass

        all_records = query.order_by(
            TAttendance.staff_type.asc(),
            TAttendance.staff_id.asc(),
            TAttendance.work_date.asc()
        ).all()

        # スタッフ別にグループ化
        staff_map = {}
        for r in all_records:
            key = (r.staff_type, r.staff_id)
            if key not in staff_map:
                staff_map[key] = {
                    'staff_type': r.staff_type,
                    'staff_id': r.staff_id,
                    'name': r.staff_name or f'スタッフ{r.staff_id}',
                    'records': [],
                    'work_days': 0,
                    'total_minutes': 0,
                    'is_working_now': False,
                }
            staff_map[key]['records'].append(r)

        # 各スタッフの集計
        currently_working = 0
        total_work_days = 0
        total_work_minutes_all = 0
        for key, s in staff_map.items():
            work_days = 0
            total_mins = 0
            is_working = False
            for r in s['records']:
                if r.clock_in:
                    work_days += 1
                    if r.clock_out:
                        diff = (r.clock_out - r.clock_in).total_seconds() / 60
                        total_mins += max(0, diff - (r.break_minutes or 0))
                    else:
                        is_working = True
            s['work_days'] = work_days
            s['total_minutes'] = int(total_mins)
            s['total_hours'] = int(total_mins) // 60
            s['total_minutes_rem'] = int(total_mins) % 60
            s['is_working_now'] = is_working
            if is_working:
                currently_working += 1
            total_work_days += work_days
            total_work_minutes_all += int(total_mins)

        staff_data = list(staff_map.values())

        # スタッフ絞り込みドロップダウン用
        all_staff_keys = db.query(
            TAttendance.staff_type,
            TAttendance.staff_id,
            TAttendance.staff_name
        ).filter(
            and_(
                TAttendance.tenant_id == tenant_id,
                TAttendance.store_id == store_id
            )
        ).distinct().all()
        # 管理者のrole情報を引き当てるマップを構築
        admin_role_map = {a.id: getattr(a, 'role', 'admin') for a in db.query(TKanrisha).filter(
            TKanrisha.tenant_id == tenant_id
        ).all()}
        all_staff = []
        for r in all_staff_keys:
            role = admin_role_map.get(r.staff_id, 'admin') if r.staff_type == 'admin' else 'employee'
            all_staff.append({
                'staff_type': r.staff_type,
                'staff_id': r.staff_id,
                'staff_name': r.staff_name or f'スタッフ{r.staff_id}',
                'role': role
            })
        # staff_dataにもrole情報を付加
        for s in staff_data:
            if s['staff_type'] == 'admin':
                s['role'] = admin_role_map.get(s['staff_id'], 'admin')
            else:
                s['role'] = 'employee'

        # 店舗に所属する全スタッフ数（店舗管理者＋従業員）を集計
        try:
            target_admin_count = db.query(TKanrisha).join(
                TKanrishaTenpo, TKanrisha.id == TKanrishaTenpo.admin_id
            ).filter(
                and_(
                    TKanrisha.tenant_id == tenant_id,
                    TKanrishaTenpo.store_id == store_id,
                    TKanrisha.active == 1
                )
            ).count()
        except Exception:
            target_admin_count = 0
        try:
            target_employee_count = db.query(TJugyoin).join(
                TJugyoinTenpo, TJugyoin.id == TJugyoinTenpo.employee_id
            ).filter(
                and_(
                    TJugyoin.tenant_id == tenant_id,
                    TJugyoinTenpo.store_id == store_id,
                    TJugyoin.active == 1
                )
            ).count()
        except Exception:
            target_employee_count = 0
        target_staff_count = target_admin_count + target_employee_count

        return render_template(
            'store_attendance.html',
            store=store,
            store_id=store_id,
            tenant=tenant,
            staff_data=staff_data,
            all_staff=all_staff,
            staff_filter=staff_filter,
            month_str=month_str,
            year_m=year_m,
            mon_m=mon_m,
            prev_month=prev_month,
            next_month=next_month,
            total_work_days=total_work_days,
            total_work_hours=total_work_minutes_all // 60,
            total_work_minutes_remainder=total_work_minutes_all % 60,
            currently_working=currently_working,
            target_staff_count=target_staff_count,
            target_admin_count=target_admin_count,
            target_employee_count=target_employee_count,
        )
    finally:
        db.close()
