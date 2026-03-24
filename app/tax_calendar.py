"""
税務年間カレンダー 期限計算ロジック
土日祝日の場合は翌営業日に自動調整
"""
from datetime import date, timedelta
import calendar


# ========== 祝日判定 ==========

def _get_jp_holidays(year):
    """
    指定年の日本の祝日セットを返す（簡易実装）
    振替休日も含む
    """
    holidays = set()

    def add(d):
        holidays.add(d)

    # 元日
    add(date(year, 1, 1))
    # 成人の日（1月第2月曜）
    add(_nth_weekday(year, 1, 0, 2))
    # 建国記念の日
    add(date(year, 2, 11))
    # 天皇誕生日
    add(date(year, 2, 23))
    # 春分の日（概算：3月20日または21日）
    add(_shunbun(year))
    # 昭和の日
    add(date(year, 4, 29))
    # 憲法記念日
    add(date(year, 5, 3))
    # みどりの日
    add(date(year, 5, 4))
    # こどもの日
    add(date(year, 5, 5))
    # 海の日（7月第3月曜）
    add(_nth_weekday(year, 7, 0, 3))
    # 山の日
    add(date(year, 8, 11))
    # 敬老の日（9月第3月曜）
    add(_nth_weekday(year, 9, 0, 3))
    # 秋分の日（概算：9月22日または23日）
    add(_shubun(year))
    # スポーツの日（10月第2月曜）
    add(_nth_weekday(year, 10, 0, 2))
    # 文化の日
    add(date(year, 11, 3))
    # 勤労感謝の日
    add(date(year, 11, 23))

    # 振替休日の計算（日曜日の祝日 → 翌月曜日）
    base = set(holidays)
    for h in sorted(base):
        if h.weekday() == 6:  # 日曜
            substitute = h + timedelta(days=1)
            while substitute in holidays:
                substitute += timedelta(days=1)
            holidays.add(substitute)

    return holidays


def _nth_weekday(year, month, weekday, n):
    """year年month月のn番目のweekday曜日（weekday: 0=月, 6=日）"""
    first = date(year, month, 1)
    diff = (weekday - first.weekday()) % 7
    return first + timedelta(days=diff + (n - 1) * 7)


def _shunbun(year):
    """春分の日（概算）"""
    day = int(20.8431 + 0.242194 * (year - 1980) - int((year - 1980) / 4))
    return date(year, 3, day)


def _shubun(year):
    """秋分の日（概算）"""
    day = int(23.2488 + 0.242194 * (year - 1980) - int((year - 1980) / 4))
    return date(year, 9, day)


# 祝日キャッシュ
_holiday_cache = {}


def is_holiday(d):
    """土日または祝日かどうか判定"""
    if d.weekday() >= 5:  # 土=5, 日=6
        return True
    if d.year not in _holiday_cache:
        _holiday_cache[d.year] = _get_jp_holidays(d.year)
    return d in _holiday_cache[d.year]


def next_business_day(d):
    """土日祝日の場合は翌営業日を返す"""
    while is_holiday(d):
        d += timedelta(days=1)
    return d


# ========== ユーティリティ ==========

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


def _deadline(d):
    """期限日を翌営業日調整して返す（元の日付も保持）"""
    adjusted = next_business_day(d)
    return adjusted, d  # (調整後, 元の日付)


# ========== 法人税務期限 ==========

