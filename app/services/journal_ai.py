# -*- coding: utf-8 -*-
"""
journal_ai.py
取引 → 仕訳（勘定科目・税区分）推定エンジン

設計方針（comment_generator.py と同じ）:
- 金額の計算・増減は一切AIにやらせない
- まず学習ルール(bk_rules)と組み込み辞書で判定（AIなしで動作）
- 判定できない摘要のみ、AIに「決められた科目リストからの分類」だけ依頼
- 各仕訳に信頼度(confidence)を付与し、呼び出し側が自動確定/レビューを振り分ける
"""
from __future__ import annotations
import json
import logging

logger = logging.getLogger(__name__)

# 支払手段 → 貸方（出金時）／借方（入金時）に使う資産・負債科目
PAYMENT_ACCOUNT = {
    'bank': '普通預金',
    'credit_card': '未払金',
    'wallet': '現金',
    None: '現金',
}

# 組み込みキーワード辞書（出金・費用）: キーワード → (勘定科目, 税区分)
EXPENSE_KEYWORDS = {
    'jr': ('旅費交通費', '課対仕入10%'),
    'suica': ('旅費交通費', '課対仕入10%'),
    'pasmo': ('旅費交通費', '課対仕入10%'),
    'タクシー': ('旅費交通費', '課対仕入10%'),
    'taxi': ('旅費交通費', '課対仕入10%'),
    '鉄道': ('旅費交通費', '課対仕入10%'),
    'ana': ('旅費交通費', '課対仕入10%'),
    'jal': ('旅費交通費', '課対仕入10%'),
    '高速': ('旅費交通費', '課対仕入10%'),
    'etc': ('旅費交通費', '課対仕入10%'),
    'パーキング': ('旅費交通費', '課対仕入10%'),
    '駐車': ('旅費交通費', '課対仕入10%'),
    '電力': ('水道光熱費', '課対仕入10%'),
    '電気': ('水道光熱費', '課対仕入10%'),
    'ガス': ('水道光熱費', '課対仕入10%'),
    '水道': ('水道光熱費', '課対仕入10%'),
    'ntt': ('通信費', '課対仕入10%'),
    'docomo': ('通信費', '課対仕入10%'),
    'ドコモ': ('通信費', '課対仕入10%'),
    'au': ('通信費', '課対仕入10%'),
    'softbank': ('通信費', '課対仕入10%'),
    'ソフトバンク': ('通信費', '課対仕入10%'),
    '携帯': ('通信費', '課対仕入10%'),
    'インターネット': ('通信費', '課対仕入10%'),
    'aws': ('通信費', '課対仕入10%'),
    'amazon': ('消耗品費', '課対仕入10%'),
    'アマゾン': ('消耗品費', '課対仕入10%'),
    'askul': ('消耗品費', '課対仕入10%'),
    'アスクル': ('消耗品費', '課対仕入10%'),
    'ヨドバシ': ('消耗品費', '課対仕入10%'),
    'ビックカメラ': ('消耗品費', '課対仕入10%'),
    '文具': ('消耗品費', '課対仕入10%'),
    'スターバックス': ('会議費', '課対仕入10%'),
    'スタバ': ('会議費', '課対仕入10%'),
    'ドトール': ('会議費', '課対仕入10%'),
    'カフェ': ('会議費', '課対仕入10%'),
    '家賃': ('地代家賃', '課対仕入10%'),
    '賃料': ('地代家賃', '課対仕入10%'),
    'テナント': ('地代家賃', '課対仕入10%'),
    '手数料': ('支払手数料', '課対仕入10%'),
    'atm': ('支払手数料', '課対仕入10%'),
    '印紙': ('租税公課', '対象外'),
    '年金': ('法定福利費', '対象外'),
    '健康保険': ('法定福利費', '対象外'),
    '労働保険': ('法定福利費', '対象外'),
    '給与': ('給料手当', '対象外'),
    '給料': ('給料手当', '対象外'),
    '賞与': ('賞与', '対象外'),
    '書店': ('新聞図書費', '課対仕入10%'),
    '図書': ('新聞図書費', '課対仕入10%'),
    '新聞': ('新聞図書費', '課対仕入10%'),
    '保険': ('保険料', '対象外'),
    '広告': ('広告宣伝費', '課対仕入10%'),
}

