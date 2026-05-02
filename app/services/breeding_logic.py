# -*- coding: utf-8 -*-
"""
breeding_logic.py
=================
ブリーダー向け交配相性評価ロジック。

【設計方針】
- COI（近交係数）はライトの公式を用いた数式で厳密計算する。AIによる推測は一切行わない。
- AIは自然文コメント生成にのみ使用する（generate_ai_comment 関数）。
- 計算過程（経路・寄与率・数式）を JSON に保持し、画面に根拠を表示できるようにする。
- 将来、犬以外の動物種にも応用できるよう、データアクセスを抽象化する。

【ライトの近交係数（Wright's Coefficient of Inbreeding）】
  F_X = Σ_A Σ_{p in paths(A)} (1/2)^(n1_p + n2_p + 1) × (1 + F_A)

  - A   : 共通祖先
  - n1  : 父犬側から祖先 A までの世代数
  - n2  : 母犬側から祖先 A までの世代数
  - F_A : 祖先 A 自身の近交係数（再帰的に計算）
  - 同じ祖先が複数経路で出現する場合、全経路を合算する
"""

from __future__ import annotations
from collections import defaultdict
from typing import Any

# ---------------------------------------------------------------------------
# 0. DB ヘルパー（テスト時にモンキーパッチ可能）
# ---------------------------------------------------------------------------

def _get_dog_name(dog_id: int, db) -> str:
    """dog_id から犬名を取得する。テスト時にモンキーパッチ可能。"""
    try:
        from app.models_breeder import Dog
        dog = db.query(Dog).filter(Dog.id == dog_id).first()
        return dog.name if dog else f'ID:{dog_id}'
    except Exception:
        return f'ID:{dog_id}'


# ---------------------------------------------------------------------------
# 1. 祖先取得
# ---------------------------------------------------------------------------

def get_ancestors(dog_id: int | None, max_depth: int, db) -> dict[int, list[int]]:
    """
    指定した犬の祖先を取得する。

    Parameters
    ----------
    dog_id    : 起点となる犬の ID
    max_depth : 探索する最大世代数（1 = 親、2 = 祖父母、…）
    db        : SQLAlchemy セッション

    Returns
    -------
    dict[ancestor_id, list[generation_distance]]
        同じ祖先が複数経路で出現する場合、世代数リストに複数の値が入る。
        例: {101: [2, 3], 202: [3]}
    """
    memo: dict[int, list[int]] = {}
    _collect_ancestors(dog_id, max_depth, memo, db)
    return memo


def _collect_ancestors(
    dog_id: int | None,
    remaining: int,
    memo: dict[int, list[int]],
    db,
) -> None:
    """再帰的に祖先を収集する内部関数。"""
    if dog_id is None or remaining <= 0:
        return

    # 同じ祖先が複数経路で出現する場合、全経路を記録する
    gen_distance = memo.get(dog_id)
    current_gen = memo.get("_depth_" + str(dog_id), [])  # 使わない、下で計算
    # remaining を世代距離に変換するため、呼び出し元で管理する
    # ここでは「残り世代数」ではなく「現在の世代距離」を渡す方式に変更
    # → _collect_ancestors_v2 を使う
    pass


def get_ancestors(dog_id: int | None, max_depth: int, db) -> dict[int, list[int]]:
    """
    指定した犬の祖先を取得する（世代距離付き）。

    Returns
    -------
    dict[ancestor_id, list[int]]
        ancestor_id -> [gen_distance, gen_distance, ...]
        gen_distance = 1 なら親、2 なら祖父母、…
    """
    result: dict[int, list[int]] = defaultdict(list)
    _walk(dog_id, 0, max_depth, result, db, visited=set())
    return dict(result)


def _walk(
    dog_id: int | None,
    depth: int,
    max_depth: int,
    result: dict[int, list[int]],
    db,
    visited: set,
) -> None:
    """
    DFS で祖先を辿る。

    depth=0 は起点（自分自身）なので result に追加しない。
    depth=1 が親、depth=2 が祖父母、…
    """
    if dog_id is None or depth > max_depth:
        return

    if depth > 0:
        result[dog_id].append(depth)

    # 無限ループ防止：同じノードを同じ深さで再訪しない
    key = (dog_id, depth)
    if key in visited:
        return
    visited.add(key)

    from app.models_breeder import Dog
    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if dog is None:
        return

    _walk(dog.father_id, depth + 1, max_depth, result, db, visited)
    _walk(dog.mother_id, depth + 1, max_depth, result, db, visited)


# ---------------------------------------------------------------------------
# 2. 共通祖先の抽出
# ---------------------------------------------------------------------------

def find_common_ancestors(
    sire_id: int,
    dam_id: int,
    max_depth: int,
    db,
) -> dict[int, dict]:
    """
    父犬・母犬の共通祖先を抽出する。

    Returns
    -------
    dict[ancestor_id, {
        'sire_gens': [int, ...],   # 父犬側からの世代距離リスト
        'dam_gens':  [int, ...],   # 母犬側からの世代距離リスト
    }]
    """
    sire_anc = get_ancestors(sire_id, max_depth, db)
    dam_anc  = get_ancestors(dam_id,  max_depth, db)

    common: dict[int, dict] = {}
    for anc_id in set(sire_anc.keys()) & set(dam_anc.keys()):
        common[anc_id] = {
            'sire_gens': sire_anc[anc_id],
            'dam_gens':  dam_anc[anc_id],
        }
    return common


# ---------------------------------------------------------------------------
# 3. 共通祖先自身の近交係数（F_A）を計算
# ---------------------------------------------------------------------------

def calculate_ancestor_inbreeding(
    dog_id: int | None,
    max_depth: int,
    db,
    _cache: dict | None = None,
) -> float:
    """
    共通祖先 A 自身の近交係数 F_A を計算する。
    その犬の父母から再帰的に calculate_coi を呼び出す。

    Returns
    -------
    float : 近交係数（0.0 〜 1.0 の小数）
    """
    if dog_id is None:
        return 0.0
    if _cache is None:
        _cache = {}
    if dog_id in _cache:
        return _cache[dog_id]

    from app.models_breeder import Dog
    dog = db.query(Dog).filter(Dog.id == dog_id).first()
    if dog is None or dog.father_id is None or dog.mother_id is None:
        _cache[dog_id] = 0.0
        return 0.0

    result = calculate_coi(dog.father_id, dog.mother_id, max_depth, db, _fa_cache=_cache)
    fa = result['coi']
    _cache[dog_id] = fa
    return fa


# ---------------------------------------------------------------------------
# 4. COI 計算（ライトの公式）
# ---------------------------------------------------------------------------

