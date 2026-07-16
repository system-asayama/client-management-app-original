# -*- coding: utf-8 -*-
"""
freee_double_check.py
freeeの登録済み取引(deals)を全件走査し、ダブルチェックの指摘を生成する。

設計方針:
- ルールベースで確定的にチェック（AI不要で動作）
- 各指摘に severity(high/warning/info) と category を付与
- 金額計算・判定はコードで実施し、AIは補助（任意）
- 再実行時に同一指摘を重複登録しない（dedup_key）
"""
from __future__ import annotations
import logging
from datetime import datetime
from sqlalchemy import func

from app.models_bookkeeping import BkCheckFinding, BkCheckRun

logger = logging.getLogger(__name__)

HIGH_AMOUNT_THRESHOLD = 1_000_000
DESC_REQUIRED_AMOUNT = 100_000


def _details(deal):
    return deal.get('details') or []


def _first_desc(deal):
    ds = _details(deal)
    return (ds[0].get('description') if ds else '') or ''


def _check_receipt_missing(deal):
    if not deal.get('receipts'):
        return [{'category': 'receipt_missing', 'severity': 'info',
                 'message': '証憑が添付されていません',
                 'detail': '電子帳簿保存法の観点からも証憑の添付・保存を確認してください。'}]
    return []


def _check_partner_missing(deal):
    if not deal.get('partner_id'):
        return [{'category': 'partner_missing', 'severity': 'info',
                 'message': '取引先(partner)が未設定です',
                 'detail': '補助元帳・インボイス管理のため取引先の設定を推奨します。'}]
    return []


def _check_description_missing(deal):
    out = []
    for d in _details(deal):
        damt = d.get('amount') or 0
        if not (d.get('description') or '').strip() and damt >= DESC_REQUIRED_AMOUNT:
            sev = 'warning' if damt >= 500_000 else 'info'
            out.append({'category': 'description_missing', 'severity': sev,
                        'message': f'摘要が空欄です（{damt:,}円）',
                        'detail': '高額仕訳のため、後日の確認・監査に備え摘要の記載を推奨します。'})
    return out


def _check_tax_consistency(deal):
    out = []
    for d in _details(deal):
        vat = d.get('vat') or 0
        amt = d.get('amount') or 0
        if vat and amt > 0:
            exp10 = round(amt * 10 / 110)
            exp8 = round(amt * 8 / 108)
            if abs(vat - exp10) > 1 and abs(vat - exp8) > 1:
                out.append({'category': 'tax_mismatch', 'severity': 'warning',
                            'message': f'消費税額が税込10%/8%と一致しません（登録{vat:,}円）',
                            'detail': f'税込想定: 10%={exp10:,}円 / 8%={exp8:,}円。税抜経理・軽減税率・非課税の可能性も含め確認してください。'})
    return out


def _check_high_amount(deal, threshold=HIGH_AMOUNT_THRESHOLD):
    amt = deal.get('amount') or 0
    if amt >= threshold:
        return [{'category': 'high_amount', 'severity': 'warning',
                 'message': f'高額取引です（{amt:,}円）',
                 'detail': '金額が大きいため、内容・計上区分に誤りがないか確認してください。'}]
    return []


def _per_deal_findings(deal):
    f = []
    f += _check_receipt_missing(deal)
    f += _check_partner_missing(deal)
    f += _check_description_missing(deal)
    f += _check_tax_consistency(deal)
    f += _check_high_amount(deal)
    return f


def _cross_checks(deals):
    """複数取引をまたぐチェック（重複計上・勘定科目のブレ）。(deal, finding)のリストを返す。"""
    out = []
    # 重複計上（同一日・同一金額・同一摘要）
    seen = {}
    for deal in deals:
        key = (deal.get('issue_date'), deal.get('amount'), _first_desc(deal))
        seen.setdefault(key, []).append(deal)
    for key, group in seen.items():
        if len(group) > 1 and key[1]:
            for deal in group[1:]:
                out.append((deal, {'category': 'duplicate', 'severity': 'high',
                                   'message': f'重複計上の可能性（{key[0]} / {key[1]:,}円）',
                                   'detail': f'同一日・同一金額・同一摘要「{key[2]}」の取引が{len(group)}件あります。二重計上でないか確認してください。'}))
    # 勘定科目のブレ（同一取引先で科目が複数）
    by_partner = {}
    for deal in deals:
        pid = deal.get('partner_id')
        if not pid:
            continue
        for d in _details(deal):
            acc = d.get('account_item_id')
            if acc:
                by_partner.setdefault(pid, set()).add(acc)
    for pid, accs in by_partner.items():
        if len(accs) > 1:
            for deal in deals:
                if deal.get('partner_id') == pid:
                    out.append((deal, {'category': 'account_variance', 'severity': 'warning',
                                       'message': '同一取引先で勘定科目が複数使われています',
                                       'detail': f'取引先ID {pid} に対し {len(accs)} 種類の勘定科目が使用されています。科目の統一を確認してください。'}))
                    break
    return out