def get_corporate_deadlines(fiscal_end_month, year=None,
                            corp_tax_extension=False,
                            consumption_tax_extension=False,
                            prefectural_tax_extension=False,
                            municipal_tax_extension=False):
    """
    法人の税務申告期限一覧を返す
    fiscal_end_month: 決算月（1～12）
    year: 基準年（Noneの場合は今年）
    corp_tax_extension: 法人税申告期限延長の有無
    consumption_tax_extension: 消費税申告期限延長の有無
    prefectural_tax_extension: 法人道府県民税・事業税申告期限延長の有無
    municipal_tax_extension: 法人市町村民税申告期限延長の有無
    """
    if year is None:
        year = date.today().year

    deadlines = []

    for offset_year in [-1, 0, 1]:
        fy_end_year = year + offset_year
        fy_end = last_day_of_month(fy_end_year, fiscal_end_month)

        # 納付期限：決算月末から2ヶ月後末日（延長の有無にかかわらず共通）
        raw_pay = last_day_of_month(
            fy_end_year + (1 if fiscal_end_month + 2 > 12 else 0),
            (fiscal_end_month + 2 - 1) % 12 + 1
        )
        pay_deadline, pay_raw = _deadline(raw_pay)

        # 申告期限：決算月末から3ヶ月後末日（1ヶ月延長後）
        raw_filing = last_day_of_month(
            fy_end_year + (1 if fiscal_end_month + 3 > 12 else 0),
            (fiscal_end_month + 3 - 1) % 12 + 1
        )
        filing_deadline, filing_raw = _deadline(raw_filing)

        # --- 法人税 ---
        if corp_tax_extension:
            deadlines.append({
                'date': filing_deadline,
                'original_date': filing_raw,
                'adjusted': filing_deadline != filing_raw,
                'type': '法人税・地方法人税申告（期限延長）',
                'category': 'corporate_tax_filing',
                'color': '#1a237e',
                'fiscal_year_end': fy_end,
                'note': '申告期限延長適用',
            })
            deadlines.append({
                'date': pay_deadline,
                'original_date': pay_raw,
                'adjusted': pay_deadline != pay_raw,
                'type': '法人税納付（見込み納付）',
                'category': 'corporate_tax_payment',
                'color': '#5c6bc0',
                'fiscal_year_end': fy_end,
                'note': '申告期限延長でも納付期限は延長不可',
            })
        else:
            deadlines.append({
                'date': pay_deadline,
                'original_date': pay_raw,
                'adjusted': pay_deadline != pay_raw,
                'type': '法人税・地方法人税申告',
                'category': 'corporate_tax',
                'color': '#1a237e',
                'fiscal_year_end': fy_end,
            })

        # --- 消費税 ---
        if consumption_tax_extension:
            deadlines.append({
                'date': filing_deadline,
                'original_date': filing_raw,
                'adjusted': filing_deadline != filing_raw,
                'type': '消費税申告（期限延長）',
                'category': 'consumption_tax_filing',
                'color': '#880e4f',
                'fiscal_year_end': fy_end,
                'note': '申告期限延長適用',
            })
            deadlines.append({
                'date': pay_deadline,
                'original_date': pay_raw,
                'adjusted': pay_deadline != pay_raw,
                'type': '消費税納付（見込み納付）',
                'category': 'consumption_tax_payment',
                'color': '#ad1457',
                'fiscal_year_end': fy_end,
                'note': '申告期限延長でも納付期限は延長不可',
            })
        else:
            deadlines.append({
                'date': pay_deadline,
                'original_date': pay_raw,
                'adjusted': pay_deadline != pay_raw,
                'type': '消費税申告',
                'category': 'consumption_tax',
                'color': '#880e4f',
                'fiscal_year_end': fy_end,
            })

        # --- 法人道府県民税・事業税 ---
        if prefectural_tax_extension:
            deadlines.append({
                'date': filing_deadline,
                'original_date': filing_raw,
                'adjusted': filing_deadline != filing_raw,
                'type': '法人道府県民税・事業税申告（期限延長）',
                'category': 'prefectural_tax',
                'color': '#1b5e20',
                'fiscal_year_end': fy_end,
                'note': '申告期限延長適用',
            })
        else:
            deadlines.append({
                'date': pay_deadline,
                'original_date': pay_raw,
                'adjusted': pay_deadline != pay_raw,
                'type': '法人道府県民税・事業税申告',
                'category': 'prefectural_tax',
                'color': '#1b5e20',
                'fiscal_year_end': fy_end,
            })

        # --- 法人市町村民税 ---
        if municipal_tax_extension:
            deadlines.append({
                'date': filing_deadline,
                'original_date': filing_raw,
                'adjusted': filing_deadline != filing_raw,
                'type': '法人市町村民税申告（期限延長）',
                'category': 'municipal_tax',
                'color': '#2e7d32',
                'fiscal_year_end': fy_end,
                'note': '申告期限延長適用',
            })
        else:
            deadlines.append({
                'date': pay_deadline,
                'original_date': pay_raw,
                'adjusted': pay_deadline != pay_raw,
                'type': '法人市町村民税申告',
                'category': 'municipal_tax',
                'color': '#2e7d32',
                'fiscal_year_end': fy_end,
            })

        # 中間申告（決算月から6ヶ月後の2ヶ月後末日）
        interim_end_month = (fiscal_end_month + 6 - 1) % 12 + 1
        interim_end_year = fy_end_year + (1 if fiscal_end_month + 6 > 12 else 0)
        interim_deadline_month = (interim_end_month + 2 - 1) % 12 + 1
        interim_deadline_year = interim_end_year + (1 if interim_end_month + 2 > 12 else 0)
        raw_interim = last_day_of_month(interim_deadline_year, interim_deadline_month)
        interim_deadline, interim_raw = _deadline(raw_interim)
        deadlines.append({
            'date': interim_deadline,
            'original_date': interim_raw,
            'adjusted': interim_deadline != interim_raw,
            'type': '法人税中間申告',
            'category': 'interim_tax',
            'color': '#e65100',
            'fiscal_year_end': fy_end,
        })

        # 償却資産申告（毎年1月末）
        raw_dep = date(fy_end_year + 1 if fiscal_end_month > 1 else fy_end_year, 1, 31)
        dep_deadline, dep_raw = _deadline(raw_dep)
        deadlines.append({
            'date': dep_deadline,
            'original_date': dep_raw,
            'adjusted': dep_deadline != dep_raw,
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


# ========== 個人税務期限 ==========

def get_individual_deadlines(year=None):
    """
    個人（確定申告等）の税務申告期限一覧を返す
    """
    if year is None:
        year = date.today().year

    deadlines = []

    for y in [year - 1, year, year + 1]:
        def add_dl(raw, dtype, category, color, note=''):
            d, r = _deadline(raw)
            deadlines.append({
                'date': d,
                'original_date': r,
                'adjusted': d != r,
                'type': dtype,
                'category': category,
                'color': color,
                'note': note,
            })

        # 所得税確定申告（3月15日）
        add_dl(date(y, 3, 15),
               f'所得税確定申告（{y-1}年分）', 'income_tax', '#1a237e',
               f'{y-1}年1月1日〜12月31日分')

        # 消費税確定申告（3月31日）
        add_dl(date(y, 3, 31),
               f'消費税確定申告（{y-1}年分）', 'consumption_tax', '#880e4f',
               f'{y-1}年分')

        # 住民税申告（3月15日）
        add_dl(date(y, 3, 15),
               f'住民税申告（{y-1}年分）', 'resident_tax', '#1b5e20',
               f'{y-1}年分')

        # 所得税予定納税（第1期：7月31日）
        add_dl(date(y, 7, 31),
               f'所得税予定納税 第1期（{y}年）', 'estimated_tax', '#e65100')

        # 所得税予定納税（第2期：11月30日）
        add_dl(date(y, 11, 30),
               f'所得税予定納税 第2期（{y}年）', 'estimated_tax', '#e65100')

        # 償却資産申告（1月末）
        add_dl(date(y, 1, 31),
               f'償却資産申告（{y}年）', 'depreciable_assets', '#4a148c')

        # 源泉徴収票・給与支払報告書提出（1月31日）
        add_dl(date(y, 1, 31),
               f'源泉徴収票・給与支払報告書提出（{y-1}年分）', 'withholding', '#006064',
               f'{y-1}年分')

    # 重複除去・ソート
    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x['date']):
        key = (d['date'], d['category'], d['type'])
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


# ========== 共通期限（源泉所得税等） ==========

def get_common_deadlines(year=None):
    """
    法人・個人共通の定期的な税務期限（源泉所得税等）
    """
    if year is None:
        year = date.today().year

    deadlines = []

    for y in [year - 1, year, year + 1]:
        # 源泉所得税納付（毎月10日：前月分を納付）
        for month in range(1, 13):
            raw = date(y, month, 10)
            d, r = _deadline(raw)
            # 納付対象は前月分（1月は前年12月分）
            prev_year = y - 1 if month == 1 else y
            prev_month = 12 if month == 1 else month - 1
            deadlines.append({
                'date': d,
                'original_date': r,
                'adjusted': d != r,
                'type': f'源泉所得税納付（{prev_year}年{prev_month}月分）',
                'category': 'withholding_tax',
                'color': '#006064',
                'note': f'{prev_year}年{prev_month}月分',
            })

        # 源泉所得税納付（納期特例：1月20日・7月10日）
        for raw, label in [
            (date(y, 1, 20), f'源泉所得税納付 納期特例（{y-1}年7〜12月分）'),
            (date(y, 7, 10), f'源泉所得税納付 納期特例（{y}年1〜6月分）'),
        ]:
            d, r = _deadline(raw)
            deadlines.append({
                'date': d,
                'original_date': r,
                'adjusted': d != r,
                'type': label,
                'category': 'withholding_special',
                'color': '#37474f',
                'note': label,
            })

    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x['date']):
        key = (d['date'], d['type'])
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


