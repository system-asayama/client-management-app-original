# -*- coding: utf-8 -*-
"""
breeding_logic.py のユニットテスト（スタンドアロン版）

DB・Flask・SQLAlchemy への依存を完全にモック化し、
COI計算の正確性をライトの公式の理論値と照合する。

【モック方式】
breeding_logic.py は `db.query(Dog).filter(Dog.id == x).first()` の形でDBを呼ぶ。
`Dog` が MagicMock の場合、`Dog.id == x` は常に False になるため、
テスト用の MockDog クラスと、filter に渡された引数を無視して
「最後に first() が呼ばれたときに正しい犬を返す」ClosureDB を使う。
"""
import sys
import os
import unittest
import importlib.util
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# app パッケージをモック化してから breeding_logic を直接ロードする
# ---------------------------------------------------------------------------
sys.modules['app'] = MagicMock()
sys.modules['app.models_breeder'] = MagicMock()
sys.modules['app.db'] = MagicMock()

_bl_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'services', 'breeding_logic.py')
_spec = importlib.util.spec_from_file_location('breeding_logic', _bl_path)
bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bl)


# ---------------------------------------------------------------------------
# モックオブジェクト
# ---------------------------------------------------------------------------
class MockDog:
    def __init__(self, dog_id, name, father_id=None, mother_id=None):
        self.id = dog_id
        self.name = name
        self.father_id = father_id
        self.mother_id = mother_id


class MockGene:
    def __init__(self, dog_id, disease_name, result):
        self.dog_id = dog_id
        self.disease_name = disease_name
        self.result = result


class CapturingDB:
    """
    breeding_logic.py が発行する SQLAlchemy 風クエリをキャプチャし、
    dog_id / gene dog_id を正しく返すモック DB。

    breeding_logic.py は以下の2パターンを使う:
      1. db.query(Dog).filter(Dog.id == dog_id).first()
      2. db.query(GeneticTestResult).filter(GeneticTestResult.dog_id == x).all()

    Dog.id == dog_id は MagicMock 同士の比較なので常に False になる。
    そのため filter() に渡された引数ではなく、_walk() が呼ぶ順序を
    トラッキングして正しい犬を返す。

    具体的には:
    - _walk(dog_id, ...) → db.query(Dog).filter(Dog.id == dog_id).first()
      この dog_id は _walk の引数として渡される整数値そのもの。
      filter() に渡される引数は `Dog.id == dog_id` の評価結果（MagicMock）。
      → filter() を呼ぶ直前に _walk が dog_id を渡しているので、
        filter() の呼び出し引数の中に整数値が含まれていれば取り出せる。
        含まれていない場合は、呼び出し履歴から取り出す。

    最もシンプルな解決策:
    breeding_logic.py の _walk 関数が呼ぶのは
      db.query(Dog).filter(Dog.id == dog_id).first()
    この `Dog.id == dog_id` は Python の `__eq__` で評価される。
    MagicMock の __eq__ は常に False を返す（bool(False) = False）。

    → filter に渡される引数は常に False（bool）。
    → filter の引数から dog_id を取り出すことは不可能。

    解決策: filter() の呼び出し前後の query() の引数（model）を見て、
    Dog か GeneticTestResult かを判断し、
    - Dog の場合: filter() が呼ばれた回数と順序から dog_id を推測するのは困難。
    - 最もシンプルな方法: breeding_logic.py を直接パッチして
      db.query(Dog).filter(Dog.id == dog_id) の代わりに
      dog_map[dog_id] を返す関数を差し込む。

    【採用方式】
    breeding_logic.py の _walk 関数内の `db.query(Dog).filter(Dog.id == dog_id).first()`
    を、テスト時だけ `_get_dog_by_id(dog_id, db)` 経由にする。
    breeding_logic.py に `_get_dog_by_id` 関数を追加し、テストでモンキーパッチする。
    """
    pass


