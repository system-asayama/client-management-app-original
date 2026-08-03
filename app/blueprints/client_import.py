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


# CSVヘッダ名 → TClient フィールド名 のマッピング（大小文字無視）
_COL_MAP = {
    'name': 'name', '名称': 'name', '名前': 'name', '顧問先名': 'name',
    'type': 'type', '区分': 'type', '種別': 'type',
    'email': 'email', 'メール': 'email', 'メールアドレス': 'email',
    'phone': 'phone', '電話': 'phone', '電話番号': 'phone',
    'address': 'address', '住所': 'address',
    'industry': 'industry', '業種': 'industry',
    'fiscal_month': 'fiscal_year_end_month', '決算月': 'fiscal_year_end_month', '決算': 'fiscal_year_end_month',
    'corporate_number': 'tax_id_number', '法人番号': 'tax_id_number',
    'tax_id_number': 'tax_id_number',
}


def _parse_rows(content):
    """テキスト/CSVを [dict(name, type, email, phone, address, industry,
    fiscal_year_end_month, tax_id_number)] に解析する。

    - 1行目が列見出し（name/名称/住所/法人番号 等）なら複数列CSVとして解釈
    - 見出しが無ければ「名前」または「名前,種別」の簡易形式として解釈
    """
    import csv
    import io
    text_ = (content or '').lstrip('﻿')
    lines = [l for l in text_.splitlines() if l.strip()]
    if not lines:
        return []

    # 先頭行がヘッダかどうか判定
    first_cells = [c.strip().lower() for c in next(csv.reader([lines[0]]))]
    header = None
    if any(c in _COL_MAP for c in first_cells):
        header = [_COL_MAP.get(c) for c in first_cells]

    rows = []
    if header:
        reader = csv.reader(io.StringIO('\n'.join(lines[1:])))
        for cells in reader:
            rec = {}
            for i, val in enumerate(cells):
                if i < len(header) and header[i] and val.strip():
                    rec[header[i]] = val.strip()
            if rec.get('name'):
                rows.append(rec)
    else:
        for line in lines:
            parts = [p.strip() for p in re.split(r'[,\t]', line)]
            if not parts or not parts[0]:
                continue
            rec = {'name': parts[0]}
            if len(parts) > 1 and parts[1] in ('法人', '個人'):
                rec['type'] = parts[1]
            rows.append(rec)

    # 種別・決算月の正規化
    for rec in rows:
        if rec.get('type') not in ('法人', '個人'):
            rec.pop('type', None)
        if 'fiscal_year_end_month' in rec:
            m = re.sub(r'\D', '', rec['fiscal_year_end_month'] or '')
            rec['fiscal_year_end_month'] = int(m) if m and 1 <= int(m) <= 12 else None
            if rec['fiscal_year_end_month'] is None:
                rec.pop('fiscal_year_end_month')
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

    _extra = ('email', 'phone', 'address', 'industry',
              'fiscal_year_end_month', 'tax_id_number')
    db = SessionLocal()
    try:
        existing = {_norm(n[0]) for n in
                    db.query(TClient.name).filter(TClient.tenant_id == tenant_id).all()}
        seen = set()
        created, skipped = 0, 0
        skipped_names = []
        for rec in rows:
            name = rec.get('name')
            k = _norm(name)
            if k in existing or k in seen:
                skipped += 1
                if len(skipped_names) < 50:
                    skipped_names.append(name)
                continue
            seen.add(k)
            c = TClient(tenant_id=tenant_id, name=name,
                        type=rec.get('type') or _guess_type(name), store_id=store_id)
            for f in _extra:
                if rec.get(f) not in (None, ''):
                    setattr(c, f, rec[f])
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
