# -*- coding: utf-8 -*-
"""
生存分析エンジン（survival_analysis.py）

設計原則：
- カプランマイヤー推定は数式で厳密計算（AI推測なし）
- 欠損データ・打ち切りデータを前提とした設計
- 生存中データは「打ち切り（censored）」として扱う
- ライン別分析・疾患発生率・体重推移も提供
"""
from __future__ import annotations
import math
from datetime import date, datetime
from typing import Optional


# ─────────────────────────────────────────────
# 1. データ構造定義
# ─────────────────────────────────────────────

def make_survival_record(
    dog_id: int,
    age_months: Optional[int],
    is_deceased: bool,
    age_range: Optional[str] = None,
) -> dict:
    """
    生存分析用レコードを作成する。

    Parameters
    ----------
    dog_id : int
        犬のID
    age_months : int or None
        死亡時または現在の月齢。不明な場合は None。
    is_deceased : bool
        True = 死亡確認済み（イベント発生）
        False = 生存中（打ち切り）
    age_range : str or None
        age_months が不明な場合の年齢帯（例: '7-10歳'）。
        age_months の代替として中央値に変換する。

    Returns
    -------
    dict
        {dog_id, time_months, event, censored}
    """
    AGE_RANGE_MIDPOINTS = {
        '0-1歳': 6,
        '1-3歳': 24,
        '3-7歳': 60,
        '7-10歳': 102,
        '10歳以上': 132,
    }
    time_months = age_months
    if time_months is None and age_range:
        time_months = AGE_RANGE_MIDPOINTS.get(age_range)

    return {
        'dog_id': dog_id,
        'time_months': time_months,
        'event': 1 if is_deceased else 0,  # 1=死亡, 0=打ち切り
        'censored': not is_deceased,
    }


# ─────────────────────────────────────────────
# 2. カプランマイヤー推定
# ─────────────────────────────────────────────

def kaplan_meier_estimate(records: list[dict]) -> dict:
    """
    カプランマイヤー法で生存曲線を推定する。

    数式：
        S(t) = Π_{t_i <= t} (1 - d_i / n_i)

        d_i = 時点 t_i での死亡数
        n_i = 時点 t_i 直前のリスク集合数（生存中 + 打ち切り前）

    打ち切り処理：
        同一時点に死亡と打ち切りがある場合、死亡を先に処理する（標準的な慣習）。

    Parameters
    ----------
    records : list[dict]
        make_survival_record() で作成したレコードのリスト。
        time_months が None のレコードは除外される。

    Returns
    -------
    dict
        {
            survival_curve: [{age_months, survival_rate, n_at_risk, n_events, n_censored}],
            median_lifespan_months: int or None,
            confidence_level: str,
            n_total: int,
            n_events: int,
            n_censored: int,
        }
    """
    # None を除外
    valid = [r for r in records if r.get('time_months') is not None]
    n_total = len(valid)

    if n_total == 0:
        return {
            'survival_curve': [],
            'median_lifespan_months': None,
            'confidence_level': 'insufficient',
            'n_total': 0,
            'n_events': 0,
            'n_censored': 0,
        }

    n_events_total = sum(r['event'] for r in valid)
    n_censored_total = sum(r['censored'] for r in valid)

    # 信頼度評価
    if n_events_total < 5:
        confidence = 'very_low'
    elif n_events_total < 10:
        confidence = 'low'
    elif n_events_total < 30:
        confidence = 'medium'
    else:
        confidence = 'high'

    # 時点ごとに集計（死亡を打ち切りより先に処理）
    # sort key: (time_months, event DESC) → 死亡(event=1)が打ち切り(event=0)より先
    sorted_records = sorted(valid, key=lambda r: (r['time_months'], -r['event']))

    # ユニーク死亡時点を取得
    death_times = sorted(set(r['time_months'] for r in sorted_records if r['event'] == 1))

    survival_rate = 1.0
    n_at_risk = n_total
    cursor = 0
    curve = []

    for t in death_times:
        # この時点より前の打ち切りを処理してリスク集合を更新
        while cursor < len(sorted_records) and sorted_records[cursor]['time_months'] < t:
            n_at_risk -= 1
            cursor += 1

        # この時点での死亡数を数える
        d = sum(1 for r in sorted_records if r['time_months'] == t and r['event'] == 1)
        c = sum(1 for r in sorted_records if r['time_months'] == t and r['event'] == 0)

        if n_at_risk > 0:
            survival_rate = survival_rate * (1.0 - d / n_at_risk)

        curve.append({
            'age_months': t,
            'survival_rate': round(survival_rate, 6),
            'n_at_risk': n_at_risk,
            'n_events': d,
            'n_censored': c,
        })

        # この時点の死亡・打ち切りを処理
        n_at_risk -= (d + c)
        cursor += (d + c)

    # 中央生存期間（S(t) <= 0.5 になる最初の時点）
    median_lifespan = None
    for point in curve:
        if point['survival_rate'] <= 0.5:
            median_lifespan = point['age_months']
            break

    return {
        'survival_curve': curve,
        'median_lifespan_months': median_lifespan,
        'confidence_level': confidence,
        'n_total': n_total,
        'n_events': n_events_total,
        'n_censored': n_censored_total,
    }