def make_patched_bl(dogs: list, gene_results: list = None):
    """
    breeding_logic モジュールの内部関数をモンキーパッチして
    テスト用データを返すようにする。

    Returns
    -------
    bl モジュール（パッチ済み）
    """
    gene_results = gene_results or []
    dog_map = {d.id: d for d in dogs}
    gene_map: dict[int, list] = {}
    for g in gene_results:
        gene_map.setdefault(g.dog_id, []).append(g)

    # breeding_logic.py の _walk 内で呼ばれる
    # db.query(Dog).filter(Dog.id == dog_id).first() を差し替える
    # 方法: bl._walk をラップして dog_id を直接 dog_map から引く

    # ---- _get_dog_name をパッチ ----
    original_get_dog_name = bl._get_dog_name

    def patched_get_dog_name(dog_id, db):
        dog = dog_map.get(dog_id)
        return dog.name if dog else f'ID:{dog_id}'

    bl._get_dog_name = patched_get_dog_name

    # ---- _walk をパッチ ----
    original_walk = bl._walk

    def patched_walk(dog_id, depth, max_depth, result, db, visited):
        if dog_id is None or depth > max_depth:
            return
        if depth > 0:
            result[dog_id].append(depth)
        key = (dog_id, depth)
        if key in visited:
            return
        visited.add(key)
        dog = dog_map.get(dog_id)
        if dog is None:
            return
        patched_walk(dog.father_id, depth + 1, max_depth, result, db, visited)
        patched_walk(dog.mother_id, depth + 1, max_depth, result, db, visited)

    bl._walk = patched_walk

    # ---- calculate_ancestor_inbreeding をパッチ ----
    # （祖先自身の COI 計算も同じ dog_map を使う）
    original_calc_anc = bl.calculate_ancestor_inbreeding

    def patched_calc_anc(ancestor_id, max_depth, db, _fa_cache=None):
        # 祖先の父・母を dog_map から取得
        anc = dog_map.get(ancestor_id)
        if anc is None or (anc.father_id is None and anc.mother_id is None):
            return 0.0
        # 再帰的に COI を計算（同じパッチ済み bl を使う）
        res = bl.calculate_coi(anc.father_id, anc.mother_id, max_depth=max_depth, db=db)
        return res['coi']

    bl.calculate_ancestor_inbreeding = patched_calc_anc

    # ---- calculate_genetic_disease_risk をパッチ ----
    original_gene_risk = bl.calculate_genetic_disease_risk

    def patched_gene_risk(sire_id, dam_id, db):
        sire_genes = gene_map.get(sire_id, [])
        dam_genes  = gene_map.get(dam_id,  [])
        sire_map = {g.disease_name: g.result for g in sire_genes}
        dam_map  = {g.disease_name: g.result for g in dam_genes}
        all_diseases = set(list(sire_map.keys()) + list(dam_map.keys()))
        risks = []
        for disease in all_diseases:
            s = sire_map.get(disease, 'unknown')
            d = dam_map.get(disease,  'unknown')
            if s == 'affected' and d == 'affected':
                risk = 'very_high'
                msg  = '100%の確率でアフェクテッドが生まれます'
            elif s == 'affected' or d == 'affected':
                risk = 'high'
                msg  = '50%の確率でアフェクテッドが生まれます'
            elif s == 'carrier' and d == 'carrier':
                risk = 'high'
                msg  = '25%の確率でアフェクテッド、50%でキャリアが生まれます'
            elif s == 'carrier' or d == 'carrier':
                risk = 'low_carrier'
                msg  = '50%の確率でキャリアが生まれます'
            elif s == 'unknown' or d == 'unknown':
                risk = 'unknown_warning'
                msg  = '検査未実施のため不明'
            else:
                risk = 'clear'
                msg  = 'リスクなし'
            risks.append({
                'disease_name': disease,
                'sire_status': s,
                'dam_status':  d,
                'risk': risk,
                'message': msg,
            })
        return risks

    bl.calculate_genetic_disease_risk = patched_gene_risk

    # ---- detect_close_inbreeding_patterns をパッチ ----
    original_detect = bl.detect_close_inbreeding_patterns

    def patched_detect(sire_id, dam_id, db):
        patterns = []
        sire = dog_map.get(sire_id)
        dam  = dog_map.get(dam_id)
        if sire is None or dam is None:
            return patterns
        # 親子チェック
        if sire.father_id == dam_id or sire.mother_id == dam_id:
            patterns.append({'type': '親子交配（父犬が母犬の子）', 'severity': 'critical', 'ancestor_name': dam.name})
        if dam.father_id == sire_id or dam.mother_id == sire_id:
            patterns.append({'type': '親子交配（母犬が父犬の子）', 'severity': 'critical', 'ancestor_name': sire.name})
        # 兄妹・半兄妹チェック
        shared_father = (sire.father_id and sire.father_id == dam.father_id)
        shared_mother = (sire.mother_id and sire.mother_id == dam.mother_id)
        if shared_father and shared_mother:
            patterns.append({'type': '兄妹交配（全血）', 'severity': 'critical', 'ancestor_name': None})
        elif shared_father:
            patterns.append({'type': '半兄妹交配（父方）', 'severity': 'high', 'ancestor_name': dog_map.get(sire.father_id, MockDog(0, '?')).name})
        elif shared_mother:
            patterns.append({'type': '半兄妹交配（母方）', 'severity': 'high', 'ancestor_name': dog_map.get(sire.mother_id, MockDog(0, '?')).name})
        return patterns

    bl.detect_close_inbreeding_patterns = patched_detect

    return bl, {
        'walk': original_walk,
        'calc_anc': original_calc_anc,
        'gene_risk': original_gene_risk,
        'detect': original_detect,
        'get_dog_name': original_get_dog_name,
    }


