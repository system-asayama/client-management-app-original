# -*- coding: utf-8 -*-
"""
survival_analysis.py のユニットテスト

カプランマイヤー推定・グリーンウッド信頼区間・疾患発生率・
ライン別分析・体重推移・ワクチンアラート・シニア通知を検証する。
"""
import sys
import os
import math
from datetime import date

# パスを追加してモジュールを直接インポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'services'))
from survival_analysis import (
    make_survival_record,
    kaplan_meier_estimate,
    greenwood_confidence_interval,
    calculate_disease_incidence,
    analyze_weight_trend,
    generate_vaccine_alerts,
    check_senior_notification,
    _evaluate_line_performance,
    SENIOR_AGE_MONTHS_BY_SIZE,
)


# ─────────────────────────────────────────────
# 1. make_survival_record
# ─────────────────────────────────────────────

def test_make_survival_record_deceased():
    r = make_survival_record(dog_id=1, age_months=120, is_deceased=True)
    assert r['dog_id'] == 1
    assert r['time_months'] == 120
    assert r['event'] == 1
    assert r['censored'] is False


def test_make_survival_record_alive():
    r = make_survival_record(dog_id=2, age_months=60, is_deceased=False)
    assert r['event'] == 0
    assert r['censored'] is True


def test_make_survival_record_age_range_fallback():
    """age_months が None の場合は age_range の中央値を使う"""
    r = make_survival_record(dog_id=3, age_months=None, is_deceased=True, age_range='7-10歳')
    assert r['time_months'] == 102  # 中央値


def test_make_survival_record_none_both():
    """age_months も age_range も None の場合は time_months=None"""
    r = make_survival_record(dog_id=4, age_months=None, is_deceased=True)
    assert r['time_months'] is None


# ─────────────────────────────────────────────
# 2. kaplan_meier_estimate
# ─────────────────────────────────────────────

def test_km_empty():
    result = kaplan_meier_estimate([])
    assert result['n_total'] == 0
    assert result['survival_curve'] == []
    assert result['median_lifespan_months'] is None


def test_km_no_events():
    """全員生存中（打ち切りのみ）→ 生存曲線は空"""
    records = [
        make_survival_record(i, 60, False) for i in range(5)
    ]
    result = kaplan_meier_estimate(records)
    assert result['n_events'] == 0
    assert result['survival_curve'] == []


def test_km_all_deceased_same_time():
    """全員同時刻に死亡 → S(t) = 0"""
    records = [make_survival_record(i, 100, True) for i in range(4)]
    result = kaplan_meier_estimate(records)
    assert len(result['survival_curve']) == 1
    assert result['survival_curve'][0]['survival_rate'] == 0.0


def test_km_simple_two_events():
    """
    n=4, t=50 で 1 死亡, t=100 で 1 死亡, 残り 2 は打ち切り(t=120)
    S(50) = 1 - 1/4 = 0.75
    S(100) = 0.75 * (1 - 1/3) = 0.5
    """
    records = [
        make_survival_record(1, 50, True),
        make_survival_record(2, 100, True),
        make_survival_record(3, 120, False),
        make_survival_record(4, 120, False),
    ]
    result = kaplan_meier_estimate(records)
    curve = result['survival_curve']
    assert len(curve) == 2
    assert abs(curve[0]['survival_rate'] - 0.75) < 1e-6
    assert abs(curve[1]['survival_rate'] - 0.5) < 1e-6


def test_km_median_lifespan():
    """中央生存期間: S(t) <= 0.5 になる最初の時点"""
    records = [
        make_survival_record(1, 50, True),
        make_survival_record(2, 100, True),
        make_survival_record(3, 120, False),
        make_survival_record(4, 120, False),
    ]
    result = kaplan_meier_estimate(records)
    # S(100) = 0.5 → 中央値 = 100
    assert result['median_lifespan_months'] == 100


def test_km_confidence_level():
    """信頼度: イベント数で分類"""
    # n_events < 5 → very_low
    records = [make_survival_record(i, 100, True) for i in range(3)]
    r = kaplan_meier_estimate(records)
    assert r['confidence_level'] == 'very_low'

    # n_events >= 30 → high
    records = [make_survival_record(i, 100, True) for i in range(30)]
    r = kaplan_meier_estimate(records)
    assert r['confidence_level'] == 'high'


