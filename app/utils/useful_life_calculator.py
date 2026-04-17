"""
耐用年数自動算定モジュール

建築年月日、取得年月日、構造から税法に基づいて耐用年数を自動算定します。
"""

from datetime import date
from typing import Tuple

# 法定耐用年数（構造別）
LEGAL_USEFUL_LIFE = {
    'RC造': 47,
    'RC造（鉄筋コンクリート造）': 47,
    '鉄筋コンクリート造': 47,
    '重量鉄骨造': 34,
    '軽量鉄骨造（肉厚3mm超4mm以下）': 27,
    '軽量鉄骨造（肉厚3mm以下）': 19,
    '軽量鉄骨造': 27,  # デフォルトは27年
    '木造': 22,
}


def calculate_useful_life(
    construction_date: date,
    acquisition_date: date,
    structure: str
) -> Tuple[int, str]:
    """
    耐用年数を自動算定します。
    
    Args:
        construction_date: 建築年月日
        acquisition_date: 取得年月日
        structure: 構造（RC造、重量鉄骨造、軽量鉄骨造、木造など）
    
    Returns:
        (耐用年数, 算定方法) のタプル
        例: (47, '新築') または (39, '中古（簡便法）')
    
    Raises:
        ValueError: 構造が不明な場合、または日付が不正な場合
    """
    # 入力検証
    if not construction_date or not acquisition_date or not structure:
        raise ValueError("建築年月日、取得年月日、構造はすべて必須です")
    
    if acquisition_date < construction_date:
        raise ValueError("取得年月日は建築年月日より後である必要があります")
    
    # 法定耐用年数を取得
    legal_life = LEGAL_USEFUL_LIFE.get(structure)
    if legal_life is None:
        raise ValueError(f"不明な構造: {structure}")
    
    # 経過月数を計算
    elapsed_months = (acquisition_date.year - construction_date.year) * 12 + (acquisition_date.month - construction_date.month)
    
    # 経過年数を計算（月単位で計算し、1年未満切り捨て）
    elapsed_years = elapsed_months // 12
    
    # 新築 or 中古を判定
    # 簡易判定: 建築後1年未満の場合は新築とみなす
    if elapsed_years < 1:
        return legal_life, '新築'
    
    # 中古資産の耐用年数算定（簡便法）
    # 月単位で計算し、1年未満切り捨て
    if elapsed_years >= legal_life:
        # 法定耐用年数の全部を経過している場合
        useful_life_months = int(legal_life * 12 * 0.2)
    else:
        # 法定耐用年数の一部を経過している場合
        useful_life_months = int((legal_life * 12 - elapsed_months) + elapsed_months * 0.2)
    
    # 月単位を年単位に変換（1年未満切り捨て）
    useful_life = useful_life_months // 12
    
    # 最低2年
    useful_life = max(useful_life, 2)
    
    return useful_life, '中古（簡便法）'


def calculate_useful_life_from_strings(
    construction_date_str: str,
    acquisition_date_str: str,
    structure: str
) -> Tuple[int, str]:
    """
    文字列形式の日付から耐用年数を算定します。
    
    Args:
        construction_date_str: 建築年月日（YYYY-MM-DD形式）
        acquisition_date_str: 取得年月日（YYYY-MM-DD形式）
        structure: 構造
    
    Returns:
        (耐用年数, 算定方法) のタプル
    
    Raises:
        ValueError: 日付形式が不正な場合
    """
    try:
        construction_date = date.fromisoformat(construction_date_str)
        acquisition_date = date.fromisoformat(acquisition_date_str)
    except (ValueError, TypeError) as e:
        raise ValueError(f"日付形式が不正です: {e}")
    
    return calculate_useful_life(construction_date, acquisition_date, structure)


# テスト用のメイン関数
if __name__ == '__main__':
    # テストケース
    test_cases = [
        {
            'name': '新築RC造マンション',
            'construction_date': date(2025, 12, 1),
            'acquisition_date': date(2026, 1, 10),
            'structure': 'RC造',
            'expected': (47, '新築'),
        },
        {
            'name': '築10年のRC造マンション',
            'construction_date': date(2016, 1, 1),
            'acquisition_date': date(2026, 1, 1),
            'structure': 'RC造',
            'expected': (39, '中古（簡便法）'),
        },
        {
            'name': '築50年のRC造マンション',
            'construction_date': date(1976, 1, 1),
            'acquisition_date': date(2026, 1, 1),
            'structure': 'RC造',
            'expected': (9, '中古（簡便法）'),
        },
        {
            'name': '築25年の木造アパート',
            'construction_date': date(2001, 1, 1),
            'acquisition_date': date(2026, 1, 1),
            'structure': '木造',
            'expected': (4, '中古（簡便法）'),
        },
        {
            'name': '築15年の重量鉄骨造マンション',
            'construction_date': date(2011, 1, 1),
            'acquisition_date': date(2026, 1, 1),
            'structure': '重量鉄骨造',
            'expected': (22, '中古（簡便法）'),
        },
    ]
    
    print("=" * 80)
    print("耐用年数算定テスト")
    print("=" * 80)
    
    for test in test_cases:
        print(f"\n【{test['name']}】")
        print(f"  建築年月日: {test['construction_date']}")
        print(f"  取得年月日: {test['acquisition_date']}")
        print(f"  構造: {test['structure']}")
        
        result = calculate_useful_life(
            test['construction_date'],
            test['acquisition_date'],
            test['structure']
        )
        
        print(f"  計算結果: {result[0]}年 ({result[1]})")
        print(f"  期待値: {test['expected'][0]}年 ({test['expected'][1]})")
        
        if result == test['expected']:
            print("  ✅ テスト成功")
        else:
            print("  ❌ テスト失敗")
    
    print("\n" + "=" * 80)
