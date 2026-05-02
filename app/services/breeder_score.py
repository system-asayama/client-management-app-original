"""
breeder_score.py
ブリーダー評価スコア計算ロジック

スコア構成（合計100点）:
  - 平均COI          : 25点  （低いほど高得点）
  - 産子生存率        : 20点  （高いほど高得点）
  - 疾患発生率        : 20点  （低いほど高得点）
  - 繁殖成功率        : 15点  （高いほど高得点）
  - データ登録率      : 10点  （高いほど高得点）
  - 飼い主継続率      : 10点  （高いほど高得点）

ランク:
  S: 90-100
  A: 75-89
  B: 60-74
  C: 40-59
  D: 0-39
"""

from __future__ import annotations
from typing import Optional


# ─────────────────────────────────────────────
# スコア計算ヘルパー
# ─────────────────────────────────────────────

def _score_avg_coi(avg_coi_pct: Optional[float]) -> float:
    """
    平均COI（%）から25点満点のスコアを計算する。
    COIが低いほど高得点。
    0%   → 25点
    5%   → 20点
    10%  → 12点
    15%  → 5点
    25%以上 → 0点
    """
    if avg_coi_pct is None:
        return 12.5  # データなし → 中間点

    coi = max(0.0, float(avg_coi_pct))
    if coi <= 0:
        return 25.0
    elif coi <= 5:
        return 25.0 - (coi / 5.0) * 5.0      # 25 → 20
    elif coi <= 10:
        return 20.0 - ((coi - 5) / 5.0) * 8.0  # 20 → 12
    elif coi <= 15:
        return 12.0 - ((coi - 10) / 5.0) * 7.0  # 12 → 5
    elif coi <= 25:
        return 5.0 - ((coi - 15) / 10.0) * 5.0  # 5 → 0
    else:
        return 0.0


def _score_puppy_survival(survival_rate_pct: Optional[float]) -> float:
    """
    産子生存率（%）から20点満点のスコアを計算する。
    100% → 20点、0% → 0点（線形）
    """
    if survival_rate_pct is None:
        return 10.0  # データなし → 中間点
    rate = max(0.0, min(100.0, float(survival_rate_pct)))
    return (rate / 100.0) * 20.0


def _score_disease_incidence(incidence_rate_pct: Optional[float]) -> float:
    """
    疾患発生率（%）から20点満点のスコアを計算する。
    0%   → 20点
    10%  → 15点
    25%  → 8点
    50%以上 → 0点
    """
    if incidence_rate_pct is None:
        return 10.0  # データなし → 中間点

    rate = max(0.0, float(incidence_rate_pct))
    if rate <= 0:
        return 20.0
    elif rate <= 10:
        return 20.0 - (rate / 10.0) * 5.0   # 20 → 15
    elif rate <= 25:
        return 15.0 - ((rate - 10) / 15.0) * 7.0  # 15 → 8
    elif rate <= 50:
        return 8.0 - ((rate - 25) / 25.0) * 8.0   # 8 → 0
    else:
        return 0.0


def _score_breeding_success(success_rate_pct: Optional[float]) -> float:
    """
    繁殖成功率（%）から15点満点のスコアを計算する。
    100% → 15点、0% → 0点（線形）
    """
    if success_rate_pct is None:
        return 7.5  # データなし → 中間点
    rate = max(0.0, min(100.0, float(success_rate_pct)))
    return (rate / 100.0) * 15.0


def _score_data_completeness(completeness_rate_pct: Optional[float]) -> float:
    """
    データ登録率（%）から10点満点のスコアを計算する。
    100% → 10点、0% → 0点（線形）
    """
    if completeness_rate_pct is None:
        return 0.0  # データなし → 0点（入力促進）
    rate = max(0.0, min(100.0, float(completeness_rate_pct)))
    return (rate / 100.0) * 10.0


def _score_owner_retention(retention_rate_pct: Optional[float]) -> float:
    """
    飼い主継続率（%）から10点満点のスコアを計算する。
    100% → 10点、0% → 0点（線形）
    """
    if retention_rate_pct is None:
        return 5.0  # データなし → 中間点
    rate = max(0.0, min(100.0, float(retention_rate_pct)))
    return (rate / 100.0) * 10.0


def get_rank(total_score: int) -> str:
    """総合スコアからランクを返す"""
    if total_score >= 90:
        return 'S'
    elif total_score >= 75:
        return 'A'
    elif total_score >= 60:
        return 'B'
    elif total_score >= 40:
        return 'C'
    else:
        return 'D'


# ─────────────────────────────────────────────
# メイン計算関数
# ─────────────────────────────────────────────

