"""
外部サービス連携ブループリント（ChatWork）

- 連携設定（APIトークン登録・疎通確認）
- ルーム → 顧問先 の対応付け
- 手動同期（今すぐ受信）
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash, jsonify,
)
from app.db import SessionLocal
from app.models_integrations import (
    TIntegrationSetting, TChatworkRoomMapping, TReceivedFile,
)
from app.models_clients import TClient
from app.utils.decorators import require_roles, ROLES
from app.utils.integrations.chatwork import ChatworkClient, ChatworkError
from app.services.chatwork_sync import sync_tenant, get_active_setting

bp = Blueprint('integrations', __name__, url_prefix='/integrations')


def _require_tenant():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return None
    return tenant_id


@bp.route('/', methods=['GET'])
@bp.route('/hub', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def hub():
    """各種連携ハブ（ストレージ / ChatWork / Gmail / 会計ソフト を選ぶ入口）"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        # 各連携の状態（接続済みか）を表示するために軽く参照
        storage = None
        chatwork = None
        gmail = None
        try:
            from sqlalchemy import text
            storage = db.execute(text(
                'SELECT provider FROM "T_外部ストレージ連携" '
                'WHERE tenant_id = :t AND status = \'active\' AND store_id IS NULL '
                'ORDER BY id DESC LIMIT 1'
            ), {"t": tenant_id}).fetchone()
        except Exception:
            storage = None
        try:
            chatwork = (db.query(TIntegrationSetting)
                          .filter(TIntegrationSetting.tenant_id == tenant_id,
                                  TIntegrationSetting.provider == 'chatwork',
                                  TIntegrationSetting.status == 'active').first())
            gmail = (db.query(TIntegrationSetting)
                       .filter(TIntegrationSetting.tenant_id == tenant_id,
                               TIntegrationSetting.provider == 'gmail',
                               TIntegrationSetting.status == 'active').first())
        except Exception:
            pass
        status = {
            'storage': storage.provider if storage else None,
            'chatwork': bool(chatwork and chatwork.api_token),
            'gmail': bool(gmail and gmail.api_token),
        }

        # 担当者ごとの連携状況（読み取り専用の一覧。認証情報は表示しない）
        staff_list = []
        try:
            from app.models_integrations import TStaffMailAccount, TStaffChatworkAccount
            from app.models_login import TKanrisha, TJugyoin
            mail_accs = (db.query(TStaffMailAccount)
                           .filter(TStaffMailAccount.tenant_id == tenant_id,
                                   TStaffMailAccount.status == 'active').all())
            cw_accs = (db.query(TStaffChatworkAccount)
                         .filter(TStaffChatworkAccount.tenant_id == tenant_id,
                                 TStaffChatworkAccount.status == 'active').all())
            admin_names = {a.id: a.name for a in db.query(TKanrisha)
                           .filter(TKanrisha.tenant_id == tenant_id).all()}
            emp_names = {e.id: e.name for e in db.query(TJugyoin)
                         .filter(TJugyoin.tenant_id == tenant_id).all()}

            def _name(staff_type, staff_id):
                m = admin_names if staff_type == 'admin' else emp_names
                return m.get(staff_id, f'ID:{staff_id}')

            merged = {}
            for a in mail_accs:
                key = (a.staff_type, a.staff_id)
                s = merged.setdefault(key, {'name': _name(*key), 'type': a.staff_type,
                                            'emails': [], 'chatwork': None})
                s['emails'].append(a.email)
            for a in cw_accs:
                key = (a.staff_type, a.staff_id)
                s = merged.setdefault(key, {'name': _name(*key), 'type': a.staff_type,
                                            'emails': [], 'chatwork': None})
                s['chatwork'] = a.account_name or '連携中'
            staff_list = sorted(merged.values(), key=lambda x: x['name'])
        except Exception:
            staff_list = []

        return render_template('integrations_hub.html', status=status, staff_list=staff_list)
    finally:
        db.close()


