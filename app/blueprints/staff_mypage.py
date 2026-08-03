# -*- coding: utf-8 -*-
"""
スタッフマイページ ブループリント
税理士事務所側スタッフ（tenant_admin / admin / employee）向けのマイページ機能
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify, current_app
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
from app.models_integrations import (
    TStaffMailAccount, TReceivedFile, TStaffChatworkAccount, TChatworkRoomMapping,
)
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

        # ログインユーザーのgps_modeを取得
        from app.models_login import TKanrisha, TJugyoin
        if role == ROLES['EMPLOYEE']:
            staff_obj = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
        else:
            staff_obj = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        staff_gps_mode = getattr(staff_obj, 'gps_mode', None) or 'always'

        # ログインユーザーの所属店舗一覧を取得
        from app.models_login import TKanrishaTenpo, TJugyoinTenpo, TTenpo
        if role == ROLES['EMPLOYEE']:
            store_links = db.query(TJugyoinTenpo, TTenpo).join(
                TTenpo, TJugyoinTenpo.store_id == TTenpo.id
            ).filter(TJugyoinTenpo.employee_id == user_id).all()
        else:
            store_links = db.query(TKanrishaTenpo, TTenpo).join(
                TTenpo, TKanrishaTenpo.store_id == TTenpo.id
            ).filter(TKanrishaTenpo.admin_id == user_id).all()
        staff_stores = [{'id': t.id, 'name': getattr(t, '名称', str(t.id))} for _, t in store_links]

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
                               android_apk_version=android_apk_version,
                               staff_gps_mode=staff_gps_mode,
                               staff_stores=staff_stores)
    finally:
        db.close()


# ─────────────────────────────────────────────
# プロフィール設定
# ─────────────────────────────────────────────
@bp.route('/mail', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def mail_settings():
    """自分のメール受信連携（担当ごと）"""
    from app.utils.integrations.mail import MAIL_PROVIDERS
    from app.services.scheduler import get_state
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        flash('ユーザーが見つかりません', 'error')
        return redirect(url_for('staff_mypage.dashboard'))

    db = SessionLocal()
    try:
        accounts = (db.query(TStaffMailAccount)
                      .filter(TStaffMailAccount.tenant_id == tenant_id,
                              TStaffMailAccount.staff_id == user.id,
                              TStaffMailAccount.staff_type == staff_type)
                      .order_by(TStaffMailAccount.id.desc()).all())
        acc_ids = [a.id for a in accounts]
        recent = []
        if acc_ids:
            recent = (db.query(TReceivedFile)
                        .filter(TReceivedFile.tenant_id == tenant_id,
                                TReceivedFile.provider == 'mail')
                        .order_by(TReceivedFile.id.desc()).limit(15).all())
        unread_count = _get_unread_count(tenant_id, session.get('user_name', ''))
        return render_template('staff_mypage_mail.html',
                               accounts=accounts, providers=MAIL_PROVIDERS,
                               recent=recent, sched=get_state(),
                               unread_count=unread_count)
    finally:
        db.close()


@bp.route('/mail/save', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def mail_save():
    """メールアカウントの追加・更新（保存時にIMAP疎通確認）"""
    from app.utils.integrations.mail import resolve_host_port, ImapMailClient, MailError
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.dashboard'))

    provider = (request.form.get('provider') or 'gmail').strip()
    email_addr = (request.form.get('email') or '').strip()
    app_password = (request.form.get('app_password') or '').strip()
    host_in = (request.form.get('imap_host') or '').strip()
    port_in = request.form.get('imap_port')
    host, port = resolve_host_port(provider, host_in, port_in)

    if not email_addr or not app_password:
        flash('メールアドレスとアプリパスワードを入力してください', 'error')
        return redirect(url_for('staff_mypage.mail_settings'))

    # 疎通確認
    try:
        ImapMailClient(email_addr, app_password, host, port).verify()
    except MailError as e:
        flash(f'メール接続に失敗しました: {e}', 'error')
        return redirect(url_for('staff_mypage.mail_settings'))

    db = SessionLocal()
    try:
        existing = (db.query(TStaffMailAccount)
                      .filter(TStaffMailAccount.tenant_id == tenant_id,
                              TStaffMailAccount.staff_id == user.id,
                              TStaffMailAccount.staff_type == staff_type,
                              TStaffMailAccount.email == email_addr)
                      .first())
        if existing:
            existing.provider = provider
            existing.imap_host = host
            existing.imap_port = port
            existing.app_password = app_password
            existing.status = 'active'
        else:
            db.add(TStaffMailAccount(
                tenant_id=tenant_id, staff_id=user.id, staff_type=staff_type,
                provider=provider, email=email_addr, imap_host=host, imap_port=port,
                app_password=app_password, since_uid=0, status='active'))
        db.commit()
        flash('メール連携を保存しました', 'success')
    finally:
        db.close()
    return redirect(url_for('staff_mypage.mail_settings'))


@bp.route('/mail/<int:account_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def mail_delete(account_id):
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.dashboard'))
    db = SessionLocal()
    try:
        acc = (db.query(TStaffMailAccount)
                 .filter(TStaffMailAccount.id == account_id,
                         TStaffMailAccount.tenant_id == tenant_id,
                         TStaffMailAccount.staff_id == user.id,
                         TStaffMailAccount.staff_type == staff_type).first())
        if acc:
            db.delete(acc)
            db.commit()
            flash('メール連携を削除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('staff_mypage.mail_settings'))


@bp.route('/mail/sync', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def mail_sync_now():
    """自分のメールを今すぐ取得"""
    from app.services.mail_sync import sync_account
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.dashboard'))
    db = SessionLocal()
    try:
        ids = [a.id for a in db.query(TStaffMailAccount).filter(
            TStaffMailAccount.tenant_id == tenant_id,
            TStaffMailAccount.staff_id == user.id,
            TStaffMailAccount.staff_type == staff_type,
            TStaffMailAccount.status == 'active').all()]
    finally:
        db.close()
    saved = skipped = errs = 0
    for aid in ids:
        r = sync_account(aid)
        saved += r['saved']; skipped += r['skipped']; errs += len(r['errors'])
    msg = f"取得完了: 保存 {saved}件 / スキップ {skipped}件"
    flash(msg + (f" / エラー {errs}件" if errs else ''), 'warning' if errs else 'success')
    return redirect(url_for('staff_mypage.mail_settings'))


# ============================================================
# ChatWork連携（担当ごと）
#   ChatWork のAPIトークンはアカウント（個人）ごとに発行されるため、
#   顧問先とやり取りしている担当者本人のトークンを担当単位で登録する。
# ============================================================
@bp.route('/chatwork', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chatwork_settings():
    """自分のChatWork連携（担当ごと）"""
    from app.services.scheduler import get_state
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        flash('ユーザーが見つかりません', 'error')
        return redirect(url_for('staff_mypage.dashboard'))

    db = SessionLocal()
    try:
        account = (db.query(TStaffChatworkAccount)
                     .filter(TStaffChatworkAccount.tenant_id == tenant_id,
                             TStaffChatworkAccount.staff_id == user.id,
                             TStaffChatworkAccount.staff_type == staff_type)
                     .order_by(TStaffChatworkAccount.id.desc()).first())
        mappings = []
        if account:
            mappings = (db.query(TChatworkRoomMapping)
                          .filter(TChatworkRoomMapping.tenant_id == tenant_id,
                                  TChatworkRoomMapping.staff_account_id == account.id)
                          .order_by(TChatworkRoomMapping.id.desc()).all())
        clients = (db.query(TClient)
                     .filter(TClient.tenant_id == tenant_id)
                     .order_by(TClient.name).all())
        client_names = {c.id: c.name for c in clients}
        recent = (db.query(TReceivedFile)
                    .filter(TReceivedFile.tenant_id == tenant_id,
                            TReceivedFile.provider == 'chatwork')
                    .order_by(TReceivedFile.id.desc()).limit(15).all())
        unread_count = _get_unread_count(tenant_id, session.get('user_name', ''))
        return render_template('staff_mypage_chatwork.html',
                               account=account, mappings=mappings,
                               clients=clients, client_names=client_names,
                               recent=recent, sched=get_state(),
                               unread_count=unread_count)
    finally:
        db.close()


@bp.route('/chatwork/save', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chatwork_save():
    """ChatWork APIトークンの登録・更新（保存時に疎通確認）"""
    from app.utils.integrations.chatwork import ChatworkClient, ChatworkError
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.dashboard'))

    api_token = (request.form.get('api_token') or '').strip()
    if not api_token:
        flash('APIトークンを入力してください', 'error')
        return redirect(url_for('staff_mypage.chatwork_settings'))

    # 疎通確認 & アカウント名取得
    account_name = None
    cw_account_id = None
    try:
        me = ChatworkClient(api_token).get_me()
        if isinstance(me, dict):
            account_name = me.get('name')
            cw_account_id = str(me.get('account_id')) if me.get('account_id') is not None else None
    except ChatworkError as e:
        flash(f'トークンの検証に失敗しました: {e}', 'error')
        return redirect(url_for('staff_mypage.chatwork_settings'))

    db = SessionLocal()
    try:
        existing = (db.query(TStaffChatworkAccount)
                      .filter(TStaffChatworkAccount.tenant_id == tenant_id,
                              TStaffChatworkAccount.staff_id == user.id,
                              TStaffChatworkAccount.staff_type == staff_type)
                      .first())
        if existing:
            existing.api_token = api_token
            existing.account_name = account_name or existing.account_name
            existing.chatwork_account_id = cw_account_id or existing.chatwork_account_id
            existing.status = 'active'
        else:
            db.add(TStaffChatworkAccount(
                tenant_id=tenant_id, staff_id=user.id, staff_type=staff_type,
                api_token=api_token, account_name=account_name,
                chatwork_account_id=cw_account_id, status='active'))
        db.commit()
        flash('ChatWork連携を保存しました', 'success')
    finally:
        db.close()
    return redirect(url_for('staff_mypage.chatwork_settings'))


@bp.route('/chatwork/rooms', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chatwork_rooms():
    """自分のChatWorkルーム一覧を取得（マッピングUIの候補）"""
    from app.utils.integrations.chatwork import ChatworkClient, ChatworkError
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return jsonify({'error': 'no user'}), 400
    db = SessionLocal()
    try:
        account = (db.query(TStaffChatworkAccount)
                     .filter(TStaffChatworkAccount.tenant_id == tenant_id,
                             TStaffChatworkAccount.staff_id == user.id,
                             TStaffChatworkAccount.staff_type == staff_type)
                     .order_by(TStaffChatworkAccount.id.desc()).first())
        if not account or not account.api_token:
            return jsonify({'error': 'ChatWork連携が未設定です'}), 400
        token = account.api_token
    finally:
        db.close()
    try:
        rooms = ChatworkClient(token).list_rooms()
    except ChatworkError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'rooms': [
        {'room_id': r.get('room_id'), 'name': r.get('name')}
        for r in (rooms or [])
    ]})


@bp.route('/chatwork/map', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chatwork_map():
    """自分のルーム → 顧問先 の紐付けを保存"""
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.dashboard'))

    room_id = (request.form.get('room_id') or '').strip()
    room_name = (request.form.get('room_name') or '').strip()
    client_id = request.form.get('client_id')
    subfolder = (request.form.get('subfolder') or 'ChatWork受信').strip()

    if not room_id or not client_id:
        flash('ルームと顧問先を指定してください', 'error')
        return redirect(url_for('staff_mypage.chatwork_settings'))

    db = SessionLocal()
    try:
        account = (db.query(TStaffChatworkAccount)
                     .filter(TStaffChatworkAccount.tenant_id == tenant_id,
                             TStaffChatworkAccount.staff_id == user.id,
                             TStaffChatworkAccount.staff_type == staff_type)
                     .order_by(TStaffChatworkAccount.id.desc()).first())
        if not account:
            flash('先にChatWorkトークンを登録してください', 'error')
            return redirect(url_for('staff_mypage.chatwork_settings'))

        # 同一アカウント・同一ルームの重複マッピングは上書き
        existing = (db.query(TChatworkRoomMapping)
                      .filter(TChatworkRoomMapping.tenant_id == tenant_id,
                              TChatworkRoomMapping.staff_account_id == account.id,
                              TChatworkRoomMapping.room_id == room_id)
                      .first())
        if existing:
            existing.client_id = int(client_id)
            existing.room_name = room_name or existing.room_name
            existing.subfolder = subfolder
            existing.status = 'active'
        else:
            db.add(TChatworkRoomMapping(
                tenant_id=tenant_id, staff_account_id=account.id,
                room_id=room_id, room_name=room_name,
                client_id=int(client_id), subfolder=subfolder, status='active'))
        db.commit()
        flash('ルームの紐付けを保存しました', 'success')
    finally:
        db.close()
    return redirect(url_for('staff_mypage.chatwork_settings'))


@bp.route('/chatwork/map/<int:mapping_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chatwork_map_delete(mapping_id):
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.dashboard'))
    db = SessionLocal()
    try:
        # 自分のアカウントに属するマッピングのみ削除可能
        account_ids = [a.id for a in db.query(TStaffChatworkAccount).filter(
            TStaffChatworkAccount.tenant_id == tenant_id,
            TStaffChatworkAccount.staff_id == user.id,
            TStaffChatworkAccount.staff_type == staff_type).all()]
        m = (db.query(TChatworkRoomMapping)
               .filter(TChatworkRoomMapping.id == mapping_id,
                       TChatworkRoomMapping.tenant_id == tenant_id,
                       TChatworkRoomMapping.staff_account_id.in_(account_ids or [-1]))
               .first())
        if m:
            db.delete(m)
            db.commit()
            flash('紐付けを削除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('staff_mypage.chatwork_settings'))


@bp.route('/chatwork/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chatwork_delete():
    """自分のChatWork連携（トークン）を削除"""
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.dashboard'))
    db = SessionLocal()
    try:
        acc = (db.query(TStaffChatworkAccount)
                 .filter(TStaffChatworkAccount.tenant_id == tenant_id,
                         TStaffChatworkAccount.staff_id == user.id,
                         TStaffChatworkAccount.staff_type == staff_type).first())
        if acc:
            db.delete(acc)
            db.commit()
            flash('ChatWork連携を削除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('staff_mypage.chatwork_settings'))


@bp.route('/chatwork/sync', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chatwork_sync_now():
    """自分のChatWorkを今すぐ取得"""
    from app.services.chatwork_sync import sync_staff_account
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.dashboard'))
    db = SessionLocal()
    try:
        ids = [a.id for a in db.query(TStaffChatworkAccount).filter(
            TStaffChatworkAccount.tenant_id == tenant_id,
            TStaffChatworkAccount.staff_id == user.id,
            TStaffChatworkAccount.staff_type == staff_type,
            TStaffChatworkAccount.status == 'active').all()]
    finally:
        db.close()
    saved = skipped = errs = 0
    for aid in ids:
        r = sync_staff_account(aid)
        saved += r['saved']; skipped += r['skipped']; errs += len(r['errors'])
    msg = f"取得完了: 保存 {saved}件 / スキップ {skipped}件"
    flash(msg + (f" / エラー {errs}件" if errs else ''), 'warning' if errs else 'success')
    return redirect(url_for('staff_mypage.chatwork_settings'))


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

        # 担当顧問先を取得（スキーマ差異などで失敗しても画面は表示する）
        assignments = []
        assigned_client_ids = []
        assignment_map = {}
        try:
            assignments = db.query(TClientAssignment).filter(
                and_(TClientAssignment.tenant_id == tenant_id,
                     TClientAssignment.staff_id == user_id)
            ).all()
            assigned_client_ids = [a.client_id for a in assignments]
            assignment_map = {a.client_id: a for a in assignments}
        except Exception as e:
            current_app.logger.exception('Failed to load client assignments on /staff/clients: %s', e)
            # 一般スタッフは担当情報が取得できない場合、空表示にする（権限過剰表示を防ぐ）
            if role not in (ROLES['TENANT_ADMIN'], ROLES['SYSTEM_ADMIN']):
                flash('担当顧問先情報の取得に失敗しました。管理者にお問い合わせください。', 'warning')

        if role in (ROLES['TENANT_ADMIN'], ROLES['SYSTEM_ADMIN']):
            # 管理者は全顧問先を表示
            clients = db.query(TClient).filter(TClient.tenant_id == tenant_id).order_by(TClient.name).all()
        else:
            # スタッフは担当顧問先のみ
            clients = db.query(TClient).filter(
                TClient.id.in_(assigned_client_ids)
            ).order_by(TClient.name).all() if assigned_client_ids else []

        # 各顧問先の未読チャット数
        unread_by_client = {}
        try:
            read_ids = {r.message_id for r in db.query(TMessageRead).filter(
                TMessageRead.reader_type == 'staff',
                TMessageRead.reader_id == user_name
            ).all()}
            for client in clients:
                msgs = db.query(TMessage).filter(
                    and_(TMessage.client_id == client.id, TMessage.sender_type == 'client')
                ).all()
                unread_by_client[client.id] = sum(1 for m in msgs if m.id not in read_ids)
        except Exception as e:
            current_app.logger.exception('Failed to load unread chat counters on /staff/clients: %s', e)
            unread_by_client = {c.id: 0 for c in clients}

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
        today = today_jst()

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

        # 今日の勤怠：未退勤のレコードを優先（再出勤対応）
        today_record = db.query(TAttendance).filter(
            and_(TAttendance.tenant_id == tenant_id,
                 TAttendance.staff_id == user_id,
                 TAttendance.staff_type == staff_type,
                 TAttendance.work_date == today,
                 TAttendance.clock_out == None)
        ).order_by(TAttendance.id.desc()).first()
        # 未退勤レコードがなければ最新レコードを取得（退勤済み状態の表示用）
        if not today_record:
            today_record = db.query(TAttendance).filter(
                and_(TAttendance.tenant_id == tenant_id,
                     TAttendance.staff_id == user_id,
                     TAttendance.staff_type == staff_type,
                     TAttendance.work_date == today)
            ).order_by(TAttendance.id.desc()).first()

        # ログインユーザーのgps_modeを取得
        from app.models_login import TKanrisha as _TK, TJugyoin as _TJ
        if role == ROLES['EMPLOYEE']:
            _staff_obj = db.query(_TJ).filter(_TJ.id == user_id).first()
        else:
            _staff_obj = db.query(_TK).filter(_TK.id == user_id).first()
        staff_gps_mode = getattr(_staff_obj, 'gps_mode', None) or 'always'

        # 所属店舗一覧を取得
        from app.models_login import TKanrishaTenpo, TJugyoinTenpo, TTenpo
        if role == ROLES['EMPLOYEE']:
            _store_links = db.query(TJugyoinTenpo, TTenpo).join(
                TTenpo, TJugyoinTenpo.store_id == TTenpo.id
            ).filter(TJugyoinTenpo.employee_id == user_id).all()
        else:
            _store_links = db.query(TKanrishaTenpo, TTenpo).join(
                TTenpo, TKanrishaTenpo.store_id == TTenpo.id
            ).filter(TKanrishaTenpo.admin_id == user_id).all()
        staff_stores = [{'id': t.id, 'name': getattr(t, '名称', str(t.id))} for _, t in _store_links]

        if request.method == 'POST':
            action = request.form.get('action', '')

            # alwaysモードはWebからの出退勤操作をブロック
            if staff_gps_mode == 'always' and action in ('clock_in', 'clock_out', 'break_start', 'break_end'):
                flash('このアカウントはGPS常時記録モードです。アプリから出退勤操作を行ってください。', 'error')
                return redirect(url_for('staff_mypage.attendance'))

            if action == 'clock_in':
                if today_record and today_record.clock_in and not today_record.clock_out:
                    flash('本日はすでに出勤中です', 'warning')
                else:
                    now = now_jst()
                    if today_record and not today_record.clock_in:
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
                    now = now_jst()
                    today_record.clock_out = now
                    today_record.updated_at = now
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
                    now = now_jst()
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
                    now = now_jst()
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
                        rec.updated_at = now_jst()
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

        # GPS設定をテナント設定から取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        gps_enabled = getattr(tenant_obj, 'gps_enabled', 0) or 0
        gps_interval_minutes = getattr(tenant_obj, 'gps_interval_minutes', 10) or 10
        gps_continuous = getattr(tenant_obj, 'gps_continuous', 0) or 0

        return render_template('staff_mypage_attendance.html',
                               records=records,
                               today_record=today_record,
                               today=today,
                               month_str=month_str,
                               year_m=year_m,
                               mon_m=mon_m,
                               total_work_minutes=total_work_minutes,
                               unread_count=unread_count,
                               gps_enabled=gps_enabled,
                               gps_interval_minutes=gps_interval_minutes,
                               gps_continuous=gps_continuous,
                               staff_gps_mode=staff_gps_mode,
                               staff_stores=staff_stores)
    finally:
        db.close()


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


# ============================================================
# 担当者ごとの個人ストレージ連携（自分のDropbox）
#   保存先の優先順位: 担当者個人 → 店舗 → 本部
#   メール/ChatWork連携と同じく、担当者本人がマイページから設定する。
# ============================================================
def _staff_set_primary_assignment(db, tenant_id, staff_id, staff_type, connection_id):
    """担当者スコープの「主に使用する接続」を connection_id に設定する。"""
    from app.models_integrations import TStoreStorageAssignment
    for a in (db.query(TStoreStorageAssignment)
                .filter(TStoreStorageAssignment.tenant_id == tenant_id,
                        TStoreStorageAssignment.staff_id == staff_id,
                        TStoreStorageAssignment.staff_type == staff_type,
                        TStoreStorageAssignment.status == 'active',
                        TStoreStorageAssignment.is_primary == 1).all()):
        a.is_primary = 0
        a.status = 'inactive'
    db.add(TStoreStorageAssignment(
        tenant_id=tenant_id, staff_id=staff_id, staff_type=staff_type,
        connection_id=connection_id, is_primary=1, status='active'))


def _staff_connect_dropbox(db, tenant_id, staff_id, staff_type,
                           access_token, refresh_token, name):
    """担当者の個人Dropbox接続を追加/更新（同一アカウントの重複は作らない）。"""
    from app.models_integrations import TStorageConnection
    from app.blueprints.tenant_storage import _dropbox_account_ref
    account_ref = _dropbox_account_ref(access_token, refresh_token, tenant_id)
    existing = None
    if account_ref:
        existing = (db.query(TStorageConnection)
                      .filter(TStorageConnection.tenant_id == tenant_id,
                              TStorageConnection.provider == 'dropbox',
                              TStorageConnection.status == 'active',
                              TStorageConnection.staff_id == staff_id,
                              TStorageConnection.staff_type == staff_type,
                              TStorageConnection.account_ref == account_ref)
                      .order_by(TStorageConnection.id.desc()).first())
    if existing:
        existing.access_token = access_token
        if refresh_token:
            existing.refresh_token = refresh_token
        existing.status = 'active'
        _staff_set_primary_assignment(db, tenant_id, staff_id, staff_type, existing.id)
        return existing, True
    conn = TStorageConnection(
        tenant_id=tenant_id, staff_id=staff_id, staff_type=staff_type,
        name=name, provider='dropbox', access_token=access_token,
        refresh_token=refresh_token, account_ref=account_ref, status='active')
    db.add(conn)
    db.flush()
    _staff_set_primary_assignment(db, tenant_id, staff_id, staff_type, conn.id)
    return conn, False


def _staff_current_connection(db, tenant_id, staff_id, staff_type):
    """担当者の現在の主・個人ストレージ接続を返す（無ければ None）。"""
    from app.models_integrations import TStorageConnection, TStoreStorageAssignment
    a = (db.query(TStoreStorageAssignment)
           .filter(TStoreStorageAssignment.tenant_id == tenant_id,
                   TStoreStorageAssignment.staff_id == staff_id,
                   TStoreStorageAssignment.staff_type == staff_type,
                   TStoreStorageAssignment.is_primary == 1,
                   TStoreStorageAssignment.status == 'active')
           .order_by(TStoreStorageAssignment.id.desc()).first())
    if not a:
        return None
    return (db.query(TStorageConnection)
              .filter(TStorageConnection.id == a.connection_id,
                      TStorageConnection.status == 'active').first())


@bp.route('/storage', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def storage_settings():
    """自分の個人ストレージ連携（担当ごと）"""
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        flash('ユーザーが見つかりません', 'error')
        return redirect(url_for('staff_mypage.dashboard'))
    db = SessionLocal()
    try:
        conn = _staff_current_connection(db, tenant_id, user.id, staff_type)
        conn_view = None
        if conn:
            conn_view = {
                'name': conn.name or 'Dropbox',
                'provider': (conn.provider or '').lower(),
                'account_ref': conn.account_ref,
            }
        return render_template('staff_mypage_storage.html', conn=conn_view)
    finally:
        db.close()


@bp.route('/storage/dropbox/oauth/start', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def storage_dropbox_start():
    """担当者個人のDropbox OAuth を開始する。
    コールバックは登録済みのテナント用URL（tenant_storage.dropbox_oauth_callback）を
    共用し、セッションに担当者スコープを持たせて識別する
    （Dropboxアプリに従業員用の別Redirect URIを登録しなくて済むように統合）。
    """
    from dropbox import DropboxOAuth2Flow
    from app.utils.tenant_storage_adapter import get_dropbox_app_credentials
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user or not tenant_id:
        flash('ユーザーが見つかりません', 'error')
        return redirect(url_for('staff_mypage.storage_settings'))
    # 共用コールバックURL（登録済み）。担当者スコープをセッションに保持
    redirect_uri = url_for('tenant_storage.dropbox_oauth_callback', _external=True)
    session.pop('dropbox_scope_store_id', None)  # 店舗スコープ残りを消す
    session['dropbox_staff_scope'] = {
        'staff_id': user.id, 'staff_type': staff_type,
        'name': f'Dropbox（{getattr(user, "name", None) or "担当"}）',
    }
    app_key, app_secret = get_dropbox_app_credentials(tenant_id)
    auth_flow = DropboxOAuth2Flow(
        consumer_key=app_key, redirect_uri=redirect_uri, session=session,
        csrf_token_session_key='dropbox_csrf_token',
        consumer_secret=app_secret, token_access_type='offline')
    return redirect(auth_flow.start())


@bp.route('/storage/dropbox/oauth/callback', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def storage_dropbox_callback():
    """担当者個人のDropbox OAuth コールバック"""
    from dropbox import DropboxOAuth2Flow
    from dropbox.oauth import BadStateException, CsrfException, NotApprovedException
    from app.utils.tenant_storage_adapter import get_dropbox_app_credentials
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        flash('ユーザーが見つかりません', 'error')
        return redirect(url_for('staff_mypage.storage_settings'))
    redirect_uri = url_for('staff_mypage.storage_dropbox_callback', _external=True)
    app_key, app_secret = get_dropbox_app_credentials(tenant_id)
    auth_flow = DropboxOAuth2Flow(
        consumer_key=app_key, redirect_uri=redirect_uri, session=session,
        csrf_token_session_key='staff_dropbox_csrf',
        consumer_secret=app_secret, token_access_type='offline')
    try:
        res = auth_flow.finish(request.args)
        db = SessionLocal()
        try:
            _, updated = _staff_connect_dropbox(
                db, tenant_id, user.id, staff_type,
                res.access_token, res.refresh_token,
                name=f'Dropbox（{getattr(user, "name", None) or "担当"}）')
            db.commit()
            flash('個人Dropboxの連携を更新しました' if updated else '個人Dropboxとの連携が完了しました！', 'success')
        except Exception as e:
            db.rollback()
            flash(f'保存に失敗しました: {e}', 'error')
        finally:
            db.close()
    except BadStateException:
        flash('セッションが切れました。もう一度お試しください。', 'error')
    except CsrfException:
        flash('セキュリティエラーが発生しました。もう一度お試しください。', 'error')
    except NotApprovedException:
        flash('Dropboxの認証がキャンセルされました。', 'warning')
    except Exception as e:
        flash(f'Dropbox連携に失敗しました: {e}', 'error')
    return redirect(url_for('staff_mypage.storage_settings'))


@bp.route('/storage/disconnect', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def storage_disconnect():
    """自分の個人ストレージ連携を解除する（このアプリ内の割当を無効化）。"""
    from app.models_integrations import TStorageConnection, TStoreStorageAssignment
    user, staff_type, role = _get_current_user()
    tenant_id = session.get('tenant_id')
    if not user:
        return redirect(url_for('staff_mypage.storage_settings'))
    db = SessionLocal()
    try:
        # 担当者スコープの割当を無効化
        for a in (db.query(TStoreStorageAssignment)
                    .filter(TStoreStorageAssignment.tenant_id == tenant_id,
                            TStoreStorageAssignment.staff_id == user.id,
                            TStoreStorageAssignment.staff_type == staff_type,
                            TStoreStorageAssignment.status == 'active').all()):
            a.status = 'inactive'
            a.is_primary = 0
        # 担当者所有の接続も無効化
        for c in (db.query(TStorageConnection)
                    .filter(TStorageConnection.tenant_id == tenant_id,
                            TStorageConnection.staff_id == user.id,
                            TStorageConnection.staff_type == staff_type,
                            TStorageConnection.status == 'active').all()):
            c.status = 'inactive'
        db.commit()
        flash('個人ストレージ連携を解除しました', 'success')
    except Exception as e:
        db.rollback()
        flash(f'解除に失敗しました: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('staff_mypage.storage_settings'))