# ========== 顧問先別 源泉所得税期限 ==========

def get_withholding_deadlines_for_client(client, year=None):
    """
    顧問先の給与支払事務所設置届・納期特例設定に応じた源泉所得税期限を返す。

    - salary_office_notification=1 かつ withholding_tax_special=0  → 毎月10日納付
    - salary_office_notification=1 かつ withholding_tax_special=1  → 納期特例（1月20日・7月10日）
    - salary_office_notification=0 → 源泉所得税なし（表示しない）
    """
    if year is None:
        year = date.today().year

    has_salary_office = getattr(client, 'salary_office_notification', 0) or 0
    has_special = getattr(client, 'withholding_tax_special', 0) or 0

    if not has_salary_office:
        return []

    deadlines = []

    def _add(raw, dtype, category, color, note=''):
        d, r = _deadline(raw)
        deadlines.append({
            'date': d,
            'original_date': r,
            'adjusted': d != r,
            'type': dtype,
            'category': category,
            'color': color,
            'note': note,
        })

    for y in [year - 1, year, year + 1]:
        if has_special:
            # 納期特例：1月20日（前年7～12月分）・7月10日（1～6月分）
            _add(date(y, 1, 20),
                 f'源泉所得税納付 納期特例（{y-1}年7～12月分）',
                 'withholding_special', '#37474f',
                 f'{y-1}年7～12月分')
            _add(date(y, 7, 10),
                 f'源泉所得税納付 納期特例（{y}年1～6月分）',
                 'withholding_special', '#37474f',
                 f'{y}年1～6月分')
        else:
            # 毎月10日納付（前月分を納付）
            for month in range(1, 13):
                prev_year = y - 1 if month == 1 else y
                prev_month = 12 if month == 1 else month - 1
                _add(date(y, month, 10),
                     f'源泉所得税納付（{prev_year}年{prev_month}月分）',
                     'withholding_tax', '#006064',
                     f'{prev_year}年{prev_month}月分')

    # 重複除去・ソート
    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x['date']):
        key = (d['date'], d['type'])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