# 軽減税率（飲食料品）を示唆するキーワード
REDUCED_TAX_KEYWORDS = ('スーパー', 'まいばすけっと', 'コンビニ', 'セブン', 'ローソン',
                        'ファミリーマート', '成城石井', '弁当', '食品')

# 入金（売上等）用
INCOME_KEYWORDS = {
    '売上': ('売上高', '課税売上10%'),
    '入金': ('売上高', '課税売上10%'),
    '振込': ('売上高', '課税売上10%'),
    '報酬': ('売上高', '課税売上10%'),
    '利息': ('受取利息', '対象外'),
    '還付': ('雑収入', '対象外'),
}

UNKNOWN_EXPENSE = ('雑費', '課対仕入10%')
UNKNOWN_INCOME = ('雑収入', '課税売上10%')

# AIが選べる勘定科目リスト（このリスト外は選ばせない）
ALLOWED_EXPENSE_ACCOUNTS = [
    '旅費交通費', '水道光熱費', '通信費', '消耗品費', '事務用品費', '会議費',
    '接待交際費', '地代家賃', '支払手数料', '租税公課', '法定福利費', '給料手当',
    '新聞図書費', '保険料', '広告宣伝費', '外注費', '修繕費', '荷造運賃',
    '福利厚生費', '車両費', '雑費',
]

# テンプレートの入力補助用
ACCOUNT_OPTIONS = sorted(set(ALLOWED_EXPENSE_ACCOUNTS + [
    '普通預金', '現金', '未払金', '売掛金', '買掛金', '売上高', '雑収入',
    '受取利息', '事業主貸', '事業主借', '仮払金', '仮受金', '預り金', '賞与',
]))
TAX_CODES = ['課対仕入10%', '課対仕入８％（軽）', '課税売上10%', '課税売上８％（軽）', '対象外', '非課税']
REDUCED_TAX_CODE = '課対仕入８％（軽）'


def _normalize(text):
    return (text or '').lower()


def match_rules(description, rules):
    """学習ルール(bk_rules)から最初にマッチしたルールを返す。rulesは辞書のリスト。"""
    desc = _normalize(description)
    for r in sorted(rules, key=lambda x: (x.get('priority', 100), -x.get('hit_count', 0))):
        pat = _normalize(r.get('pattern'))
        if not pat:
            continue
        if r.get('match_type') == 'exact':
            if desc == pat:
                return r
        else:
            if pat in desc:
                return r
    return None


def _payment_account(wallet_type):
    return PAYMENT_ACCOUNT.get(wallet_type, '現金')


