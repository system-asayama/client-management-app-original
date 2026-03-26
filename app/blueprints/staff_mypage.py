# -*- coding: utf-8 -*-
"""
スタッフマイページ ブループリント
税理士事務所側スタッフ（tenant_admin / admin / employee）向けのマイページ機能
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from sqlalchemy import and_, or_, func as sqlfunc
from datetime import date, datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from app.db import SessionLocal
from app.models_login import TKanrisha, TJugyoin, TTenant, TNotice, TAttendance, TAttendanceLocation, TClientAssignment, TNoticeRead
from app.models_clients import TClient, TMessage, TMessageRead
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('staff_mypage', __name__, url_prefix='/staff')


def _get_current_user():
    """セッションからログイン中ユーザーを取得する"""
    role = session.get('role', '')
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    if not user_id or not tenant_id:
        return None, None, role
    db = SessionLocal()
    try:
        if role == ROLES['EMPLOYEE']:
            user = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
            staff_type = 'employee'
        else:
            user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
            staff_type = 'admin'
        return user, staff_type, role
    finally:
        db.close()


def _get_unread_count(tenant_id, user_name):
    """担当顧問先の未読チャット数を取得する"""
    db = SessionLocal()
    try:
        # 全顧問先のclient側未読メッセージ数
        read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'staff',
            TMessageRead.reader_id == user_name
        ).all()}
        unread = db.query(TMessage).filter(
            TMessage.sender_type == 'client'
        ).count()
        # 既読分を引く
        already_read = db.query(TMessage).filter(
            TMessage.sender_type == 'client',
            TMessage.id.in_(read_ids)
        ).count() if read_ids else 0
        return max(0, unread - already_read)
    except Exception:
        return 0
    finally:
        db.close()


# ─────────────────────────────────────────────
# ダッシュボード
# ─────────────────────────────────────────────
@bp.route('/')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def dashboard():
    tenant_id = session.get('tenant_id')
    user_name = session.get('user_name', '')
    user_id = session.get('user_id')
    role = session.get('role', '')
    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()

        # 担当顧問先数
        assignments = db.query(TClientAssignment).filter(
            and_(TClientAssignment.tenant_id == tenant_id,
                 TClientAssignment.staff_id == user_id)
        ).all()
        assigned_client_ids = [a.client_id for a in assignments]
        assigned_count = len(assigned_client_ids)

        # 全顧問先数（tenant_admin/adminは全件表示）
        total_clients = db.query(TClient).filter(TClient.tenant_id == tenant_id).count()

        # 未読チャット数（担当顧問先のclient側メッセージ）
        read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'staff',
            TMessageRead.reader_id == user_name
        ).all()}
        unread_msgs = db.query(TMessage).filter(
            TMessage.sender_type == 'client',
            TMessage.client_id.in_(assigned_client_ids) if assigned_client_ids else False
        ).all() if assigned_client_ids else []
        unread_count = sum(1 for m in unread_msgs if m.id not in read_ids)

        # 最新お知らせ（5件）
        notices = db.query(TNotice).filter(
            TNotice.tenant_id == tenant_id
        ).order_by(TNotice.created_at.desc()).limit(5).all()

        # 今日の勤怠
        today = date.today()
        staff_type = 'employee' if role == ROLES['EMPLOYEE'] else 'admin'
        today_attendance = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.staff_id == user_id,
                 TAttendance.staff_type == staff_type,
                 TAttendance.work_date == today)
        ).first()

        # 直近の税務期限（担当顧問先）
        upcoming_deadlines = []
        if assigned_client_ids:
            from app.tax_calendar import get_all_deadlines_for_client  # noqa
            year = today.year
            clients_q = db.query(TClient).filter(
                TClient.id.in_(assigned_client_ids)
            ).all()
            for client in clients_q:
                deadlines = get_all_deadlines_for_client(client, year)
                for d in deadlines:
                    if d['date'] >= today:
                        upcoming_deadlines.append(d)
            upcoming_deadlines.sort(key=lambda x: x['date'])
            upcoming_deadlines = upcoming_deadlines[:5]

        return render_template('staff_mypage_dashboard.html',
                               tenant=tenant,
                               assigned_count=assigned_count,
                               total_clients=total_clients,
                               unread_count=unread_count,
                               notices=notices,
                               today_attendance=today_attendance,
                               upcoming_deadlines=upcoming_deadlines,
                               today=today)
    finally:
        db.close()


# ─────────────────────────────────────────────
# プロフィール設定
# ─────────────────────────────────────────────
@bp.route('/profile', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def profile():
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    role = session.get('role', '')
    db = SessionLocal()
    try:
        if role == ROLES['EMPLOYEE']:
            user = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
        else:
            user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()

        if not user:
            flash('ユーザーが見つかりません', 'error')
            return redirect(url_for('staff_mypage.dashboard'))

        unread_count = _get_unread_count(tenant_id, session.get('user_name', ''))

        if request.method == 'POST':
            action = request.form.get('action', 'profile')

            if action == 'profile':
                name = request.form.get('name', '').strip()
                email = request.form.get('email', '').strip()
                phone = request.form.get('phone', '').strip()
                position = request.form.get('position', '').strip()
                if not name or not email:
                    flash('氏名・メールアドレスは必須です', 'error')
                else:
                    user.name = name
                    user.email = email
                    user.phone = phone if phone else None
                    user.position = position if position else None
                    db.commit()
                    session['user_name'] = name
                    session['user_position'] = position
                    flash('プロフィールを更新しました', 'success')
                    return redirect(url_for('staff_mypage.profile'))

            elif action == 'change_login_id':
                new_login_id = request.form.get('new_login_id', '').strip()
                current_pw = request.form.get('current_password_id', '')
                if not new_login_id or not current_pw:
                    flash('ログインIDと現在のパスワードを入力してください', 'error')
                elif not check_password_hash(user.password_hash, current_pw):
                    flash('現在のパスワードが正しくありません', 'error')
                else:
                    # 重複チェック
                    if role == ROLES['EMPLOYEE']:
                        dup = db.query(TJugyoin).filter(
                            and_(TJugyoin.login_id == new_login_id, TJugyoin.id != user_id)
                        ).first()
                    else:
                        dup = db.query(TKanrisha).filter(
                            and_(TKanrisha.login_id == new_login_id, TKanrisha.id != user_id)
                        ).first()
                    if dup:
                        flash('そのログインIDは既に使用されています', 'error')
                    else:
                        user.login_id = new_login_id
                        db.commit()
                        flash('ログインIDを変更しました', 'success')
                        return redirect(url_for('staff_mypage.profile'))

            elif action == 'change_password':
                current_pw = request.form.get('current_password', '')
                new_pw = request.form.get('new_password', '')
                confirm_pw = request.form.get('confirm_password', '')
                if not current_pw or not new_pw:
                    flash('パスワードを入力してください', 'error')
                elif not check_password_hash(user.password_hash, current_pw):
                    flash('現在のパスワードが正しくありません', 'error')
                elif new_pw != confirm_pw:
                    flash('新しいパスワードが一致しません', 'error')
                elif len(new_pw) < 8:
                    flash('パスワードは8文字以上にしてください', 'error')
                else:
                    user.password_hash = generate_password_hash(new_pw)
                    db.commit()
                    flash('パスワードを変更しました', 'success')
                    return redirect(url_for('staff_mypage.profile'))

        return render_template('staff_mypage_profile.html', user=user, unread_count=unread_count)
    finally:
        db.close()


# ─────────────────────────────────────────────
# 担当顧問先一覧
# ─────────────────────────────────────────────
@bp.route('/clients')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def my_clients():
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    user_name = session.get('user_name', '')
    role = session.get('role', '')
    db = SessionLocal()
    try:
        unread_count = _get_unread_count(tenant_id, user_name)

        # 担当顧問先を取得
        assignments = db.query(TClientAssignment).filter(
            and_(TClientAssignment.tenant_id == tenant_id,
                 TClientAssignment.staff_id == user_id)
        ).all()
        assigned_client_ids = [a.client_id for a in assignments]
        assignment_map = {a.client_id: a for a in assignments}

        if role in (ROLES['TENANT_ADMIN'], ROLES['SYSTEM_ADMIN']):
            # 管理者は全顧問先を表示
            clients = db.query(TClient).filter(TClient.tenant_id == tenant_id).order_by(TClient.name).all()
        else:
            # スタッフは担当顧問先のみ
            clients = db.query(TClient).filter(
                TClient.id.in_(assigned_client_ids)
            ).order_by(TClient.name).all() if assigned_client_ids else []

        # 各顧問先の未読チャット数
        read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'staff',
            TMessageRead.reader_id == user_name
        ).all()}
        unread_by_client = {}
        for client in clients:
            msgs = db.query(TMessage).filter(
                and_(TMessage.client_id == client.id, TMessage.sender_type == 'client')
            ).all()
            unread_by_client[client.id] = sum(1 for m in msgs if m.id not in read_ids)

        return render_template('staff_mypage_clients.html',
                               clients=clients,
                               assignment_map=assignment_map,
                               unread_by_client=unread_by_client,
                               unread_count=unread_count)
    finally:
        db.close()


# ─────────────────────────────────────────────
# チャット一覧
# ─────────────────────────────────────────────
@bp.route('/chats')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def my_chats():
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    user_name = session.get('user_name', '')
    role = session.get('role', '')
    db = SessionLocal()
    try:
        # 担当顧問先
        assignments = db.query(TClientAssignment).filter(
            and_(TClientAssignment.tenant_id == tenant_id,
                 TClientAssignment.staff_id == user_id)
        ).all()
        assigned_client_ids = [a.client_id for a in assignments]

        if role in (ROLES['TENANT_ADMIN'], ROLES['SYSTEM_ADMIN']):
            clients = db.query(TClient).filter(TClient.tenant_id == tenant_id).order_by(TClient.name).all()
        else:
            clients = db.query(TClient).filter(
                TClient.id.in_(assigned_client_ids)
            ).order_by(TClient.name).all() if assigned_client_ids else []

        # 各顧問先の最新メッセージと未読数
        read_ids = {r.message_id for r in db.query(TMessageRead).filter(
            TMessageRead.reader_type == 'staff',
            TMessageRead.reader_id == user_name
        ).all()}

        chat_list = []
        for client in clients:
            last_msg = db.query(TMessage).filter(
                TMessage.client_id == client.id
            ).order_by(TMessage.id.desc()).first()
            unread = db.query(TMessage).filter(
                and_(TMessage.client_id == client.id, TMessage.sender_type == 'client')
            ).all()
            unread_n = sum(1 for m in unread if m.id not in read_ids)
            chat_list.append({
                'client': client,
                'last_msg': last_msg,
                'unread': unread_n
            })

        # 未読数でソート
        chat_list.sort(key=lambda x: (-x['unread'], x['client'].name))
        total_unread = sum(c['unread'] for c in chat_list)

        return render_template('staff_mypage_chats.html',
                               chat_list=chat_list,
                               unread_count=total_unread)
    finally:
        db.close()


# ─────────────────────────────────────────────
# 税務カレンダー（担当顧問先の直近期限）
# ─────────────────────────────────────────────
@bp.route('/calendar')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def my_calendar():
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    user_name = session.get('user_name', '')
    role = session.get('role', '')
    db = SessionLocal()
    try:
        from app.tax_calendar import get_all_deadlines_for_client, group_by_month  # noqa

        year = int(request.args.get('year', date.today().year))
        unread_count = _get_unread_count(tenant_id, user_name)

        assignments = db.query(TClientAssignment).filter(
            and_(TClientAssignment.tenant_id == tenant_id,
                 TClientAssignment.staff_id == user_id)
        ).all()
        assigned_client_ids = [a.client_id for a in assignments]

        if role in (ROLES['TENANT_ADMIN'], ROLES['SYSTEM_ADMIN']):
            clients_q = db.query(TClient).filter(TClient.tenant_id == tenant_id).all()
        else:
            clients_q = db.query(TClient).filter(
                TClient.id.in_(assigned_client_ids)
            ).all() if assigned_client_ids else []

        all_deadlines = []
        for client in clients_q:
            deadlines = get_all_deadlines_for_client(client, year)
            all_deadlines.extend(deadlines)

        all_deadlines = [d for d in all_deadlines if d['date'].year == year]
        all_deadlines.sort(key=lambda x: x['date'])
        grouped = group_by_month(all_deadlines)
        today = date.today()

        return render_template('staff_mypage_calendar.html',
                               grouped=grouped,
                               year=year,
                               today=today,
                               clients=clients_q,
                               unread_count=unread_count)
    finally:
        db.close()


# ─────────────────────────────────────────────
# ファイル共有（担当顧問先のファイル一覧）
# ─────────────────────────────────────────────
@bp.route('/files')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def my_files():
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    user_name = session.get('user_name', '')
    role = session.get('role', '')
    db = SessionLocal()
    try:
        from app.models_clients import TFile

        unread_count = _get_unread_count(tenant_id, user_name)

        assignments = db.query(TClientAssignment).filter(
            and_(TClientAssignment.tenant_id == tenant_id,
                 TClientAssignment.staff_id == user_id)
        ).all()
        assigned_client_ids = [a.client_id for a in assignments]

        if role in (ROLES['TENANT_ADMIN'], ROLES['SYSTEM_ADMIN']):
            clients_q = db.query(TClient).filter(TClient.tenant_id == tenant_id).all()
        else:
            clients_q = db.query(TClient).filter(
                TClient.id.in_(assigned_client_ids)
            ).all() if assigned_client_ids else []

        client_ids = [c.id for c in clients_q]
        # 最新ファイル（50件）
        recent_files = db.query(TFile).filter(
            TFile.client_id.in_(client_ids)
        ).order_by(TFile.id.desc()).limit(50).all() if client_ids else []

        # クライアント名マップ
        client_map = {c.id: c for c in clients_q}

        return render_template('staff_mypage_files.html',
                               recent_files=recent_files,
                               client_map=client_map,
                               clients=clients_q,
                               unread_count=unread_count)
    finally:
        db.close()


# ─────────────────────────────────────────────
# 勤怠管理
# ─────────────────────────────────────────────
@bp.route('/attendance', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def attendance():
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    user_name = session.get('user_name', '')
    role = session.get('role', '')
    staff_type = 'employee' if role == ROLES['EMPLOYEE'] else 'admin'
    db = SessionLocal()
    try:
        unread_count = _get_unread_count(tenant_id, user_name)
        today = date.today()

        # 今月の勤怠一覧
        month_str = request.args.get('month', today.strftime('%Y-%m'))
        try:
            year_m, mon_m = map(int, month_str.split('-'))
        except Exception:
            year_m, mon_m = today.year, today.month

        from calendar import monthrange
        _, last_day = monthrange(year_m, mon_m)
        month_start = date(year_m, mon_m, 1)
        month_end = date(year_m, mon_m, last_day)

        records = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.staff_id == user_id,
                 TAttendance.staff_type == staff_type,
                 TAttendance.work_date >= month_start,
                 TAttendance.work_date <= month_end)
        ).order_by(TAttendance.work_date.asc()).all()

        # 今日の勤怠
        today_record = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.staff_id == user_id,
                 TAttendance.staff_type == staff_type,
                 TAttendance.work_date == today)
        ).first()

        if request.method == 'POST':
            action = request.form.get('action', '')

            if action == 'clock_in':
                if today_record and today_record.clock_in:
                    flash('本日はすでに出勤済みです', 'warning')
                else:
                    now = datetime.now()
                    if today_record:
                        today_record.clock_in = now
                        today_record.updated_at = now
                    else:
                        new_rec = TAttendance(
                            tenant_id=tenant_id,
                            staff_id=user_id,
                            staff_type=staff_type,
                            staff_name=user_name,
                            work_date=today,
                            clock_in=now
                        )
                        db.add(new_rec)
                    db.commit()
                    flash(f'出勤を記録しました（{now.strftime("%H:%M")}）', 'success')
                return redirect(url_for('staff_mypage.attendance'))

            elif action == 'clock_out':
                if not today_record or not today_record.clock_in:
                    flash('出勤記録がありません', 'error')
                elif today_record.clock_out:
                    flash('本日はすでに退勤済です', 'warning')
                else:
                    now = datetime.now()
                    today_record.clock_out = now
                    today_record.updated_at = now
                    # 休憩中のまま退勤した場合は休憩終了も記録
                    if today_record.break_start and not today_record.break_end:
                        today_record.break_end = now
                        mins = int((now - today_record.break_start).total_seconds() / 60)
                        today_record.break_minutes = (today_record.break_minutes or 0) + mins
                    db.commit()
                    flash(f'退勤を記録しました（{now.strftime("%H:%M")}）', 'success')
                return redirect(url_for('staff_mypage.attendance'))

            elif action == 'break_start':
                if not today_record or not today_record.clock_in:
                    flash('出勤記録がありません', 'error')
                elif today_record.clock_out:
                    flash('すでに退勤済です', 'warning')
                elif today_record.break_start and not today_record.break_end:
                    flash('すでに休憩中です', 'warning')
                else:
                    now = datetime.now()
                    today_record.break_start = now
                    today_record.break_end = None
                    today_record.updated_at = now
                    db.commit()
                    flash(f'休憩を開始しました（{now.strftime("%H:%M")}）', 'success')
                return redirect(url_for('staff_mypage.attendance'))

            elif action == 'break_end':
                if not today_record or not today_record.break_start:
                    flash('休憩開始記録がありません', 'error')
                elif today_record.break_end:
                    flash('すでに休憩終了済です', 'warning')
                else:
                    now = datetime.now()
                    today_record.break_end = now
                    mins = int((now - today_record.break_start).total_seconds() / 60)
                    today_record.break_minutes = (today_record.break_minutes or 0) + mins
                    today_record.updated_at = now
                    db.commit()
                    flash(f'休憩を終了しました（{mins}分）', 'success')
                return redirect(url_for('staff_mypage.attendance'))

            elif action == 'save_record':
                rec_id = request.form.get('record_id')
                work_date_str = request.form.get('work_date', '')
                clock_in_str = request.form.get('clock_in', '')
                clock_out_str = request.form.get('clock_out', '')
                break_min = int(request.form.get('break_minutes', 60))
                note = request.form.get('note', '').strip()
                status = request.form.get('status', 'normal')

                try:
                    work_date = datetime.strptime(work_date_str, '%Y-%m-%d').date()
                    clock_in = datetime.strptime(clock_in_str, '%Y-%m-%dT%H:%M') if clock_in_str else None
                    clock_out = datetime.strptime(clock_out_str, '%Y-%m-%dT%H:%M') if clock_out_str else None
                except Exception:
                    flash('日時の形式が正しくありません', 'error')
                    return redirect(url_for('staff_mypage.attendance', month=month_str))

                if rec_id:
                    rec = db.query(TAttendance).filter(
                        and_(TAttendance.id == int(rec_id),
                             TAttendance.staff_id == user_id)
                    ).first()
                    if rec:
                        rec.work_date = work_date
                        rec.clock_in = clock_in
                        rec.clock_out = clock_out
                        rec.break_minutes = break_min
                        rec.note = note
                        rec.status = status
                        rec.updated_at = datetime.now()
                        db.commit()
                        flash('勤怠記録を更新しました', 'success')
                else:
                    new_rec = TAttendance(
                        tenant_id=tenant_id,
                        staff_id=user_id,
                        staff_type=staff_type,
                        staff_name=user_name,
                        work_date=work_date,
                        clock_in=clock_in,
                        clock_out=clock_out,
                        break_minutes=break_min,
                        note=note,
                        status=status
                    )
                    db.add(new_rec)
                    db.commit()
                    flash('勤怠記録を追加しました', 'success')
                return redirect(url_for('staff_mypage.attendance', month=month_str))

        # 月間集計
        total_work_minutes = 0
        for r in records:
            if r.clock_in and r.clock_out:
                diff = (r.clock_out - r.clock_in).total_seconds() / 60
                total_work_minutes += max(0, diff - r.break_minutes)

        # GPS記録間隔をテナント設定から取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        gps_interval_minutes = getattr(tenant_obj, 'gps_interval_minutes', 10) or 10

        return render_template('staff_mypage_attendance.html',
                               records=records,
                               today_record=today_record,
                               today=today,
                               month_str=month_str,
                               year_m=year_m,
                               mon_m=mon_m,
                               total_work_minutes=total_work_minutes,
                               unread_count=unread_count,
                               gps_interval_minutes=gps_interval_minutes)
    finally:
        db.close()


# ─────────────────────────────────────────────
# お知らせ一覧
# ─────────────────────────────────────────────
@bp.route('/notices')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def notices():
    tenant_id  = session.get('tenant_id')
    user_name  = session.get('user_name', '')
    user_id    = session.get('user_id')
    role       = session.get('role', '')
    staff_type = 'employee' if role == ROLES['EMPLOYEE'] else 'admin'
    db = SessionLocal()
    try:
        unread_count = _get_unread_count(tenant_id, user_name)
        notices_list = db.query(TNotice).filter(
            TNotice.tenant_id == tenant_id
        ).order_by(TNotice.is_important.desc(), TNotice.created_at.desc()).all()
        # 各お知らせの既読フラグを付加
        if user_id:
            read_ids = {r.notice_id for r in db.query(TNoticeRead).filter(
                and_(
                    TNoticeRead.staff_id   == user_id,
                    TNoticeRead.staff_type == staff_type,
                )
            ).all()}
        else:
            read_ids = set()
        for n in notices_list:
            n.is_read = (n.id in read_ids)
        notice_unread_count = sum(1 for n in notices_list if not n.is_read)
        return render_template('staff_mypage_notices.html',
                               notices=notices_list,
                               unread_count=unread_count,
                               notice_unread_count=notice_unread_count)
    finally:
        db.close()


# ─────────────────────────────────────────────
# お知らせ詳細
# ─────────────────────────────────────────────
@bp.route('/notices/<int:notice_id>')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def notice_detail(notice_id):
    tenant_id = session.get('tenant_id')
    user_name = session.get('user_name', '')
    user_id   = session.get('user_id')
    role      = session.get('role', '')
    staff_type = 'employee' if role == ROLES['EMPLOYEE'] else 'admin'
    db = SessionLocal()
    try:
        unread_count = _get_unread_count(tenant_id, user_name)
        notice = db.query(TNotice).filter(
            and_(TNotice.id == notice_id, TNotice.tenant_id == tenant_id)
        ).first()
        if not notice:
            flash('お知らせが見つかりません', 'error')
            return redirect(url_for('staff_mypage.notices'))
        # 既読マーク
        if user_id:
            already = db.query(TNoticeRead).filter(
                and_(
                    TNoticeRead.notice_id  == notice_id,
                    TNoticeRead.staff_id   == user_id,
                    TNoticeRead.staff_type == staff_type,
                )
            ).first()
            if not already:
                db.add(TNoticeRead(
                    notice_id  = notice_id,
                    staff_id   = user_id,
                    staff_type = staff_type,
                ))
                db.commit()
        return render_template('staff_mypage_notice_detail.html',
                               notice=notice,
                               unread_count=unread_count)
    finally:
        db.close()


# ─────────────────────────────────────────────
# お知らせ投稿（tenant_admin / admin のみ）
# ─────────────────────────────────────────────
@bp.route('/notices/new', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def notice_new():
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    user_name = session.get('user_name', '')
    db = SessionLocal()
    try:
        unread_count = _get_unread_count(tenant_id, user_name)

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            body = request.form.get('body', '').strip()
            is_important = 1 if request.form.get('is_important') else 0
            if not title:
                flash('タイトルは必須です', 'error')
            else:
                notice = TNotice(
                    tenant_id=tenant_id,
                    title=title,
                    body=body,
                    author_id=user_id,
                    author_name=user_name,
                    is_important=is_important,
                    published_at=datetime.now()
                )
                db.add(notice)
                db.commit()
                flash('お知らせを投稿しました', 'success')
                return redirect(url_for('staff_mypage.notices'))

        return render_template('staff_mypage_notice_new.html', unread_count=unread_count)
    finally:
        db.close()


# ─────────────────────────────────────────────
# お知らせ削除（tenant_admin / admin のみ）
# ─────────────────────────────────────────────
@bp.route('/notices/<int:notice_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def notice_delete(notice_id):
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        notice = db.query(TNotice).filter(
            and_(TNotice.id == notice_id, TNotice.tenant_id == tenant_id)
        ).first()
        if notice:
            db.delete(notice)
            db.commit()
            flash('お知らせを削除しました', 'success')
        return redirect(url_for('staff_mypage.notices'))
    finally:
        db.close()


# ─────────────────────────────────────────────
# GPS位置記録 API（勤怠画面からのAjaxリクエスト用）
# ─────────────────────────────────────────────
@bp.route('/attendance/location', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def record_location():
    """勤怠中のGPS位置を記録するAPIエンドポイント

    JSONボディ: { latitude, longitude, accuracy, is_background }
    """
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    role = session.get('role', '')
    staff_type = 'employee' if role == ROLES['EMPLOYEE'] else 'admin'

    data = request.get_json(silent=True) or {}
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy')
    is_background = 1 if data.get('is_background') else 0

    if latitude is None or longitude is None:
        return jsonify({'ok': False, 'error': '緯度・経度が必要です'}), 400

    db = SessionLocal()
    try:
        today = date.today()
        # 今日の勤怠レコードを取得（attendance_idの紐付け用）
        today_record = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.staff_id == user_id,
                 TAttendance.staff_type == staff_type,
                 TAttendance.work_date == today)
        ).first()

        loc = TAttendanceLocation(
            tenant_id=tenant_id,
            attendance_id=today_record.id if today_record else None,
            staff_id=user_id,
            staff_type=staff_type,
            latitude=float(latitude),
            longitude=float(longitude),
            accuracy=float(accuracy) if accuracy is not None else None,
            is_background=is_background,
            recorded_at=datetime.now()
        )
        db.add(loc)
        db.commit()
        return jsonify({'ok': True, 'id': loc.id})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/attendance/location/today')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def today_locations():
    """今日のGPS位置履歴を返すAPIエンドポイント"""
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    role = session.get('role', '')
    staff_type = 'employee' if role == ROLES['EMPLOYEE'] else 'admin'

    db = SessionLocal()
    try:
        today = date.today()
        today_record = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.staff_id == user_id,
                 TAttendance.staff_type == staff_type,
                 TAttendance.work_date == today)
        ).first()

        if not today_record:
            return jsonify({'locations': [], 'count': 0})

        locs = db.query(TAttendanceLocation).filter(
            and_(TAttendanceLocation.attendance_id == today_record.id,
                 TAttendanceLocation.tenant_id == tenant_id)
        ).order_by(TAttendanceLocation.recorded_at.asc()).all()

        result = [{
            'id': l.id,
            'latitude': l.latitude,
            'longitude': l.longitude,
            'accuracy': l.accuracy,
            'is_background': l.is_background,
            'recorded_at': l.recorded_at.strftime('%H:%M:%S')
        } for l in locs]

        return jsonify({'locations': result, 'count': len(result)})
    finally:
        db.close()


# ─────────────────────────────────────────────
# 管理者向け：スタッフ位置確認画面
# ─────────────────────────────────────────────
@bp.route('/attendance/map')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def attendance_map():
    """管理者向け：スタッフの当日移動ルートを地図で確認する画面"""
    tenant_id = session.get('tenant_id')
    user_name = session.get('user_name', '')
    db = SessionLocal()
    try:
        unread_count = _get_unread_count(tenant_id, user_name)
        today = date.today()

        # 対象日（クエリパラメータで変更可能）
        date_str = request.args.get('date', today.strftime('%Y-%m-%d'))
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            target_date = today

        # 対象スタッフID（未指定なら全スタッフ）
        staff_id_param = request.args.get('staff_id')

        # テナント内の全スタッフ（管理者 + 従業員）を取得
        admins = db.query(TKanrisha).filter(
            and_(TKanrisha.tenant_id == tenant_id, TKanrisha.active == 1)
        ).all()
        employees = db.query(TJugyoin).filter(
            and_(TJugyoin.tenant_id == tenant_id, TJugyoin.active == 1)
        ).all()

        staff_list = [{'id': a.id, 'name': a.name, 'type': 'admin'} for a in admins]
        staff_list += [{'id': e.id, 'name': e.name, 'type': 'employee'} for e in employees]

        # 対象日の勤怠レコードを取得
        attendances = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.work_date == target_date)
        ).all()
        attendance_map_by_key = {
            (a.staff_id, a.staff_type): a for a in attendances
        }

        # GPS位置履歴を取得
        loc_query = db.query(TAttendanceLocation).filter(
            and_(TAttendanceLocation.tenant_id == tenant_id,
                 TAttendanceLocation.recorded_at >= datetime.combine(target_date, datetime.min.time()),
                 TAttendanceLocation.recorded_at < datetime.combine(target_date + timedelta(days=1), datetime.min.time()))
        )
        if staff_id_param:
            try:
                sid = int(staff_id_param)
                loc_query = loc_query.filter(TAttendanceLocation.staff_id == sid)
            except ValueError:
                pass

        locations = loc_query.order_by(
            TAttendanceLocation.staff_id.asc(),
            TAttendanceLocation.recorded_at.asc()
        ).all()

        # スタッフごとに位置データをまとめる
        staff_tracks = {}
        for loc in locations:
            key = (loc.staff_id, loc.staff_type)
            if key not in staff_tracks:
                staff_tracks[key] = []
            staff_tracks[key].append({
                'lat': loc.latitude,
                'lng': loc.longitude,
                'accuracy': loc.accuracy,
                'is_background': loc.is_background,
                'time': loc.recorded_at.strftime('%H:%M:%S')
            })

        # テンプレートに渡すデータを整形
        tracks_data = []
        for s in staff_list:
            key = (s['id'], s['type'])
            att = attendance_map_by_key.get(key)
            pts = staff_tracks.get(key, [])
            tracks_data.append({
                'staff_id': s['id'],
                'staff_name': s['name'],
                'staff_type': s['type'],
                'clock_in': att.clock_in.strftime('%H:%M') if att and att.clock_in else None,
                'clock_out': att.clock_out.strftime('%H:%M') if att and att.clock_out else None,
                'points': pts,
                'point_count': len(pts)
            })

        # 位置データがあるスタッフを先頭に
        tracks_data.sort(key=lambda x: -x['point_count'])

        return render_template('staff_attendance_map.html',
                               tracks_data=tracks_data,
                               staff_list=staff_list,
                               target_date=target_date,
                               date_str=date_str,
                               selected_staff_id=staff_id_param,
                               unread_count=unread_count)
    finally:
        db.close()
