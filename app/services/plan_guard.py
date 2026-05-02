"""
plan_guard.py
プラン制御ロジック

各プランで利用可能な機能を定義し、
機能制限チェック・利用ログ記録を提供する。
"""

from __future__ import annotations
from typing import Optional
from datetime import datetime

# ─────────────────────────────────────────────
# プラン定義
# ─────────────────────────────────────────────

PLAN_FEATURES = {
    'free': {
        'display_name': 'フリープラン',
        'price_monthly': 0,
        'max_dogs': 5,
        'max_owners': 3,
        'features': [
            'basic_coi',           # 簡易COI計算
            'basic_mating_eval',   # 基本交配評価
            'owner_app',           # 飼い主アプリ利用
            'health_log',          # 健康ログ記録
        ],
    },
    'standard': {
        'display_name': 'スタンダード',
        'price_monthly': 4980,
        'max_dogs': None,          # 無制限
        'max_owners': None,
        'features': [
            'basic_coi',
            'advanced_coi',        # 詳細COI分析
            'avk_analysis',        # AVK分析
            'genetic_disease',     # 遺伝病リスク分析
            'basic_mating_eval',
            'advanced_mating_eval',# 詳細交配評価
            'basic_report',        # 基本レポート出力
            'owner_app',
            'health_log',
            'medical_event',       # 通院履歴
            'vaccine_schedule',    # ワクチン管理
        ],
    },
    'pro': {
        'display_name': 'プロ',
        'price_monthly': 9800,
        'max_dogs': None,
        'max_owners': None,
        'features': [
            'basic_coi',
            'advanced_coi',
            'avk_analysis',
            'genetic_disease',
            'basic_mating_eval',
            'advanced_mating_eval',
            'breeding_history',    # 繁殖履歴分析
            'puppy_data',          # 産子データ分析
            'line_analysis',       # ライン分析
            'candidate_ranking',   # 候補比較ランキング
            'basic_report',
            'advanced_report',     # 詳細レポート
            'pdf_report',          # PDFレポート出力
            'survival_analysis',   # 生存分析
            'breeder_score',       # ブリーダー評価スコア
            'owner_app',
            'health_log',
            'medical_event',
            'vaccine_schedule',
            'priority_support',    # 優先サポート
        ],
    },
    'enterprise': {
        'display_name': 'エンタープライズ',
        'price_monthly': 0,        # 別途見積もり
        'max_dogs': None,
        'max_owners': None,
        'features': [
            'basic_coi', 'advanced_coi', 'avk_analysis', 'genetic_disease',
            'basic_mating_eval', 'advanced_mating_eval',
            'breeding_history', 'puppy_data', 'line_analysis',
            'candidate_ranking', 'basic_report', 'advanced_report', 'pdf_report',
            'survival_analysis', 'breeder_score',
            'owner_app', 'health_log', 'medical_event', 'vaccine_schedule',
            'priority_support',
            'api_access',          # API連携
            'data_export',         # データエクスポート（無制限）
            'custom_analysis',     # カスタム分析
        ],
    },
}

# 機能の日本語名マッピング
FEATURE_NAMES = {
    'basic_coi':            '簡易COI計算',
    'advanced_coi':         '詳細COI分析',
    'avk_analysis':         'AVK分析',
    'genetic_disease':      '遺伝病リスク分析',
    'basic_mating_eval':    '基本交配評価',
    'advanced_mating_eval': '詳細交配評価',
    'breeding_history':     '繁殖履歴分析',
    'puppy_data':           '産子データ分析',
    'line_analysis':        'ライン分析',
    'candidate_ranking':    '候補比較ランキング',
    'basic_report':         '基本レポート出力',
    'advanced_report':      '詳細レポート',
    'pdf_report':           'PDFレポート出力',
    'survival_analysis':    '生存分析',
    'breeder_score':        'ブリーダー評価スコア',
    'owner_app':            '飼い主アプリ',
    'health_log':           '健康ログ記録',
    'medical_event':        '通院履歴管理',
    'vaccine_schedule':     'ワクチン管理',
    'priority_support':     '優先サポート',
    'api_access':           'API連携',
    'data_export':          'データエクスポート（無制限）',
    'custom_analysis':      'カスタム分析',
}

# 機能が属する最低プラン（アップグレード誘導用）
FEATURE_MIN_PLAN = {
    'basic_coi':            'free',
    'basic_mating_eval':    'free',
    'owner_app':            'free',
    'health_log':           'free',
    'advanced_coi':         'standard',
    'avk_analysis':         'standard',
    'genetic_disease':      'standard',
    'advanced_mating_eval': 'standard',
    'basic_report':         'standard',
    'medical_event':        'standard',
    'vaccine_schedule':     'standard',
    'breeding_history':     'pro',
    'puppy_data':           'pro',
    'line_analysis':        'pro',
    'candidate_ranking':    'pro',
    'advanced_report':      'pro',
    'pdf_report':           'pro',
    'survival_analysis':    'pro',
    'breeder_score':        'pro',
    'priority_support':     'pro',
    'api_access':           'enterprise',
    'data_export':          'enterprise',
    'custom_analysis':      'enterprise',
}


# ─────────────────────────────────────────────
# プラン取得ヘルパー
# ─────────────────────────────────────────────

def get_tenant_plan(db, tenant_id: int) -> str:
    """
    テナントの現在のプラン名を返す。
    サブスクリプションが存在しない場合は 'free' を返す。
    """
    try:
        from sqlalchemy import text
        row = db.execute(text(
            """
            SELECT p.name FROM subscriptions s
            JOIN plans p ON s.plan_id = p.id
            WHERE s.tenant_id = :tid
              AND s.status IN ('active', 'trialing')
            ORDER BY s.id DESC LIMIT 1
            """
        ), {'tid': tenant_id}).fetchone()
        if row:
            return row[0]
    except Exception:
        pass
    return 'free'