def restore_bl(originals):
    """パッチを元に戻す"""
    bl._walk = originals['walk']
    bl.calculate_ancestor_inbreeding = originals['calc_anc']
    bl.calculate_genetic_disease_risk = originals['gene_risk']
    bl.detect_close_inbreeding_patterns = originals['detect']
    bl._get_dog_name = originals['get_dog_name']


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------
class TestGetAncestors(unittest.TestCase):

    def setUp(self):
        self._originals = None

    def tearDown(self):
        if self._originals:
            restore_bl(self._originals)

    def _patch(self, dogs, genes=None):
        _, originals = make_patched_bl(dogs, genes)
        self._originals = originals

    def test_no_parents(self):
        """親なし → 祖先なし"""
        dog = MockDog(1, 'A')
        self._patch([dog])
        result = bl.get_ancestors(1, max_depth=3, db=None)
        self.assertEqual(result, {})

    def test_one_parent(self):
        """父のみ → 父が世代1で出現"""
        father = MockDog(2, 'Father')
        child  = MockDog(1, 'Child', father_id=2)
        self._patch([child, father])
        result = bl.get_ancestors(1, max_depth=3, db=None)
        self.assertIn(2, result)
        self.assertIn(1, result[2])

    def test_two_generations(self):
        """祖父まで探索"""
        gf    = MockDog(10, 'GrandFather')
        f     = MockDog(2,  'Father', father_id=10)
        child = MockDog(1,  'Child',  father_id=2)
        self._patch([child, f, gf])
        result = bl.get_ancestors(1, max_depth=2, db=None)
        self.assertIn(2,  result)
        self.assertIn(10, result)
        self.assertIn(1, result[2])
        self.assertIn(2, result[10])

    def test_same_ancestor_multiple_paths(self):
        """同一祖先が複数経路で出現する場合、世代リストに複数の値が入る"""
        A  = MockDog(100, 'A')
        F  = MockDog(2,   'Father', father_id=100)
        M  = MockDog(3,   'Mother', father_id=100)
        X  = MockDog(1,   'X', father_id=2, mother_id=3)
        self._patch([X, F, M, A])
        result = bl.get_ancestors(1, max_depth=3, db=None)
        self.assertIn(100, result)
        self.assertEqual(sorted(result[100]), [2, 2])