def calculate_coi(
    sire_id: int,
    dam_id: int,
    max_depth: int = 5,
    db=None,
    _fa_cache: dict | None = None,
) -> dict:
    """
    ライトの近交係数公式で COI を計算する。

    F_X = Σ_A Σ_{(n1,n2) in paths(A)} (1/2)^(n1+n2+1) × (1 + F_A)

    Parameters
    ----------
    sire_id   : 父犬 ID
    dam_id    : 母犬 ID
    max_depth : 最大探索世代数（デフォルト 5）
    db        : SQLAlchemy セッション
    _fa_cache : F_A 計算の再帰キャッシュ（内部用）

    Returns
    -------
    dict:
        coi              : float  近交係数（0.0〜1.0）
        coi_percent      : float  近交係数（%表示）
        common_ancestors : list   共通祖先ごとの詳細
    """
    if _fa_cache is None:
        _fa_cache = {}

    common = find_common_ancestors(sire_id, dam_id, max_depth, db)

    total_coi = 0.0
    common_ancestors_detail = []

    for anc_id, gens in common.items():
        sire_gens = gens['sire_gens']
        dam_gens  = gens['dam_gens']

        # 共通祖先自身の F_A を再帰計算
        fa = calculate_ancestor_inbreeding(anc_id, max_depth, db, _fa_cache)

        # 全経路の組み合わせで寄与率を計算
        paths_detail = []
        ancestor_contribution = 0.0

        for n1 in sire_gens:
            for n2 in dam_gens:
                # ライトの公式: (1/2)^(n1+n2+1) × (1 + F_A)
                contribution = (0.5 ** (n1 + n2 + 1)) * (1.0 + fa)
                ancestor_contribution += contribution
                paths_detail.append({
                    'n1': n1,
                    'n2': n2,
                    'formula': f'(1/2)^({n1}+{n2}+1) × (1 + {fa:.4f})',
                    'contribution': round(contribution, 8),
                    'contribution_percent': round(contribution * 100, 4),
                })

        total_coi += ancestor_contribution

        # 出現パターン（例: "2x3", "2x2"）
        patterns = list({f'{n1}x{n2}' for n1 in sire_gens for n2 in dam_gens})

        # 祖先名を取得
        anc_name = _get_dog_name(anc_id, db)

        common_ancestors_detail.append({
            'dog_id': anc_id,
            'name': anc_name,
            'patterns': patterns,
            'sire_generations': sire_gens,
            'dam_generations': dam_gens,
            'ancestor_inbreeding': round(fa, 6),
            'ancestor_inbreeding_percent': round(fa * 100, 4),
            'contribution': round(ancestor_contribution, 8),
            'contribution_percent': round(ancestor_contribution * 100, 4),
            'paths': paths_detail,
        })

    # 寄与率の高い順にソート
    common_ancestors_detail.sort(key=lambda x: x['contribution'], reverse=True)

    return {
        'coi': round(total_coi, 8),
        'coi_percent': round(total_coi * 100, 4),
        'common_ancestors': common_ancestors_detail,
    }


# ---------------------------------------------------------------------------
# 5. COI ランク判定
# ---------------------------------------------------------------------------

def get_coi_rank(coi_percent: float) -> dict:
    """
    COI% からランク・リスクレベル・推奨を返す。

    Returns
    -------
    dict: rank, risk_level, recommendation
    """
    if coi_percent < 5.0:
        return {'rank': 'A', 'risk_level': '安全寄り', 'recommendation': '推奨可能'}
    elif coi_percent < 10.0:
        return {'rank': 'B', 'risk_level': '軽いラインブリード', 'recommendation': '条件付きで検討可'}
    elif coi_percent < 15.0:
        return {'rank': 'C', 'risk_level': '注意', 'recommendation': '慎重に検討'}
    elif coi_percent < 20.0:
        return {'rank': 'D', 'risk_level': '高リスク', 'recommendation': '原則非推奨'}
    else:
        return {'rank': 'E', 'risk_level': '非常に高リスク', 'recommendation': '非推奨'}


# ---------------------------------------------------------------------------
# 6. 近親交配パターン検出
# ---------------------------------------------------------------------------

def detect_close_inbreeding_patterns(
    sire_id: int,
    dam_id: int,
    db,
) -> list[dict]:
    """
    危険な近親交配パターンを検出する。

    検出対象:
    - 親子交配（sire が dam の親、またはその逆）
    - 兄妹交配（共通の父または母を持つ）
    - 半兄妹交配（父または母の一方のみ共通）
    - 祖父母×孫
    - 2×2, 2×3, 3×3 パターン
    - 共通祖先 3 頭以上

    Returns
    -------
    list of dict: [{type, ancestor_id, ancestor_name, severity}, ...]
    """
    from app.models_breeder import Dog

    patterns = []

    sire = db.query(Dog).filter(Dog.id == sire_id).first()
    dam  = db.query(Dog).filter(Dog.id == dam_id).first()
    if not sire or not dam:
        return patterns

    # --- 親子交配 ---
    if sire.father_id == dam_id or sire.mother_id == dam_id:
        patterns.append({
            'type': '親子交配（父犬が母犬の子）',
            'ancestor_id': dam_id,
            'ancestor_name': dam.name,
            'severity': 'critical',
        })
    if dam.father_id == sire_id or dam.mother_id == sire_id:
        patterns.append({
            'type': '親子交配（母犬が父犬の子）',
            'ancestor_id': sire_id,
            'ancestor_name': sire.name,
            'severity': 'critical',
        })

    # --- 兄妹・半兄妹交配 ---
    sire_parents = {p for p in [sire.father_id, sire.mother_id] if p}
    dam_parents  = {p for p in [dam.father_id,  dam.mother_id]  if p}
    shared_parents = sire_parents & dam_parents

    if len(shared_parents) == 2:
        for pid in shared_parents:
            parent = db.query(Dog).filter(Dog.id == pid).first()
            pname = parent.name if parent else f'ID:{pid}'
            patterns.append({
                'type': '兄妹交配',
                'ancestor_id': pid,
                'ancestor_name': pname,
                'severity': 'critical',
            })
    elif len(shared_parents) == 1:
        pid = list(shared_parents)[0]
        parent = db.query(Dog).filter(Dog.id == pid).first()
        pname = parent.name if parent else f'ID:{pid}'
        patterns.append({
            'type': '半兄妹交配',
            'ancestor_id': pid,
            'ancestor_name': pname,
            'severity': 'high',
        })

    # --- 祖父母×孫（1世代先の親の親が相手） ---
    sire_grandparents = set()
    for pid in sire_parents:
        p = db.query(Dog).filter(Dog.id == pid).first()
        if p:
            if p.father_id: sire_grandparents.add(p.father_id)
            if p.mother_id: sire_grandparents.add(p.mother_id)

    if dam_id in sire_grandparents:
        patterns.append({
            'type': '祖父母×孫（母犬が父犬の祖父母）',
            'ancestor_id': dam_id,
            'ancestor_name': dam.name,
            'severity': 'critical',
        })

    dam_grandparents = set()
    for pid in dam_parents:
        p = db.query(Dog).filter(Dog.id == pid).first()
        if p:
            if p.father_id: dam_grandparents.add(p.father_id)
            if p.mother_id: dam_grandparents.add(p.mother_id)

    if sire_id in dam_grandparents:
        patterns.append({
            'type': '祖父母×孫（父犬が母犬の祖父母）',
            'ancestor_id': sire_id,
            'ancestor_name': sire.name,
            'severity': 'critical',
        })

    # --- 共通祖先の出現パターン（2x2, 2x3, 3x3 等）---
    common = find_common_ancestors(sire_id, dam_id, max_depth=5, db=db)

    if len(common) >= 3:
        patterns.append({
            'type': f'共通祖先{len(common)}頭以上',
            'ancestor_id': None,
            'ancestor_name': None,
            'severity': 'medium',
        })

    for anc_id, gens in common.items():
        from app.models_breeder import Dog as DogModel
        anc = db.query(DogModel).filter(DogModel.id == anc_id).first()
        anc_name = anc.name if anc else f'ID:{anc_id}'

        for n1 in gens['sire_gens']:
            for n2 in gens['dam_gens']:
                pattern_str = f'{n1}x{n2}'
                # 2x2 は特に危険
                if n1 == 2 and n2 == 2:
                    patterns.append({
                        'type': f'2×2（{anc_name}）',
                        'ancestor_id': anc_id,
                        'ancestor_name': anc_name,
                        'severity': 'high',
                    })
                # 同じ祖先が複数経路で出現
                if len(gens['sire_gens']) > 1 or len(gens['dam_gens']) > 1:
                    patterns.append({
                        'type': f'同一祖先が複数経路で出現（{anc_name}）',
                        'ancestor_id': anc_id,
                        'ancestor_name': anc_name,
                        'severity': 'medium',
                    })
                    break  # 1回だけ追加

    # 重複除去（type + ancestor_id で一意化）
    seen = set()
    unique_patterns = []
    for p in patterns:
        key = (p['type'], p['ancestor_id'])
        if key not in seen:
            seen.add(key)
            unique_patterns.append(p)

    return unique_patterns


# ---------------------------------------------------------------------------
# 7. 遺伝病リスク判定
# ---------------------------------------------------------------------------

