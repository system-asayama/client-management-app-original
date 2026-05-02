# -*- coding: utf-8 -*-
"""
繁殖意思決定支援システム 拡張機能のユニットテスト
AVK・祖先集中度・ライン依存度・総合スコア・候補比較
"""
import sys, os
from unittest.mock import MagicMock
import importlib.util

# ---- 既存テストと同じ方式でimport ----
sys.modules['app'] = MagicMock()
sys.modules['app.models_breeder'] = MagicMock()
sys.modules['app.db'] = MagicMock()

_bl_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'services', 'breeding_logic.py')
_spec = importlib.util.spec_from_file_location('breeding_logic', _bl_path)
bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bl)

_cg_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'services', 'comment_generator.py')
_cg_spec = importlib.util.spec_from_file_location('comment_generator', _cg_path)
cg = importlib.util.module_from_spec(_cg_spec)
_cg_spec.loader.exec_module(cg)

# ============================================================
# テスト用ヘルパー
# ============================================================
def make_dog(dog_id, name, father_id=None, mother_id=None):
    """シンプルなDogオブジェクトを作る"""
    class FakeDog:
        pass
    d = FakeDog()
    d.id = dog_id
    d.name = name
    d.father_id = father_id
    d.mother_id = mother_id
    d.breed = 'トイプードル'
    d.sex = 'male'
    d.birth_date = None
    return d

def make_db(dogs):
    """辞書ベースのFakeDB"""
    dog_map = {d.id: d for d in dogs}

    class FakeQuery:
        def __init__(self, model):
            self._model = model
        def filter(self, *args):
            return self
        def all(self):
            return list(dog_map.values())
        def first(self):
            return None

    class FakeDB:
        def query(self, model):
            return FakeQuery(model)

    return FakeDB(), dog_map


# ============================================================
# AVK テスト
# ============================================================
def test_avk_no_ancestors():
    """祖先なし（父・母のみ）→ AVK は低い値になる"""
    sire = make_dog(1, 'Sire')
    dam  = make_dog(2, 'Dam')
    db, dog_map = make_db([sire, dam])

    orig_get_ancestors = bl.get_ancestors
    def mock_get_ancestors(dog_id, max_depth, db):
        return {}
    bl.get_ancestors = mock_get_ancestors

    result = bl.calculate_avk(sire_id=1, dam_id=2, max_depth=5, db=db)
    bl.get_ancestors = orig_get_ancestors

    # 父・母の2頭のみ → unique=2, expected=126 → AVK ≈ 1.59%
    assert result['unique_ancestors'] == 2, f"Expected 2 unique ancestors, got {result['unique_ancestors']}"
    assert result['avk_percent'] < 10.0, f"Expected low AVK, got {result['avk_percent']}"
    assert 'avk_percent' in result


def test_avk_full_overlap():
    """全祖先が同一 → AVK は低い値（重複多い）"""
    sire = make_dog(1, 'Sire')
    dam  = make_dog(2, 'Dam')
    db, dog_map = make_db([sire, dam])

    # 両親とも同じ祖先セット（3頭）
    shared_ancestors = {10: [1], 11: [1], 12: [2]}

    orig_get_ancestors = bl.get_ancestors
    def mock_get_ancestors(dog_id, max_depth, db):
        return dict(shared_ancestors)
    bl.get_ancestors = mock_get_ancestors

    result = bl.calculate_avk(sire_id=1, dam_id=2, max_depth=5, db=db)
    bl.get_ancestors = orig_get_ancestors

    # 父・母・共通祖先3頭 = 5頭ユニーク、expected=126 → AVK ≈ 3.97%（低い）
    assert result['avk_percent'] < 10.0, f"Expected low AVK due to overlap, got {result['avk_percent']}"
    assert result['diversity_level'] in ('low', 'medium_low')


# ============================================================
# 祖先集中度テスト
# ============================================================
def test_ancestor_concentration_high():
    """同一祖先が5回出現 → 高集中度"""
    sire = make_dog(1, 'Sire')
    dam  = make_dog(2, 'Dam')
    db, dog_map = make_db([sire, dam, make_dog(99, 'CommonAncestor')])

    orig_get_ancestors = bl.get_ancestors
    def mock_get_ancestors(dog_id, max_depth, db):
        # 祖先99が5回出現
        return {99: [1, 2, 3, 4, 5]}
    bl.get_ancestors = mock_get_ancestors

    orig_get_dog_name = bl._get_dog_name
    def mock_get_dog_name(dog_id, db):
        return 'CommonAncestor'
    bl._get_dog_name = mock_get_dog_name

    result = bl.calculate_ancestor_concentration(sire_id=1, dam_id=2, max_depth=5, db=db)
    bl.get_ancestors = orig_get_ancestors
    bl._get_dog_name = orig_get_dog_name

    assert len(result) > 0
    # 父側5 + 母側5 = 合計10回出現
    assert result[0]['appearance_count'] == 10
    assert result[0]['concentration_level'] == 'high'


