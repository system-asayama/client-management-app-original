# -*- coding: utf-8 -*-
"""
スタッフマイページ ブループリント
税理士事務所側スタッフ（tenant_admin / admin / employee）向けのマイページ機能
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from sqlalchemy import and_, or_, func as sqlfunc
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')

def now_jst():
    """日本時間（JST）の現在時刻をタイムゾーンなしdatetimeで返す"""
    return datetime.now(JST).replace(tzinfo=None)

def today_jst():
    """日本時間（JST）の今日の日付を返す"""
    return datetime.now(JST).date()
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
        today = today_jst()
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

        android_apk_url = getattr(tenant, 'android_apk_url', None) if tenant else None
        android_apk_version = getattr(tenant, 'android_apk_version', None) if tenant else None
        return render_template('staff_mypage_dashboard.html',
                               tenant=tenant,
                               assigned_count=assigned_count,
                               total_clients=total_clients,
                               unread_count=unread_count,
                               notices=notices,
                               today_attendance=today_attendance,
                               upcoming_deadlines=upcoming_deadlines,
                               today=today,
                               android_apk_url=android_apk_url,
                               android_apk_version=android_apk_version)
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

        year = int(request.args.get('year', today_jst().year))
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
        today = today_jst()

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
# 勤怠管理（/kintaikanri/ へ移動済み）
# 旧URLからの後方互換リダイレクト
# ─────────────────────────────────────────────
@bp.route('/attendance', methods=['GET', 'POST'])
@bp.route('/attendance/', methods=['GET', 'POST'])
def attendance():
    """旧URL → /kintaikanri/attendance/ へ301リダイレクト"""
    month = request.args.get('month', '')
    if month:
        return redirect(url_for('kintaikanri.attendance', month=month), code=301)
    return redirect(url_for('kintaikanri.attendance'), code=301)


@bp.route('/attendance/location', methods=['POST'])
def record_location():
    """旧URL → /kintaikanri/attendance/location へ301リダイレクト"""
    return redirect(url_for('kintaikanri.record_location'), code=301)


@bp.route('/attendance/location/today')
def today_locations():
    """旧URL → /kintaikanri/attendance/location/today へ301リダイレクト"""
    return redirect(url_for('kintaikanri.today_locations'), code=301)


@bp.route('/attendance/map')
def attendance_map():
    """旧URL → /kintaikanri/attendance/map へ301リダイレクト"""
    date_str = request.args.get('date', '')
    staff_id = request.args.get('staff_id', '')
    kwargs = {}
    if date_str:
        kwargs['date'] = date_str
    if staff_id:
        kwargs['staff_id'] = staff_id
    return redirect(url_for('kintaikanri.attendance_map', **kwargs), code=301)


@bp.route('/attendance/realtime_mode', methods=['POST', 'GET'])
def toggle_realtime_mode():
    """旧URL → /kintaikanri/attendance/realtime_mode へ301リダイレクト"""
    return redirect(url_for('kintaikanri.toggle_realtime_mode'), code=301)


@bp.route('/attendance/map/realtime_data')
def attendance_map_realtime_data():
    """旧URL → /kintaikanri/attendance/map/realtime_data へ301リダイレクト"""
    date_str = request.args.get('date', '')
    staff_id = request.args.get('staff_id', '')
    kwargs = {}
    if date_str:
        kwargs['date'] = date_str
    if staff_id:
        kwargs['staff_id'] = staff_id
    return redirect(url_for('kintaikanri.attendance_map_realtime_data', **kwargs), code=301)

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
                    published_at=now_jst()
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
# APKプロキシダウンロード（永続URL）
# ─────────────────────────────────────────────
@bp.route('/apk_download')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def apk_download():
    """APKファイルをプロキシ配信する（署名付きURLの期限切れに依存しない永続エンドポイント）"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        apk_url = getattr(tenant, 'android_apk_url', None) if tenant else None
        if not apk_url:
            flash('APKファイルが設定されていません。管理者にお問い合わせください。', 'error')
            return redirect(url_for('staff_mypage.dashboard'))
        import requests as req_lib
        from flask import Response, stream_with_context
        try:
            resp = req_lib.get(apk_url, stream=True, timeout=30)
            if resp.status_code == 200:
                apk_version = getattr(tenant, 'android_apk_version', None) or '1.0'
                filename = 'staff-gps-app-{}.apk'.format(apk_version)
                return Response(
                    stream_with_context(resp.iter_content(chunk_size=8192)),
                    content_type='application/vnd.android.package-archive',
                    headers={
                        'Content-Disposition': 'attachment; filename="{}"'.format(filename),
                        'Content-Length': resp.headers.get('Content-Length', ''),
                    }
                )
            else:
                flash('APKファイルのダウンロードに失敗しました（HTTP {}）。管理者にお問い合わせください。'.format(resp.status_code), 'error')
                return redirect(url_for('staff_mypage.dashboard'))
        except Exception as e:
            flash('APKファイルの取得中にエラーが発生しました: {}'.format(str(e)), 'error')
            return redirect(url_for('staff_mypage.dashboard'))
    finally:
        db.close()