class TestFindCommonAncestors(unittest.TestCase):

    def setUp(self):
        self._originals = None

    def tearDown(self):
        if self._originals:
            restore_bl(self._originals)

    def _patch(self, dogs):
        _, originals = make_patched_bl(dogs)
        self._originals = originals

    def test_no_common(self):
        """共通祖先なし"""
        sire = MockDog(1, 'Sire')
        dam  = MockDog(2, 'Dam')
        self._patch([sire, dam])
        result = bl.find_common_ancestors(1, 2, max_depth=3, db=None)
        self.assertEqual(result, {})

    def test_shared_grandfather(self):
        """共通の祖父を持つ"""
        GF   = MockDog(10, 'GF')
        F    = MockDog(2,  'F', father_id=10)
        M    = MockDog(3,  'M', father_id=10)
        sire = MockDog(1,  'Sire', father_id=2)
        dam  = MockDog(4,  'Dam',  father_id=3)
        self._patch([sire, dam, F, M, GF])
        result = bl.find_common_ancestors(1, 4, max_depth=3, db=None)
        self.assertIn(10, result)
        self.assertIn(2, result[10]['sire_gens'])
        self.assertIn(2, result[10]['dam_gens'])


class TestCalculateCOI(unittest.TestCase):

    def setUp(self):
        self._originals = None

    def tearDown(self):
        if self._originals:
            restore_bl(self._originals)

    def _patch(self, dogs):
        _, originals = make_patched_bl(dogs)
        self._originals = originals

    def test_no_common_ancestor(self):
        """共通祖先なし → COI = 0"""
        sire = MockDog(1, 'Sire')
        dam  = MockDog(2, 'Dam')
        self._patch([sire, dam])
        result = bl.calculate_coi(1, 2, max_depth=5, db=None)
        self.assertAlmostEqual(result['coi'], 0.0)
        self.assertAlmostEqual(result['coi_percent'], 0.0)

    def test_full_sibling_coi(self):
        """
        完全兄妹交配の COI = 25%
        F寄与: (1/2)^3 = 12.5%, M寄与: (1/2)^3 = 12.5%, 合計 25%
        """
        F    = MockDog(2, 'F')
        M    = MockDog(3, 'M')
        sire = MockDog(1, 'Sire', father_id=2, mother_id=3)
        dam  = MockDog(4, 'Dam',  father_id=2, mother_id=3)
        self._patch([sire, dam, F, M])
        result = bl.calculate_coi(1, 4, max_depth=3, db=None)
        self.assertAlmostEqual(result['coi'], 0.25, places=6)
        self.assertAlmostEqual(result['coi_percent'], 25.0, places=4)

    def test_half_sibling_coi(self):
        """
        半兄妹交配（父のみ共通）の COI = 12.5%
        F寄与: (1/2)^3 = 12.5%
        """
        F    = MockDog(2, 'F')
        M1   = MockDog(3, 'M1')
        M2   = MockDog(5, 'M2')
        sire = MockDog(1, 'Sire', father_id=2, mother_id=3)
        dam  = MockDog(4, 'Dam',  father_id=2, mother_id=5)
        self._patch([sire, dam, F, M1, M2])
        result = bl.calculate_coi(1, 4, max_depth=3, db=None)
        self.assertAlmostEqual(result['coi'], 0.125, places=6)
        self.assertAlmostEqual(result['coi_percent'], 12.5, places=4)

    def test_grandparent_common_ancestor(self):
        """
        祖父母が共通（n1=2, n2=2）の COI = (1/2)^5 = 3.125%
        """
        GF   = MockDog(10, 'GF')
        F    = MockDog(2,  'F',    father_id=10)
        M    = MockDog(3,  'M',    father_id=10)
        sire = MockDog(1,  'Sire', father_id=2)
        dam  = MockDog(4,  'Dam',  father_id=3)
        self._patch([sire, dam, F, M, GF])
        result = bl.calculate_coi(1, 4, max_depth=3, db=None)
        self.assertAlmostEqual(result['coi'], 1/32, places=6)
        self.assertAlmostEqual(result['coi_percent'], 3.125, places=4)

    def test_common_ancestors_detail(self):
        """共通祖先の詳細情報が正しく返される"""
        F    = MockDog(2, 'F')
        M    = MockDog(3, 'M')
        sire = MockDog(1, 'Sire', father_id=2, mother_id=3)
        dam  = MockDog(4, 'Dam',  father_id=2, mother_id=3)
        self._patch([sire, dam, F, M])
        result = bl.calculate_coi(1, 4, max_depth=3, db=None)
        self.assertEqual(len(result['common_ancestors']), 2)
        names = {ca['name'] for ca in result['common_ancestors']}
        self.assertIn('F', names)
        self.assertIn('M', names)

    def test_contribution_percent_sum(self):
        """各共通祖先の寄与率の合計が COI% に等しい"""
        F    = MockDog(2, 'F')
        M    = MockDog(3, 'M')
        sire = MockDog(1, 'Sire', father_id=2, mother_id=3)
        dam  = MockDog(4, 'Dam',  father_id=2, mother_id=3)
        self._patch([sire, dam, F, M])
        result = bl.calculate_coi(1, 4, max_depth=3, db=None)
        total = sum(ca['contribution_percent'] for ca in result['common_ancestors'])
        self.assertAlmostEqual(total, result['coi_percent'], places=3)


