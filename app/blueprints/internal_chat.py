"""
社内チャット（スタッフ間メッセージ）ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.db import SessionLocal
from app.models_login import (
    TKanrisha, TJugyoin, TInternalChatRoom,
    TInternalChatMember, TInternalMessage, TInternalMessageRead
)
from app.utils.decorators import require_roles, ROLES
from sqlalchemy import and_, or_, func as sqlfunc
from datetime import datetime

bp = Blueprint('internal_chat', __name__, url_prefix='/internal_chat')

STAFF_ROLES = (ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])


def _get_current_staff(db):
    """セッションから現在のスタッフ情報を取得する"""
    role = session.get('role', '')
    user_name = session.get('user_name', '')
    tenant_id = session.get('tenant_id')
    if role == 'employee':
        staff = db.query(TJugyoin).filter(
            and_(TJugyoin.login_id == user_name, TJugyoin.tenant_id == tenant_id)
        ).first()
        staff_type = 'employee'
    else:
        staff = db.query(TKanrisha).filter(
            and_(TKanrisha.login_id == user_name, TKanrisha.tenant_id == tenant_id)
        ).first()
        staff_type = 'admin'
    return staff, staff_type


def _get_unread_count_for_room(db, room_id, staff_id, staff_type):
    """指定ルームの未読数を取得する"""
    all_msgs = db.query(TInternalMessage.id).filter(
        TInternalMessage.room_id == room_id
    ).all()
    all_ids = [m.id for m in all_msgs]
    if not all_ids:
        return 0
    read_ids = [r.message_id for r in db.query(TInternalMessageRead).filter(
        and_(
            TInternalMessageRead.message_id.in_(all_ids),
            TInternalMessageRead.staff_id == staff_id,
            TInternalMessageRead.staff_type == staff_type,
        )
    ).all()]
    return len(all_ids) - len(read_ids)


@bp.route('/')
@require_roles(*STAFF_ROLES)
def room_list():
    """社内チャットルーム一覧"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        staff, staff_type = _get_current_staff(db)
        if not staff:
            flash('スタッフ情報が見つかりません', 'error')
            return redirect(url_for('staff_mypage.dashboard'))

        # 自分が参加しているルーム
        my_memberships = db.query(TInternalChatMember).filter(
            and_(
                TInternalChatMember.staff_id   == staff.id,
                TInternalChatMember.staff_type == staff_type,
            )
        ).all()
        room_ids = [m.room_id for m in my_memberships]

        rooms = db.query(TInternalChatRoom).filter(
            and_(
                TInternalChatRoom.id.in_(room_ids),
                TInternalChatRoom.tenant_id == tenant_id,
            )
        ).order_by(TInternalChatRoom.updated_at.desc()).all() if room_ids else []

        # 各ルームのメタ情報を付加
        for room in rooms:
            # 最新メッセージ
            last_msg = db.query(TInternalMessage).filter(
                TInternalMessage.room_id == room.id
            ).order_by(TInternalMessage.created_at.desc()).first()
            room.last_message = last_msg

            # 未読数
            room.unread_count = _get_unread_count_for_room(db, room.id, staff.id, staff_type)

            # メンバー名（1対1の場合は相手の名前）
            members = db.query(TInternalChatMember).filter(
                TInternalChatMember.room_id == room.id
            ).all()
            room.member_names = [m.staff_name for m in members if not (m.staff_id == staff.id and m.staff_type == staff_type)]
            if room.room_type == 'direct' and room.member_names:
                room.display_name = room.member_names[0]
            else:
                room.display_name = room.name or '名称未設定グループ'

        # 全スタッフ（新規DM作成用）
        all_admins    = db.query(TKanrisha).filter(
            and_(TKanrisha.tenant_id == tenant_id, TKanrisha.active == 1)
        ).order_by(TKanrisha.name).all()
        all_employees = db.query(TJugyoin).filter(
            and_(TJugyoin.tenant_id == tenant_id, TJugyoin.active == 1)
        ).order_by(TJugyoin.name).all()

        return render_template(
            'internal_chat_rooms.html',
            rooms         = rooms,
            staff         = staff,
            staff_type    = staff_type,
            all_admins    = all_admins,
            all_employees = all_employees,
        )
    finally:
        db.close()