def get_plan_features(plan_name: str) -> list:
    """プラン名から利用可能な機能リストを返す"""
    return PLAN_FEATURES.get(plan_name, PLAN_FEATURES['free'])['features']


def get_plan_limits(plan_name: str) -> dict:
    """プラン名から制限値を返す"""
    plan = PLAN_FEATURES.get(plan_name, PLAN_FEATURES['free'])
    return {
        'max_dogs': plan['max_dogs'],
        'max_owners': plan['max_owners'],
    }


# ─────────────────────────────────────────────
# 機能制限チェック
# ─────────────────────────────────────────────

def can_use_feature(plan_name: str, feature_key: str) -> bool:
    """指定プランで機能が利用可能かチェックする"""
    features = get_plan_features(plan_name)
    return feature_key in features


def check_dog_limit(db, tenant_id: int, plan_name: str) -> dict:
    """
    犬の登録数がプランの上限に達しているかチェックする。

    Returns
    -------
    dict
        {'allowed': bool, 'current': int, 'max': int | None}
    """
    limits = get_plan_limits(plan_name)
    max_dogs = limits['max_dogs']

    if max_dogs is None:
        return {'allowed': True, 'current': 0, 'max': None}

    try:
        from sqlalchemy import text
        row = db.execute(text(
            "SELECT COUNT(*) FROM dogs WHERE tenant_id = :tid AND is_deleted = 0"
        ), {'tid': tenant_id}).fetchone()
        current = row[0] if row else 0
    except Exception:
        current = 0

    return {
        'allowed': current < max_dogs,
        'current': current,
        'max': max_dogs,
    }


def check_owner_limit(db, tenant_id: int, plan_name: str) -> dict:
    """
    飼い主の登録数がプランの上限に達しているかチェックする。
    """
    limits = get_plan_limits(plan_name)
    max_owners = limits['max_owners']

    if max_owners is None:
        return {'allowed': True, 'current': 0, 'max': None}

    try:
        from sqlalchemy import text
        row = db.execute(text(
            "SELECT COUNT(*) FROM owners WHERE breeder_tenant_id = :tid"
        ), {'tid': tenant_id}).fetchone()
        current = row[0] if row else 0
    except Exception:
        current = 0

    return {
        'allowed': current < max_owners,
        'current': current,
        'max': max_owners,
    }


def get_upgrade_required_plan(feature_key: str) -> Optional[str]:
    """機能を利用するために必要な最低プランを返す"""
    return FEATURE_MIN_PLAN.get(feature_key)


def build_upgrade_message(feature_key: str) -> str:
    """機能制限時のアップグレード誘導メッセージを生成する"""
    feature_name = FEATURE_NAMES.get(feature_key, feature_key)
    min_plan = get_upgrade_required_plan(feature_key)
    if min_plan:
        plan_display = PLAN_FEATURES.get(min_plan, {}).get('display_name', min_plan)
        return f'「{feature_name}」は{plan_display}以上でご利用いただけます。プランをアップグレードしてください。'
    return f'「{feature_name}」はご利用のプランでは使用できません。'


# ─────────────────────────────────────────────
# 利用ログ記録
# ─────────────────────────────────────────────

def log_feature_usage(db, tenant_id: int, feature_key: str,
                      user_id: Optional[int] = None, meta: Optional[dict] = None):
    """機能利用ログをfeature_usagesテーブルに記録する"""
    try:
        from app.models_breeder import FeatureUsage
        log = FeatureUsage(
            tenant_id=tenant_id,
            feature_key=feature_key,
            user_id=user_id,
            meta=meta,
        )
        db.add(log)
        db.commit()
    except Exception:
        pass  # ログ記録失敗はサイレントに無視


# ─────────────────────────────────────────────
# プランガードデコレータ（Flaskルート用）
# ─────────────────────────────────────────────

def require_feature(feature_key: str):
    """
    Flaskルートに適用するプランガードデコレータ。

    使用例:
        @bp.route('/simulation')
        @require_feature('advanced_coi')
        def simulation():
            ...
    """
    from functools import wraps
    from flask import session, jsonify, request, redirect, url_for, flash

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from app.extensions import db
            tenant_id = session.get('tenant_id')
            if not tenant_id:
                if request.is_json:
                    return jsonify({'error': 'Unauthorized'}), 401
                return redirect(url_for('breeder.login'))

            plan_name = get_tenant_plan(db, tenant_id)
            if not can_use_feature(plan_name, feature_key):
                msg = build_upgrade_message(feature_key)
                if request.is_json:
                    return jsonify({
                        'error': 'plan_limit',
                        'message': msg,
                        'required_plan': get_upgrade_required_plan(feature_key),
                    }), 403
                flash(msg, 'warning')
                return redirect(url_for('breeder.plan_upgrade'))

            # 利用ログ記録
            user_id = session.get('user_id')
            log_feature_usage(db, tenant_id, feature_key, user_id=user_id)

            return f(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# プラン情報取得（テンプレート用）
# ─────────────────────────────────────────────

def get_plan_context(db, tenant_id: int) -> dict:
    """
    テンプレートに渡すプラン情報を返す。
    """
    plan_name = get_tenant_plan(db, tenant_id)
    plan_info = PLAN_FEATURES.get(plan_name, PLAN_FEATURES['free'])
    features = plan_info['features']

    return {
        'current_plan': plan_name,
        'current_plan_display': plan_info['display_name'],
        'available_features': features,
        'plan_features': PLAN_FEATURES,
        'feature_names': FEATURE_NAMES,
    }