def calculate_breeder_score(
    avg_coi: Optional[float] = None,
    puppy_survival_rate: Optional[float] = None,
    disease_incidence_rate: Optional[float] = None,
    breeding_success_rate: Optional[float] = None,
    data_completeness_rate: Optional[float] = None,
    owner_retention_rate: Optional[float] = None,
) -> dict:
    """
    ブリーダー評価スコアを計算して返す。

    Parameters
    ----------
    avg_coi : float | None
        平均COI（%）
    puppy_survival_rate : float | None
        産子生存率（%）
    disease_incidence_rate : float | None
        疾患発生率（%）
    breeding_success_rate : float | None
        繁殖成功率（%）
    data_completeness_rate : float | None
        データ登録率（%）
    owner_retention_rate : float | None
        飼い主継続率（%）

    Returns
    -------
    dict
        {
          "total_score": int,
          "rank": str,
          "breakdown": {...},
          "strengths": [...],
          "weaknesses": [...],
          "improvement_tips": [...]
        }
    """
    # 各指標のスコア計算
    s_coi = _score_avg_coi(avg_coi)
    s_survival = _score_puppy_survival(puppy_survival_rate)
    s_disease = _score_disease_incidence(disease_incidence_rate)
    s_success = _score_breeding_success(breeding_success_rate)
    s_data = _score_data_completeness(data_completeness_rate)
    s_retention = _score_owner_retention(owner_retention_rate)

    total = s_coi + s_survival + s_disease + s_success + s_data + s_retention
    total_int = max(0, min(100, round(total)))
    rank = get_rank(total_int)

    breakdown = {
        'avg_coi':               {'score': round(s_coi, 1),      'max': 25, 'value': avg_coi},
        'puppy_survival_rate':   {'score': round(s_survival, 1), 'max': 20, 'value': puppy_survival_rate},
        'disease_incidence_rate':{'score': round(s_disease, 1),  'max': 20, 'value': disease_incidence_rate},
        'breeding_success_rate': {'score': round(s_success, 1),  'max': 15, 'value': breeding_success_rate},
        'data_completeness_rate':{'score': round(s_data, 1),     'max': 10, 'value': data_completeness_rate},
        'owner_retention_rate':  {'score': round(s_retention, 1),'max': 10, 'value': owner_retention_rate},
    }

    strengths, weaknesses, tips = _analyze_strengths_weaknesses(
        avg_coi, puppy_survival_rate, disease_incidence_rate,
        breeding_success_rate, data_completeness_rate, owner_retention_rate,
        s_coi, s_survival, s_disease, s_success, s_data, s_retention
    )

    return {
        'total_score': total_int,
        'rank': rank,
        'breakdown': breakdown,
        'strengths': strengths,
        'weaknesses': weaknesses,
        'improvement_tips': tips,
    }


def _analyze_strengths_weaknesses(
    avg_coi, puppy_survival_rate, disease_incidence_rate,
    breeding_success_rate, data_completeness_rate, owner_retention_rate,
    s_coi, s_survival, s_disease, s_success, s_data, s_retention
) -> tuple[list, list, list]:
    """強み・弱み・改善提案を分析する"""
    strengths = []
    weaknesses = []
    tips = []

    # COI評価
    if avg_coi is not None:
        if avg_coi <= 3.0:
            strengths.append('低COI（近親交配リスクが非常に低い）')
        elif avg_coi <= 6.25:
            strengths.append('COIが適正範囲内')
        elif avg_coi >= 12.5:
            weaknesses.append('高COI（近親交配リスクが高い）')
            tips.append('COI 6.25%以下を目標に、血縁の遠い交配相手を選択してください')
    else:
        tips.append('血統情報を登録してCOI分析を有効化してください')

    # 産子生存率
    if puppy_survival_rate is not None:
        if puppy_survival_rate >= 95:
            strengths.append('高い産子生存率')
        elif puppy_survival_rate < 80:
            weaknesses.append('産子生存率が低い')
            tips.append('出産後の健康管理・体重記録を徹底してください')
    else:
        tips.append('産子記録を登録して生存率分析を有効化してください')

    # 疾患発生率
    if disease_incidence_rate is not None:
        if disease_incidence_rate <= 5:
            strengths.append('疾患発生率が低い')
        elif disease_incidence_rate >= 20:
            weaknesses.append('疾患発生率が高い')
            tips.append('遺伝疾患検査を実施し、キャリア同士の交配を避けてください')
    else:
        tips.append('遺伝疾患検査結果を登録して疾患リスク分析を有効化してください')

    # 繁殖成功率
    if breeding_success_rate is not None:
        if breeding_success_rate >= 80:
            strengths.append('高い繁殖成功率')
        elif breeding_success_rate < 50:
            weaknesses.append('繁殖成功率が低い')
            tips.append('交配タイミングの記録・ホルモン検査の活用を検討してください')
    else:
        tips.append('交配記録を登録して繁殖成功率を計測してください')

    # データ登録率
    if data_completeness_rate is not None:
        if data_completeness_rate >= 90:
            strengths.append('データ登録率が高い（分析精度が高い）')
        elif data_completeness_rate < 50:
            weaknesses.append('データ登録率が低い（分析精度が低下）')
            tips.append('犬の基本情報・健康記録を定期的に更新してください')
    else:
        weaknesses.append('データ登録が不足しています')
        tips.append('犬の基本情報・血統・健康記録を登録してください')

    # 飼い主継続率
    if owner_retention_rate is not None:
        if owner_retention_rate >= 80:
            strengths.append('飼い主との継続的な関係構築ができている')
        elif owner_retention_rate < 40:
            weaknesses.append('飼い主の継続率が低い')
            tips.append('飼い主アプリへの招待・健康アラートの活用で関係を維持してください')

    return strengths[:5], weaknesses[:5], tips[:5]