# ============================================================
# ライン依存度テスト
# ============================================================
def test_line_dependency_very_high():
    """共通祖先の出現率が50%超 → very_high"""
    sire = make_dog(1, 'Sire')
    dam  = make_dog(2, 'Dam')
    db, dog_map = make_db([sire, dam, make_dog(99, 'TopAncestor')])

    orig_get_ancestors = bl.get_ancestors
    def mock_get_ancestors(dog_id, max_depth, db):
        # 全8祖先スロットのうち6回が同一祖先
        return {99: [1, 2, 3, 4, 5, 6], 100: [1], 101: [1]}
    bl.get_ancestors = mock_get_ancestors

    orig_find_common = bl.find_common_ancestors
    def mock_find_common(sire_id, dam_id, max_depth, db):
        return {99: {'sire_paths': [[1,2]], 'dam_paths': [[1,2,3]]}}
    bl.find_common_ancestors = mock_find_common

    orig_get_dog_name = bl._get_dog_name
    def mock_get_dog_name(dog_id, db):
        return 'TopAncestor'
    bl._get_dog_name = mock_get_dog_name

    result = bl.calculate_line_dependency(sire_id=1, dam_id=2, max_depth=5, db=db)
    bl.get_ancestors = orig_get_ancestors
    bl.find_common_ancestors = orig_find_common
    bl._get_dog_name = orig_get_dog_name

    assert result['dependency_level'] in ('high', 'very_high')


# ============================================================
# 総合スコアテスト
# ============================================================
def test_total_score_perfect():
    """全指標が最良 → 高スコア"""
    result = bl.calculate_total_score(
        coi_percent=0.0,
        avk_result={'avk_percent': 100.0, 'diversity_level': 'high'},
        gene_risks=[],
        health_result={'health_score': 15, 'health_warnings': []},
        breeding_result={'breeding_score': 10, 'breeding_warnings': []},
        offspring_result={'offspring_score': 10, 'performance_level': 'excellent'},
        breed_risk_result={'breed_risk_score': 5, 'breed_warnings': [], 'missing_tests': []},
        close_patterns=[],
    )
    assert result['total_score'] >= 90, f"Expected >=90, got {result['total_score']}"
    assert result['judgment_level'] in ('excellent', 'good')


def test_total_score_forced_deduction_parent_child():
    """親子交配 → 強制減点で不適切判定"""
    result = bl.calculate_total_score(
        coi_percent=25.0,
        avk_result={'avk_percent': 50.0, 'diversity_level': 'low'},
        gene_risks=[],
        health_result={'health_score': 15, 'health_warnings': []},
        breeding_result={'breeding_score': 10, 'breeding_warnings': []},
        offspring_result={'offspring_score': 10, 'performance_level': 'unknown'},
        breed_risk_result={'breed_risk_score': 5, 'breed_warnings': [], 'missing_tests': []},
        close_patterns=[{'pattern': 'parent_child', 'description': '親子交配', 'severity': 'critical'}],
    )
    # 親子交配(-50) + COI>=20%(-30) = -80点の強制減点
    assert len(result['forced_deductions']) >= 1, f"Expected forced deductions, got {result['forced_deductions']}"
    assert result['total_score'] < 50, f"Expected score < 50 due to forced deductions, got {result['total_score']}"


def test_total_score_high_genetic_risk():
    """遺伝病リスク very_high → スコア低下"""
    result = bl.calculate_total_score(
        coi_percent=3.0,
        avk_result={'avk_percent': 90.0, 'diversity_level': 'high'},
        gene_risks=[{'disease_name': 'PRA', 'risk': 'very_high', 'risk_label': '非常に高リスク'}],
        health_result={'health_score': 15, 'health_warnings': []},
        breeding_result={'breeding_score': 10, 'breeding_warnings': []},
        offspring_result={'offspring_score': 10, 'performance_level': 'good'},
        breed_risk_result={'breed_risk_score': 5, 'breed_warnings': [], 'missing_tests': []},
        close_patterns=[],
    )
    # 遺伝病スコアが減点される（20点満点 - 15点 = 5点）
    assert result['score_breakdown']['genetic_disease'] == 5
    # COI 3%→25, AVK 90%→15, gene→5, health→15, breeding→10, offspring(good)→8, breed→5 = 83点
    assert result['score_breakdown']['genetic_disease'] < 20, 'gene score should be reduced from 20'


