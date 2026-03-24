"""
税務年間カレンダー 期限計算ロジック
"""
from datetime import date, timedelta
import calendar


def last_day_of_month(year, month):
    """指定年月の末日を返す"""
    return date(year, month, calendar.monthrange(year, month)[1])


def add_months(dt, months):
    """日付に月数を加算する"""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_corporate_deadlines(fiscal_end_month, year=None):
    """
    法人の税務申告期限一覧を返す
    fiscal_end_month: 決算月（1〜12）
    year: 基準年（Noneの場合は今年）
    """
    if year is None:
        year = date.today().year

    deadlines = []

    # 決算月から2ヶ月後が申告期限
    # 例：3月決算 → 5月末が申告期限
    fiscal_end = last_day_of_month(year, fiscal_end_month)
    # 前期の決算も含める（今年の決算月が過去の場合は来年分も）
    for offset_year in [-1, 0, 1]:
        fy_end_year = year + offset_year
        fy_end = last_day_of_month(fy_end_year, fiscal_end_month)
        fy_start_month = (fiscal_end_month % 12) + 1
        fy_start_year = fy_end_year if fiscal_end_month != 12 else fy_end_year
        if fiscal_end_month == 12:
            fy_start_year = fy_end_year
        else:
            fy_start_year = fy_end_year

        # 法人税・地方法人税申告（決算月末から2ヶ月後末日）
        corp_tax_deadline = last_day_of_month(
            fy_end_year + (1 if fiscal_end_month + 2 > 12 else 0),
            (fiscal_end_month + 2 - 1) % 12 + 1
        )
        deadlines.append({
            'date': corp_tax_deadline,
            'type': '法人税・地方法人税申告',
            'category': 'corporate_tax',
            'color': '#1a237e',
            'fiscal_year_end': fy_end,
        })

        # 消費税申告（決算月末から2ヶ月後末日）
        consumption_deadline = corp_tax_deadline
        deadlines.append({
            'date': consumption_deadline,
            'type': '消費税申告',
            'category': 'consumption_tax',
            'color': '#880e4f',
            'fiscal_year_end': fy_end,
        })

        # 法人住民税・事業税申告（決算月末から2ヶ月後末日）
        deadlines.append({
            'date': corp_tax_deadline,
            'type': '法人住民税・事業税申告',
            'category': 'local_tax',
            'color': '#1b5e20',
            'fiscal_year_end': fy_end,
        })

        # 中間申告（決算月から6ヶ月後の2ヶ月後末日）
        interim_end_month = (fiscal_end_month + 6 - 1) % 12 + 1
        interim_end_year = fy_end_year + (1 if fiscal_end_month + 6 > 12 else 0)
        interim_deadline_month = (interim_end_month + 2 - 1) % 12 + 1
        interim_deadline_year = interim_end_year + (1 if interim_end_month + 2 > 12 else 0)
        interim_deadline = last_day_of_month(interim_deadline_year, interim_deadline_month)
        deadlines.append({
            'date': interim_deadline,
            'type': '法人税中間申告',
            'category': 'interim_tax',
            'color': '#e65100',
            'fiscal_year_end': fy_end,
        })

        # 償却資産申告（毎年1月末）
        deadlines.append({
            'date': date(fy_end_year + 1 if fiscal_end_month > 1 else fy_end_year, 1, 31),
            'type': '償却資産申告',
            'category': 'depreciable_assets',
            'color': '#4a148c',
            'fiscal_year_end': fy_end,
        })

    # 重複除去・ソート
    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x['date']):
        key = (d['date'], d['category'])
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