def calculate_genetic_disease_risk(
    sire_id: int,
    dam_id: int,
    db,
) -> list[dict]:
    """
    両親の遺伝病検査結果を比較してリスクを評価する。

    リスク判定基準:
    - affected × affected  → very_high
    - carrier  × affected  → high
    - affected × carrier   → high
    - carrier  × carrier   → high（25% 発症リスク）
    - clear    × carrier   → low_carrier（50% キャリアリスク）
    - unknown が含まれる   → unknown_warning

    Returns
    -------
    list of dict: [{disease_name, sire_status, dam_status, risk, message}, ...]
    """
    from app.models_breeder import GeneticTestResult

    sire_genes = db.query(GeneticTestResult).filter(
        GeneticTestResult.dog_id == sire_id
    ).all()
    dam_genes = db.query(GeneticTestResult).filter(
        GeneticTestResult.dog_id == dam_id
    ).all()

    sire_map = {g.disease_name: g.result for g in sire_genes}
    dam_map  = {g.disease_name: g.result for g in dam_genes}
    all_diseases = set(list(sire_map.keys()) + list(dam_map.keys()))

    risks = []
    for disease in sorted(all_diseases):
        s = sire_map.get(disease, 'unknown')
        d = dam_map.get(disease,  'unknown')

        if s == 'affected' and d == 'affected':
            risk = 'very_high'
            msg  = '両親ともアフェクテッドです。子犬は100%発症します。'
        elif (s == 'affected' and d == 'carrier') or (s == 'carrier' and d == 'affected'):
            risk = 'high'
            msg  = '一方がアフェクテッド、他方がキャリアです。子犬の50%が発症します。'
        elif s == 'affected' or d == 'affected':
            risk = 'high'
            msg  = 'いずれかの親がアフェクテッドです。発症個体が生まれる可能性があります。'
        elif s == 'carrier' and d == 'carrier':
            risk = 'high'
            msg  = '両親が同じ疾患のキャリアです。子犬の25%が発症します。'
        elif s == 'carrier' or d == 'carrier':
            risk = 'low_carrier'
            msg  = 'いずれかの親がキャリアです。子犬の50%がキャリアになります。発症はしません。'
        elif s == 'unknown' or d == 'unknown':
            risk = 'unknown_warning'
            msg  = '検査未確認の親がいます。交配前に遺伝病検査を実施してください。'
        else:
            risk = 'clear'
            msg  = '両親ともクリアです。'

        risks.append({
            'disease_name': disease,
            'sire_status': s,
            'dam_status':  d,
            'risk': risk,
            'message': msg,
        })

    return risks


# ---------------------------------------------------------------------------
# 8. 警告・ポジティブポイント生成
# ---------------------------------------------------------------------------

def build_warnings_and_points(
    coi_percent: float,
    close_patterns: list[dict],
    gene_risks: list[dict],
    common_ancestors: list[dict],
    sire_id: int,
    dam_id: int,
    db,
) -> tuple[list[str], list[str], list[str]]:
    """
    警告・ポジティブポイント・ネガティブポイントを生成する。

    Returns
    -------
    (warnings, positive_points, negative_points)
    """
    warnings = []
    positive = []
    negative = []

    # COI 警告
    if coi_percent >= 20.0:
        warnings.append(f'COIが20%を超えています（{coi_percent:.2f}%）。非常に高リスクです。')
    elif coi_percent >= 15.0:
        warnings.append(f'COIが15%を超えています（{coi_percent:.2f}%）。高リスクです。')
    elif coi_percent >= 10.0:
        warnings.append(f'COIが10%を超えています（{coi_percent:.2f}%）。注意が必要です。')
    elif coi_percent >= 5.0:
        warnings.append(f'COIが5%を超えています（{coi_percent:.2f}%）。軽度のラインブリードです。')

    if coi_percent < 5.0:
        positive.append(f'COIは{coi_percent:.2f}%と低く、近親交配リスクは低い水準です。')
    elif coi_percent < 10.0:
        positive.append('COIは10%未満です。')

    # 近親パターン警告
    severity_map = {'critical': '【重大】', 'high': '【高】', 'medium': '【中】'}
    for p in close_patterns:
        label = severity_map.get(p['severity'], '')
        warnings.append(f'{label}{p["type"]}が検出されました。')

    if not close_patterns:
        positive.append('親子・兄妹交配などの危険な近親パターンは検出されませんでした。')

    # 共通祖先
    if len(common_ancestors) == 0:
        positive.append('共通祖先は見つかりませんでした。血縁関係は低い水準です。')
    else:
        negative.append(f'共通祖先が{len(common_ancestors)}頭存在します。')
        for ca in common_ancestors:
            if len(ca['sire_generations']) > 1 or len(ca['dam_generations']) > 1:
                warnings.append(f'祖先「{ca["name"]}」が複数経路で出現しています。')

    # 遺伝病リスク
    high_risk_diseases = [r for r in gene_risks if r['risk'] in ('very_high', 'high')]
    unknown_diseases   = [r for r in gene_risks if r['risk'] == 'unknown_warning']

    for r in high_risk_diseases:
        warnings.append(f'遺伝病「{r["disease_name"]}」: {r["message"]}')
        negative.append(f'遺伝病「{r["disease_name"]}」のリスクが高い組み合わせです。')

    for r in unknown_diseases:
        warnings.append(f'遺伝病「{r["disease_name"]}」: {r["message"]}')

    if not gene_risks:
        positive.append('遺伝病検査情報が登録されていません。交配前に検査を実施してください。')
        warnings.append('遺伝病検査情報が未登録です。交配前に検査を実施することを推奨します。')
    elif not high_risk_diseases and not unknown_diseases:
        positive.append('登録済みの遺伝病検査では高リスクな組み合わせは検出されませんでした。')

    # 血統情報不足
    from app.models_breeder import Dog
    sire = db.query(Dog).filter(Dog.id == sire_id).first()
    dam  = db.query(Dog).filter(Dog.id == dam_id).first()
    if sire and (sire.father_id is None and sire.mother_id is None):
        warnings.append('父犬の血統情報（父母）が未登録です。COI計算が不完全な可能性があります。')
    if dam and (dam.father_id is None and dam.mother_id is None):
        warnings.append('母犬の血統情報（父母）が未登録です。COI計算が不完全な可能性があります。')

    return warnings, positive, negative


# ---------------------------------------------------------------------------
# 9. 改善案生成（ルールベース）
# ---------------------------------------------------------------------------

def build_improvement_suggestions(
    coi_percent: float,
    close_patterns: list[dict],
    gene_risks: list[dict],
    common_ancestors: list[dict],
) -> list[str]:
    """
    ルールベースで改善案を生成する（AI不使用）。
    """
    suggestions = []

    if coi_percent >= 5.0:
        suggestions.append(
            f'COIを5%未満に下げるため、共通祖先を持たない交配相手候補を比較検討してください。'
        )

    for ca in common_ancestors[:3]:  # 上位3頭まで
        suggestions.append(
            f'共通祖先「{ca["name"]}」を含まない交配相手候補を検討してください。'
        )

    high_risk = [r for r in gene_risks if r['risk'] in ('very_high', 'high')]
    for r in high_risk:
        suggestions.append(
            f'遺伝病「{r["disease_name"]}」のリスクを下げるため、'
            f'クリア個体との交配を検討してください。'
        )

    unknown = [r for r in gene_risks if r['risk'] == 'unknown_warning']
    for r in unknown:
        suggestions.append(
            f'遺伝病「{r["disease_name"]}」の検査が未確認です。交配前に検査を実施してください。'
        )

    critical_patterns = [p for p in close_patterns if p['severity'] == 'critical']
    for p in critical_patterns:
        suggestions.append(
            f'「{p["type"]}」が検出されました。この組み合わせは避けることを強く推奨します。'
        )

    if not suggestions:
        suggestions.append(
            'この交配組み合わせに大きな問題は検出されませんでした。'
            '引き続き遺伝病検査と血統情報の更新を継続してください。'
        )

    return suggestions