@bp.route('/new_dm', methods=['POST'])
@require_roles(*STAFF_ROLES)
def new_dm():
    """1対1ダイレクトメッセージルームを作成する"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        staff, staff_type = _get_current_staff(db)
        if not staff:
            flash('スタッフ情報が見つかりません', 'error')
            return redirect(url_for('internal_chat.room_list'))

        target_id   = int(request.form.get('target_id', 0))
        target_type = request.form.get('target_type', 'admin')

        if target_type == 'employee':
            target = db.query(TJugyoin).filter(TJugyoin.id == target_id).first()
        else:
            target = db.query(TKanrisha).filter(TKanrisha.id == target_id).first()

        if not target:
            flash('相手が見つかりません', 'error')
            return redirect(url_for('internal_chat.room_list'))

        # 既存のDMルームを探す
        my_rooms = [m.room_id for m in db.query(TInternalChatMember).filter(
            and_(TInternalChatMember.staff_id == staff.id, TInternalChatMember.staff_type == staff_type)
        ).all()]
        target_rooms = [m.room_id for m in db.query(TInternalChatMember).filter(
            and_(TInternalChatMember.staff_id == target_id, TInternalChatMember.staff_type == target_type)
        ).all()]
        common_rooms = set(my_rooms) & set(target_rooms)

        existing_dm = None
        for rid in common_rooms:
            room = db.query(TInternalChatRoom).filter(
                and_(TInternalChatRoom.id == rid, TInternalChatRoom.room_type == 'direct')
            ).first()
            if room:
                # メンバーが2人だけか確認
                cnt = db.query(TInternalChatMember).filter(TInternalChatMember.room_id == rid).count()
                if cnt == 2:
                    existing_dm = room
                    break

        if existing_dm:
            return redirect(url_for('internal_chat.room_view', room_id=existing_dm.id))

        # 新規作成
        room = TInternalChatRoom(
            tenant_id      = tenant_id,
            room_type      = 'direct',
            created_by_id  = staff.id,
            created_by_type= staff_type,
        )
        db.add(room)
        db.flush()

        db.add(TInternalChatMember(room_id=room.id, staff_id=staff.id, staff_type=staff_type, staff_name=staff.name))
        db.add(TInternalChatMember(room_id=room.id, staff_id=target_id, staff_type=target_type, staff_name=target.name))
        db.commit()

        return redirect(url_for('internal_chat.room_view', room_id=room.id))
    finally:
        db.close()


@bp.route('/new_group', methods=['POST'])
@require_roles(*STAFF_ROLES)
def new_group():
    """グループチャットルームを作成する"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        staff, staff_type = _get_current_staff(db)
        if not staff:
            flash('スタッフ情報が見つかりません', 'error')
            return redirect(url_for('internal_chat.room_list'))

        group_name = request.form.get('group_name', '').strip() or 'グループチャット'
        member_ids_raw = request.form.getlist('member_ids')  # "admin:1", "employee:3" 形式

        room = TInternalChatRoom(
            tenant_id      = tenant_id,
            name           = group_name,
            room_type      = 'group',
            created_by_id  = staff.id,
            created_by_type= staff_type,
        )
        db.add(room)
        db.flush()

        # 作成者を追加
        db.add(TInternalChatMember(room_id=room.id, staff_id=staff.id, staff_type=staff_type, staff_name=staff.name))

        for raw in member_ids_raw:
            parts = raw.split(':')
            if len(parts) != 2:
                continue
            mtype, mid = parts[0], int(parts[1])
            if mtype == 'employee':
                m = db.query(TJugyoin).filter(TJugyoin.id == mid).first()
            else:
                m = db.query(TKanrisha).filter(TKanrisha.id == mid).first()
            if m and not (mtype == staff_type and mid == staff.id):
                db.add(TInternalChatMember(room_id=room.id, staff_id=mid, staff_type=mtype, staff_name=m.name))

        db.commit()
        flash(f'グループ「{group_name}」を作成しました', 'success')
        return redirect(url_for('internal_chat.room_view', room_id=room.id))
    finally:
        db.close()


