# -*- coding: utf-8 -*-
"""
bookkeeping.py
完全自動記帳代行サービス（Phase 1 MVP）

フロー:
  freee明細/デモ取込 → AI・ルールで仕訳生成（信頼度付き）
  → 高信頼度は自動確定 / 低信頼度は税理士レビュー
  → 承認・修正を学習し、自動化率を高める
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash)
from datetime import datetime

from app.db import SessionLocal
from app.models_clients import TClient
from app.models_bookkeeping import BkTransaction, BkJournalEntry, BkFreeeConnection
from app.services import bookkeeping_engine as engine
from app.services.freee_client import generate_demo_transactions, FreeeClient
from app.services.journal_ai import ACCOUNT_OPTIONS, TAX_CODES
from app.utils.decorators import ROLES, require_roles

bp = Blueprint('bookkeeping', __name__, url_prefix='/bookkeeping')

# テーブル自動作成（冪等）
try:
    from app.db import Base, engine as _sa_engine
    from app import models_bookkeeping  # noqa: F401
    Base.metadata.create_all(bind=_sa_engine)
except Exception as _e:  # pragma: no cover
    print(f"⚠️ bookkeeping テーブル作成: {_e}")

_ALLOWED = (ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])


def _tenant_id():
    return session.get('tenant_id')


@bp.route('/')
@require_roles(*_ALLOWED)
def dashboard():
    tenant_id = _tenant_id()
    db = SessionLocal()
    try:
        if not tenant_id:
            clients, summary = [], {}
        else:
            clients = db.query(TClient).filter(TClient.tenant_id == tenant_id).order_by(TClient.id).all()
            summary = engine.dashboard_summary(db, tenant_id)
        totals = engine.tenant_totals(summary)
        return render_template('bookkeeping/dashboard.html',
                               clients=clients, summary=summary, totals=totals)
    finally:
        db.close()


@bp.route('/client/<int:client_id>')
@require_roles(*_ALLOWED)
def client_detail(client_id):
    tenant_id = _tenant_id()
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        if not client:
            flash('顧問先が見つかりません', 'warning')
            return redirect(url_for('bookkeeping.dashboard'))
        entries = (db.query(BkJournalEntry)
                   .filter(BkJournalEntry.client_id == client_id)
                   .order_by(BkJournalEntry.entry_date.desc(), BkJournalEntry.id.desc())
                   .limit(200).all())
        counts = engine.client_summary(db, tenant_id or client.tenant_id, client_id)
        conn = db.query(BkFreeeConnection).filter(BkFreeeConnection.client_id == client_id).first()
        return render_template('bookkeeping/client_detail.html',
                               client=client, entries=entries, counts=counts, conn=conn)
    finally:
        db.close()


@bp.route('/client/<int:client_id>/import', methods=['POST'])
@require_roles(*_ALLOWED)
def import_transactions(client_id):
    source = request.form.get('source', 'demo')
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        if not client:
            flash('顧問先が見つかりません', 'warning')
            return redirect(url_for('bookkeeping.dashboard'))
        tenant_id = client.tenant_id
        if source == 'freee':
            conn = db.query(BkFreeeConnection).filter(BkFreeeConnection.client_id == client_id).first()
            fc = FreeeClient(conn)
            if not fc.is_connected():
                flash('freee未連携です。設定画面でアクセストークンを登録してください。（デモデータで動作確認できます）', 'warning')
                return redirect(url_for('bookkeeping.settings', client_id=client_id))
            txns = fc.fetch_wallet_txns()
        else:
            txns = generate_demo_transactions()
        imported = engine.import_transactions(db, tenant_id, client_id, txns, source=source)
        result = engine.process_pending(db, tenant_id, client_id, use_ai=True)
        flash(f'{imported}件を取込み、{result["created"]}件の仕訳を生成しました'
              f'（自動確定 {result["auto_confirmed"]}件 / 要レビュー {result["needs_review"]}件）', 'success')
        return redirect(url_for('bookkeeping.client_detail', client_id=client_id))
    finally:
        db.close()


@bp.route('/review')
@require_roles(*_ALLOWED)
def review():
    tenant_id = _tenant_id()
    db = SessionLocal()
    try:
        q = (db.query(BkJournalEntry, TClient)
             .join(TClient, TClient.id == BkJournalEntry.client_id)
             .filter(BkJournalEntry.status == 'needs_review'))
        if tenant_id:
            q = q.filter(BkJournalEntry.tenant_id == tenant_id)
        rows = q.order_by(BkJournalEntry.confidence.asc(), BkJournalEntry.id.desc()).limit(200).all()
        items = []
        for entry, client in rows:
            txn = db.query(BkTransaction).filter(BkTransaction.id == entry.transaction_id).first()
            items.append({'entry': entry, 'client': client, 'txn': txn})
        return render_template('bookkeeping/review.html',
                               items=items, account_options=ACCOUNT_OPTIONS, tax_codes=TAX_CODES)
    finally:
        db.close()


@bp.route('/entry/<int:entry_id>/approve', methods=['POST'])
@require_roles(*_ALLOWED)
def approve_entry(entry_id):
    reviewer = session.get('login_id') or session.get('name') or 'staff'
    corrections = {
        'debit_account': request.form.get('debit_account'),
        'credit_account': request.form.get('credit_account'),
        'tax_code': request.form.get('tax_code'),
        'amount': request.form.get('amount'),
    }
    db = SessionLocal()
    try:
        ok = engine.approve_entry(db, entry_id, reviewer, corrections)
        flash('仕訳を承認し、学習ルールに反映しました。' if ok else '対象が見つかりません',
              'success' if ok else 'warning')
    finally:
        db.close()
    return redirect(request.form.get('next') or url_for('bookkeeping.review'))


@bp.route('/entry/<int:entry_id>/reject', methods=['POST'])
@require_roles(*_ALLOWED)
def reject_entry(entry_id):
    reviewer = session.get('login_id') or session.get('name') or 'staff'
    db = SessionLocal()
    try:
        engine.reject_entry(db, entry_id, reviewer)
        flash('仕訳を却下しました', 'success')
    finally:
        db.close()
    return redirect(request.form.get('next') or url_for('bookkeeping.review'))


@bp.route('/settings/<int:client_id>', methods=['GET', 'POST'])
@require_roles(*_ALLOWED)
def settings(client_id):
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(TClient.id == client_id).first()
        if not client:
            flash('顧問先が見つかりません', 'warning')
            return redirect(url_for('bookkeeping.dashboard'))
        conn = db.query(BkFreeeConnection).filter(BkFreeeConnection.client_id == client_id).first()
        if request.method == 'POST':
            if not conn:
                conn = BkFreeeConnection(tenant_id=client.tenant_id, client_id=client_id)
                db.add(conn)
            fid = (request.form.get('freee_company_id') or '').strip()
            conn.freee_company_id = int(fid) if fid.isdigit() else None
            at = request.form.get('access_token')
            rt = request.form.get('refresh_token')
            if at:
                conn.access_token = at
            if rt:
                conn.refresh_token = rt
            try:
                conn.auto_confirm_threshold = float(request.form.get('auto_confirm_threshold') or 0.9)
            except ValueError:
                conn.auto_confirm_threshold = 0.9
            conn.auto_post_to_freee = 1 if request.form.get('auto_post_to_freee') else 0
            conn.enabled = 1 if request.form.get('enabled') else 0
            conn.updated_at = datetime.utcnow()
            db.commit()
            flash('連携設定を保存しました', 'success')
            return redirect(url_for('bookkeeping.settings', client_id=client_id))
        return render_template('bookkeeping/settings.html', client=client, conn=conn)
    finally:
        db.close()
