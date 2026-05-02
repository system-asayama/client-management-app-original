"""
test_platform_features.py
プラットフォーム機能（plan_guard / breeder_score）のユニットテスト

既存テストと同じスタンドアロン方式：
appパッケージをモック化してからモジュールを直接ロードする。
"""
import sys
import os
import pytest
import importlib.util
from unittest.mock import MagicMock

# appパッケージをモック化（既存テストと同じ方式）
if 'app' not in sys.modules:
    sys.modules['app'] = MagicMock()
if 'app.models_breeder' not in sys.modules:
    sys.modules['app.models_breeder'] = MagicMock()
if 'app.db' not in sys.modules:
    sys.modules['app.db'] = MagicMock()
if 'app.extensions' not in sys.modules:
    sys.modules['app.extensions'] = MagicMock()

# plan_guardを直接ロード
_pg_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'services', 'plan_guard.py')
_pg_spec = importlib.util.spec_from_file_location('plan_guard_module', _pg_path)
pg = importlib.util.module_from_spec(_pg_spec)
_pg_spec.loader.exec_module(pg)

# breeder_scoreを直接ロード
_bs_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'services', 'breeder_score.py')
_bs_spec = importlib.util.spec_from_file_location('breeder_score_module', _bs_path)
bs = importlib.util.module_from_spec(_bs_spec)
_bs_spec.loader.exec_module(bs)


# ─────────────────────────────────────────────
# plan_guard テスト
# ─────────────────────────────────────────────

class TestPlanFeatures:
    """PLAN_FEATURES定数の構造テスト"""

    def test_all_plans_exist(self):
        for plan in ('free', 'standard', 'pro', 'enterprise'):
            assert plan in pg.PLAN_FEATURES, f"プラン '{plan}' が存在しない"

    def test_plan_has_required_keys(self):
        required_keys = ('display_name', 'price_monthly', 'max_dogs', 'max_owners', 'features')
        for plan_name, plan_info in pg.PLAN_FEATURES.items():
            for key in required_keys:
                assert key in plan_info, f"プラン '{plan_name}' に '{key}' がない"

    def test_free_plan_has_dog_limit(self):
        assert pg.PLAN_FEATURES['free']['max_dogs'] is not None
        assert pg.PLAN_FEATURES['free']['max_dogs'] > 0

    def test_paid_plans_have_no_dog_limit(self):
        for plan in ('standard', 'pro', 'enterprise'):
            assert pg.PLAN_FEATURES[plan]['max_dogs'] is None, \
                f"有料プラン '{plan}' は犬数制限なしであるべき"

    def test_features_are_list(self):
        for plan_name, plan_info in pg.PLAN_FEATURES.items():
            assert isinstance(plan_info['features'], list), \
                f"プラン '{plan_name}' の features はリストであるべき"

    def test_enterprise_includes_all_pro_features(self):
        pro_features = set(pg.PLAN_FEATURES['pro']['features'])
        enterprise_features = set(pg.PLAN_FEATURES['enterprise']['features'])
        missing = pro_features - enterprise_features
        assert not missing, f"エンタープライズにProの機能が不足: {missing}"

    def test_pro_includes_all_standard_features(self):
        standard_features = set(pg.PLAN_FEATURES['standard']['features'])
        pro_features = set(pg.PLAN_FEATURES['pro']['features'])
        missing = standard_features - pro_features
        assert not missing, f"ProにStandardの機能が不足: {missing}"

    def test_standard_includes_all_free_features(self):
        free_features = set(pg.PLAN_FEATURES['free']['features'])
        standard_features = set(pg.PLAN_FEATURES['standard']['features'])
        missing = free_features - standard_features
        assert not missing, f"StandardにFreeの機能が不足: {missing}"


class TestCanUseFeature:
    """can_use_feature関数のテスト"""

    def test_free_plan_basic_coi(self):
        assert pg.can_use_feature('free', 'basic_coi') is True

    def test_free_plan_advanced_coi_denied(self):
        assert pg.can_use_feature('free', 'advanced_coi') is False

    def test_standard_plan_advanced_coi(self):
        assert pg.can_use_feature('standard', 'advanced_coi') is True

    def test_standard_plan_breeder_score_denied(self):
        assert pg.can_use_feature('standard', 'breeder_score') is False

    def test_pro_plan_breeder_score(self):
        assert pg.can_use_feature('pro', 'breeder_score') is True

    def test_pro_plan_api_access_denied(self):
        assert pg.can_use_feature('pro', 'api_access') is False

    def test_enterprise_plan_api_access(self):
        assert pg.can_use_feature('enterprise', 'api_access') is True

    def test_unknown_feature_denied(self):
        assert pg.can_use_feature('pro', 'nonexistent_feature') is False

    def test_unknown_plan_defaults_to_free(self):
        # 未知のプランはfreeと同等の制限
        assert pg.can_use_feature('unknown_plan', 'advanced_coi') is False

    def test_owner_app_available_on_all_plans(self):
        for plan in ('free', 'standard', 'pro', 'enterprise'):
            assert pg.can_use_feature(plan, 'owner_app') is True, \
                f"owner_app は全プランで利用可能であるべき（{plan}で失敗）"


