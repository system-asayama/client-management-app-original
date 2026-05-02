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