# ─────────────────────────────────────────────
# データ収集ヘルパー（DBから指標を計算）
# ─────────────────────────────────────────────

def collect_metrics_from_db(db, tenant_id: int) -> dict:
    """
    DBからブリーダーの各指標を収集して返す。
    実際のDBクエリはここに集約する。

    Returns
    -------
    dict : calculate_breeder_score() に渡す引数辞書
    """
    from sqlalchemy import text

    metrics = {
        'avg_coi': None,
        'puppy_survival_rate': None,
        'disease_incidence_rate': None,
        'breeding_success_rate': None,
        'data_completeness_rate': None,
        'owner_retention_rate': None,
    }

    try:
        # 平均COI: mating_evaluationsテーブルから取得
        row = db.execute(text(
            "SELECT AVG(coi_percent) FROM mating_evaluations WHERE tenant_id = :tid AND coi_percent IS NOT NULL"
        ), {'tid': tenant_id}).fetchone()
        if row and row[0] is not None:
            metrics['avg_coi'] = float(row[0])
    except Exception:
        pass

    try:
        # 産子生存率: puppy_recordsテーブルから計算
        row = db.execute(text(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN survival_status = 'alive' THEN 1 ELSE 0 END) as alive
            FROM puppy_records
            WHERE tenant_id = :tid
            """
        ), {'tid': tenant_id}).fetchone()
        if row and row[0] and row[0] > 0:
            metrics['puppy_survival_rate'] = float(row[1] or 0) / float(row[0]) * 100
    except Exception:
        pass

    try:
        # 繁殖成功率: breeding_historiesテーブルから計算
        row = db.execute(text(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result = 'success' THEN 1 ELSE 0 END) as success
            FROM breeding_histories
            WHERE tenant_id = :tid
            """
        ), {'tid': tenant_id}).fetchone()
        if row and row[0] and row[0] > 0:
            metrics['breeding_success_rate'] = float(row[1] or 0) / float(row[0]) * 100
    except Exception:
        pass

    try:
        # データ登録率: dogsテーブルの必須フィールド充足率
        row = db.execute(text(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN birth_date IS NOT NULL AND father_id IS NOT NULL AND mother_id IS NOT NULL THEN 1 ELSE 0 END) as complete
            FROM dogs
            WHERE tenant_id = :tid AND is_deleted = 0
            """
        ), {'tid': tenant_id}).fetchone()
        if row and row[0] and row[0] > 0:
            metrics['data_completeness_rate'] = float(row[1] or 0) / float(row[0]) * 100
    except Exception:
        pass

    try:
        # 飼い主継続率: owner_dogsテーブルのアクティブ率
        row = db.execute(text(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN share_health_data = 1 OR share_followup_data = 1 THEN 1 ELSE 0 END) as active
            FROM owner_dogs od
            JOIN owners o ON od.owner_id = o.id
            WHERE o.breeder_tenant_id = :tid
            """
        ), {'tid': tenant_id}).fetchone()
        if row and row[0] and row[0] > 0:
            metrics['owner_retention_rate'] = float(row[1] or 0) / float(row[0]) * 100
    except Exception:
        pass

    return metrics


def calculate_and_save_breeder_score(db, tenant_id: int) -> dict:
    """
    DBから指標を収集してスコアを計算し、breeder_scoresテーブルに保存する。
    """
    from app.models_breeder import BreederScore

    metrics = collect_metrics_from_db(db, tenant_id)
    result = calculate_breeder_score(**metrics)

    score_record = BreederScore(
        tenant_id=tenant_id,
        total_score=result['total_score'],
        rank=result['rank'],
        avg_coi=metrics['avg_coi'],
        puppy_survival_rate=metrics['puppy_survival_rate'],
        disease_incidence_rate=metrics['disease_incidence_rate'],
        breeding_success_rate=metrics['breeding_success_rate'],
        data_completeness_rate=metrics['data_completeness_rate'],
        owner_retention_rate=metrics['owner_retention_rate'],
        strengths=result['strengths'],
        weaknesses=result['weaknesses'],
        improvement_tips=result['improvement_tips'],
    )
    db.add(score_record)
    db.commit()

    return result