class TestGetPlanLimits:
    """get_plan_limits関数のテスト"""

    def test_free_plan_limits(self):
        limits = pg.get_plan_limits('free')
        assert limits['max_dogs'] == 5
        assert limits['max_owners'] == 3

    def test_standard_plan_no_limits(self):
        limits = pg.get_plan_limits('standard')
        assert limits['max_dogs'] is None
        assert limits['max_owners'] is None

    def test_unknown_plan_defaults_to_free(self):
        limits = pg.get_plan_limits('unknown')
        assert limits['max_dogs'] == 5


class TestCheckDogLimit:
    """check_dog_limit関数のテスト（DBモックを使用）"""

    def _make_mock_db(self, count):
        """指定した件数を返すモックDBを作成"""
        class MockRow:
            def __getitem__(self, i):
                return count

        class MockResult:
            def fetchone(self):
                return MockRow()

        class MockDB:
            def execute(self, *args, **kwargs):
                return MockResult()

        return MockDB()

    def test_within_limit(self):
        db = self._make_mock_db(3)
        result = pg.check_dog_limit(db, tenant_id=1, plan_name='free')
        assert result['allowed'] is True
        assert result['current'] == 3
        assert result['max'] == 5

    def test_at_limit(self):
        db = self._make_mock_db(5)
        result = pg.check_dog_limit(db, tenant_id=1, plan_name='free')
        assert result['allowed'] is False

    def test_unlimited_plan(self):
        db = self._make_mock_db(9999)
        result = pg.check_dog_limit(db, tenant_id=1, plan_name='pro')
        assert result['allowed'] is True
        assert result['max'] is None


class TestUpgradeMessages:
    """アップグレードメッセージのテスト"""

    def test_upgrade_message_contains_feature_name(self):
        msg = pg.build_upgrade_message('advanced_coi')
        assert '詳細COI分析' in msg

    def test_upgrade_message_contains_plan_name(self):
        msg = pg.build_upgrade_message('advanced_coi')
        assert 'スタンダード' in msg

    def test_get_upgrade_required_plan_basic_coi(self):
        assert pg.get_upgrade_required_plan('basic_coi') == 'free'

    def test_get_upgrade_required_plan_advanced_coi(self):
        assert pg.get_upgrade_required_plan('advanced_coi') == 'standard'

    def test_get_upgrade_required_plan_breeder_score(self):
        assert pg.get_upgrade_required_plan('breeder_score') == 'pro'

    def test_get_upgrade_required_plan_api_access(self):
        assert pg.get_upgrade_required_plan('api_access') == 'enterprise'


class TestFeatureNames:
    """FEATURE_NAMES定数のテスト"""

    def test_all_features_have_names(self):
        all_features = set()
        for plan_info in pg.PLAN_FEATURES.values():
            all_features.update(plan_info['features'])
        for feat in all_features:
            assert feat in pg.FEATURE_NAMES, f"機能 '{feat}' に日本語名がない"

    def test_feature_names_are_non_empty(self):
        for key, name in pg.FEATURE_NAMES.items():
            assert name, f"機能 '{key}' の名前が空"


# ─────────────────────────────────────────────
# breeder_score テスト
# ─────────────────────────────────────────────

class TestBreederScoreModule:
    """breeder_score.pyのモジュール構造テスト"""

    def test_module_loaded(self):
        assert bs is not None, "breeder_score モジュールがロードされていない"

    def test_calculate_function_exists(self):
        assert hasattr(bs, 'calculate_and_save_breeder_score'), \
            "calculate_and_save_breeder_score関数が存在しない"

    def test_calculate_function_callable(self):
        assert callable(bs.calculate_and_save_breeder_score)

    def test_calculate_breeder_score_exists(self):
        assert hasattr(bs, 'calculate_breeder_score'), \
            "calculate_breeder_score関数が存在しない"

    def test_collect_metrics_exists(self):
        assert hasattr(bs, 'collect_metrics_from_db'), \
            "collect_metrics_from_db関数が存在しない"


