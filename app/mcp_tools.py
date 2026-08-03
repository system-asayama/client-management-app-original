# -*- coding: utf-8 -*-
"""
MCP（AI連携）ツール定義とハンドラ

このアプリの機能を、外部のAI（Claude等）が MCP 経由で利用できるように
「ツール」として公開する。各ツールは権限レベル（read/write/full）と
スコープ（tenant/staff）に従ってアクセス制御される。

ツールは TOOLS リストに登録され、mcp_api ブループリントが tools/list・
tools/call で参照する。ハンドラは (ctx, args) を受け取り、JSON化可能な
結果（dict/list/str）を返す。ctx は MCPContext（tenant_id・scope・staff・
permission・db セッション）を持つ。
"""
from datetime import datetime

from app.models_clients import (
    TClient, TCommissionedWork, TMessage, TFile, TTaxRecord,
)
from app.models_login import TClientAssignment, TKanrisha, TJugyoin
from app.models_integrations import TReceivedFile


# 権限の強さ（read < write < full）
_PERM_RANK = {'read': 1, 'write': 2, 'full': 3}


class ToolError(Exception):
    """ツール実行時の業務エラー（AIへ返すメッセージ）。"""
    pass


class PermissionDenied(ToolError):
    pass


# ---------------------------------------------------------------------------
# スコープ（担当者トークン）用ヘルパー
# ---------------------------------------------------------------------------
def _assigned_client_ids(ctx):
    """担当者スコープのとき、その担当者が担当する顧問先IDの集合を返す。"""
    rows = (ctx.db.query(TClientAssignment.client_id)
              .filter(TClientAssignment.tenant_id == ctx.tenant_id,
                      TClientAssignment.staff_id == ctx.staff_id,
                      TClientAssignment.staff_type == ctx.staff_type).all())
    return {r[0] for r in rows}


def _get_client_or_raise(ctx, client_id):
    """テナント内の顧問先を取得。担当者スコープなら担当分に限定。無ければエラー。"""
    c = (ctx.db.query(TClient)
           .filter(TClient.id == client_id, TClient.tenant_id == ctx.tenant_id).first())
    if not c:
        raise ToolError(f'顧問先ID {client_id} が見つかりません')
    if ctx.scope == 'staff' and c.id not in _assigned_client_ids(ctx):
        raise PermissionDenied(f'この担当者トークンでは顧問先ID {client_id} にアクセスできません（担当外）')
    return c


# ---------------------------------------------------------------------------
# シリアライズ
# ---------------------------------------------------------------------------
def _client_dict(c, full=False):
    d = {
        'id': c.id, 'name': c.name, 'type': c.type,
        'email': c.email, 'phone': c.phone, 'store_id': c.store_id,
        'industry': c.industry, 'address': c.address,
    }
    if full:
        d.update({
            'notes': c.notes,
            'tax_accountant_code': c.tax_accountant_code,
            'tax_id_number': c.tax_id_number,
            'fiscal_year_start_month': c.fiscal_year_start_month,
            'fiscal_year_end_month': c.fiscal_year_end_month,
            'established_date': c.established_date,
            'blue_return': c.blue_return,
            'consumption_tax_payer': c.consumption_tax_payer,
            'consumption_tax_method': c.consumption_tax_method,
            'qualified_invoice_number': c.qualified_invoice_number,
            'employee_count': c.employee_count,
            'contract_start_date': c.contract_start_date,
            'storage_folder_path': c.storage_folder_path,
            'bookkeeping_instructions': c.bookkeeping_instructions,
        })
    return d


def _msg_dict(m):
    return {
        'id': m.id, 'client_id': m.client_id, 'sender': m.sender,
        'sender_type': m.sender_type, 'message': m.message,
        'message_type': m.message_type, 'file_name': m.file_name,
        'file_url': m.file_url,
        'timestamp': m.timestamp.isoformat() if m.timestamp else None,
    }


def _file_dict(f):
    return {
        'id': f.id, 'client_id': f.client_id, 'filename': f.filename,
        'file_url': f.file_url, 'uploader': f.uploader,
        'timestamp': f.timestamp.isoformat() if f.timestamp else None,
    }