# ─────────────────────────────────────────────
# 3. グリーンウッドの公式（信頼区間）
# ─────────────────────────────────────────────

def greenwood_confidence_interval(
    survival_curve: list[dict],
    alpha: float = 0.05,
) -> list[dict]:
    """
    グリーンウッドの公式で95%信頼区間を計算する。

    数式：
        Var[S(t)] = S(t)^2 × Σ_{t_i <= t} d_i / (n_i × (n_i - d_i))
        CI = S(t) ± z_{alpha/2} × sqrt(Var[S(t)])

    Parameters
    ----------
    survival_curve : list[dict]
        kaplan_meier_estimate() の survival_curve
    alpha : float
        有意水準（デフォルト 0.05 → 95%CI）

    Returns
    -------
    list[dict]
        各時点に ci_lower, ci_upper を追加したリスト
    """
    # z_{0.025} ≈ 1.96
    z = 1.96 if alpha == 0.05 else 1.645

    cumulative_variance_term = 0.0
    result = []

    for point in survival_curve:
        s = point['survival_rate']
        d = point['n_events']
        n = point['n_at_risk']

        if n > d and n > 0:
            cumulative_variance_term += d / (n * (n - d))

        variance = (s ** 2) * cumulative_variance_term
        se = math.sqrt(variance) if variance > 0 else 0.0

        ci_lower = max(0.0, round(s - z * se, 6))
        ci_upper = min(1.0, round(s + z * se, 6))

        result.append({**point, 'ci_lower': ci_lower, 'ci_upper': ci_upper})

    return result


# ─────────────────────────────────────────────
# 4. 疾患発生率計算
# ─────────────────────────────────────────────

def calculate_disease_incidence(
    medical_events: list[dict],
    total_dogs: int,
    disease_name: Optional[str] = None,
) -> dict:
    """
    疾患発生率を計算する。

    Parameters
    ----------
    medical_events : list[dict]
        {dog_id, title, category, severity} のリスト
    total_dogs : int
        対象犬の総数
    disease_name : str or None
        特定疾患名でフィルタ。None の場合は全疾患を集計。

    Returns
    -------
    dict
        {disease_name, affected_count, total_dogs, incidence_rate_percent, severity_breakdown}
    """
    if total_dogs == 0:
        return {
            'disease_name': disease_name or 'all',
            'affected_count': 0,
            'total_dogs': 0,
            'incidence_rate_percent': None,
            'severity_breakdown': {},
        }

    if disease_name:
        filtered = [e for e in medical_events
                    if disease_name.lower() in e.get('title', '').lower()]
    else:
        filtered = medical_events

    affected_dog_ids = set(e['dog_id'] for e in filtered)
    affected_count = len(affected_dog_ids)

    severity_breakdown = {}
    for e in filtered:
        sev = e.get('severity', 'unknown') or 'unknown'
        severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1

    return {
        'disease_name': disease_name or 'all',
        'affected_count': affected_count,
        'total_dogs': total_dogs,
        'incidence_rate_percent': round(affected_count / total_dogs * 100, 2),
        'severity_breakdown': severity_breakdown,
    }


# ─────────────────────────────────────────────
# 5. ライン別分析
# ─────────────────────────────────────────────