@bp.route('/room/<int:room_id>', methods=['GET', 'POST'])
@require_roles(*STAFF_ROLES)
def room_view(room_id):
    """チャットルーム表示・メッセージ送信"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        staff, staff_type = _get_current_staff(db)
        if not staff:
            flash('スタッフ情報が見つかりません', 'error')
            return redirect(url_for('internal_chat.room_list'))

        room = db.query(TInternalChatRoom).filter(
            and_(TInternalChatRoom.id == room_id, TInternalChatRoom.tenant_id == tenant_id)
        ).first()
        if not room:
            flash('チャットルームが見つかりません', 'error')
            return redirect(url_for('internal_chat.room_list'))

        # メンバーかどうか確認
        membership = db.query(TInternalChatMember).filter(
            and_(
                TInternalChatMember.room_id    == room_id,
                TInternalChatMember.staff_id   == staff.id,
                TInternalChatMember.staff_type == staff_type,
            )
        ).first()
        if not membership:
            flash('このチャットルームへのアクセス権がありません', 'error')
            return redirect(url_for('internal_chat.room_list'))

        if request.method == 'POST':
            msg_text = request.form.get('message', '').strip()
            if msg_text:
                msg = TInternalMessage(
                    room_id     = room_id,
                    sender_id   = staff.id,
                    sender_type = staff_type,
                    sender_name = staff.name,
                    message     = msg_text,
                    message_type= 'text',
                )
                db.add(msg)
                # ルームのupdated_atを更新
                room.updated_at = datetime.utcnow()
                db.commit()
            return redirect(url_for('internal_chat.room_view', room_id=room_id))

        # メッセージ取得
        messages = db.query(TInternalMessage).filter(
            TInternalMessage.room_id == room_id
        ).order_by(TInternalMessage.created_at.asc()).all()

        # 既読マーク
        msg_ids = [m.id for m in messages]
        if msg_ids:
            already_read = {r.message_id for r in db.query(TInternalMessageRead).filter(
                and_(
                    TInternalMessageRead.message_id.in_(msg_ids),
                    TInternalMessageRead.staff_id   == staff.id,
                    TInternalMessageRead.staff_type == staff_type,
                )
            ).all()}
            for mid in msg_ids:
                if mid not in already_read:
                    db.add(TInternalMessageRead(
                        message_id = mid,
                        staff_id   = staff.id,
                        staff_type = staff_type,
                    ))
            db.commit()

        # メンバー一覧
        members = db.query(TInternalChatMember).filter(
            TInternalChatMember.room_id == room_id
        ).all()

        # ルーム表示名
        other_names = [m.staff_name for m in members if not (m.staff_id == staff.id and m.staff_type == staff_type)]
        if room.room_type == 'direct' and other_names:
            room.display_name = other_names[0]
        else:
            room.display_name = room.name or 'グループチャット'

        return render_template(
            'internal_chat_room.html',
            room       = room,
            messages   = messages,
            members    = members,
            staff      = staff,
            staff_type = staff_type,
        )
    finally:
        db.close()


@bp.route('/room/<int:room_id>/messages')
@require_roles(*STAFF_ROLES)
def room_messages_api(room_id):
    """チャットメッセージのJSON API（ポーリング用）"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        staff, staff_type = _get_current_staff(db)
        if not staff:
            return jsonify({'error': 'unauthorized'}), 401

        since_id = int(request.args.get('since_id', 0))
        messages = db.query(TInternalMessage).filter(
            and_(
                TInternalMessage.room_id == room_id,
                TInternalMessage.id > since_id,
            )
        ).order_by(TInternalMessage.created_at.asc()).all()

        # 既読マーク
        for msg in messages:
            exists = db.query(TInternalMessageRead).filter(
                and_(
                    TInternalMessageRead.message_id == msg.id,
                    TInternalMessageRead.staff_id   == staff.id,
                    TInternalMessageRead.staff_type == staff_type,
                )
            ).first()
            if not exists:
                db.add(TInternalMessageRead(
                    message_id = msg.id,
                    staff_id   = staff.id,
                    staff_type = staff_type,
                ))
        if messages:
            db.commit()

        return jsonify([{
            'id'         : m.id,
            'sender_name': m.sender_name,
            'sender_id'  : m.sender_id,
            'sender_type': m.sender_type,
            'message'    : m.message,
            'created_at' : m.created_at.strftime('%H:%M') if m.created_at else '',
        } for m in messages])
    finally:
        db.close()