def _received_dict(r):
    return {
        'id': r.id, 'provider': r.provider, 'client_id': r.client_id,
        'filename': r.filename, 'storage_url': r.storage_url,
        'status': r.status, 'error_message': r.error_message,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    }


# ---------------------------------------------------------------------------
# ハンドラ: 顧問先
# ---------------------------------------------------------------------------
def _h_list_clients(ctx, args):
    q = ctx.db.query(TClient).filter(TClient.tenant_id == ctx.tenant_id)
    if ctx.scope == 'staff':
        ids = _assigned_client_ids(ctx)
        if not ids:
            return {'clients': [], 'count': 0}
        q = q.filter(TClient.id.in_(ids))
    kw = (args.get('query') or '').strip()
    if kw:
        like = f'%{kw}%'
        q = q.filter((TClient.name.like(like)) | (TClient.email.like(like)))
    if args.get('store_id'):
        q = q.filter(TClient.store_id == int(args['store_id']))
    limit = min(int(args.get('limit') or 100), 500)
    rows = q.order_by(TClient.name).limit(limit).all()
    return {'clients': [_client_dict(c) for c in rows], 'count': len(rows)}


def _h_get_client(ctx, args):
    c = _get_client_or_raise(ctx, int(args['client_id']))
    return _client_dict(c, full=True)


_CLIENT_WRITABLE = {
    'name', 'type', 'email', 'phone', 'notes', 'address', 'industry',
    'store_id', 'tax_accountant_code', 'tax_id_number',
    'fiscal_year_start_month', 'fiscal_year_end_month', 'established_date',
    'blue_return', 'consumption_tax_payer', 'consumption_tax_method',
    'qualified_invoice_number', 'employee_count', 'contract_start_date',
    'bookkeeping_instructions',
}


def _h_create_client(ctx, args):
    name = (args.get('name') or '').strip()
    if not name:
        raise ToolError('name（顧問先名）は必須です')
    c = TClient(tenant_id=ctx.tenant_id, name=name)
    for k in _CLIENT_WRITABLE:
        if k in args and args[k] is not None:
            setattr(c, k, args[k])
    ctx.db.add(c)
    ctx.db.flush()
    # 担当者トークンで作成した場合は、その担当者を主担当として自動割当
    if ctx.scope == 'staff':
        ctx.db.add(TClientAssignment(
            tenant_id=ctx.tenant_id, client_id=c.id,
            staff_id=ctx.staff_id, staff_type=ctx.staff_type, is_primary=1))
    ctx.db.commit()
    return {'created': True, 'client': _client_dict(c, full=True)}


def _h_update_client(ctx, args):
    c = _get_client_or_raise(ctx, int(args['client_id']))
    changed = []
    for k in _CLIENT_WRITABLE:
        if k in args and args[k] is not None:
            setattr(c, k, args[k])
            changed.append(k)
    ctx.db.commit()
    return {'updated': True, 'changed_fields': changed, 'client': _client_dict(c, full=True)}


def _h_delete_client(ctx, args):
    c = _get_client_or_raise(ctx, int(args['client_id']))
    name = c.name
    ctx.db.delete(c)
    ctx.db.commit()
    return {'deleted': True, 'client_id': int(args['client_id']), 'name': name}


def _norm_name(s):
    return ''.join((s or '').split()).lower()