def get_individual_deadlines(year=None):
    """
    個人（確定申告等）の税務申告期限一覧を返す
    """
    if year is None:
        year = date.today().year

    deadlines = []

    for y in [year - 1, year, year + 1]:
        # 所得税確定申告（3月15日）
        deadlines.append({
            'date': date(y, 3, 15),
            'type': f'所得税確定申告（{y-1}年分）',
            'category': 'income_tax',
            'color': '#1a237e',
            'note': f'{y-1}年1月1日〜12月31日分',
        })

        # 消費税確定申告（3月31日）
        deadlines.append({
            'date': date(y, 3, 31),
            'type': f'消費税確定申告（{y-1}年分）',
            'category': 'consumption_tax',
            'color': '#880e4f',
            'note': f'{y-1}年分',
        })

        # 住民税申告（3月15日）
        deadlines.append({
            'date': date(y, 3, 15),
            'type': f'住民税申告（{y-1}年分）',
            'category': 'resident_tax',
            'color': '#1b5e20',
            'note': f'{y-1}年分',
        })

        # 所得税予定納税（第1期：7月31日）
        deadlines.append({
            'date': date(y, 7, 31),
            'type': f'所得税予定納税 第1期（{y}年）',
            'category': 'estimated_tax',
            'color': '#e65100',
            'note': '',
        })

        # 所得税予定納税（第2期：11月30日）
        deadlines.append({
            'date': date(y, 11, 30),
            'type': f'所得税予定納税 第2期（{y}年）',
            'category': 'estimated_tax',
            'color': '#e65100',
            'note': '',
        })

        # 償却資産申告（1月末）
        deadlines.append({
            'date': date(y, 1, 31),
            'type': f'償却資産申告（{y}年）',
            'category': 'depreciable_assets',
            'color': '#4a148c',
            'note': '',
        })

        # 青色申告承認申請（3月15日または開業から2ヶ月以内）
        # 年末調整（1月31日：源泉徴収票等提出）
        deadlines.append({
            'date': date(y, 1, 31),
            'type': f'源泉徴収票・給与支払報告書提出（{y-1}年分）',
            'category': 'withholding',
            'color': '#006064',
            'note': f'{y-1}年分',
        })

    # 重複除去・ソート
    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x['date']):
        key = (d['date'], d['category'], d['type'])
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


def get_common_deadlines(year=None):
    """
    法人・個人共通の定期的な税務期限（源泉所得税等）
    """
    if year is None:
        year = date.today().year

    deadlines = []

    for y in [year - 1, year, year + 1]:
        # 源泉所得税納付（毎月10日）
        for month in range(1, 13):
            deadlines.append({
                'date': date(y, month, 10),
                'type': f'源泉所得税納付（{y}年{month}月分）',
                'category': 'withholding_tax',
                'color': '#006064',
                'note': f'{y}年{month}月分',
            })

        # 源泉所得税納付（納期特例：1月20日・7月10日）
        deadlines.append({
            'date': date(y, 1, 20),
            'type': f'源泉所得税納付 納期特例（{y-1}年7〜12月分）',
            'category': 'withholding_special',
            'color': '#37474f',
            'note': f'{y-1}年7〜12月分',
        })
        deadlines.append({
            'date': date(y, 7, 10),
            'type': f'源泉所得税納付 納期特例（{y}年1〜6月分）',
            'category': 'withholding_special',
            'color': '#37474f',
            'note': f'{y}年1〜6月分',
        })

    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x['date']):
        key = (d['date'], d['type'])
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


def get_all_deadlines_for_client(client, year=None):
    """
    顧問先1件の全税務期限を返す
    """
    if year is None:
        year = date.today().year

    deadlines = []

    if client.type == '法人':
        fiscal_end = client.fiscal_year_end_month or (
            int(client.fiscal_year_end) if client.fiscal_year_end and client.fiscal_year_end.isdigit() else None
        )
        if fiscal_end:
            for d in get_corporate_deadlines(fiscal_end, year):
                d['client_id'] = client.id
                d['client_name'] = client.name
                d['client_type'] = '法人'
                deadlines.append(d)
    else:
        for d in get_individual_deadlines(year):
            d['client_id'] = client.id
            d['client_name'] = client.name
            d['client_type'] = '個人'
            deadlines.append(d)

    return deadlines


def group_by_month(deadlines):
    """期限一覧を月ごとにグループ化する"""
    grouped = {}
    for d in deadlines:
        key = (d['date'].year, d['date'].month)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(d)
    return dict(sorted(grouped.items()))