# ============================================================
# 候補比較テスト（モック版）
# ============================================================
def test_compare_candidates_ranking_order():
    """スコアが高い候補が上位にランクされる"""
    # compare_mating_candidates は DB が必要なため、
    # calculate_total_score の結果を直接テストする
    high = bl.calculate_total_score(
        coi_percent=1.0,
        avk_result={'avk_percent': 95.0, 'diversity_level': 'high'},
        gene_risks=[],
        health_result={'health_score': 15, 'health_warnings': []},
        breeding_result={'breeding_score': 10, 'breeding_warnings': []},
        offspring_result={'offspring_score': 10, 'performance_level': 'excellent'},
        breed_risk_result={'breed_risk_score': 5, 'breed_warnings': [], 'missing_tests': []},
        close_patterns=[],
    )
    low = bl.calculate_total_score(
        coi_percent=20.0,
        avk_result={'avk_percent': 60.0, 'diversity_level': 'low'},
        gene_risks=[{'disease_name': 'PRA', 'risk': 'very_high', 'risk_label': '非常に高リスク'}],
        health_result={'health_score': 5, 'health_warnings': ['重篤な疾患あり']},
        breeding_result={'breeding_score': 5, 'breeding_warnings': []},
        offspring_result={'offspring_score': 3, 'performance_level': 'poor'},
        breed_risk_result={'breed_risk_score': 2, 'breed_warnings': [], 'missing_tests': []},
        close_patterns=[],
    )
    assert high['total_score'] > low['total_score'], \
        f"High score ({high['total_score']}) should be > low score ({low['total_score']})"


# ============================================================
# comment_generator テスト
# ============================================================
def test_rule_based_summary_no_coi():
    """COI 0% → 共通祖先なしのコメントが含まれる"""
    eval_data = {
        'coi_percent': 0.0,
        'rank': 'A',
        'total_score': 95,
        'judgment': '非常に推奨',
        'avk': {'avk_percent': 100.0, 'diversity_level': 'excellent'},
        'genetic_disease_risks': [],
        'health_evaluation': {'health_warnings': []},
        'breeding_evaluation': {'breeding_warnings': []},
        'offspring_evaluation': {'performance_level': 'excellent'},
        'breed_risk_evaluation': {'breed_warnings': [], 'missing_tests': []},
        'ancestor_concentration': [],
        'line_dependency': {},
        'warnings': [],
        'improvement_suggestions': [],
        'forced_deductions': [],
    }
    comment = cg.generate_rule_based_summary(eval_data)
    assert '0%' in comment or '共通祖先' in comment, f"Expected COI 0% mention, got: {comment}"


def test_rule_based_improvements_high_coi():
    """COI 15% → COI改善提案が含まれる"""
    eval_data = {
        'coi_percent': 15.0,
        'rank': 'D',
        'total_score': 40,
        'judgment': '非推奨',
        'avk': {'avk_percent': 70.0, 'diversity_level': 'fair'},
        'genetic_disease_risks': [],
        'health_evaluation': {'health_warnings': []},
        'breeding_evaluation': {'dam_stats': {'total_litters': 2}, 'breeding_warnings': []},
        'offspring_evaluation': {'performance_level': 'fair'},
        'breed_risk_evaluation': {'breed_warnings': [], 'missing_tests': []},
        'ancestor_concentration': [],
        'line_dependency': {},
        'warnings': [],
        'improvement_suggestions': [],
        'forced_deductions': [],
    }
    improvements = cg.generate_rule_based_improvements(eval_data)
    assert any('COI' in s or 'アウトクロス' in s for s in improvements), \
        f"Expected COI improvement suggestion, got: {improvements}"


# ============================================================
# 実行
# ============================================================
if __name__ == '__main__':
    tests = [
        test_avk_no_ancestors,
        test_avk_full_overlap,
        test_ancestor_concentration_high,
        test_line_dependency_very_high,
        test_total_score_perfect,
        test_total_score_forced_deduction_parent_child,
        test_total_score_high_genetic_risk,
        test_compare_candidates_ranking_order,
        test_rule_based_summary_no_coi,
        test_rule_based_improvements_high_coi,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f'  PASSED: {t.__name__}')
            passed += 1
        except Exception as e:
            print(f'  FAILED: {t.__name__}: {e}')
            failed += 1
    print(f'\n{passed} passed, {failed} failed')
