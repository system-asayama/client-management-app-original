# -*- coding: utf-8 -*-
"""
顧問先の一括インポート（貼り付け / CSVアップロード）

freee等から書き出した顧問先名を、貼り付け or ファイルで一括登録する。
既存の顧問先名・バッチ内の重複は自動でスキップする。MCPや外部通信に依存しない。

  GET  /tenant/import/         … 入力フォーム
  POST /tenant/import/run      … 取り込み実行（結果表示）
"""
import re
import unicodedata

from flask import (Blueprint, render_template, session, redirect, url_for,
                   flash, request)
from sqlalchemy import text

from app.db import SessionLocal
from app.models_clients import TClient
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('client_import', __name__, url_prefix='/tenant/import')

_CORP = ['株式会社', '有限会社', '合同会社', '合資会社', '合名会社', '一般社団法人',
         '一般財団法人', '公益社団法人', '公益財団法人', '特定非営利活動法人', 'NPO法人',
         '協同組合', '税理士法人', '医療法人', '司法書士', '有限責任組合', 'ホールディングス',
         '投資事業有限責任組合']


def _norm(s):
    return re.sub(r'[\s　]+', '', unicodedata.normalize('NFKC', s or '')).lower()


def _guess_type(name):
    nf = unicodedata.normalize('NFKC', name or '')
    return '法人' if any(w in nf for w in _CORP) else '個人'


def _stores(db, tenant_id):
    try:
        return db.execute(text('SELECT id, "名称" AS name FROM "T_店舗" WHERE tenant_id = :t ORDER BY id'),
                          {"t": tenant_id}).fetchall()
    except Exception:
        return []


@bp.route('/', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def index():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        stores = [{'id': s.id, 'name': s.name} for s in _stores(db, tenant_id)]
        result = session.pop('import_result', None)
        return render_template('client_import.html', stores=stores, result=result)
    finally:
        db.close()


def _parse_rows(content):
    """テキスト（貼り付け or ファイル）を [(name, type_or_None)] に解析する。"""
    rows = []
    for raw in (content or '').splitlines():
        line = raw.strip().lstrip('﻿')
        if not line:
            continue
        low = line.lower().replace(' ', '')
        if low in ('name,type', 'name', '名前,種別', '名前', 'name\ttype'):
            continue  # ヘッダ行はスキップ
        parts = [p.strip() for p in re.split(r'[,\t]', line)]
        name = parts[0].strip()
        if not name:
            continue
        typ = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        if typ not in ('法人', '個人', None):
            typ = None
        rows.append((name, typ))
    return rows


@bp.route('/run', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"])
def run():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))

    raw = request.form.get('pasted') or ''
    up = request.files.get('file')
    if up and up.filename:
        try:
            data = up.read()
            try:
                raw = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                raw = data.decode('cp932', errors='replace')  # Excel(Shift-JIS)保険
        except Exception as e:
            flash(f'ファイルの読み込みに失敗しました: {e}', 'error')
            return redirect(url_for('client_import.index'))

    rows = _parse_rows(raw)
    if not rows:
        flash('取り込むデータがありません。名前を貼り付けるか、ファイルを選んでください。', 'error')
        return redirect(url_for('client_import.index'))

    store_raw = request.form.get('store_id')
    store_id = int(store_raw) if (store_raw and store_raw.isdigit()) else None

    db = SessionLocal()
    try:
        existing = {_norm(n[0]) for n in
                    db.query(TClient.name).filter(TClient.tenant_id == tenant_id).all()}
        seen = set()
        created, skipped = 0, 0
        skipped_names = []
        for name, typ in rows:
            k = _norm(name)
            if k in existing or k in seen:
                skipped += 1
                if len(skipped_names) < 50:
                    skipped_names.append(name)
                continue
            seen.add(k)
            c = TClient(tenant_id=tenant_id, name=name,
                        type=typ or _guess_type(name), store_id=store_id)
            db.add(c)
            created += 1
        db.commit()
        session['import_result'] = {
            'total': len(rows), 'created': created, 'skipped': skipped,
            'skipped_names': skipped_names,
            'store_id': store_id,
        }
        flash(f'{created}件を登録しました（重複スキップ {skipped}件）', 'success')
    except Exception as e:
        db.rollback()
        flash(f'取り込みに失敗しました: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('client_import.index'))