# ========== 顧問先別 特別徴収住民税期限 ==========

def get_inhabitant_tax_deadlines_for_client(client, year=None):
    """
    特別徴収の住民税納付期限を返す。
    - salary_office_notification=1 かつ withholding_tax_special=0  → 毎朆10日（前月分）
    - salary_office_notification=1 かつ withholding_tax_special=1  → 納期特例（6朆10日）
    - salary_office_notification=0 → 表示しない
    """
    if year is None:
        year = date.today().year

    has_salary_office = getattr(client, 'salary_office_notification', 0) or 0
    has_special = getattr(client, 'withholding_tax_special', 0) or 0

    if not has_salary_office:
        return []

    deadlines = []

    def _add(raw, dtype, category, color, note=''):
        d, r = _deadline(raw)
        deadlines.append({
            'date': d,
            'original_date': r,
            'adjusted': d != r,
            'type': dtype,
            'category': category,
            'color': color,
            'note': note,
        })

    for y in [year - 1, year, year + 1]:
        if has_special:
            # 納期特例：6朆10日（前年7月～当年5月分）
            _add(date(y, 6, 10),
                 f'住民税特別徴収納付 納期特例（{y-1}年7月～{y}年5月分）',
                 'inhabitant_tax_special', '#e65100',
                 f'{y-1}年7月～{y}年5月分')
        else:
            # 毎朆10日納付（前月分を納付）
            for month in range(1, 13):
                prev_year = y - 1 if month == 1 else y
                prev_month = 12 if month == 1 else month - 1
                _add(date(y, month, 10),
                     f'住民税特別徴収納付（{prev_year}年{prev_month}月分）',
                     'inhabitant_tax', '#e65100',
                     f'{prev_year}年{prev_month}月分')

    # 重複除去・ソート
    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x['date']):
        key = (d['date'], d['type'])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