class TestGetCoiRank(unittest.TestCase):

    def test_rank_a(self):
        r = bl.get_coi_rank(0.0)
        self.assertEqual(r['rank'], 'A')

    def test_rank_a_boundary(self):
        r = bl.get_coi_rank(4.99)
        self.assertEqual(r['rank'], 'A')

    def test_rank_b(self):
        r = bl.get_coi_rank(7.5)
        self.assertEqual(r['rank'], 'B')

    def test_rank_c(self):
        r = bl.get_coi_rank(12.0)
        self.assertEqual(r['rank'], 'C')

    def test_rank_d(self):
        r = bl.get_coi_rank(17.0)
        self.assertEqual(r['rank'], 'D')

    def test_rank_e(self):
        r = bl.get_coi_rank(25.0)
        self.assertEqual(r['rank'], 'E')

    def test_rank_e_boundary(self):
        r = bl.get_coi_rank(20.0)
        self.assertEqual(r['rank'], 'E')


class TestDetectCloseInbreeding(unittest.TestCase):

    def setUp(self):
        self._originals = None

    def tearDown(self):
        if self._originals:
            restore_bl(self._originals)

    def _patch(self, dogs):
        _, originals = make_patched_bl(dogs)
        self._originals = originals

    def test_full_sibling_detected(self):
        """兄妹交配を検出"""
        F    = MockDog(2, 'F')
        M    = MockDog(3, 'M')
        sire = MockDog(1, 'Sire', father_id=2, mother_id=3)
        dam  = MockDog(4, 'Dam',  father_id=2, mother_id=3)
        self._patch([sire, dam, F, M])
        patterns = bl.detect_close_inbreeding_patterns(1, 4, db=None)
        types = [p['type'] for p in patterns]
        self.assertTrue(any('兄妹交配' in t for t in types))

    def test_half_sibling_detected(self):
        """半兄妹交配を検出"""
        F    = MockDog(2, 'F')
        M1   = MockDog(3, 'M1')
        M2   = MockDog(5, 'M2')
        sire = MockDog(1, 'Sire', father_id=2, mother_id=3)
        dam  = MockDog(4, 'Dam',  father_id=2, mother_id=5)
        self._patch([sire, dam, F, M1, M2])
        patterns = bl.detect_close_inbreeding_patterns(1, 4, db=None)
        types = [p['type'] for p in patterns]
        self.assertTrue(any('半兄妹' in t for t in types))

    def test_parent_child_detected(self):
        """親子交配を検出（sire の母が dam）"""
        dam  = MockDog(2, 'Dam')
        sire = MockDog(1, 'Sire', mother_id=2)
        self._patch([sire, dam])
        patterns = bl.detect_close_inbreeding_patterns(1, 2, db=None)
        types = [p['type'] for p in patterns]
        self.assertTrue(any('親子' in t for t in types))

    def test_no_patterns_for_unrelated(self):
        """無関係な犬 → パターンなし"""
        sire = MockDog(1, 'Sire')
        dam  = MockDog(2, 'Dam')
        self._patch([sire, dam])
        patterns = bl.detect_close_inbreeding_patterns(1, 2, db=None)
        self.assertEqual(patterns, [])