def _h_bulk_create_clients(ctx, args):
    """顧問先を一括登録する。既存名・バッチ内の重複はスキップする。
    clients: [{name(必須), type, email, phone, address, industry, notes}] の配列
    """
    items = args.get('clients') or []
    if not isinstance(items, list) or not items:
        raise ToolError('clients（登録する顧問先の配列）が必要です')
    if len(items) > 1000:
        raise ToolError('一度に登録できるのは1000件までです')
    store_id = args.get('store_id')

    # 既存の顧問先名（正規化）を集める（重複防止）
    existing = {_norm_name(n[0]) for n in
                ctx.db.query(TClient.name).filter(TClient.tenant_id == ctx.tenant_id).all()}
    seen = set()
    created, skipped = [], []
    for it in items:
        name = (it.get('name') or '').strip() if isinstance(it, dict) else ''
        if not name:
            skipped.append({'name': '(空)', 'reason': 'name無し'})
            continue
        key = _norm_name(name)
        if key in existing or key in seen:
            skipped.append({'name': name, 'reason': '重複'})
            continue
        seen.add(key)
        c = TClient(tenant_id=ctx.tenant_id, name=name)
        if store_id is not None:
            c.store_id = store_id
        for k in ('type', 'email', 'phone', 'address', 'industry', 'notes'):
            if it.get(k):
                setattr(c, k, it[k])
        ctx.db.add(c)
        ctx.db.flush()
        if ctx.scope == 'staff':
            ctx.db.add(TClientAssignment(
                tenant_id=ctx.tenant_id, client_id=c.id,
                staff_id=ctx.staff_id, staff_type=ctx.staff_type, is_primary=1))
        created.append({'id': c.id, 'name': name})
    ctx.db.commit()
    return {'created_count': len(created), 'skipped_count': len(skipped),
            'created': created, 'skipped': skipped}


# ---------------------------------------------------------------------------
# ハンドラ: 受託業務
# ---------------------------------------------------------------------------
def _h_list_commissioned_work(ctx, args):
    _get_client_or_raise(ctx, int(args['client_id']))
    rows = (ctx.db.query(TCommissionedWork)
              .filter(TCommissionedWork.tenant_id == ctx.tenant_id,
                      TCommissionedWork.client_id == int(args['client_id'])).all())
    return {'works': [{
        'id': w.id, 'work_name': w.work_name, 'start_date': w.start_date,
        'fee': w.fee, 'fee_cycle': w.fee_cycle, 'notes': w.notes,
    } for w in rows]}


# ---------------------------------------------------------------------------
# ハンドラ: ファイル
# ---------------------------------------------------------------------------
def _h_list_client_files(ctx, args):
    _get_client_or_raise(ctx, int(args['client_id']))
    limit = min(int(args.get('limit') or 100), 500)
    rows = (ctx.db.query(TFile)
              .filter(TFile.client_id == int(args['client_id']))
              .order_by(TFile.id.desc()).limit(limit).all())
    return {'files': [_file_dict(f) for f in rows], 'count': len(rows)}


def _h_delete_file(ctx, args):
    f = ctx.db.query(TFile).filter(TFile.id == int(args['file_id'])).first()
    if not f:
        raise ToolError(f'ファイルID {args["file_id"]} が見つかりません')
    _get_client_or_raise(ctx, f.client_id)  # テナント/担当チェック
    ctx.db.delete(f)
    ctx.db.commit()
    return {'deleted': True, 'file_id': int(args['file_id'])}


# ---------------------------------------------------------------------------
# ハンドラ: 受信ファイル（メール/ChatWork）
# ---------------------------------------------------------------------------
def _h_list_received_files(ctx, args):
    q = ctx.db.query(TReceivedFile).filter(TReceivedFile.tenant_id == ctx.tenant_id)
    if ctx.scope == 'staff':
        ids = _assigned_client_ids(ctx)
        q = q.filter(TReceivedFile.client_id.in_(ids or [-1]))
    if args.get('client_id'):
        _get_client_or_raise(ctx, int(args['client_id']))
        q = q.filter(TReceivedFile.client_id == int(args['client_id']))
    if args.get('provider'):
        q = q.filter(TReceivedFile.provider == args['provider'])
    if args.get('status'):
        q = q.filter(TReceivedFile.status == args['status'])
    limit = min(int(args.get('limit') or 100), 500)
    rows = q.order_by(TReceivedFile.id.desc()).limit(limit).all()
    return {'received_files': [_received_dict(r) for r in rows], 'count': len(rows)}


