# -*- coding: utf-8 -*-
"""
MCP（AI連携）トークン管理（テナント管理者向け）

  GET  /tenant/mcp/            … トークン一覧・接続手順
  POST /tenant/mcp/issue       … トークン発行（発行直後だけ平文を表示）
  POST /tenant/mcp/<id>/revoke … トークン失効
"""
import hashlib
import secrets

from flask import (Blueprint, render_template, session, redirect, url_for,
                   flash, request)
from sqlalchemy import text

from app.db import SessionLocal
from app.models_integrations import TMCPToken
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('mcp_admin', __name__, url_prefix='/tenant/mcp')

_PERM_LABEL = {'read': '閲覧のみ', 'write': '閲覧＋登録・更新', 'full': '閲覧＋登録・更新＋削除'}
_SCOPE_LABEL = {'tenant': '事務所全体', 'staff': '担当者（担当分のみ）'}


def _hash_token(raw: str) -> str:
    return hashlib.sha256((raw or '').encode('utf-8')).hexdigest()


def _staff_name(db, tenant_id, staff_id, staff_type):
    if not staff_id:
        return None
    tbl = 'T_管理者' if staff_type == 'admin' else 'T_従業員'
    try:
        r = db.execute(text(f'SELECT name FROM "{tbl}" WHERE id = :i AND tenant_id = :t'),
                       {"i": staff_id, "t": tenant_id}).fetchone()
        return r.name if r else None
    except Exception:
        return None


@bp.route('/', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def index():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        tokens = (db.query(TMCPToken)
                    .filter(TMCPToken.tenant_id == tenant_id,
                            TMCPToken.status == 'active')
                    .order_by(TMCPToken.id.desc()).all())
        rows = [{
            'id': t.id, 'name': t.name or '(名称なし)',
            'prefix': t.token_prefix, 'scope': _SCOPE_LABEL.get(t.scope, t.scope),
            'permission': _PERM_LABEL.get(t.permission, t.permission),
            'staff': _staff_name(db, tenant_id, t.staff_id, t.staff_type) if t.scope == 'staff' else None,
            'last_used': t.last_used_at.strftime('%Y-%m-%d %H:%M') if t.last_used_at else '未使用',
            'created': t.created_at.strftime('%Y-%m-%d') if t.created_at else '',
        } for t in tokens]

        # 担当者スコープ用のスタッフ候補
        staff = []
        try:
            for tbl, stype in (('T_管理者', 'admin'), ('T_従業員', 'employee')):
                for r in db.execute(text(f'SELECT id, name FROM "{tbl}" WHERE tenant_id = :t ORDER BY id'),
                                    {"t": tenant_id}).fetchall():
                    staff.append({'id': r.id, 'name': r.name, 'type': stype})
        except Exception:
            pass

        mcp_url = url_for('mcp_api.mcp_endpoint', _external=True).rstrip('/')
        new_token = session.pop('mcp_new_token', None)
        return render_template('mcp_tokens.html', tokens=rows, staff=staff,
                               mcp_url=mcp_url, new_token=new_token)
    finally:
        db.close()


@bp.route('/issue', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def issue():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    name = (request.form.get('name') or '').strip() or 'AI連携トークン'
    scope = request.form.get('scope') if request.form.get('scope') in ('tenant', 'staff') else 'tenant'
    permission = request.form.get('permission') if request.form.get('permission') in ('read', 'write', 'full') else 'read'
    staff_id = None
    staff_type = None
    if scope == 'staff':
        raw = request.form.get('staff') or ''
        # 形式: "<staff_type>:<id>"
        if ':' in raw:
            staff_type, sid = raw.split(':', 1)
            staff_id = int(sid) if sid.isdigit() else None
        if not staff_id:
            flash('担当者スコープを選んだ場合は、対象の担当者を選択してください', 'error')
            return redirect(url_for('mcp_admin.index'))

    # トークン生成（平文は発行時のみ表示）
    raw_token = 'mcp_' + secrets.token_urlsafe(32)
    db = SessionLocal()
    try:
        tk = TMCPToken(
            tenant_id=tenant_id, name=name,
            token_hash=_hash_token(raw_token),
            token_prefix=raw_token[:12],
            scope=scope, staff_id=staff_id, staff_type=staff_type,
            permission=permission, status='active')
        db.add(tk)
        db.commit()
        session['mcp_new_token'] = raw_token
        flash('トークンを発行しました。この画面を離れると再表示できませんので、今すぐコピーしてください。', 'success')
    except Exception as e:
        db.rollback()
        flash(f'発行に失敗しました: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('mcp_admin.index'))


@bp.route('/<int:token_id>/revoke', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def revoke(token_id):
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        tk = (db.query(TMCPToken)
                .filter(TMCPToken.id == token_id,
                        TMCPToken.tenant_id == tenant_id).first())
        if tk:
            tk.status = 'revoked'
            db.commit()
            flash('トークンを失効しました', 'success')
    finally:
        db.close()
    return redirect(url_for('mcp_admin.index'))