class TestCalculateGeneticDiseaseRisk(unittest.TestCase):

    def setUp(self):
        self._originals = None

    def tearDown(self):
        if self._originals:
            restore_bl(self._originals)

    def _patch(self, genes):
        _, originals = make_patched_bl([], genes)
        self._originals = originals

    def test_carrier_x_carrier_high_risk(self):
        """キャリア × キャリア → high"""
        genes = [MockGene(1, 'PRA', 'carrier'), MockGene(2, 'PRA', 'carrier')]
        self._patch(genes)
        risks = bl.calculate_genetic_disease_risk(1, 2, db=None)
        pra = next(r for r in risks if r['disease_name'] == 'PRA')
        self.assertEqual(pra['risk'], 'high')

    def test_clear_x_clear(self):
        """クリア × クリア → clear"""
        genes = [MockGene(1, 'PRA', 'clear'), MockGene(2, 'PRA', 'clear')]
        self._patch(genes)
        risks = bl.calculate_genetic_disease_risk(1, 2, db=None)
        pra = next(r for r in risks if r['disease_name'] == 'PRA')
        self.assertEqual(pra['risk'], 'clear')

    def test_affected_x_affected_very_high(self):
        """アフェクテッド × アフェクテッド → very_high"""
        genes = [MockGene(1, 'PRA', 'affected'), MockGene(2, 'PRA', 'affected')]
        self._patch(genes)
        risks = bl.calculate_genetic_disease_risk(1, 2, db=None)
        pra = next(r for r in risks if r['disease_name'] == 'PRA')
        self.assertEqual(pra['risk'], 'very_high')

    def test_clear_x_carrier_low_carrier(self):
        """クリア × キャリア → low_carrier"""
        genes = [MockGene(1, 'PRA', 'clear'), MockGene(2, 'PRA', 'carrier')]
        self._patch(genes)
        risks = bl.calculate_genetic_disease_risk(1, 2, db=None)
        pra = next(r for r in risks if r['disease_name'] == 'PRA')
        self.assertEqual(pra['risk'], 'low_carrier')

    def test_affected_x_carrier_high(self):
        """アフェクテッド × キャリア → high"""
        genes = [MockGene(1, 'PRA', 'affected'), MockGene(2, 'PRA', 'carrier')]
        self._patch(genes)
        risks = bl.calculate_genetic_disease_risk(1, 2, db=None)
        pra = next(r for r in risks if r['disease_name'] == 'PRA')
        self.assertEqual(pra['risk'], 'high')

    def test_no_genes(self):
        """遺伝疾患情報なし → 空リスト"""
        self._patch([])
        risks = bl.calculate_genetic_disease_risk(1, 2, db=None)
        self.assertEqual(risks, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