# ---------------------------------------------------------------------------
# ハンドラ: メッセージ（顧問先チャット）
# ---------------------------------------------------------------------------
def _h_list_messages(ctx, args):
    _get_client_or_raise(ctx, int(args['client_id']))
    limit = min(int(args.get('limit') or 50), 300)
    rows = (ctx.db.query(TMessage)
              .filter(TMessage.client_id == int(args['client_id']))
              .order_by(TMessage.id.desc()).limit(limit).all())
    rows = list(reversed(rows))
    return {'messages': [_msg_dict(m) for m in rows], 'count': len(rows)}


def _h_send_message(ctx, args):
    _get_client_or_raise(ctx, int(args['client_id']))
    text_body = (args.get('message') or '').strip()
    if not text_body:
        raise ToolError('message（本文）は必須です')
    sender = args.get('sender') or 'AI連携'
    m = TMessage(
        client_id=int(args['client_id']), sender=sender,
        sender_type='staff', message=text_body, message_type='text',
        timestamp=datetime.utcnow())
    ctx.db.add(m)
    ctx.db.commit()
    return {'sent': True, 'message': _msg_dict(m)}


# ---------------------------------------------------------------------------
# ハンドラ: スタッフ / 担当 / 店舗
# ---------------------------------------------------------------------------
def _h_list_staff(ctx, args):
    admins = (ctx.db.query(TKanrisha)
                .filter(TKanrisha.tenant_id == ctx.tenant_id).all())
    emps = (ctx.db.query(TJugyoin)
              .filter(TJugyoin.tenant_id == ctx.tenant_id).all())
    out = [{'staff_id': a.id, 'staff_type': 'admin', 'name': a.name,
            'email': a.email, 'role': a.role} for a in admins]
    out += [{'staff_id': e.id, 'staff_type': 'employee', 'name': e.name,
             'email': e.email, 'role': 'employee'} for e in emps]
    return {'staff': out, 'count': len(out)}


def _h_list_assignments(ctx, args):
    q = ctx.db.query(TClientAssignment).filter(TClientAssignment.tenant_id == ctx.tenant_id)
    if args.get('client_id'):
        _get_client_or_raise(ctx, int(args['client_id']))
        q = q.filter(TClientAssignment.client_id == int(args['client_id']))
    if args.get('staff_id'):
        q = q.filter(TClientAssignment.staff_id == int(args['staff_id']))
        if args.get('staff_type'):
            q = q.filter(TClientAssignment.staff_type == args['staff_type'])
    if ctx.scope == 'staff':
        ids = _assigned_client_ids(ctx)
        q = q.filter(TClientAssignment.client_id.in_(ids or [-1]))
    rows = q.all()
    return {'assignments': [{
        'id': a.id, 'client_id': a.client_id, 'staff_id': a.staff_id,
        'staff_type': a.staff_type, 'is_primary': a.is_primary,
    } for a in rows]}


def _h_assign_staff(ctx, args):
    _get_client_or_raise(ctx, int(args['client_id']))
    staff_id = int(args['staff_id'])
    staff_type = args.get('staff_type') or 'admin'
    existing = (ctx.db.query(TClientAssignment)
                  .filter(TClientAssignment.tenant_id == ctx.tenant_id,
                          TClientAssignment.client_id == int(args['client_id']),
                          TClientAssignment.staff_id == staff_id,
                          TClientAssignment.staff_type == staff_type).first())
    if existing:
        return {'assigned': True, 'already': True, 'assignment_id': existing.id}
    a = TClientAssignment(
        tenant_id=ctx.tenant_id, client_id=int(args['client_id']),
        staff_id=staff_id, staff_type=staff_type,
        is_primary=1 if args.get('is_primary') else 0)
    ctx.db.add(a)
    ctx.db.commit()
    return {'assigned': True, 'assignment_id': a.id}


def _h_unassign_staff(ctx, args):
    _get_client_or_raise(ctx, int(args['client_id']))
    staff_type = args.get('staff_type') or 'admin'
    n = (ctx.db.query(TClientAssignment)
           .filter(TClientAssignment.tenant_id == ctx.tenant_id,
                   TClientAssignment.client_id == int(args['client_id']),
                   TClientAssignment.staff_id == int(args['staff_id']),
                   TClientAssignment.staff_type == staff_type)
           .delete(synchronize_session=False))
    ctx.db.commit()
    return {'unassigned': True, 'removed': int(n)}