def suggest_journal(txn, rules=None, use_ai=True, tenant_id=None):
    """
    1件の取引から仕訳案を返す。

    txn : dict {description, amount, entry_side, wallet_type, txn_date, counterparty}
    rules : list[dict]  学習ルール
    use_ai : bool  未判定時にAI分類を試みるか

    Returns dict {debit_account, credit_account, amount, tax_code, confidence, reason, matched_rule_id}
    """
    rules = rules or []
    description = txn.get('description') or txn.get('counterparty') or ''
    amount = int(txn.get('amount') or 0)
    side = txn.get('entry_side') or 'expense'
    wallet = txn.get('wallet_type')
    pay_acc = _payment_account(wallet)

    # 1) 学習ルール
    rule = match_rules(description, rules)
    if rule:
        hit = rule.get('hit_count', 1)
        conf = 0.95 if hit >= 3 else 0.88
        if side == 'income':
            debit = pay_acc
            credit = rule.get('credit_account') or rule.get('debit_account') or '売上高'
        else:
            debit = rule.get('debit_account') or '雑費'
            credit = rule.get('credit_account') or pay_acc
        return {
            'debit_account': debit, 'credit_account': credit, 'amount': amount,
            'tax_code': rule.get('tax_code'), 'confidence': conf,
            'reason': f'学習ルール「{rule.get("pattern")}」に一致（過去{hit}回）',
            'matched_rule_id': rule.get('id'),
        }

    # 2) 組み込み辞書
    desc_l = _normalize(description)
    if side == 'income':
        for kw, (acc, tax) in INCOME_KEYWORDS.items():
            if _normalize(kw) in desc_l:
                return {'debit_account': pay_acc, 'credit_account': acc, 'amount': amount,
                        'tax_code': tax, 'confidence': 0.82,
                        'reason': f'キーワード「{kw}」から{acc}と推定', 'matched_rule_id': None}
    else:
        for kw, (acc, tax) in EXPENSE_KEYWORDS.items():
            if _normalize(kw) in desc_l:
                if any(_normalize(f) in desc_l for f in REDUCED_TAX_KEYWORDS):
                    tax = REDUCED_TAX_CODE
                return {'debit_account': acc, 'credit_account': pay_acc, 'amount': amount,
                        'tax_code': tax, 'confidence': 0.82,
                        'reason': f'キーワード「{kw}」から{acc}と推定', 'matched_rule_id': None}
        if any(_normalize(f) in desc_l for f in REDUCED_TAX_KEYWORDS):
            return {'debit_account': '福利厚生費', 'credit_account': pay_acc, 'amount': amount,
                    'tax_code': REDUCED_TAX_CODE, 'confidence': 0.6,
                    'reason': '飲食料品の購入と推定（軽減税率）', 'matched_rule_id': None}

    # 3) AI分類（任意・失敗時スキップ）
    if use_ai and description.strip():
        ai = _ai_classify(description, side, tenant_id)
        if ai:
            acc, reason = ai
            if side == 'income':
                return {'debit_account': pay_acc, 'credit_account': acc, 'amount': amount,
                        'tax_code': '課税売上10%', 'confidence': 0.6,
                        'reason': f'AI分類: {reason}', 'matched_rule_id': None}
            return {'debit_account': acc, 'credit_account': pay_acc, 'amount': amount,
                    'tax_code': '課対仕入10%', 'confidence': 0.6,
                    'reason': f'AI分類: {reason}', 'matched_rule_id': None}

    # 4) 不明（低信頼度・要レビュー）
    if side == 'income':
        acc, tax = UNKNOWN_INCOME
        return {'debit_account': pay_acc, 'credit_account': acc, 'amount': amount,
                'tax_code': tax, 'confidence': 0.3,
                'reason': '摘要から判定できませんでした。確認してください。', 'matched_rule_id': None}
    acc, tax = UNKNOWN_EXPENSE
    return {'debit_account': acc, 'credit_account': pay_acc, 'amount': amount,
            'tax_code': tax, 'confidence': 0.3,
            'reason': '摘要から判定できませんでした。確認してください。', 'matched_rule_id': None}


def _ai_classify(description, side, tenant_id=None):
    """AIに勘定科目リストからの分類だけ依頼する。失敗時 None。"""
    try:
        from app.utils.api_key import get_openai_client
        client = get_openai_client(tenant_id=tenant_id, app_name='bookkeeping')
        if client is None:
            return None
        income_accounts = ['売上高', '雑収入', '受取利息']
        valid = ALLOWED_EXPENSE_ACCOUNTS if side != 'income' else income_accounts
        accounts = '、'.join(valid)
        prompt = (
            'あなたは日本の税理士の記帳補助AIです。\n'
            '次の取引摘要に最も適切な勘定科目を、下記リストから1つだけ選んでください。\n\n'
            f'摘要: {description}\n'
            f'区分: {"入金（収入）" if side == "income" else "出金（費用）"}\n'
            f'選択可能な勘定科目: {accounts}\n\n'
            '必ず次のJSON形式のみで回答してください:\n'
            '{"account": "科目名", "reason": "選定理由（20文字以内）"}'
        )
        resp = client.chat.completions.create(
            model='gpt-4.1-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=100, temperature=0.0,
            response_format={'type': 'json_object'},
        )
        data = json.loads(resp.choices[0].message.content)
        acc = data.get('account')
        if acc in valid:
            return acc, data.get('reason', '')
        return None
    except Exception as e:
        logger.info(f'AI仕訳分類スキップ: {e}')
        return None
