# -*- coding: utf-8 -*-
"""
freee_client.py
freee会計 API ラッパ（Phase 1 MVP）

- アクセストークンが未設定でも import エラーにならないよう requests は遅延 import
- 実連携がない環境でも動作確認できるよう generate_demo_transactions() を提供
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

FREEE_API_BASE = 'https://api.freee.co.jp'


class FreeeClient:
    """freee会計APIの薄いラッパ。connectionは BkFreeeConnection もしくはNone。"""

    def __init__(self, connection=None):
        self.conn = connection

    def is_connected(self):
        return bool(self.conn and getattr(self.conn, 'access_token', None)
                    and getattr(self.conn, 'freee_company_id', None)
                    and getattr(self.conn, 'enabled', 1))

    def _headers(self):
        return {'Authorization': f'Bearer {self.conn.access_token}',
                'Content-Type': 'application/json'}

    def fetch_wallet_txns(self, limit=100):
        """未仕訳の口座明細（wallet_txns）を取得して正規化して返す。"""
        if not self.is_connected():
            return []
        try:
            import requests
        except Exception:
            logger.warning('requests未インストールのためfreee取得不可')
            return []
        try:
            params = {'company_id': self.conn.freee_company_id, 'limit': limit}
            r = requests.get(f'{FREEE_API_BASE}/api/1/wallet_txns',
                             headers=self._headers(), params=params, timeout=30)
            if r.status_code != 200:
                logger.warning(f'freee wallet_txns 取得失敗: {r.status_code} {r.text[:200]}')
                return []
            data = r.json().get('wallet_txns', [])
            out = []
            for w in data:
                out.append({
                    'external_id': f"freee_wt_{w.get('id')}",
                    'txn_date': w.get('date'),
                    'entry_side': 'income' if w.get('entry_side') == 'income' else 'expense',
                    'amount': int(w.get('amount') or 0),
                    'description': w.get('description') or '',
                    'counterparty': w.get('description') or '',
                    'wallet_type': _map_wallet_type(w.get('walletable_type')),
                })
            return out
        except Exception as e:
            logger.warning(f'freee取得エラー: {e}')
            return []

    def create_deal(self, entry):
        """承認済み仕訳をfreeeに取引(deal)として登録。deal_idを返す（失敗時None）。

        ※ 実運用では account_item_id / tax_code をfreeeの勘定科目マスタと
           マッピングする必要がある。Phase 1 では骨組みのみ。
        """
        if not self.is_connected():
            return None
        try:
            import requests
        except Exception:
            return None
        try:
            entry_type = 'income' if entry.credit_account in ('売上高', '雑収入', '受取利息') else 'expense'
            payload = {
                'company_id': self.conn.freee_company_id,
                'issue_date': entry.entry_date or datetime.utcnow().strftime('%Y-%m-%d'),
                'type': entry_type,
                'details': [{'amount': int(entry.amount or 0),
                             'account_item_id': None, 'tax_code': None}],
            }
            r = requests.post(f'{FREEE_API_BASE}/api/1/deals',
                              headers=self._headers(), json=payload, timeout=30)
            if r.status_code in (200, 201):
                return r.json().get('deal', {}).get('id')
            logger.warning(f'freee deal作成失敗: {r.status_code} {r.text[:200]}')
            return None
        except Exception as e:
            logger.warning(f'freee deal作成エラー: {e}')
            return None


def _map_wallet_type(t):
    return {'bank_account': 'bank', 'credit_card': 'credit_card', 'wallet': 'wallet'}.get(t, 'bank')


def generate_demo_transactions():
    """freee未連携でもフローを試せるデモ明細。"""
    today = datetime.utcnow().date()

    def d(days):
        return (today - timedelta(days=days)).strftime('%Y-%m-%d')

    samples = [
        ('JR東日本 モバイルSuica', 1200, 'expense', 'bank'),
        ('Amazon.co.jp', 3480, 'expense', 'credit_card'),
        ('スターバックス 渋谷店', 680, 'expense', 'credit_card'),
        ('東京電力エナジーパートナー', 8640, 'expense', 'bank'),
        ('NTTドコモ 携帯料金', 7920, 'expense', 'bank'),
        ('アスクル オフィス用品', 5280, 'expense', 'credit_card'),
        ('タイムズ24 駐車場', 800, 'expense', 'credit_card'),
        ('株式会社サンプル商事 売上入金', 330000, 'income', 'bank'),
        ('AWS クラウド利用料', 15400, 'expense', 'credit_card'),
        ('セブンイレブン', 540, 'expense', 'wallet'),
        ('三井不動産 事務所家賃', 120000, 'expense', 'bank'),
        ('謎の引落し ABC', 4980, 'expense', 'bank'),
    ]
    out = []
    for i, (desc, amt, side, wallet) in enumerate(samples):
        out.append({
            'external_id': f'demo_{d(i)}_{i}_{amt}',
            'txn_date': d(i), 'entry_side': side, 'amount': amt,
            'description': desc, 'counterparty': desc, 'wallet_type': wallet,
        })
    return out