def _h_list_stores(ctx, args):
    from sqlalchemy import text
    rows = ctx.db.execute(
        text('SELECT id, "名称" AS name FROM "T_店舗" WHERE tenant_id = :t ORDER BY id'),
        {"t": ctx.tenant_id}).fetchall()
    return {'stores': [{'id': r.id, 'name': r.name} for r in rows]}


def _h_list_tax_records(ctx, args):
    _get_client_or_raise(ctx, int(args['client_id']))
    rows = (ctx.db.query(TTaxRecord)
              .filter(TTaxRecord.tenant_id == ctx.tenant_id,
                      TTaxRecord.client_id == int(args['client_id']))
              .order_by(TTaxRecord.fiscal_year.desc()).all())
    return {'tax_records': [{
        'id': r.id, 'fiscal_year': r.fiscal_year,
    } for r in rows]}


# ---------------------------------------------------------------------------
# ツール登録
#   permission: read / write / full（そのツールを呼ぶのに必要な最低権限）
# ---------------------------------------------------------------------------
def _tool(name, permission, description, properties, required, handler):
    return {
        'name': name, 'permission': permission, 'handler': handler,
        'schema': {
            'name': name, 'description': description,
            'inputSchema': {
                'type': 'object', 'properties': properties,
                'required': required,
            },
        },
    }


_S = lambda desc: {'type': 'string', 'description': desc}
_I = lambda desc: {'type': 'integer', 'description': desc}
_B = lambda desc: {'type': 'boolean', 'description': desc}


