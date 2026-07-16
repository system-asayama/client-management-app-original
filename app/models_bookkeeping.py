# -*- coding: utf-8 -*-
"""
models_bookkeeping.py
完全自動記帳代行サービス - データモデル（Phase 1 MVP + ダブルチェック）

設計方針:
- freee 等の連携先から取り込んだ取引を bk_transactions に保持
- AI/ルールで生成した仕訳を bk_journal_entries に信頼度付きで保持
- freeeの登録済み取引を全件チェックした指摘を bk_check_findings に保持（ダブルチェック）
- テーブル名は英語 snake_case（PostgreSQL/SQLite 両対応・引用符不要）
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Index
from datetime import datetime
from app.db import Base


class BkFreeeConnection(Base):
    """顧問先ごとの freee 連携設定・OAuthトークン"""
    __tablename__ = 'bk_freee_connections'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)  # T_顧問先.id
    freee_company_id = Column(Integer, nullable=True)        # freee事業所ID
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    auto_confirm_threshold = Column(Float, nullable=False, default=0.90)  # 自動確定の信頼度閾値
    auto_post_to_freee = Column(Integer, nullable=False, default=0)       # 確定時にfreeeへ自動登録
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BkTransaction(Base):
    """取り込んだ生取引（銀行・カード明細・証憑など）"""
    __tablename__ = 'bk_transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    source = Column(String(20), nullable=False, default='freee')  # freee/csv/manual/demo
    external_id = Column(String(100), nullable=True)              # 連携先の一意ID（重複取込防止）
    txn_date = Column(String(20), nullable=True)                 # 取引日 YYYY-MM-DD
    entry_side = Column(String(10), nullable=True)               # income(入金)/expense(出金)
    amount = Column(Integer, nullable=False, default=0)          # 金額（正の整数・税込）
    description = Column(Text, nullable=True)                    # 摘要
    counterparty = Column(String(255), nullable=True)           # 取引先
    wallet_type = Column(String(20), nullable=True)             # bank/credit_card/wallet
    raw_json = Column(Text, nullable=True)                      # 連携先の生データ
    status = Column(String(20), nullable=False, default='pending')  # pending/journalized/ignored
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_bk_txn_client_status', 'client_id', 'status'),
    )


class BkJournalEntry(Base):
    """生成された仕訳（信頼度・レビュー状態付き）"""
    __tablename__ = 'bk_journal_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    transaction_id = Column(Integer, nullable=True, index=True)  # bk_transactions.id
    entry_date = Column(String(20), nullable=True)
    debit_account = Column(String(100), nullable=True)   # 借方勘定科目
    credit_account = Column(String(100), nullable=True)  # 貸方勘定科目
    amount = Column(Integer, nullable=False, default=0)  # 金額（税込）
    tax_code = Column(String(50), nullable=True)         # 税区分（課対仕入10%等）
    description = Column(Text, nullable=True)            # 摘要
    confidence = Column(Float, nullable=False, default=0.0)  # 0.0-1.0
    status = Column(String(20), nullable=False, default='needs_review')
    # auto_confirmed / needs_review / approved / rejected / posted
    matched_rule_id = Column(Integer, nullable=True)     # 学習ルールで判定した場合
    ai_reason = Column(Text, nullable=True)             # 推定根拠（説明）
    freee_deal_id = Column(Integer, nullable=True)      # freee登録後のdeal ID
    reviewed_by = Column(String(255), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_bk_entry_client_status', 'client_id', 'status'),
    )


class BkRule(Base):
    """学習ルール（摘要パターン→勘定科目マッピング）"""
    __tablename__ = 'bk_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)  # NULL=テナント共通
    match_type = Column(String(20), nullable=False, default='keyword')  # keyword/exact
    pattern = Column(String(255), nullable=False)         # 摘要キーワード
    debit_account = Column(String(100), nullable=True)
    credit_account = Column(String(100), nullable=True)
    tax_code = Column(String(50), nullable=True)
    priority = Column(Integer, nullable=False, default=100)
    hit_count = Column(Integer, nullable=False, default=1)
    source = Column(String(20), nullable=False, default='learned')  # learned/builtin/manual
    last_used_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class BkMonthlyClose(Base):
    """月次締め状態"""
    __tablename__ = 'bk_monthly_close'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    year_month = Column(String(7), nullable=False)  # 2026-07
    status = Column(String(20), nullable=False, default='open')  # open/review/closed
    total_entries = Column(Integer, default=0)
    auto_confirmed_count = Column(Integer, default=0)
    reviewed_count = Column(Integer, default=0)
    note = Column(Text, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BkCheckRun(Base):
    """ダブルチェックの実行履歴"""
    __tablename__ = 'bk_check_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    source = Column(String(20), nullable=False, default='freee')  # freee/demo
    checked_count = Column(Integer, default=0)       # 精査した取引件数
    findings_count = Column(Integer, default=0)      # 新規検出した指摘件数
    high_count = Column(Integer, default=0)          # 重要度highの件数
    used_ai = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class BkCheckFinding(Base):
    """ダブルチェックの指摘（要確認項目）"""
    __tablename__ = 'bk_check_findings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    run_id = Column(Integer, nullable=True, index=True)
    freee_deal_id = Column(String(40), nullable=True)   # 対象取引ID（文字列）
    deal_date = Column(String(20), nullable=True)
    amount = Column(Integer, nullable=True)
    severity = Column(String(10), nullable=False, default='warning')  # high/warning/info
    category = Column(String(40), nullable=True)  # receipt_missing/partner_missing/tax_mismatch/duplicate/...
    message = Column(Text, nullable=True)
    detail = Column(Text, nullable=True)
    dedup_key = Column(String(120), nullable=True, index=True)  # 再実行時の重複防止
    status = Column(String(20), nullable=False, default='open')  # open/resolved/ignored
    resolved_by = Column(String(255), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_bk_finding_client_status', 'client_id', 'status'),
    )