def analyze_line_performance(
    ancestor_id: int,
    ancestor_name: str,
    descendant_records: list[dict],
    medical_events: list[dict],
    breeding_results: list[dict],
) -> dict:
    """
    特定祖先ラインの総合パフォーマンス分析。

    Parameters
    ----------
    ancestor_id : int
        分析対象の祖先犬ID
    ancestor_name : str
        祖先犬名
    descendant_records : list[dict]
        make_survival_record() で作成した子孫の生存レコードリスト
    medical_events : list[dict]
        子孫の医療イベントリスト {dog_id, title, category, severity}
    breeding_results : list[dict]
        繁殖結果リスト {litter_id, puppy_count, survival_count, health_issues}

    Returns
    -------
    dict
        ライン別分析結果
    """
    n_descendants = len(descendant_records)

    # 生存分析
    km_result = kaplan_meier_estimate(descendant_records)

    # 平均寿命（死亡確認済みのみ）
    deceased = [r for r in descendant_records
                if r.get('event') == 1 and r.get('time_months') is not None]
    avg_lifespan_months = None
    if deceased:
        avg_lifespan_months = round(sum(r['time_months'] for r in deceased) / len(deceased), 1)

    # 疾患発生率
    disease_incidence = calculate_disease_incidence(medical_events, n_descendants)

    # 繁殖成功率
    total_litters = len(breeding_results)
    successful_litters = sum(1 for b in breeding_results
                              if b.get('survival_count', 0) > 0)
    breeding_success_rate = None
    if total_litters > 0:
        breeding_success_rate = round(successful_litters / total_litters * 100, 1)

    # パフォーマンス評価
    performance = _evaluate_line_performance(
        km_result, disease_incidence, breeding_success_rate
    )

    return {
        'ancestor_id': ancestor_id,
        'ancestor_name': ancestor_name,
        'n_descendants': n_descendants,
        'survival_analysis': km_result,
        'average_lifespan_months': avg_lifespan_months,
        'average_lifespan_years': round(avg_lifespan_months / 12, 1) if avg_lifespan_months else None,
        'disease_incidence': disease_incidence,
        'breeding_success_rate': breeding_success_rate,
        'total_litters': total_litters,
        'performance': performance,
    }


def _evaluate_line_performance(
    km_result: dict,
    disease_incidence: dict,
    breeding_success_rate: Optional[float],
) -> str:
    """
    ライン総合パフォーマンスを評価する（excellent/good/fair/poor）。

    評価基準：
    - 中央生存期間 >= 120ヶ月（10年）: +2点
    - 中央生存期間 >= 96ヶ月（8年）: +1点
    - 疾患発生率 < 10%: +2点
    - 疾患発生率 < 20%: +1点
    - 繁殖成功率 >= 80%: +2点
    - 繁殖成功率 >= 60%: +1点
    """
    score = 0

    median = km_result.get('median_lifespan_months')
    if median is not None:
        if median >= 120:
            score += 2
        elif median >= 96:
            score += 1

    disease_rate = disease_incidence.get('incidence_rate_percent')
    if disease_rate is not None:
        if disease_rate < 10:
            score += 2
        elif disease_rate < 20:
            score += 1

    if breeding_success_rate is not None:
        if breeding_success_rate >= 80:
            score += 2
        elif breeding_success_rate >= 60:
            score += 1

    if score >= 5:
        return 'excellent'
    elif score >= 3:
        return 'good'
    elif score >= 1:
        return 'fair'
    else:
        return 'poor'


# ─────────────────────────────────────────────
# 6. 体重推移・成長曲線
# ─────────────────────────────────────────────

def analyze_weight_trend(
    health_logs: list[dict],
    breed_avg_weight: Optional[float] = None,
) -> dict:
    """
    体重推移を分析する。

    Parameters
    ----------
    health_logs : list[dict]
        {log_date, weight} のリスト（weight は float or None）
    breed_avg_weight : float or None
        犬種の平均体重（kg）。比較用。

    Returns
    -------
    dict
        {trend, current_weight, min_weight, max_weight, avg_weight,
         vs_breed_avg_percent, data_points}
    """
    valid_logs = [
        {'date': l['log_date'], 'weight': float(l['weight'])}
        for l in health_logs
        if l.get('weight') is not None
    ]

    if not valid_logs:
        return {
            'trend': 'unknown',
            'current_weight': None,
            'min_weight': None,
            'max_weight': None,
            'avg_weight': None,
            'vs_breed_avg_percent': None,
            'data_points': [],
        }

    # 日付順にソート
    valid_logs.sort(key=lambda x: x['date'])

    weights = [l['weight'] for l in valid_logs]
    current = weights[-1]
    min_w = min(weights)
    max_w = max(weights)
    avg_w = round(sum(weights) / len(weights), 2)

    # トレンド判定（最初と最後の3点平均で比較）
    trend = 'stable'
    if len(weights) >= 4:
        first_avg = sum(weights[:2]) / 2
        last_avg = sum(weights[-2:]) / 2
        diff_pct = (last_avg - first_avg) / first_avg * 100 if first_avg > 0 else 0
        if diff_pct > 5:
            trend = 'increasing'
        elif diff_pct < -5:
            trend = 'decreasing'

    vs_breed = None
    if breed_avg_weight and breed_avg_weight > 0:
        vs_breed = round((current - breed_avg_weight) / breed_avg_weight * 100, 1)

    return {
        'trend': trend,
        'current_weight': current,
        'min_weight': min_w,
        'max_weight': max_w,
        'avg_weight': avg_w,
        'vs_breed_avg_percent': vs_breed,
        'data_points': [{'date': str(l['date']), 'weight': l['weight']} for l in valid_logs],
    }


