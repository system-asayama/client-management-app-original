# -*- coding: utf-8 -*-
"""
MCP（AI連携）HTTPエンドポイント

外部のAI（Claude等）が Model Context Protocol（JSON-RPC 2.0 / Streamable HTTP）
でこのアプリの機能を呼び出せるようにする単一エンドポイント。

  POST /mcp   … JSON-RPC（initialize / tools/list / tools/call / ping）
  認証        … Authorization: Bearer <トークン>

トークンは T_MCP連携トークン で管理し、スコープ（tenant/staff）と
権限（read/write/full）に従ってアクセス制御する。
"""
import hashlib
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app

from app.db import SessionLocal
from app.models_integrations import TMCPToken
from app import mcp_tools

bp = Blueprint('mcp_api', __name__, url_prefix='/mcp')

# サーバーが名乗るプロトコルバージョン（クライアント要求があればそれを優先）
_DEFAULT_PROTOCOL = '2025-06-18'
_SERVER_INFO = {'name': '顧問先管理アプリ MCP', 'version': '1.0.0'}


class MCPContext:
    """1リクエストの実行コンテキスト（テナント・スコープ・権限・DBセッション）。"""
    def __init__(self, db, token_row):
        self.db = db
        self.tenant_id = token_row.tenant_id
        self.scope = token_row.scope or 'tenant'
        self.staff_id = token_row.staff_id
        self.staff_type = token_row.staff_type
        self.permission = token_row.permission or 'read'


def _hash_token(raw: str) -> str:
    return hashlib.sha256((raw or '').encode('utf-8')).hexdigest()


def _lookup_token(db, raw):
    if not raw:
        return None
    row = (db.query(TMCPToken)
             .filter(TMCPToken.token_hash == _hash_token(raw),
                     TMCPToken.status == 'active').first())
    return row


def _bearer_from_request():
    auth = request.headers.get('Authorization', '') or ''
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    # 予備: X-API-Key ヘッダも許容
    return (request.headers.get('X-API-Key', '') or '').strip()


# --- JSON-RPC ヘルパー -------------------------------------------------------
def _ok(req_id, result):
    return jsonify({'jsonrpc': '2.0', 'id': req_id, 'result': result})


def _err(req_id, code, message, http=200):
    resp = jsonify({'jsonrpc': '2.0', 'id': req_id,
                    'error': {'code': code, 'message': message}})
    resp.status_code = http
    return resp


# --- メソッド実装 -----------------------------------------------------------
def _handle_initialize(params, ctx):
    proto = (params or {}).get('protocolVersion') or _DEFAULT_PROTOCOL
    return {
        'protocolVersion': proto,
        'capabilities': {'tools': {'listChanged': False}},
        'serverInfo': _SERVER_INFO,
    }


def _handle_tools_list(params, ctx):
    return {'tools': mcp_tools.tools_for_permission(ctx.permission)}


def _handle_tools_call(params, ctx):
    params = params or {}
    name = params.get('name')
    args = params.get('arguments') or {}
    try:
        result = mcp_tools.call_tool(ctx, name, args)
        import json as _json
        text = _json.dumps(result, ensure_ascii=False, default=str, indent=2)
        return {'content': [{'type': 'text', 'text': text}], 'isError': False}
    except mcp_tools.ToolError as e:
        # 業務エラーは JSON-RPC エラーではなく、ツール結果の isError で返す（MCP慣習）
        return {'content': [{'type': 'text', 'text': f'エラー: {e}'}], 'isError': True}
    except Exception as e:  # noqa: BLE001
        ctx.db.rollback()
        current_app.logger.exception('MCP tool error: %s', e)
        return {'content': [{'type': 'text', 'text': f'内部エラー: {e}'}], 'isError': True}


_METHODS = {
    'initialize': _handle_initialize,
    'tools/list': _handle_tools_list,
    'tools/call': _handle_tools_call,
    'ping': lambda params, ctx: {},
}


def _process(db, token_row):
    """認証済みトークンで JSON-RPC を処理してレスポンスを返す（共通本体）。"""
    payload = request.get_json(silent=True)
    if payload is None:
        return _err(None, -32700, 'JSONの解析に失敗しました', http=400)

    # バッチ（配列）にも対応
    single = not isinstance(payload, list)
    messages = [payload] if single else payload

    ctx = MCPContext(db, token_row)
    # 最終利用時刻を更新
    try:
        token_row.last_used_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()

    responses = []
    for msg in messages:
        if not isinstance(msg, dict):
            responses.append({'jsonrpc': '2.0', 'id': None,
                              'error': {'code': -32600, 'message': '不正なリクエスト'}})
            continue
        req_id = msg.get('id')
        method = msg.get('method')
        params = msg.get('params')
        # 通知（idなし）はレスポンスを返さない
        is_notification = 'id' not in msg
        handler = _METHODS.get(method)
        if handler is None:
            if not is_notification:
                responses.append({'jsonrpc': '2.0', 'id': req_id,
                                  'error': {'code': -32601,
                                            'message': f'未対応のメソッド: {method}'}})
            continue
        try:
            result = handler(params, ctx)
            if not is_notification:
                responses.append({'jsonrpc': '2.0', 'id': req_id, 'result': result})
        except Exception as e:  # noqa: BLE001
            db.rollback()
            current_app.logger.exception('MCP method error: %s', e)
            if not is_notification:
                responses.append({'jsonrpc': '2.0', 'id': req_id,
                                  'error': {'code': -32603, 'message': f'内部エラー: {e}'}})

    if not responses:
        # 通知のみ → 202 No Content 相当
        return ('', 202)
    return jsonify(responses[0] if single else responses)


@bp.route('', methods=['POST'])
@bp.route('/', methods=['POST'])
def mcp_endpoint():
    """トークンは Authorization: Bearer ヘッダで受け取る（Claude Desktop 等）。"""
    db = SessionLocal()
    try:
        token_row = _lookup_token(db, _bearer_from_request())
        if not token_row:
            return _err(None, -32001, '認証に失敗しました（有効なトークンが必要です）', http=401)
        return _process(db, token_row)
    finally:
        db.close()


@bp.route('/t/<token>', methods=['POST'])
def mcp_endpoint_token_in_url(token):
    """トークンをURLに埋め込む方式（claude.ai の「カスタムコネクタ」用）。
    ヘッダにトークンを付けられないクライアント向け。URLの秘匿に注意。
    """
    db = SessionLocal()
    try:
        token_row = _lookup_token(db, token)
        if not token_row:
            return _err(None, -32001, '認証に失敗しました（URLのトークンが無効です）', http=401)
        return _process(db, token_row)
    finally:
        db.close()


@bp.route('', methods=['GET'])
@bp.route('/', methods=['GET'])
@bp.route('/t/<token>', methods=['GET'])
def mcp_info(token=None):
    """疎通確認用（GET）。MCP自体はPOSTで話す。"""
    return jsonify({'name': _SERVER_INFO['name'], 'transport': 'streamable-http',
                    'usage': 'POST JSON-RPC 2.0. 認証はヘッダ Authorization: Bearer <token> '
                             'または URL /mcp/t/<token>'})