def test_km_censored_before_event():
    """
    打ち切りが死亡より前にある場合のリスク集合計算
    n=3, t=30 で 1 打ち切り, t=60 で 1 死亡, t=90 で 1 死亡
    S(60) = 1 - 1/2 = 0.5
    S(90) = 0.5 * (1 - 1/1) = 0.0
    """
    records = [
        make_survival_record(1, 30, False),   # 打ち切り
        make_survival_record(2, 60, True),    # 死亡
        make_survival_record(3, 90, True),    # 死亡
    ]
    result = kaplan_meier_estimate(records)
    curve = result['survival_curve']
    assert abs(curve[0]['survival_rate'] - 0.5) < 1e-6
    assert abs(curve[1]['survival_rate'] - 0.0) < 1e-6


# ─────────────────────────────────────────────
# 3. greenwood_confidence_interval
# ─────────────────────────────────────────────

def test_greenwood_ci_bounds():
    """CI は 0〜1 の範囲内"""
    records = [
        make_survival_record(1, 50, True),
        make_survival_record(2, 100, True),
        make_survival_record(3, 120, False),
        make_survival_record(4, 120, False),
    ]
    km = kaplan_meier_estimate(records)
    ci_curve = greenwood_confidence_interval(km['survival_curve'])
    for point in ci_curve:
        assert 0.0 <= point['ci_lower'] <= 1.0
        assert 0.0 <= point['ci_upper'] <= 1.0
        assert point['ci_lower'] <= point['survival_rate'] <= point['ci_upper']


def test_greenwood_ci_empty():
    """空の曲線に対して空リストを返す"""
    result = greenwood_confidence_interval([])
    assert result == []


# ─────────────────────────────────────────────
# 4. calculate_disease_incidence
# ─────────────────────────────────────────────

def test_disease_incidence_basic():
    events = [
        {'dog_id': 1, 'title': '股関節形成不全', 'category': 'illness', 'severity': 'moderate'},
        {'dog_id': 2, 'title': '股関節形成不全', 'category': 'illness', 'severity': 'severe'},
        {'dog_id': 3, 'title': '白内障', 'category': 'illness', 'severity': 'mild'},
    ]
    result = calculate_disease_incidence(events, total_dogs=10)
    assert result['affected_count'] == 3
    assert result['incidence_rate_percent'] == 30.0


def test_disease_incidence_filter():
    events = [
        {'dog_id': 1, 'title': '股関節形成不全', 'category': 'illness', 'severity': 'moderate'},
        {'dog_id': 2, 'title': '白内障', 'category': 'illness', 'severity': 'mild'},
    ]
    result = calculate_disease_incidence(events, total_dogs=10, disease_name='股関節')
    assert result['affected_count'] == 1
    assert result['incidence_rate_percent'] == 10.0


def test_disease_incidence_zero_total():
    result = calculate_disease_incidence([], total_dogs=0)
    assert result['incidence_rate_percent'] is None


def test_disease_incidence_same_dog_multiple_events():
    """同一犬の複数イベントは1頭としてカウント"""
    events = [
        {'dog_id': 1, 'title': '胃腸炎', 'category': 'illness', 'severity': 'mild'},
        {'dog_id': 1, 'title': '胃腸炎', 'category': 'illness', 'severity': 'mild'},
    ]
    result = calculate_disease_incidence(events, total_dogs=5)
    assert result['affected_count'] == 1
    assert result['incidence_rate_percent'] == 20.0


# ─────────────────────────────────────────────
# 5. analyze_weight_trend
# ─────────────────────────────────────────────

def test_weight_trend_empty():
    result = analyze_weight_trend([])
    assert result['trend'] == 'unknown'
    assert result['current_weight'] is None


def test_weight_trend_stable():
    logs = [
        {'log_date': date(2025, 1, 1), 'weight': 5.0},
        {'log_date': date(2025, 2, 1), 'weight': 5.1},
        {'log_date': date(2025, 3, 1), 'weight': 4.9},
        {'log_date': date(2025, 4, 1), 'weight': 5.0},
    ]
    result = analyze_weight_trend(logs)
    assert result['trend'] == 'stable'
    assert result['current_weight'] == 5.0


def test_weight_trend_increasing():
    logs = [
        {'log_date': date(2025, 1, 1), 'weight': 4.0},
        {'log_date': date(2025, 2, 1), 'weight': 4.2},
        {'log_date': date(2025, 3, 1), 'weight': 4.5},
        {'log_date': date(2025, 4, 1), 'weight': 4.8},
    ]
    result = analyze_weight_trend(logs)
    assert result['trend'] == 'increasing'


def test_weight_trend_vs_breed_avg():
    logs = [{'log_date': date(2025, 1, 1), 'weight': 6.0}]
    result = analyze_weight_trend(logs, breed_avg_weight=5.0)
    assert result['vs_breed_avg_percent'] == 20.0  # (6-5)/5 * 100


# ─────────────────────────────────────────────
# 6. generate_vaccine_alerts
# ─────────────────────────────────────────────