# ─────────────────────────────────────────────
# 7. 犬種別統計比較
# ─────────────────────────────────────────────

def compare_breed_statistics(
    breed_name: str,
    individual_records: list[dict],
    breed_population_records: list[dict],
) -> dict:
    """
    個体データを犬種全体統計と比較する。

    Parameters
    ----------
    breed_name : str
        犬種名
    individual_records : list[dict]
        対象個体の生存レコード
    breed_population_records : list[dict]
        犬種全体の生存レコード

    Returns
    -------
    dict
        比較結果
    """
    individual_km = kaplan_meier_estimate(individual_records)
    breed_km = kaplan_meier_estimate(breed_population_records)

    individual_median = individual_km.get('median_lifespan_months')
    breed_median = breed_km.get('median_lifespan_months')

    comparison = 'unknown'
    if individual_median is not None and breed_median is not None and breed_median > 0:
        diff_pct = (individual_median - breed_median) / breed_median * 100
        if diff_pct > 10:
            comparison = 'above_average'
        elif diff_pct < -10:
            comparison = 'below_average'
        else:
            comparison = 'average'

    return {
        'breed_name': breed_name,
        'individual_median_months': individual_median,
        'breed_median_months': breed_median,
        'comparison': comparison,
        'individual_km': individual_km,
        'breed_km': breed_km,
    }


# ─────────────────────────────────────────────
# 8. 繁殖評価へのフィードバック統合
# ─────────────────────────────────────────────

def build_breeding_feedback(
    sire_id: int,
    dam_id: int,
    sire_line_analysis: Optional[dict],
    dam_line_analysis: Optional[dict],
    past_combination_records: list[dict],
    disease_incidence: Optional[dict],
) -> dict:
    """
    実データを繁殖評価にフィードバックする。

    理論値（COI）＋実データ（結果）を統合して
    「この交配は実際にどうなるか」の予測材料を提供する。

    Parameters
    ----------
    sire_id : int
        父犬ID
    dam_id : int
        母犬ID
    sire_line_analysis : dict or None
        父犬ラインの分析結果（analyze_line_performance の出力）
    dam_line_analysis : dict or None
        母犬ラインの分析結果
    past_combination_records : list[dict]
        同じ組み合わせの過去産子の生存レコード
    disease_incidence : dict or None
        この組み合わせの疾患発生率

    Returns
    -------
    dict
        フィードバックデータ（繁殖評価に追加する形式）
    """
    feedback = {
        'sire_id': sire_id,
        'dam_id': dam_id,
        'has_real_data': False,
        'past_combination': None,
        'sire_line': None,
        'dam_line': None,
        'disease_feedback': None,
        'summary_points': [],
        'data_quality': 'insufficient',
    }

    data_points = 0

    # 過去の同組み合わせ実績
    if past_combination_records:
        past_km = kaplan_meier_estimate(past_combination_records)
        feedback['past_combination'] = {
            'n_offspring': len(past_combination_records),
            'km_result': past_km,
        }
        if past_km['n_events'] > 0:
            feedback['summary_points'].append(
                f"この組み合わせの過去産子{len(past_combination_records)}頭のデータあり"
            )
        data_points += len(past_combination_records)

    # 父犬ラインのフィードバック
    if sire_line_analysis:
        feedback['sire_line'] = {
            'performance': sire_line_analysis.get('performance'),
            'average_lifespan_years': sire_line_analysis.get('average_lifespan_years'),
            'disease_incidence_rate': sire_line_analysis.get('disease_incidence', {}).get(
                'incidence_rate_percent'
            ),
        }
        perf = sire_line_analysis.get('performance', 'unknown')
        feedback['summary_points'].append(f"父犬ラインのパフォーマンス: {perf}")
        data_points += sire_line_analysis.get('n_descendants', 0)

    # 母犬ラインのフィードバック
    if dam_line_analysis:
        feedback['dam_line'] = {
            'performance': dam_line_analysis.get('performance'),
            'average_lifespan_years': dam_line_analysis.get('average_lifespan_years'),
            'disease_incidence_rate': dam_line_analysis.get('disease_incidence', {}).get(
                'incidence_rate_percent'
            ),
        }
        perf = dam_line_analysis.get('performance', 'unknown')
        feedback['summary_points'].append(f"母犬ラインのパフォーマンス: {perf}")
        data_points += dam_line_analysis.get('n_descendants', 0)

    # 疾患フィードバック
    if disease_incidence:
        rate = disease_incidence.get('incidence_rate_percent')
        if rate is not None:
            feedback['disease_feedback'] = disease_incidence
            if rate > 20:
                feedback['summary_points'].append(
                    f"このラインの疾患発生率は{rate}%と高めです"
                )
            elif rate < 5:
                feedback['summary_points'].append(
                    f"このラインの疾患発生率は{rate}%と低い水準です"
                )

    # データ品質評価
    if data_points >= 30:
        feedback['data_quality'] = 'high'
    elif data_points >= 10:
        feedback['data_quality'] = 'medium'
    elif data_points >= 3:
        feedback['data_quality'] = 'low'
    else:
        feedback['data_quality'] = 'insufficient'

    feedback['has_real_data'] = data_points > 0

    return feedback