# ========== 顧問先別 固定資産税期限 ==========

def get_fixed_asset_tax_deadlines(year=None):
    """
    固定資産税の納付期限を返す。
    標準的な期限：第1期 4月末日、第2期 7月末日、第3期 12月末日、第4期 翌年2月末日
    （実際の期限は市区町村により異なる）
    """
    if year is None:
        year = date.today().year

    deadlines = []

    for y in [year - 1, year, year + 1]:
        periods = [
            (y,     4,  '第1期'),
            (y,     7,  '第2期'),
            (y,    12,  '第3期'),
            (y + 1, 2,  '第4期'),
        ]
        for p_year, p_month, label in periods:
            raw = last_day_of_month(p_year, p_month)
            d, r = _deadline(raw)
            deadlines.append({
                'date': d,
                'original_date': r,
                'adjusted': d != r,
                'type': f'固定資産税・償却資産税納付（{y}年度{label}）',
                'category': 'fixed_asset_tax',
                'color': '#bf360c',
                'note': f'{y}年度{label}（市区町村により期限は異なる場合あり）',
            })

    # 重複除去・ソート
    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x['date']):
        key = (d['date'], d['type'])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


# ========== 顧問先別全期限 ==========

def get_all_deadlines_for_client(client, year=None):
    """
    顧問先１件の全税務期限を返す
    給与支払事務所設置届・納期特例の設定に応じて源泉所得税期限も含む。
    """
    if year is None:
        year = date.today().year

    deadlines = []

    if client.type == '法人':
        fiscal_end = client.fiscal_year_end_month or (
            int(client.fiscal_year_end) if client.fiscal_year_end and client.fiscal_year_end.isdigit() else None
        )
        if fiscal_end:
            corp_ext = bool(getattr(client, 'corp_tax_extension', 0) or 0)
            cons_ext = bool(getattr(client, 'consumption_tax_extension', 0) or 0)
            pref_ext = bool(getattr(client, 'prefectural_tax_extension', 0) or 0)
            muni_ext = bool(getattr(client, 'municipal_tax_extension', 0) or 0)
            for d in get_corporate_deadlines(
                fiscal_end, year,
                corp_tax_extension=corp_ext,
                consumption_tax_extension=cons_ext,
                prefectural_tax_extension=pref_ext,
                municipal_tax_extension=muni_ext
            ):
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

    # 源泉所得税期限（給与支払事務所設置届の有無に応じて追加）
    for d in get_withholding_deadlines_for_client(client, year):
        d['client_id'] = client.id
        d['client_name'] = client.name
        d['client_type'] = client.type or ''
        deadlines.append(d)

    # 特別徴収住民税期限（給与支払事務所設置届の有無に応じて追加）
    for d in get_inhabitant_tax_deadlines_for_client(client, year):
        d['client_id'] = client.id
        d['client_name'] = client.name
        d['client_type'] = client.type or ''
        deadlines.append(d)

    # 固定資産税期限（has_fixed_asset_tax=1 または has_depreciable_asset_tax=1 の場合に追加）
    # 固定資産税・償却資産税の納付期限は同じ時期なので、どちらかがあれば表示する
    if bool(getattr(client, 'has_fixed_asset_tax', 0) or 0) or bool(getattr(client, 'has_depreciable_asset_tax', 0) or 0):
        for d in get_fixed_asset_tax_deadlines(year):
            d['client_id'] = client.id
            d['client_name'] = client.name
            d['client_type'] = client.type or ''
            deadlines.append(d)

    # 償却資産税申告期限（has_depreciable_asset_tax=1 の場合のみ追加）
    # 法人の get_corporate_deadlines 内の償却資産申告は常に追加されるため、
    # 顧問先フラグがない場合は除去する
    if client.type == '法人' and not bool(getattr(client, 'has_depreciable_asset_tax', 0) or 0):
        deadlines = [d for d in deadlines if d.get('category') != 'depreciable_assets']

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