@bp.route('/chatwork', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def chatwork_settings():
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        mappings = (db.query(TChatworkRoomMapping)
                      .filter(TChatworkRoomMapping.tenant_id == tenant_id)
                      .order_by(TChatworkRoomMapping.id.desc()).all())
        clients = (db.query(TClient)
                     .filter(TClient.tenant_id == tenant_id)
                     .order_by(TClient.name).all())
        recent = (db.query(TReceivedFile)
                    .filter(TReceivedFile.tenant_id == tenant_id,
                            TReceivedFile.provider == 'chatwork')
                    .order_by(TReceivedFile.id.desc()).limit(20).all())
        # マッピング済みルームIDのclient名を引くための辞書
        client_names = {c.id: c.name for c in clients}
        from app.services.scheduler import get_state
        return render_template('integrations_chatwork.html',
                               setting=setting, mappings=mappings,
                               clients=clients, recent=recent,
                               client_names=client_names,
                               sched=get_state())
    finally:
        db.close()


@bp.route('/chatwork/save_token', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def chatwork_save_token():
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    api_token = (request.form.get('api_token') or '').strip()
    if not api_token:
        flash('APIトークンを入力してください', 'error')
        return redirect(url_for('integrations.chatwork_settings'))

    # 疎通確認
    try:
        ChatworkClient(api_token).get_me()
    except ChatworkError as e:
        flash(f'トークンの検証に失敗しました: {e}', 'error')
        return redirect(url_for('integrations.chatwork_settings'))

    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        if setting:
            setting.api_token = api_token
            setting.status = 'active'
        else:
            db.add(TIntegrationSetting(
                tenant_id=tenant_id, provider='chatwork',
                api_token=api_token, status='active',
            ))
        db.commit()
        flash('ChatWork連携を保存しました', 'success')
    finally:
        db.close()
    return redirect(url_for('integrations.chatwork_settings'))


@bp.route('/chatwork/rooms', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def chatwork_rooms():
    """ChatWork のルーム一覧を取得（マッピングUIの候補）"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return jsonify({'error': 'no tenant'}), 400
    db = SessionLocal()
    try:
        setting = get_active_setting(db, tenant_id)
        if not setting or not setting.api_token:
            return jsonify({'error': 'ChatWork連携が未設定です'}), 400
        try:
            rooms = ChatworkClient(setting.api_token).list_rooms()
        except ChatworkError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify({'rooms': [
            {'room_id': r.get('room_id'), 'name': r.get('name')}
            for r in (rooms or [])
        ]})
    finally:
        db.close()


@bp.route('/chatwork/map', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def chatwork_map():
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    room_id = (request.form.get('room_id') or '').strip()
    room_name = (request.form.get('room_name') or '').strip()
    client_id = request.form.get('client_id')
    subfolder = (request.form.get('subfolder') or 'ChatWork受信').strip()

    if not room_id or not client_id:
        flash('ルームIDと顧問先を指定してください', 'error')
        return redirect(url_for('integrations.chatwork_settings'))

    db = SessionLocal()
    try:
        # 同一テナント・同一ルームの重複マッピングは上書き
        existing = (db.query(TChatworkRoomMapping)
                      .filter(TChatworkRoomMapping.tenant_id == tenant_id,
                              TChatworkRoomMapping.room_id == room_id)
                      .first())
        if existing:
            existing.client_id = int(client_id)
            existing.room_name = room_name or existing.room_name
            existing.subfolder = subfolder
            existing.status = 'active'
        else:
            db.add(TChatworkRoomMapping(
                tenant_id=tenant_id, room_id=room_id, room_name=room_name,
                client_id=int(client_id), subfolder=subfolder, status='active',
            ))
        db.commit()
        flash('ルームの紐付けを保存しました', 'success')
    finally:
        db.close()
    return redirect(url_for('integrations.chatwork_settings'))


@bp.route('/chatwork/map/<int:mapping_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def chatwork_map_delete(mapping_id):
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        m = (db.query(TChatworkRoomMapping)
               .filter(TChatworkRoomMapping.id == mapping_id,
                       TChatworkRoomMapping.tenant_id == tenant_id)
               .first())
        if m:
            db.delete(m)
            db.commit()
            flash('紐付けを削除しました', 'success')
    finally:
        db.close()
    return redirect(url_for('integrations.chatwork_settings'))


@bp.route('/scheduler/save', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def scheduler_save():
    """自動取得のオンオフ・巡回間隔を保存（アプリ全体共通設定）"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    from app.services.scheduler import set_config
    enabled = request.form.get('enabled') == 'on'
    try:
        interval = int(request.form.get('interval_minutes') or 5)
    except Exception:
        interval = 5
    cfg = set_config(enabled, interval)

    state = '有効' if cfg['enabled'] else '無効'
    flash(f"自動取得を保存しました（{state} / {cfg['interval_minutes']}分ごと）", 'success')

    # 送信元の画面に戻る（chatwork / gmail）
    back = request.form.get('back') or 'chatwork'
    if back == 'gmail':
        return redirect(url_for('gmail_integration.settings'))
    return redirect(url_for('integrations.chatwork_settings'))


@bp.route('/chatwork/sync', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def chatwork_sync():
    """今すぐ同期（手動）"""
    tenant_id = _require_tenant()
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    result = sync_tenant(tenant_id)
    msg = f"同期完了: 保存 {result['saved']}件 / スキップ {result['skipped']}件"
    if result['errors']:
        msg += f" / エラー {len(result['errors'])}件"
        flash(msg, 'warning')
        for e in result['errors'][:5]:
            flash(e, 'error')
    else:
        flash(msg, 'success')
    return redirect(url_for('integrations.chatwork_settings'))