# ─────────────────────────────────────────────
# 9. ワクチン・予防アラート生成
# ─────────────────────────────────────────────

def generate_vaccine_alerts(
    vaccine_schedules: list[dict],
    today: Optional[date] = None,
    alert_days_before: int = 30,
) -> list[dict]:
    """
    ワクチン・予防薬の期限アラートを生成する。

    Parameters
    ----------
    vaccine_schedules : list[dict]
        {id, vaccine_type, scheduled_date, is_completed} のリスト
    today : date or None
        基準日（None の場合は今日）
    alert_days_before : int
        何日前からアラートを出すか（デフォルト30日）

    Returns
    -------
    list[dict]
        アラートリスト [{id, vaccine_type, scheduled_date, days_until, urgency}]
    """
    if today is None:
        today = date.today()

    alerts = []
    for s in vaccine_schedules:
        if s.get('is_completed'):
            continue
        scheduled = s.get('scheduled_date')
        if scheduled is None:
            continue
        if isinstance(scheduled, str):
            scheduled = date.fromisoformat(scheduled)

        days_until = (scheduled - today).days

        if days_until < 0:
            urgency = 'overdue'
        elif days_until <= 7:
            urgency = 'urgent'
        elif days_until <= alert_days_before:
            urgency = 'upcoming'
        else:
            continue  # アラート不要

        alerts.append({
            'id': s.get('id'),
            'vaccine_type': s.get('vaccine_type'),
            'scheduled_date': str(scheduled),
            'days_until': days_until,
            'urgency': urgency,
        })

    # 緊急度順にソート
    urgency_order = {'overdue': 0, 'urgent': 1, 'upcoming': 2}
    alerts.sort(key=lambda a: (urgency_order.get(a['urgency'], 9), a['days_until']))

    return alerts


# ─────────────────────────────────────────────
# 10. シニア期通知
# ─────────────────────────────────────────────

SENIOR_AGE_MONTHS_BY_SIZE = {
    'small': 84,    # 小型犬: 7歳
    'medium': 84,   # 中型犬: 7歳
    'large': 72,    # 大型犬: 6歳
    'giant': 60,    # 超大型犬: 5歳
    'unknown': 84,  # 不明: 7歳
}


def check_senior_notification(
    birth_date: Optional[date],
    dog_size: str = 'unknown',
    today: Optional[date] = None,
) -> dict:
    """
    シニア期に入っているか・近づいているかを通知する。

    Parameters
    ----------
    birth_date : date or None
        誕生日
    dog_size : str
        犬のサイズ（small/medium/large/giant/unknown）
    today : date or None
        基準日

    Returns
    -------
    dict
        {is_senior, age_months, senior_threshold_months, months_until_senior, notification}
    """
    if today is None:
        today = date.today()

    if birth_date is None:
        return {
            'is_senior': None,
            'age_months': None,
            'senior_threshold_months': SENIOR_AGE_MONTHS_BY_SIZE.get(dog_size, 84),
            'months_until_senior': None,
            'notification': None,
        }

    age_months = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)
    threshold = SENIOR_AGE_MONTHS_BY_SIZE.get(dog_size, 84)
    is_senior = age_months >= threshold
    months_until = max(0, threshold - age_months)

    if is_senior:
        notification = f'シニア期です（{age_months // 12}歳{age_months % 12}ヶ月）。定期健診を推奨します。'
    elif months_until <= 6:
        notification = f'あと{months_until}ヶ月でシニア期に入ります。健康管理を強化しましょう。'
    else:
        notification = None

    return {
        'is_senior': is_senior,
        'age_months': age_months,
        'senior_threshold_months': threshold,
        'months_until_senior': months_until,
        'notification': notification,
    }