# ---------------------------------------------------------------------------
# 10. AI コメント生成（OpenAI API 使用）
# ---------------------------------------------------------------------------

def generate_ai_comment(evaluation_result: dict) -> str:
    """
    評価結果をもとに AI が自然文コメントを生成する。
    COI 計算には一切関与しない。

    Parameters
    ----------
    evaluation_result : evaluate_mating_compatibility の戻り値

    Returns
    -------
    str : ブリーダー向けコメント
    """
    try:
        import os
        from openai import OpenAI

        client = OpenAI()

        coi_pct  = evaluation_result.get('coi_percent', 0)
        rank     = evaluation_result.get('rank', '?')
        rec      = evaluation_result.get('recommendation', '')
        warnings = evaluation_result.get('warnings', [])
        sire_name = evaluation_result.get('sire', {}).get('name', '父犬')
        dam_name  = evaluation_result.get('dam', {}).get('name', '母犬')
        ca_count  = len(evaluation_result.get('common_ancestors', []))

        warning_text = '\n'.join(f'- {w}' for w in warnings[:5]) if warnings else '特になし'

        prompt = f"""あなたはブリーダー向けの犬の繁殖管理アドバイザーです。
以下の交配評価データをもとに、ブリーダー向けの簡潔なコメントを日本語で生成してください。
法的・獣医学的な断定表現は避け、「安全寄り」「低リスク」などの表現を使ってください。
200文字以内でまとめてください。

父犬: {sire_name}
母犬: {dam_name}
COI: {coi_pct:.2f}%
ランク: {rank}
推奨: {rec}
共通祖先数: {ca_count}頭
主な警告:
{warning_text}
"""
        response = client.chat.completions.create(
            model='gpt-4.1-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=300,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        # AI が利用できない場合はルールベースのコメントを返す
        return _generate_rule_based_comment(evaluation_result)


def _generate_rule_based_comment(result: dict) -> str:
    """AI が使えない場合のルールベースコメント。"""
    coi_pct = result.get('coi_percent', 0)
    rank    = result.get('rank', '?')
    rec     = result.get('recommendation', '')
    ca_count = len(result.get('common_ancestors', []))

    if rank == 'A':
        base = 'この交配は近交係数が低く、血縁関係は低い水準です。'
    elif rank == 'B':
        base = 'この交配は軽度のラインブリードです。狙った形質の固定が期待できますが、遺伝病検査の確認を推奨します。'
    elif rank == 'C':
        base = 'この交配は注意が必要な近親度です。過去の繁殖実績と遺伝病検査を十分に確認してください。'
    elif rank == 'D':
        base = 'この交配は近親度が高く、原則として非推奨です。別の交配相手を検討することを推奨します。'
    else:
        base = 'この交配は近親度が非常に高く、非推奨です。別の交配相手を強く推奨します。'

    if ca_count > 0:
        base += f'共通祖先が{ca_count}頭存在します。'

    return base


# ---------------------------------------------------------------------------
# 11. 総合評価（メイン関数）
# ---------------------------------------------------------------------------

def evaluate_mating_compatibility(
    sire_id: int,
    dam_id: int,
    max_depth: int = 5,
    db=None,
    use_ai_comment: bool = True,
) -> dict:
    """
    交配相性の総合評価を返すメイン関数。

    Parameters
    ----------
    sire_id        : 父犬 ID
    dam_id         : 母犬 ID
    max_depth      : 最大探索世代数（デフォルト 5）
    db             : SQLAlchemy セッション
    use_ai_comment : AI コメントを使用するか（デフォルト True）

    Returns
    -------
    dict : 仕様書 # 8 の出力 JSON 形式に準拠
    """
    from app.models_breeder import Dog

    sire = db.query(Dog).filter(Dog.id == sire_id).first()
    dam  = db.query(Dog).filter(Dog.id == dam_id).first()

    # --- COI 計算（数式ロジック）---
    coi_result = calculate_coi(sire_id, dam_id, max_depth, db)
    coi        = coi_result['coi']
    coi_pct    = coi_result['coi_percent']
    common_ancestors = coi_result['common_ancestors']

    # --- ランク判定 ---
    rank_info = get_coi_rank(coi_pct)

    # --- 近親パターン検出 ---
    close_patterns = detect_close_inbreeding_patterns(sire_id, dam_id, db)

    # --- 遺伝病リスク ---
    gene_risks = calculate_genetic_disease_risk(sire_id, dam_id, db)

    # --- 警告・ポイント ---
    warnings, positive_points, negative_points = build_warnings_and_points(
        coi_pct, close_patterns, gene_risks, common_ancestors, sire_id, dam_id, db
    )

    # --- 改善案（ルールベース）---
    suggestions = build_improvement_suggestions(
        coi_pct, close_patterns, gene_risks, common_ancestors
    )

    # --- 評価結果を組み立て ---
    result = {
        'sire': {
            'id': sire_id,
            'name': sire.name if sire else f'ID:{sire_id}',
        },
        'dam': {
            'id': dam_id,
            'name': dam.name if dam else f'ID:{dam_id}',
        },
        'max_depth': max_depth,
        'coi': coi,
        'coi_percent': coi_pct,
        'rank': rank_info['rank'],
        'risk_level': rank_info['risk_level'],
        'recommendation': rank_info['recommendation'],
        'common_ancestors': common_ancestors,
        'close_inbreeding_patterns': close_patterns,
        'genetic_disease_risks': gene_risks,
        'warnings': warnings,
        'positive_points': positive_points,
        'negative_points': negative_points,
        'improvement_suggestions': suggestions,
        'comment': '',  # AI コメントは後から追加
    }

    # --- AI コメント生成（COI 計算とは完全分離）---
    if use_ai_comment:
        result['comment'] = generate_ai_comment(result)
    else:
        result['comment'] = _generate_rule_based_comment(result)

    return result


# ===========================================================================
# 拡張ロジック：繁殖意思決定支援システム
# ===========================================================================

# ---------------------------------------------------------------------------
# AVK（Ancestor Loss Coefficient）計算
# ---------------------------------------------------------------------------

def calculate_avk(sire_id: int, dam_id: int, max_depth: int, db) -> dict:
    """
    AVK（Ancestor Loss Coefficient / 祖先消失係数）を計算する。

    目的：
    血統表上に本来存在するはずの祖先数に対して、
    実際にユニークな祖先が何頭いるかの割合を計算する。

    計算式：
    AVK% = (ユニーク祖先数 / 理論上の祖先数) × 100

    理論上の祖先数 = 2^1 + 2^2 + ... + 2^max_depth
                  = 2^(max_depth+1) - 2

    Returns
    -------
    dict:
        avk_percent         : float  AVK%（高いほど多様性が高い）
        expected_ancestors  : int    理論上の祖先数
        unique_ancestors    : int    実際のユニーク祖先数
        ancestor_loss_percent : float 祖先消失率%
        diversity_level     : str   多様性レベル
    """
    sire_ancestors = get_ancestors(sire_id, max_depth, db)
    dam_ancestors  = get_ancestors(dam_id,  max_depth, db)

    # 子犬視点の祖先（父・母の祖先 + 父・母自身）
    all_ancestor_ids = set(sire_ancestors.keys()) | set(dam_ancestors.keys())
    all_ancestor_ids.add(sire_id)
    all_ancestor_ids.add(dam_id)

    unique_count = len(all_ancestor_ids)

    # 理論上の祖先数（子犬の視点で max_depth+1 世代まで）
    # 子犬の親 = 2頭（世代1）、祖父母 = 4頭（世代2）、...
    expected_count = sum(2 ** g for g in range(1, max_depth + 2))

    avk_percent = round(unique_count / expected_count * 100, 2) if expected_count > 0 else 0.0
    ancestor_loss_percent = round(100.0 - avk_percent, 2)

    if avk_percent >= 90:
        diversity_level = 'high'
        diversity_label = '多様性高い'
    elif avk_percent >= 80:
        diversity_level = 'medium_high'
        diversity_label = 'やや重複あり'
    elif avk_percent >= 70:
        diversity_level = 'medium_low'
        diversity_label = '重複多め'
    else:
        diversity_level = 'low'
        diversity_label = '祖先集中が強い'

    return {
        'avk_percent': avk_percent,
        'expected_ancestors': expected_count,
        'unique_ancestors': unique_count,
        'ancestor_loss_percent': ancestor_loss_percent,
        'diversity_level': diversity_level,
        'diversity_label': diversity_label,
    }


# ---------------------------------------------------------------------------
# 祖先集中度スコア
# ---------------------------------------------------------------------------

def calculate_ancestor_concentration(sire_id: int, dam_id: int, max_depth: int, db) -> list:
    """
    同一祖先が何回出現しているかを集計し、集中度を返す。

    Returns
    -------
    list of dict:
        dog_id              : int
        name                : str
        appearance_count    : int  出現回数（父側＋母側の合計）
        generations         : list 出現した世代のリスト（重複あり）
        concentration_level : str  通常/軽度/中度/高度
    """
    sire_ancestors = get_ancestors(sire_id, max_depth, db)
    dam_ancestors  = get_ancestors(dam_id,  max_depth, db)

    all_ids = set(sire_ancestors.keys()) | set(dam_ancestors.keys())
    result = []

    for anc_id in all_ids:
        sire_gens = sire_ancestors.get(anc_id, [])
        dam_gens  = dam_ancestors.get(anc_id, [])
        count = len(sire_gens) + len(dam_gens)
        all_gens = sorted(set(sire_gens + dam_gens))

        if count == 1:
            level = 'normal'
            label = '通常'
        elif count == 2:
            level = 'mild'
            label = '軽度集中'
        elif count == 3:
            level = 'moderate'
            label = '中度集中'
        else:
            level = 'high'
            label = '高度集中'

        result.append({
            'dog_id': anc_id,
            'name': _get_dog_name(anc_id, db),
            'appearance_count': count,
            'sire_appearances': len(sire_gens),
            'dam_appearances': len(dam_gens),
            'generations': all_gens,
            'concentration_level': level,
            'concentration_label': label,
        })

    result.sort(key=lambda x: x['appearance_count'], reverse=True)
    return result


# ---------------------------------------------------------------------------
# ライン依存度
# ---------------------------------------------------------------------------

def calculate_line_dependency(sire_id: int, dam_id: int, max_depth: int, db) -> dict:
    """
    特定の祖先または血統ラインへの依存度を計算する。

    Returns
    -------
    dict:
        top_ancestor        : str  最頻出祖先名
        top_ancestor_id     : int
        top_ancestor_ratio  : float 全出現数に占める割合%
        dependency_level    : str  low/medium/high/very_high
        total_appearances   : int  全祖先の出現数合計
        top_ancestors       : list 上位5祖先
    """
    concentration = calculate_ancestor_concentration(sire_id, dam_id, max_depth, db)

    if not concentration:
        return {
            'top_ancestor': None,
            'top_ancestor_id': None,
            'top_ancestor_ratio': 0.0,
            'dependency_level': 'low',
            'dependency_label': '依存なし',
            'total_appearances': 0,
            'top_ancestors': [],
        }

    total_appearances = sum(a['appearance_count'] for a in concentration)
    top = concentration[0]
    top_ratio = round(top['appearance_count'] / total_appearances * 100, 2) if total_appearances > 0 else 0.0

    if top_ratio >= 30:
        dep_level = 'very_high'
        dep_label = '特定祖先への依存が非常に高い'
    elif top_ratio >= 20:
        dep_level = 'high'
        dep_label = '特定祖先への依存が高い'
    elif top_ratio >= 10:
        dep_level = 'medium'
        dep_label = '特定祖先への依存がやや見られる'
    else:
        dep_level = 'low'
        dep_label = '依存は低い'

    return {
        'top_ancestor': top['name'],
        'top_ancestor_id': top['dog_id'],
        'top_ancestor_ratio': top_ratio,
        'dependency_level': dep_level,
        'dependency_label': dep_label,
        'total_appearances': total_appearances,
        'top_ancestors': concentration[:5],
    }


# ---------------------------------------------------------------------------
# 犬種別リスク評価
# ---------------------------------------------------------------------------

# 組み込みリスクマスタ（DBにデータがない場合のフォールバック）
_BUILTIN_BREED_RISKS = {
    'トイプードル': [
        {'risk_name': 'PRA（進行性網膜萎縮症）', 'severity': 'high', 'recommended_test': 'PRA遺伝子検査'},
        {'risk_name': '膝蓋骨脱臼', 'severity': 'medium', 'recommended_test': '整形外科検査'},
    ],
    'チワワ': [
        {'risk_name': '水頭症', 'severity': 'high', 'recommended_test': 'MRI/CT検査'},
        {'risk_name': '膝蓋骨脱臼', 'severity': 'medium', 'recommended_test': '整形外科検査'},
    ],
    '柴犬': [
        {'risk_name': 'アトピー性皮膚炎', 'severity': 'medium', 'recommended_test': 'アレルギー検査'},
        {'risk_name': '緑内障', 'severity': 'high', 'recommended_test': '眼科検査'},
    ],
    'フレンチブルドッグ': [
        {'risk_name': '短頭種気道症候群（BOAS）', 'severity': 'high', 'recommended_test': '呼吸機能検査'},
        {'risk_name': '椎間板ヘルニア', 'severity': 'high', 'recommended_test': 'MRI/X線検査'},
    ],
    'ゴールデンレトリバー': [
        {'risk_name': '股関節形成不全', 'severity': 'high', 'recommended_test': 'X線検査（OFA/PennHIP）'},
        {'risk_name': '腫瘍系疾患', 'severity': 'high', 'recommended_test': '定期健康診断'},
    ],
    'ラブラドールレトリバー': [
        {'risk_name': '股関節形成不全', 'severity': 'high', 'recommended_test': 'X線検査'},
        {'risk_name': '進行性網膜萎縮症', 'severity': 'high', 'recommended_test': 'PRA遺伝子検査'},
    ],
    'ダックスフンド': [
        {'risk_name': '椎間板ヘルニア', 'severity': 'high', 'recommended_test': 'MRI/X線検査'},
        {'risk_name': '進行性網膜萎縮症', 'severity': 'medium', 'recommended_test': 'PRA遺伝子検査'},
    ],
    'ポメラニアン': [
        {'risk_name': '気管虚脱', 'severity': 'medium', 'recommended_test': 'X線/内視鏡検査'},
        {'risk_name': '膝蓋骨脱臼', 'severity': 'medium', 'recommended_test': '整形外科検査'},
    ],
    'マルチーズ': [
        {'risk_name': '膝蓋骨脱臼', 'severity': 'medium', 'recommended_test': '整形外科検査'},
        {'risk_name': '白内障', 'severity': 'medium', 'recommended_test': '眼科検査'},
    ],
    'ビーグル': [
        {'risk_name': '脊椎疾患', 'severity': 'medium', 'recommended_test': 'X線検査'},
        {'risk_name': '甲状腺機能低下症', 'severity': 'medium', 'recommended_test': '血液検査'},
    ],
}


def evaluate_breed_risks(sire_breed: str | None, dam_breed: str | None, sire_gene_results: list, dam_gene_results: list, db) -> dict:
    """
    犬種別リスクマスタを参照し、検査不足や注意項目を返す。

    Parameters
    ----------
    sire_breed        : 父犬の犬種
    dam_breed         : 母犬の犬種
    sire_gene_results : 父犬の遺伝疾患検査結果リスト（MockGene 相当）
    dam_gene_results  : 母犬の遺伝疾患検査結果リスト
    db                : SQLAlchemy セッション

    Returns
    -------
    dict:
        breed_warnings  : list  犬種別警告
        missing_tests   : list  未実施の推奨検査
    """
    warnings = []
    missing_tests = []

    sire_tested = {g.disease_name for g in sire_gene_results}
    dam_tested  = {g.disease_name for g in dam_gene_results}

    for breed in set(filter(None, [sire_breed, dam_breed])):
        # DBから取得を試みる
        breed_risks = []
        try:
            from app.models_breeder import BreedRiskMaster
            breed_risks = db.query(BreedRiskMaster).filter(BreedRiskMaster.breed == breed).all()
        except Exception:
            pass

        # DBにデータがなければ組み込みマスタを使う
        if not breed_risks:
            builtin = _BUILTIN_BREED_RISKS.get(breed, [])
            for r in builtin:
                risk_name = r['risk_name']
                severity  = r.get('severity', 'medium')
                rec_test  = r.get('recommended_test', '')
                # 検査未実施チェック
                if risk_name not in sire_tested and sire_breed == breed:
                    missing_tests.append({
                        'breed': breed,
                        'side': 'sire',
                        'risk_name': risk_name,
                        'recommended_test': rec_test,
                        'severity': severity,
                    })
                if risk_name not in dam_tested and dam_breed == breed:
                    missing_tests.append({
                        'breed': breed,
                        'side': 'dam',
                        'risk_name': risk_name,
                        'recommended_test': rec_test,
                        'severity': severity,
                    })
                if severity == 'high':
                    warnings.append(f'【{breed}】{risk_name}のリスクがあります。{rec_test}の確認を推奨します。')
        else:
            for r in breed_risks:
                if r.severity == 'high':
                    warnings.append(f'【{r.breed}】{r.risk_name}のリスクがあります。{r.recommended_test or ""}の確認を推奨します。')
                if r.risk_name not in sire_tested and sire_breed == breed:
                    missing_tests.append({
                        'breed': breed,
                        'side': 'sire',
                        'risk_name': r.risk_name,
                        'recommended_test': r.recommended_test or '',
                        'severity': r.severity or 'medium',
                    })
                if r.risk_name not in dam_tested and dam_breed == breed:
                    missing_tests.append({
                        'breed': breed,
                        'side': 'dam',
                        'risk_name': r.risk_name,
                        'recommended_test': r.recommended_test or '',
                        'severity': r.severity or 'medium',
                    })

    return {
        'breed_warnings': warnings,
        'missing_tests': missing_tests,
    }


# ---------------------------------------------------------------------------
# 健康履歴評価
# ---------------------------------------------------------------------------

def evaluate_health_records(sire_id: int, dam_id: int, db) -> dict:
    """
    父犬・母犬の健康履歴を評価し、リスクスコアと警告を返す。

    Returns
    -------
    dict:
        health_warnings  : list  警告リスト
        health_score_penalty : int  減点（0〜50）
        sire_issues      : list  父犬の問題
        dam_issues       : list  母犬の問題
    """
    warnings = []
    penalty = 0
    sire_issues = []
    dam_issues  = []

    for dog_id, side, issues in [(sire_id, '父犬', sire_issues), (dam_id, '母犬', dam_issues)]:
        try:
            from app.models_breeder import DogHealthRecord
            records = db.query(DogHealthRecord).filter(DogHealthRecord.dog_id == dog_id).all()
        except Exception:
            records = []

        for r in records:
            issue = {
                'title': r.title,
                'category': r.category,
                'severity': r.severity,
                'resolved': bool(r.resolved),
            }
            issues.append(issue)

            # 重度疾患
            if r.severity == 'critical':
                warnings.append(f'{side}に重篤な疾患歴があります：{r.title}')
                penalty += 20
            elif r.severity == 'high':
                warnings.append(f'{side}に重大な疾患歴があります：{r.title}')
                penalty += 10

            # 未解決疾患
            if not r.resolved:
                warnings.append(f'{side}に未解決の疾患があります：{r.title}')
                penalty += 5

            # 繁殖関連疾患
            if r.category == 'reproductive':
                warnings.append(f'{side}に繁殖関連の疾患歴があります：{r.title}（繁殖前に獣医師への相談を推奨します）')
                penalty += 15

    # 同一カテゴリの疾患が父母双方にある場合
    sire_cats = {i['category'] for i in sire_issues if i['category']}
    dam_cats  = {i['category'] for i in dam_issues  if i['category']}
    shared_cats = sire_cats & dam_cats
    for cat in shared_cats:
        warnings.append(f'父犬・母犬の双方に{cat}カテゴリの疾患歴があります。子犬への影響を慎重に評価してください。')
        penalty += 5

    return {
        'health_warnings': warnings,
        'health_score_penalty': min(penalty, 50),
        'sire_issues': sire_issues,
        'dam_issues': dam_issues,
    }


# ---------------------------------------------------------------------------
# 繁殖履歴評価
# ---------------------------------------------------------------------------

def evaluate_breeding_history(sire_id: int, dam_id: int, db) -> dict:
    """
    父犬・母犬の繁殖履歴を評価し、統計と警告を返す。

    Returns
    -------
    dict:
        sire_stats       : dict  父犬の繁殖統計
        dam_stats        : dict  母犬の繁殖統計
        pair_history     : list  同ペアの過去の繁殖記録
        breeding_warnings : list  警告
    """
    warnings = []

    def _calc_stats(dog_id: int, role: str) -> dict:
        try:
            from app.models_breeder import BreedingHistory
            if role == 'sire':
                records = db.query(BreedingHistory).filter(BreedingHistory.sire_id == dog_id).all()
            else:
                records = db.query(BreedingHistory).filter(BreedingHistory.dam_id == dog_id).all()
        except Exception:
            records = []

        total = len(records)
        if total == 0:
            return {'total_litters': 0, 'success_rate': None, 'avg_puppy_count': None, 'stillbirth_rate': None, 'c_section_rate': None}

        success = sum(1 for r in records if r.pregnancy_result == 'success')
        total_puppies    = sum(r.puppy_count or 0 for r in records)
        live_births      = sum(r.live_birth_count or 0 for r in records)
        stillbirths      = sum(r.stillbirth_count or 0 for r in records)
        c_sections       = sum(1 for r in records if r.c_section)

        success_rate     = round(success / total * 100, 1) if total > 0 else None
        avg_puppies      = round(total_puppies / total, 1) if total > 0 else None
        stillbirth_rate  = round(stillbirths / total_puppies * 100, 1) if total_puppies > 0 else None
        c_section_rate   = round(c_sections / total * 100, 1) if total > 0 else None

        return {
            'total_litters': total,
            'success_rate': success_rate,
            'avg_puppy_count': avg_puppies,
            'stillbirth_rate': stillbirth_rate,
            'c_section_rate': c_section_rate,
        }

    sire_stats = _calc_stats(sire_id, 'sire')
    dam_stats  = _calc_stats(dam_id,  'dam')

    # 同ペアの過去記録
    pair_history = []
    try:
        from app.models_breeder import BreedingHistory
        pairs = db.query(BreedingHistory).filter(
            BreedingHistory.sire_id == sire_id,
            BreedingHistory.dam_id == dam_id
        ).all()
        for p in pairs:
            pair_history.append({
                'mating_date': str(p.mating_date) if p.mating_date else None,
                'pregnancy_result': p.pregnancy_result,
                'puppy_count': p.puppy_count,
                'live_birth_count': p.live_birth_count,
                'stillbirth_count': p.stillbirth_count,
                'c_section': bool(p.c_section),
            })
    except Exception:
        pass

    # 警告
    if dam_stats['total_litters'] and dam_stats['total_litters'] >= 5:
        warnings.append(f'母犬の出産回数が{dam_stats["total_litters"]}回と多い状態です。繁殖休止を検討してください。')
    if dam_stats.get('c_section_rate') and dam_stats['c_section_rate'] >= 50:
        warnings.append(f'母犬の帝王切開率が{dam_stats["c_section_rate"]}%と高い状態です。')
    if dam_stats.get('stillbirth_rate') and dam_stats['stillbirth_rate'] >= 10:
        warnings.append(f'母犬の死産率が{dam_stats["stillbirth_rate"]}%と高い状態です。')

    return {
        'sire_stats': sire_stats,
        'dam_stats': dam_stats,
        'pair_history': pair_history,
        'breeding_warnings': warnings,
    }


# ---------------------------------------------------------------------------
# 産子実績評価
# ---------------------------------------------------------------------------

def evaluate_offspring_performance(sire_id: int, dam_id: int, db) -> dict:
    """
    過去産子データから産子実績スコアを算出する。

    Returns
    -------
    dict:
        total_litters      : int
        total_puppies      : int
        live_birth_rate    : float
        stillbirth_rate    : float
        defect_rate        : float
        known_disease_rate : float
        performance_level  : str  excellent/good/fair/poor
        offspring_warnings : list
    """
    warnings = []

    try:
        from app.models_breeder import BreedingHistory, PuppyRecord, PuppyFollowUp
        histories = db.query(BreedingHistory).filter(
            BreedingHistory.sire_id == sire_id,
            BreedingHistory.dam_id == dam_id
        ).all()
    except Exception:
        histories = []

    if not histories:
        return {
            'total_litters': 0,
            'total_puppies': 0,
            'live_birth_rate': None,
            'stillbirth_rate': None,
            'defect_rate': None,
            'known_disease_rate': None,
            'performance_level': 'unknown',
            'offspring_warnings': [],
        }

    total_litters  = len(histories)
    total_puppies  = 0
    live_births    = 0
    stillbirths    = 0
    defect_count   = 0
    disease_count  = 0

    for h in histories:
        try:
            puppies = db.query(PuppyRecord).filter(PuppyRecord.breeding_history_id == h.id).all()
        except Exception:
            puppies = []

        for p in puppies:
            total_puppies += 1
            if p.survived:
                live_births += 1
            else:
                stillbirths += 1
            if p.defects:
                defect_count += 1

            # フォローアップで疾患発見
            try:
                followups = db.query(PuppyFollowUp).filter(
                    PuppyFollowUp.puppy_id == p.id,
                    PuppyFollowUp.disease_found == 1
                ).all()
                if followups:
                    disease_count += 1
            except Exception:
                pass

    live_birth_rate   = round(live_births / total_puppies * 100, 1) if total_puppies > 0 else None
    stillbirth_rate   = round(stillbirths / total_puppies * 100, 1) if total_puppies > 0 else None
    defect_rate       = round(defect_count / total_puppies * 100, 1) if total_puppies > 0 else None
    known_disease_rate = round(disease_count / total_puppies * 100, 1) if total_puppies > 0 else None

    # パフォーマンスレベル
    score = 100
    if live_birth_rate is not None and live_birth_rate < 90:
        score -= 20
    if stillbirth_rate is not None and stillbirth_rate >= 10:
        score -= 20
        warnings.append(f'過去産子の死産率が{stillbirth_rate}%と高い状態です。')
    if defect_rate is not None and defect_rate >= 5:
        score -= 30
        warnings.append(f'過去産子の先天異常率が{defect_rate}%と高い状態です。同じ組み合わせの再交配は慎重に判断してください。')
    if known_disease_rate is not None and known_disease_rate >= 10:
        score -= 20
        warnings.append(f'過去産子の疾患発生率が{known_disease_rate}%と高い状態です。')

    if score >= 85:
        level = 'excellent'
    elif score >= 70:
        level = 'good'
    elif score >= 55:
        level = 'fair'
    else:
        level = 'poor'

    return {
        'total_litters': total_litters,
        'total_puppies': total_puppies,
        'live_birth_rate': live_birth_rate,
        'stillbirth_rate': stillbirth_rate,
        'defect_rate': defect_rate,
        'known_disease_rate': known_disease_rate,
        'performance_level': level,
        'offspring_warnings': warnings,
    }


# ---------------------------------------------------------------------------
# 総合スコア計算
# ---------------------------------------------------------------------------

def calculate_total_score(
    coi_percent: float,
    avk_result: dict,
    gene_risks: list,
    health_result: dict,
    breeding_result: dict,
    offspring_result: dict,
    breed_risk_result: dict,
    close_patterns: list,
) -> dict:
    """
    100点満点の総合スコアを計算する。

    配点：
    - COI         : 25点
    - AVK         : 15点
    - 遺伝病リスク : 20点
    - 健康履歴     : 15点
    - 繁殖履歴     : 10点
    - 産子実績     : 10点
    - 犬種別検査充足度 : 5点

    強制減点：
    - carrier × carrier  : -30点
    - affected を含む    : -40点
    - COI 20%以上        : -30点
    - 親子/兄妹交配      : -50点
    - 重大な未解決疾患   : -30点

    Returns
    -------
    dict:
        total_score     : int   0〜100（強制減点後は0以下になる場合あり）
        score_breakdown : dict  各項目のスコア
        judgment        : str   推奨候補/条件付き/慎重/原則非推奨/非推奨
        forced_deductions : list 強制減点リスト
    """
    breakdown = {}
    forced_deductions = []

    # --- COI スコア（25点）---
    if coi_percent < 5:
        coi_score = 25
    elif coi_percent < 10:
        coi_score = 20
    elif coi_percent < 15:
        coi_score = 15
    elif coi_percent < 20:
        coi_score = 8
    else:
        coi_score = 0
    breakdown['coi'] = coi_score

    # --- AVK スコア（15点）---
    avk_pct = avk_result.get('avk_percent', 100)
    if avk_pct >= 90:
        avk_score = 15
    elif avk_pct >= 80:
        avk_score = 12
    elif avk_pct >= 70:
        avk_score = 8
    else:
        avk_score = 4
    breakdown['avk'] = avk_score

    # --- 遺伝病リスク スコア（20点）---
    gene_score = 20
    for r in gene_risks:
        if r['risk'] == 'very_high':
            gene_score -= 15
        elif r['risk'] == 'high':
            gene_score -= 10
        elif r['risk'] == 'low_carrier':
            gene_score -= 3
        elif r['risk'] == 'unknown_warning':
            gene_score -= 2
    gene_score = max(gene_score, 0)
    breakdown['genetic_disease'] = gene_score

    # --- 健康履歴 スコア（15点）---
    health_penalty = health_result.get('health_score_penalty', 0)
    health_score = max(15 - health_penalty, 0)
    breakdown['health_history'] = health_score

    # --- 繁殖履歴 スコア（10点）---
    breeding_score = 10
    dam_stats = breeding_result.get('dam_stats', {})
    if dam_stats.get('total_litters', 0) >= 5:
        breeding_score -= 3
    if dam_stats.get('c_section_rate') and dam_stats['c_section_rate'] >= 50:
        breeding_score -= 3
    if dam_stats.get('stillbirth_rate') and dam_stats['stillbirth_rate'] >= 10:
        breeding_score -= 4
    breeding_score = max(breeding_score, 0)
    breakdown['breeding_history'] = breeding_score

    # --- 産子実績 スコア（10点）---
    perf_level = offspring_result.get('performance_level', 'unknown')
    perf_map = {'excellent': 10, 'good': 8, 'fair': 5, 'poor': 2, 'unknown': 7}
    offspring_score = perf_map.get(perf_level, 7)
    breakdown['offspring_performance'] = offspring_score

    # --- 犬種別検査充足度 スコア（5点）---
    missing_tests = breed_risk_result.get('missing_tests', [])
    high_missing = sum(1 for t in missing_tests if t.get('severity') == 'high')
    breed_score = max(5 - high_missing * 2, 0)
    breakdown['breed_risk'] = breed_score

    base_score = sum(breakdown.values())

    # --- 強制減点 ---
    forced_total = 0

    # carrier × carrier
    has_carrier_x_carrier = any(r['risk'] == 'high' and
                                 r.get('sire_status') == 'carrier' and
                                 r.get('dam_status') == 'carrier'
                                 for r in gene_risks)
    if has_carrier_x_carrier:
        forced_deductions.append({'reason': 'carrier × carrier の遺伝病リスク', 'deduction': -30})
        forced_total -= 30

    # affected を含む
    has_affected = any(r.get('sire_status') == 'affected' or r.get('dam_status') == 'affected'
                       for r in gene_risks)
    if has_affected:
        forced_deductions.append({'reason': 'affected（発症個体）を含む', 'deduction': -40})
        forced_total -= 40

    # COI 20%以上
    if coi_percent >= 20:
        forced_deductions.append({'reason': f'COIが{coi_percent:.1f}%と非常に高い', 'deduction': -30})
        forced_total -= 30

    # 親子/兄妹交配
    critical_patterns = [p for p in close_patterns if p.get('severity') == 'critical']
    if critical_patterns:
        forced_deductions.append({'reason': '親子または兄妹交配', 'deduction': -50})
        forced_total -= 50

    # 重大な未解決疾患
    has_critical_unresolved = (
        any(i.get('severity') == 'critical' and not i.get('resolved')
            for i in health_result.get('sire_issues', []))
        or
        any(i.get('severity') == 'critical' and not i.get('resolved')
            for i in health_result.get('dam_issues', []))
    )
    if has_critical_unresolved:
        forced_deductions.append({'reason': '重大な未解決疾患あり', 'deduction': -30})
        forced_total -= 30

    total_score = max(base_score + forced_total, 0)

    # 総合判定
    if total_score >= 85:
        judgment = '推奨候補'
        judgment_level = 'excellent'
    elif total_score >= 70:
        judgment = '条件付きで有力'
        judgment_level = 'good'
    elif total_score >= 55:
        judgment = '慎重に検討'
        judgment_level = 'fair'
    elif total_score >= 40:
        judgment = '原則非推奨'
        judgment_level = 'poor'
    else:
        judgment = '非推奨'
        judgment_level = 'very_poor'

    return {
        'total_score': total_score,
        'base_score': base_score,
        'score_breakdown': breakdown,
        'forced_deductions': forced_deductions,
        'forced_total': forced_total,
        'judgment': judgment,
        'judgment_level': judgment_level,
    }


# ---------------------------------------------------------------------------
# 交配候補比較
# ---------------------------------------------------------------------------

def compare_mating_candidates(
    fixed_dog_id: int,
    fixed_role: str,
    candidate_ids: list[int],
    max_depth: int,
    db,
    use_ai_comment: bool = False,
) -> list:
    """
    固定した犬（父犬または母犬）に対して、複数の候補をランキング評価する。

    Parameters
    ----------
    fixed_dog_id  : 固定する犬の ID
    fixed_role    : 'sire'（固定が父犬）または 'dam'（固定が母犬）
    candidate_ids : 候補犬の ID リスト
    max_depth     : COI 計算の最大世代数
    db            : SQLAlchemy セッション

    Returns
    -------
    list of dict（total_score の降順でソート済み）
    """
    results = []

    for cand_id in candidate_ids:
        if fixed_role == 'sire':
            sire_id, dam_id = fixed_dog_id, cand_id
        else:
            sire_id, dam_id = cand_id, fixed_dog_id

        try:
            eval_result = evaluate_mating_compatibility_full(
                sire_id=sire_id,
                dam_id=dam_id,
                max_depth=max_depth,
                db=db,
                use_ai_comment=use_ai_comment,
            )
            results.append({
                'candidate_id': cand_id,
                'candidate_name': _get_dog_name(cand_id, db),
                'total_score': eval_result.get('total_score', 0),
                'coi_percent': eval_result.get('coi_percent', 0),
                'avk_percent': eval_result.get('avk', {}).get('avk_percent', 0),
                'judgment': eval_result.get('judgment', ''),
                'judgment_level': eval_result.get('judgment_level', ''),
                'rank': eval_result.get('rank', ''),
                'warnings': eval_result.get('warnings', []),
                'positive_points': eval_result.get('positive_points', []),
                'improvement_suggestions': eval_result.get('improvement_suggestions', []),
                'detail': eval_result,
            })
        except Exception as e:
            results.append({
                'candidate_id': cand_id,
                'candidate_name': _get_dog_name(cand_id, db),
                'total_score': 0,
                'error': str(e),
            })

    results.sort(key=lambda x: x.get('total_score', 0), reverse=True)

    for i, r in enumerate(results):
        r['rank_position'] = i + 1
        if i == 0:
            r['recommendation'] = '最有力候補'
        elif i == 1:
            r['recommendation'] = '有力候補'
        elif r.get('total_score', 0) >= 70:
            r['recommendation'] = '検討候補'
        else:
            r['recommendation'] = '要検討'

    return results


# ---------------------------------------------------------------------------
# 総合評価（拡張版）
# ---------------------------------------------------------------------------

def evaluate_mating_compatibility_full(
    sire_id: int,
    dam_id: int,
    max_depth: int = 5,
    db = None,
    use_ai_comment: bool = False,
    sire_breed: str | None = None,
    dam_breed: str | None = None,
) -> dict:
    """
    繁殖意思決定支援システムの総合評価関数。

    既存の evaluate_mating_compatibility に加えて、
    AVK・祖先集中度・ライン依存度・健康履歴・繁殖履歴・産子実績・
    犬種別リスク・総合スコアを統合して返す。

    Returns
    -------
    dict: 全評価指標を含む総合評価 JSON
    """
    # 基本評価（COI・遺伝病・近親パターン）
    base = evaluate_mating_compatibility(
        sire_id=sire_id,
        dam_id=dam_id,
        max_depth=max_depth,
        db=db,
        use_ai_comment=False,
    )

    # AVK
    avk = calculate_avk(sire_id, dam_id, max_depth, db)

    # 祖先集中度
    concentration = calculate_ancestor_concentration(sire_id, dam_id, max_depth, db)

    # ライン依存度
    line_dep = calculate_line_dependency(sire_id, dam_id, max_depth, db)

    # 健康履歴
    health = evaluate_health_records(sire_id, dam_id, db)

    # 繁殖履歴
    breeding = evaluate_breeding_history(sire_id, dam_id, db)

    # 産子実績
    offspring = evaluate_offspring_performance(sire_id, dam_id, db)

    # 犬種別リスク
    sire_genes = []
    dam_genes  = []
    try:
        from app.models_breeder import GeneticTestResult
        sire_genes = db.query(GeneticTestResult).filter(GeneticTestResult.dog_id == sire_id).all()
        dam_genes  = db.query(GeneticTestResult).filter(GeneticTestResult.dog_id == dam_id).all()
    except Exception:
        pass

    breed_risks = evaluate_breed_risks(sire_breed, dam_breed, sire_genes, dam_genes, db)

    # 総合スコア
    score = calculate_total_score(
        coi_percent=base['coi_percent'],
        avk_result=avk,
        gene_risks=base['genetic_disease_risks'],
        health_result=health,
        breeding_result=breeding,
        offspring_result=offspring,
        breed_risk_result=breed_risks,
        close_patterns=base['close_inbreeding_patterns'],
    )

    # 全警告を統合
    all_warnings = (
        base.get('warnings', []) +
        health.get('health_warnings', []) +
        breeding.get('breeding_warnings', []) +
        offspring.get('offspring_warnings', []) +
        breed_risks.get('breed_warnings', [])
    )

    result = {
        **base,
        'avk': avk,
        'ancestor_concentration': concentration,
        'line_dependency': line_dep,
        'health_evaluation': health,
        'breeding_evaluation': breeding,
        'offspring_evaluation': offspring,
        'breed_risk_evaluation': breed_risks,
        'total_score': score['total_score'],
        'base_score': score['base_score'],
        'score_breakdown': score['score_breakdown'],
        'forced_deductions': score['forced_deductions'],
        'judgment': score['judgment'],
        'judgment_level': score['judgment_level'],
        'warnings': all_warnings,
    }

    # AI コメント（分離済み）
    if use_ai_comment:
        result['comment'] = generate_ai_comment(result)
    else:
        result['comment'] = _generate_rule_based_comment(result)

    return result