def run_check(db, tenant_id, client_id, deals, source='freee', use_ai=False):
    """deals(freee deal dict list)を走査し、指摘をDBに記録する。サマリを返す。"""
    deals = deals or []
    run = BkCheckRun(tenant_id=tenant_id, client_id=client_id, source=source,
                     checked_count=len(deals), used_ai=1 if use_ai else 0)
    db.add(run)
    db.flush()

    raw = []  # list of (deal, finding_dict)
    for deal in deals:
        for f in _per_deal_findings(deal):
            raw.append((deal, f))
    raw += _cross_checks(deals)

    if use_ai:
        try:
            raw += _ai_review(deals, tenant_id)
        except Exception as e:
            logger.info(f'AIレビュースキップ: {e}')

    created = high = 0
    for deal, f in raw:
        deal_id = str(deal.get('id') or '')
        dedup = f"{deal_id}:{f['category']}"
        exists = (db.query(BkCheckFinding)
                  .filter(BkCheckFinding.client_id == client_id,
                          BkCheckFinding.dedup_key == dedup,
                          BkCheckFinding.status == 'open').first())
        if exists:
            continue
        db.add(BkCheckFinding(
            tenant_id=tenant_id, client_id=client_id, run_id=run.id,
            freee_deal_id=deal_id, deal_date=deal.get('issue_date'),
            amount=deal.get('amount'), severity=f['severity'],
            category=f['category'], message=f['message'], detail=f.get('detail'),
            dedup_key=dedup, status='open'))
        created += 1
        if f['severity'] == 'high':
            high += 1
    run.findings_count = created
    run.high_count = high
    db.commit()
    return {'checked': len(deals), 'created': created, 'high': high}


def _ai_review(deals, tenant_id=None):
    """AIによる補助チェック（私的経費・科目妥当性）。失敗時 []。"""
    import json
    from app.utils.api_key import get_openai_client
    client = get_openai_client(tenant_id=tenant_id, app_name='bookkeeping')
    if client is None or not deals:
        return []
    compact = []
    for deal in deals[:40]:
        d0 = (_details(deal) or [{}])[0]
        compact.append({'id': deal.get('id'), 'date': deal.get('issue_date'),
                        'amount': deal.get('amount'), 'type': deal.get('type'),
                        'account_item_id': d0.get('account_item_id'),
                        'description': d0.get('description') or ''})
    prompt = (
        'あなたは日本の税理士の記帳ダブルチェックAIです。\n'
        '次の取引一覧から、私的経費の混入疑い・勘定科目の不自然さが疑われるものだけを挙げてください。\n'
        '確実でないものは挙げないでください。金額計算はしないでください。\n\n'
        f'取引一覧(JSON): {json.dumps(compact, ensure_ascii=False)}\n\n'
        '次のJSON形式のみで回答:\n'
        '{"findings":[{"id":取引id,"message":"指摘(30文字以内)"}]}'
    )
    resp = client.chat.completions.create(
        model='gpt-4.1-mini',
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=500, temperature=0.0,
        response_format={'type': 'json_object'})
    data = json.loads(resp.choices[0].message.content)
    out = []
    id_map = {deal.get('id'): deal for deal in deals}
    for item in data.get('findings', []):
        deal = id_map.get(item.get('id'))
        if deal is None:
            continue
        out.append((deal, {'category': 'ai_review', 'severity': 'warning',
                           'message': f'AI指摘: {item.get("message", "")}',
                           'detail': 'AIによる補助的な指摘です。最終判断は税理士が行ってください。'}))
    return out


# ── 集計・一覧 ──

def open_findings_summary(db, tenant_id):
    rows = (db.query(BkCheckFinding.severity, func.count(BkCheckFinding.id))
            .filter(BkCheckFinding.tenant_id == tenant_id,
                    BkCheckFinding.status == 'open')
            .group_by(BkCheckFinding.severity).all())
    out = {'high': 0, 'warning': 0, 'info': 0, 'total': 0}
    for sev, cnt in rows:
        if sev in out:
            out[sev] = cnt
        out['total'] += cnt
    return out


def client_open_count(db, client_id):
    return (db.query(func.count(BkCheckFinding.id))
            .filter(BkCheckFinding.client_id == client_id,
                    BkCheckFinding.status == 'open').scalar() or 0)


def resolve_finding(db, finding_id, reviewer, status='resolved'):
    f = db.query(BkCheckFinding).filter(BkCheckFinding.id == finding_id).first()
    if not f:
        return False
    f.status = status
    f.resolved_by = reviewer
    f.resolved_at = datetime.utcnow()
    db.commit()
    return True