TOOLS = [
    _tool('list_clients', 'read',
          '顧問先の一覧を取得する。query（名前・メール部分一致）、store_id、limit で絞り込み可能。',
          {'query': _S('検索キーワード（顧問先名・メール）'),
           'store_id': _I('店舗IDで絞り込み'),
           'limit': _I('最大件数（既定100・最大500）')}, [],
          _h_list_clients),
    _tool('get_client', 'read',
          '顧問先1件の詳細（税務区分・会計期間・登録番号等を含む）を取得する。',
          {'client_id': _I('顧問先ID')}, ['client_id'], _h_get_client),
    _tool('create_client', 'write',
          '新しい顧問先を登録する。name は必須。担当者トークンの場合は自動でその担当者に割り当てる。',
          {'name': _S('顧問先名（必須）'), 'type': _S('個人/法人'),
           'email': _S('メール'), 'phone': _S('電話'),
           'address': _S('住所'), 'industry': _S('業種'),
           'notes': _S('備考'), 'store_id': _I('店舗ID')},
          ['name'], _h_create_client),
    _tool('update_client', 'write',
          '既存の顧問先情報を更新する。指定したフィールドのみ変更する。',
          {'client_id': _I('顧問先ID（必須）'), 'name': _S('顧問先名'),
           'type': _S('個人/法人'), 'email': _S('メール'), 'phone': _S('電話'),
           'address': _S('住所'), 'industry': _S('業種'), 'notes': _S('備考'),
           'store_id': _I('店舗ID')},
          ['client_id'], _h_update_client),
    _tool('delete_client', 'full',
          '顧問先を削除する。取り消せないので注意。',
          {'client_id': _I('顧問先ID')}, ['client_id'], _h_delete_client),
    _tool('bulk_create_clients', 'write',
          '顧問先を一括登録する。既存名・バッチ内の重複は自動でスキップする。'
          'freee等から取り込んだ多数の顧問先をまとめて登録する用途。',
          {'clients': {'type': 'array',
                       'description': '顧問先の配列。各要素は {name(必須), type, email, phone, address, industry, notes}',
                       'items': {'type': 'object',
                                 'properties': {
                                     'name': _S('顧問先名（必須）'), 'type': _S('個人/法人'),
                                     'email': _S('メール'), 'phone': _S('電話'),
                                     'address': _S('住所'), 'industry': _S('業種'),
                                     'notes': _S('備考')},
                                 'required': ['name']}},
           'store_id': _I('登録先の店舗ID（全件に適用）')},
          ['clients'], _h_bulk_create_clients),
    _tool('list_commissioned_work', 'read',
          '顧問先の受託業務（顧問料・業務名等）の一覧を取得する。',
          {'client_id': _I('顧問先ID')}, ['client_id'], _h_list_commissioned_work),
    _tool('list_client_files', 'read',
          '顧問先に紐づく共有ファイルの一覧を取得する。',
          {'client_id': _I('顧問先ID'), 'limit': _I('最大件数')},
          ['client_id'], _h_list_client_files),
    _tool('delete_file', 'full',
          '共有ファイルを1件削除する。',
          {'file_id': _I('ファイルID')}, ['file_id'], _h_delete_file),
    _tool('list_received_files', 'read',
          'メール/ChatWork連携で受信・保存したファイルのログ一覧を取得する。',
          {'client_id': _I('顧問先IDで絞り込み'),
           'provider': _S("'gmail'/'mail'/'chatwork'"),
           'status': _S("'saved'/'error'/'skipped'"),
           'limit': _I('最大件数')}, [], _h_list_received_files),
    _tool('list_messages', 'read',
          '顧問先とのチャットメッセージ履歴を取得する（新しい順に取得し古い順で返す）。',
          {'client_id': _I('顧問先ID'), 'limit': _I('最大件数（既定50）')},
          ['client_id'], _h_list_messages),
    _tool('send_message', 'write',
          '顧問先チャットにメッセージ（税理士側）を送信する。',
          {'client_id': _I('顧問先ID'), 'message': _S('本文'),
           'sender': _S('送信者名（省略時 AI連携）')},
          ['client_id', 'message'], _h_send_message),
    _tool('list_staff', 'read',
          '事務所のスタッフ（管理者・従業員）の一覧を取得する。',
          {}, [], _h_list_staff),
    _tool('list_assignments', 'read',
          '顧問先の担当割当を取得する。client_id または staff_id で絞り込み可能。',
          {'client_id': _I('顧問先ID'), 'staff_id': _I('スタッフID'),
           'staff_type': _S("'admin'/'employee'")}, [], _h_list_assignments),
    _tool('assign_staff', 'write',
          '顧問先にスタッフを担当として割り当てる。',
          {'client_id': _I('顧問先ID'), 'staff_id': _I('スタッフID'),
           'staff_type': _S("'admin'/'employee'（既定admin）"),
           'is_primary': _B('主担当にするか')},
          ['client_id', 'staff_id'], _h_assign_staff),
    _tool('unassign_staff', 'write',
          '顧問先からスタッフの担当割当を外す。',
          {'client_id': _I('顧問先ID'), 'staff_id': _I('スタッフID'),
           'staff_type': _S("'admin'/'employee'（既定admin）")},
          ['client_id', 'staff_id'], _h_unassign_staff),
    _tool('list_stores', 'read',
          '事務所の店舗（拠点）一覧を取得する。',
          {}, [], _h_list_stores),
    _tool('list_tax_records', 'read',
          '顧問先の納税実績（決算年度）の一覧を取得する。',
          {'client_id': _I('顧問先ID')}, ['client_id'], _h_list_tax_records),
]

TOOLS_BY_NAME = {t['name']: t for t in TOOLS}


def tools_for_permission(permission):
    """トークンの権限で利用可能なツールの schema 一覧を返す。"""
    rank = _PERM_RANK.get(permission, 1)
    return [t['schema'] for t in TOOLS if _PERM_RANK[t['permission']] <= rank]


def call_tool(ctx, name, args):
    """ツールを実行する。権限・存在チェックの上でハンドラを呼ぶ。"""
    tool = TOOLS_BY_NAME.get(name)
    if not tool:
        raise ToolError(f'不明なツールです: {name}')
    if _PERM_RANK[tool['permission']] > _PERM_RANK.get(ctx.permission, 1):
        raise PermissionDenied(
            f'このトークンの権限（{ctx.permission}）では {name} を実行できません'
            f'（必要権限: {tool["permission"]}）')
    return tool['handler'](ctx, args or {})