class TestBreederScoreCalculation:
    """calculate_breeder_score純粋関数のテスト（DB不要）"""

    def test_score_returns_dict(self):
        result = bs.calculate_breeder_score(
            avg_coi=5.0, puppy_survival_rate=90.0,
            disease_incidence_rate=5.0, breeding_success_rate=80.0,
            data_completeness_rate=80.0, owner_retention_rate=80.0
        )
        assert isinstance(result, dict), "結果はdictであるべき"

    def test_score_has_total_score(self):
        result = bs.calculate_breeder_score(
            avg_coi=5.0, puppy_survival_rate=90.0,
            disease_incidence_rate=5.0, breeding_success_rate=80.0,
            data_completeness_rate=80.0, owner_retention_rate=80.0
        )
        assert 'total_score' in result, "total_scoreキーが存在しない"

    def test_score_range(self):
        result = bs.calculate_breeder_score(
            avg_coi=5.0, puppy_survival_rate=90.0,
            disease_incidence_rate=5.0, breeding_success_rate=80.0,
            data_completeness_rate=80.0, owner_retention_rate=80.0
        )
        total = result.get('total_score', 0)
        assert 0 <= total <= 100, f"スコアは0〜100の範囲であるべき: {total}"

    def test_score_with_no_data(self):
        result = bs.calculate_breeder_score(
            avg_coi=None, puppy_survival_rate=None,
            disease_incidence_rate=None, breeding_success_rate=None,
            data_completeness_rate=None, owner_retention_rate=None
        )
        total = result.get('total_score', 0)
        assert total >= 0, "データなしでもスコアは0以上であるべき"

    def test_score_with_rich_data_higher_than_no_data(self):
        result_empty = bs.calculate_breeder_score(
            avg_coi=None, puppy_survival_rate=None,
            disease_incidence_rate=None, breeding_success_rate=None,
            data_completeness_rate=None, owner_retention_rate=None
        )
        result_rich = bs.calculate_breeder_score(
            avg_coi=1.0, puppy_survival_rate=98.0,
            disease_incidence_rate=1.0, breeding_success_rate=95.0,
            data_completeness_rate=95.0, owner_retention_rate=95.0
        )
        assert result_rich.get('total_score', 0) >= result_empty.get('total_score', 0), \
            "データが豊富なほどスコアが高いべき"

    def test_score_has_rank(self):
        result = bs.calculate_breeder_score(
            avg_coi=1.0, puppy_survival_rate=98.0,
            disease_incidence_rate=1.0, breeding_success_rate=95.0,
            data_completeness_rate=95.0, owner_retention_rate=95.0
        )
        assert 'rank' in result, "rankキーが存在しない"
        assert result['rank'] in ('S', 'A', 'B', 'C', 'D'), \
            f"rankはS/A/B/C/Dのいずれかであるべき: {result['rank']}"

    def test_perfect_score_is_s_rank(self):
        result = bs.calculate_breeder_score(
            avg_coi=0.0, puppy_survival_rate=100.0,
            disease_incidence_rate=0.0, breeding_success_rate=100.0,
            data_completeness_rate=100.0, owner_retention_rate=100.0
        )
        assert result.get('rank') == 'S', \
            f"完璧なデータはSランクであるべき: {result.get('rank')}"


class TestGetRank:
    """get_rank関数のテスト"""

    def test_s_rank_range(self):
        assert bs.get_rank(90) == 'S'
        assert bs.get_rank(100) == 'S'

    def test_a_rank_range(self):
        assert bs.get_rank(75) == 'A'
        assert bs.get_rank(89) == 'A'

    def test_b_rank_range(self):
        assert bs.get_rank(60) == 'B'
        assert bs.get_rank(74) == 'B'

    def test_c_rank_range(self):
        assert bs.get_rank(40) == 'C'
        assert bs.get_rank(59) == 'C'

    def test_d_rank_range(self):
        assert bs.get_rank(0) == 'D'
        assert bs.get_rank(39) == 'D'


# ─────────────────────────────────────────────
# plan_guard モジュール構造テスト
# ─────────────────────────────────────────────

class TestPlanGuardModule:
    """plan_guard.pyのモジュール構造テスト"""

    def test_module_loaded(self):
        assert pg is not None, "plan_guard モジュールがロードされていない"

    def test_required_functions_exist(self):
        required = [
            'can_use_feature', 'check_dog_limit', 'check_owner_limit',
            'get_plan_features', 'get_plan_limits', 'get_upgrade_required_plan',
            'build_upgrade_message', 'log_feature_usage', 'get_plan_context',
            'require_feature',
        ]
        for func_name in required:
            assert hasattr(pg, func_name), \
                f"plan_guard.pyに '{func_name}' が存在しない"

    def test_required_constants_exist(self):
        required = ['PLAN_FEATURES', 'FEATURE_NAMES', 'FEATURE_MIN_PLAN']
        for const_name in required:
            assert hasattr(pg, const_name), \
                f"plan_guard.pyに '{const_name}' が存在しない"
