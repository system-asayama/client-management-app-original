# -*- coding: utf-8 -*-
"""
bookkeeping_engine.py
記帳エンジン: 取込 → 仕訳生成（信頼度判定）→ 自動確定/レビュー振り分け → 学習 → 集計
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from sqlalchemy import func, or_

from app.models_bookkeeping import (BkTransaction, BkJournalEntry, BkRule,
                                    BkFreeeConnection)
from app.services.journal_ai import suggest_journal

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.90


def get_threshold(db, tenant_id, client_id):
    conn = db.query(BkFreeeConnection).filter(BkFreeeConnection.client_id == client_id).first()
    if conn and conn.auto_confirm_threshold:
        return float(conn.auto_confirm_threshold)
    return DEFAULT_THRESHOLD


def _load_rules(db, tenant_id, client_id):
    rules = (db.query(BkRule)
             .filter(BkRule.tenant_id == tenant_id,
                     or_(BkRule.client_id == client_id, BkRule.client_id.is_(None)))
             .all())
    return [{'id': r.id, 'match_type': r.match_type, 'pattern': r.pattern,
             'debit_account': r.debit_account, 'credit_account': r.credit_account,
             'tax_code': r.tax_code, 'priority': r.priority, 'hit_count': r.hit_count}
            for r in rules]


def import_transactions(db, tenant_id, client_id, txns, source='freee'):
    """取引を取込む（external_idで重複排除）。取込件数を返す。"""
    existing = set()
    ext_ids = [t.get('external_id') for t in (txns or []) if t.get('external_id')]
    if ext_ids:
        rows = (db.query(BkTransaction.external_id)
                .filter(BkTransaction.client_id == client_id,
                        BkTransaction.external_id.in_(ext_ids)).all())
        existing = {r[0] for r in rows}
    count = 0
    for t in txns or []:
        ext = t.get('external_id')
        if ext and ext in existing:
            continue
        db.add(BkTransaction(
            tenant_id=tenant_id, client_id=client_id, source=source,
            external_id=ext, txn_date=t.get('txn_date'),
            entry_side=t.get('entry_side', 'expense'),
            amount=int(t.get('amount') or 0),
            description=t.get('description'), counterparty=t.get('counterparty'),
            wallet_type=t.get('wallet_type'),
            raw_json=json.dumps(t, ensure_ascii=False), status='pending'))
        count += 1
    db.commit()
    return count


def process_pending(db, tenant_id, client_id, use_ai=True):
    """未処理取引に仕訳を生成。閾値で自動確定/レビューを振り分ける。"""
    threshold = get_threshold(db, tenant_id, client_id)
    rules = _load_rules(db, tenant_id, client_id)
    pend = (db.query(BkTransaction)
            .filter(BkTransaction.client_id == client_id,
                    BkTransaction.status == 'pending').all())
    created = auto_confirmed = needs_review = 0
    for txn in pend:
        sug = suggest_journal({
            'description': txn.description, 'amount': txn.amount,
            'entry_side': txn.entry_side, 'wallet_type': txn.wallet_type,
            'counterparty': txn.counterparty, 'txn_date': txn.txn_date,
        }, rules=rules, use_ai=use_ai, tenant_id=tenant_id)
        conf = float(sug.get('confidence') or 0)
        status = 'auto_confirmed' if conf >= threshold else 'needs_review'
        db.add(BkJournalEntry(
            tenant_id=tenant_id, client_id=client_id, transaction_id=txn.id,
            entry_date=txn.txn_date, debit_account=sug.get('debit_account'),
            credit_account=sug.get('credit_account'),
            amount=int(sug.get('amount') or txn.amount),
            tax_code=sug.get('tax_code'), description=txn.description,
            confidence=conf, status=status,
            matched_rule_id=sug.get('matched_rule_id'), ai_reason=sug.get('reason')))
        txn.status = 'journalized'
        created += 1
        if status == 'auto_confirmed':
            auto_confirmed += 1
        else:
            needs_review += 1
    db.commit()
    return {'created': created, 'auto_confirmed': auto_confirmed, 'needs_review': needs_review}


def approve_entry(db, entry_id, reviewer, corrections=None):
    entry = db.query(BkJournalEntry).filter(BkJournalEntry.id == entry_id).first()
    if not entry:
        return False
    corrections = corrections or {}
    if corrections.get('debit_account'):
        entry.debit_account = corrections['debit_account']
    if corrections.get('credit_account'):
        entry.credit_account = corrections['credit_account']
    if corrections.get('tax_code'):
        entry.tax_code = corrections['tax_code']
    amt = corrections.get('amount')
    if amt:
        try:
            entry.amount = int(str(amt).replace(',', ''))
        except ValueError:
            pass
    entry.status = 'approved'
    entry.reviewed_by = reviewer
    entry.reviewed_at = datetime.utcnow()
    db.commit()
    try:
        _learn_rule(db, entry)
    except Exception as e:
        logger.info(f'学習スキップ: {e}')
    try:
        _maybe_post_to_freee(db, entry)
    except Exception as e:
        logger.info(f'freee登録スキップ: {e}')
    return True


def reject_entry(db, entry_id, reviewer):
    entry = db.query(BkJournalEntry).filter(BkJournalEntry.id == entry_id).first()
    if not entry:
        return False
    entry.status = 'rejected'
    entry.reviewed_by = reviewer
    entry.reviewed_at = datetime.utcnow()
    db.commit()
    return True


def _learn_rule(db, entry):
    """承認された仕訳の摘要・取引先をキーに学習ルールをupsertする。"""
    txn = db.query(BkTransaction).filter(BkTransaction.id == entry.transaction_id).first()
    if not txn:
        return
    pattern = (txn.counterparty or txn.description or '').strip()[:40]
    if not pattern:
        return
    existing = (db.query(BkRule)
                .filter(BkRule.tenant_id == entry.tenant_id,
                        BkRule.client_id == entry.client_id,
                        BkRule.pattern == pattern).first())
    if existing:
        existing.debit_account = entry.debit_account
        existing.credit_account = entry.credit_account
        existing.tax_code = entry.tax_code
        existing.hit_count = (existing.hit_count or 1) + 1
        existing.last_used_at = datetime.utcnow()
        if existing.priority > 10:
            existing.priority -= 1
    else:
        db.add(BkRule(
            tenant_id=entry.tenant_id, client_id=entry.client_id,
            match_type='keyword', pattern=pattern,
            debit_account=entry.debit_account, credit_account=entry.credit_account,
            tax_code=entry.tax_code, priority=50, hit_count=1, source='learned'))
    db.commit()


def _maybe_post_to_freee(db, entry):
    conn = db.query(BkFreeeConnection).filter(BkFreeeConnection.client_id == entry.client_id).first()
    if not conn or not conn.auto_post_to_freee:
        return
    from app.services.freee_client import FreeeClient
    fc = FreeeClient(conn)
    if not fc.is_connected():
        return
    deal_id = fc.create_deal(entry)
    if deal_id:
        entry.freee_deal_id = deal_id
        entry.status = 'posted'
        db.commit()


# ── 集計 ──

def client_summary(db, tenant_id, client_id):
    def c(status):
        return (db.query(func.count(BkJournalEntry.id))
                .filter(BkJournalEntry.client_id == client_id,
                        BkJournalEntry.status == status).scalar() or 0)
    pending_txn = (db.query(func.count(BkTransaction.id))
                   .filter(BkTransaction.client_id == client_id,
                           BkTransaction.status == 'pending').scalar() or 0)
    auto = c('auto_confirmed')
    review = c('needs_review')
    approved = c('approved')
    posted = c('posted')
    rejected = c('rejected')
    total = auto + review + approved + posted + rejected
    rate = round((auto + approved + posted) / total * 100) if total else 0
    return {'pending_txn': pending_txn, 'auto_confirmed': auto, 'needs_review': review,
            'approved': approved, 'posted': posted, 'rejected': rejected,
            'total': total, 'rate': rate}


def dashboard_summary(db, tenant_id):
    """顧問先ごとの集計を返す {client_id: {...}}"""
    summary = {}

    def _slot(cid):
        return summary.setdefault(cid, {'auto_confirmed': 0, 'needs_review': 0,
                                        'approved': 0, 'posted': 0, 'rejected': 0,
                                        'pending_txn': 0})
    rows = (db.query(BkJournalEntry.client_id, BkJournalEntry.status,
                     func.count(BkJournalEntry.id))
            .filter(BkJournalEntry.tenant_id == tenant_id)
            .group_by(BkJournalEntry.client_id, BkJournalEntry.status).all())
    for cid, status, cnt in rows:
        s = _slot(cid)
        if status in s:
            s[status] = cnt
    trows = (db.query(BkTransaction.client_id, func.count(BkTransaction.id))
             .filter(BkTransaction.tenant_id == tenant_id,
                     BkTransaction.status == 'pending')
             .group_by(BkTransaction.client_id).all())
    for cid, cnt in trows:
        _slot(cid)['pending_txn'] = cnt
    for cid, s in summary.items():
        total = s['auto_confirmed'] + s['needs_review'] + s['approved'] + s['posted'] + s['rejected']
        s['total'] = total
        s['rate'] = round((s['auto_confirmed'] + s['approved'] + s['posted']) / total * 100) if total else 0
    return summary


def tenant_totals(summary):
    t = {'auto_confirmed': 0, 'needs_review': 0, 'approved': 0, 'posted': 0,
         'rejected': 0, 'pending_txn': 0, 'total': 0}
    for s in summary.values():
        for k in list(t.keys()):
            t[k] += s.get(k, 0)
    t['rate'] = round((t['auto_confirmed'] + t['approved'] + t['posted']) / t['total'] * 100) if t['total'] else 0
    return t