def test_vaccine_alert_overdue():
    schedules = [
        {'id': 1, 'vaccine_type': '混合ワクチン', 'scheduled_date': date(2025, 1, 1), 'is_completed': False}
    ]
    alerts = generate_vaccine_alerts(schedules, today=date(2025, 3, 1))
    assert len(alerts) == 1
    assert alerts[0]['urgency'] == 'overdue'


def test_vaccine_alert_urgent():
    schedules = [
        {'id': 1, 'vaccine_type': 'フィラリア', 'scheduled_date': date(2025, 3, 5), 'is_completed': False}
    ]
    alerts = generate_vaccine_alerts(schedules, today=date(2025, 3, 1))
    assert len(alerts) == 1
    assert alerts[0]['urgency'] == 'urgent'


def test_vaccine_alert_upcoming():
    schedules = [
        {'id': 1, 'vaccine_type': '狂犬病', 'scheduled_date': date(2025, 3, 20), 'is_completed': False}
    ]
    alerts = generate_vaccine_alerts(schedules, today=date(2025, 3, 1))
    assert len(alerts) == 1
    assert alerts[0]['urgency'] == 'upcoming'


def test_vaccine_alert_completed_excluded():
    """完了済みはアラートに含まれない"""
    schedules = [
        {'id': 1, 'vaccine_type': '混合ワクチン', 'scheduled_date': date(2025, 1, 1), 'is_completed': True}
    ]
    alerts = generate_vaccine_alerts(schedules, today=date(2025, 3, 1))
    assert len(alerts) == 0


def test_vaccine_alert_far_future_excluded():
    """30日以上先はアラートに含まれない"""
    schedules = [
        {'id': 1, 'vaccine_type': '混合ワクチン', 'scheduled_date': date(2025, 12, 31), 'is_completed': False}
    ]
    alerts = generate_vaccine_alerts(schedules, today=date(2025, 3, 1))
    assert len(alerts) == 0


# ─────────────────────────────────────────────
# 7. check_senior_notification
# ─────────────────────────────────────────────

def test_senior_small_dog():
    """小型犬: 7歳（84ヶ月）でシニア"""
    birth = date(2018, 1, 1)
    today = date(2025, 2, 1)  # 7歳1ヶ月
    result = check_senior_notification(birth, dog_size='small', today=today)
    assert result['is_senior'] is True
    assert result['notification'] is not None


def test_senior_giant_dog():
    """超大型犬: 5歳（60ヶ月）でシニア"""
    birth = date(2020, 1, 1)
    today = date(2025, 2, 1)  # 5歳1ヶ月
    result = check_senior_notification(birth, dog_size='giant', today=today)
    assert result['is_senior'] is True


def test_senior_not_yet():
    """まだシニアでない"""
    birth = date(2022, 1, 1)
    today = date(2025, 2, 1)  # 3歳1ヶ月
    result = check_senior_notification(birth, dog_size='small', today=today)
    assert result['is_senior'] is False


def test_senior_approaching_notification():
    """シニア期まで6ヶ月以内→通知あり"""
    birth = date(2018, 9, 1)
    today = date(2025, 3, 1)  # 6歳6ヶ月 → あと6ヶ月でシニア
    result = check_senior_notification(birth, dog_size='small', today=today)
    assert result['notification'] is not None


def test_senior_no_birth_date():
    """誕生日不明の場合"""
    result = check_senior_notification(None)
    assert result['is_senior'] is None
    assert result['notification'] is None


# ─────────────────────────────────────────────
# 8. _evaluate_line_performance
# ─────────────────────────────────────────────

def test_line_performance_excellent():
    km = {'median_lifespan_months': 130, 'n_total': 20, 'n_events': 10, 'n_censored': 10, 'survival_curve': [], 'confidence_level': 'medium'}
    disease = {'incidence_rate_percent': 5.0}
    result = _evaluate_line_performance(km, disease, breeding_success_rate=85.0)
    assert result == 'excellent'


def test_line_performance_poor():
    km = {'median_lifespan_months': 60, 'n_total': 5, 'n_events': 5, 'n_censored': 0, 'survival_curve': [], 'confidence_level': 'low'}
    disease = {'incidence_rate_percent': 35.0}
    result = _evaluate_line_performance(km, disease, breeding_success_rate=40.0)
    assert result == 'poor'


def test_line_performance_no_data():
    """データなしの場合"""
    km = {'median_lifespan_months': None, 'n_total': 0, 'n_events': 0, 'n_censored': 0, 'survival_curve': [], 'confidence_level': 'insufficient'}
    disease = {'incidence_rate_percent': None}
    result = _evaluate_line_performance(km, disease, breeding_success_rate=None)
    assert result == 'poor'


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
