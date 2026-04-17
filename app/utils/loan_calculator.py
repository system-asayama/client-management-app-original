"""
ローン計算ユーティリティ
詳細モードのローン計算ロジックを提供
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date
from dateutil.relativedelta import relativedelta


def calculate_detailed_loan_payment(
    loan_amount: Decimal,
    loan_start_date: date,
    payment_day: int,
    payment_start_ym: str,
    grace_period_end_ym: str,
    first_interest_payment_method: int,
    interest_schedules: list,
    repayment_method: str,
    repayment_period_years: int,
    start_year: int,
    period_years: int
) -> dict:
    """
    詳細モードのローン返済計算
    
    Parameters:
    - loan_amount: 借入金額
    - loan_start_date: 借入日
    - payment_day: 返済日（毎月何日）
    - payment_start_ym: 返済開始年月（YYYY-MM形式）
    - grace_period_end_ym: 据置期間終了年月（YYYY-MM形式、Noneの場合は据置なし）
    - first_interest_payment_method: 初回利息支払方法（1:まとめて, 2:月末に, 3:無視）
    - interest_schedules: 金利スケジュールのリスト [{'開始年月': 'YYYY-MM', '終了年月': 'YYYY-MM' or None, '金利': Decimal}]
    - repayment_method: 返済方法（'元利均等' or '元金均等'）
    - repayment_period_years: 返済期間（年）
    - start_year: シミュレーション開始年度
    - period_years: シミュレーション期間（年）
    
    Returns:
    - dict: 年度ごとの返済データ {year: {'元本返済額': Decimal, '利息': Decimal, '返済額': Decimal, 'ローン残高': Decimal}}
    """
    
    # 返済開始日を計算
    payment_start_date = datetime.strptime(payment_start_ym, '%Y-%m').date()
    payment_start_date = payment_start_date.replace(day=payment_day)
    
    # 据置期間終了日を計算
    if grace_period_end_ym:
        grace_period_end_date = datetime.strptime(grace_period_end_ym, '%Y-%m').date()
        grace_period_end_date = grace_period_end_date.replace(day=payment_day)
    else:
        grace_period_end_date = payment_start_date
    
    # 月次返済スケジュールを生成
    monthly_schedule = []
    current_balance = loan_amount
    current_date = payment_start_date
    total_months = repayment_period_years * 12
    
    # 元金均等の場合の月次元本返済額
    if repayment_method == '元金均等':
        monthly_principal = loan_amount / Decimal(total_months)
    
    for month_idx in range(total_months):
        # 現在の月の金利を取得
        current_rate = get_interest_rate_for_month(current_date, interest_schedules)
        monthly_rate = current_rate / Decimal('100') / Decimal('12')
        
        # 据置期間中かどうか
        is_grace_period = current_date < grace_period_end_date
        
        if is_grace_period:
            # 据置期間中は利息のみ
            interest = (current_balance * monthly_rate).quantize(Decimal('0'), rounding=ROUND_HALF_UP)
            principal = Decimal('0')
            payment = interest
        else:
            # 通常返済
            if repayment_method == '元利均等':
                # 元利均等: 毎月の返済額が一定
                if monthly_rate == 0:
                    payment = loan_amount / Decimal(total_months)
                    interest = Decimal('0')
                    principal = payment
                else:
                    # 残りの返済回数を計算
                    remaining_months = total_months - month_idx
                    payment = (current_balance * monthly_rate * (Decimal('1') + monthly_rate) ** remaining_months / 
                              ((Decimal('1') + monthly_rate) ** remaining_months - Decimal('1'))).quantize(Decimal('0'), rounding=ROUND_HALF_UP)
                    interest = (current_balance * monthly_rate).quantize(Decimal('0'), rounding=ROUND_HALF_UP)
                    principal = payment - interest
            else:
                # 元金均等: 元本部分が一定
                principal = monthly_principal.quantize(Decimal('0'), rounding=ROUND_HALF_UP)
                interest = (current_balance * monthly_rate).quantize(Decimal('0'), rounding=ROUND_HALF_UP)
                payment = principal + interest
        
        monthly_schedule.append({
            'date': current_date,
            'year': current_date.year,
            'month': current_date.month,
            'payment': payment,
            'principal': principal,
            'interest': interest,
            'balance': current_balance - principal
        })
        
        current_balance -= principal
        current_date = current_date + relativedelta(months=1)
    
    # 初回利息の処理
    first_interest = Decimal('0')
    if first_interest_payment_method != 3:  # 無視しない場合
        days_to_first_payment = (payment_start_date - loan_start_date).days
        if days_to_first_payment > 0:
            # 最初の金利を取得
            first_rate = get_interest_rate_for_month(loan_start_date, interest_schedules)
            daily_rate = first_rate / Decimal('100') / Decimal('365')
            first_interest = (loan_amount * daily_rate * Decimal(days_to_first_payment)).quantize(Decimal('0'), rounding=ROUND_HALF_UP)
    
    # 年度ごとに集計
    yearly_data = {}
    for year in range(start_year, start_year + period_years):
        year_payments = [m for m in monthly_schedule if m['year'] == year]
        
        total_payment = sum(m['payment'] for m in year_payments)
        total_principal = sum(m['principal'] for m in year_payments)
        total_interest = sum(m['interest'] for m in year_payments)
        
        # 初回利息の処理
        if year == start_year and first_interest_payment_method == 1:
            # 初回返済時にまとめて支払う
            total_interest += first_interest
            total_payment += first_interest
        elif year == loan_start_date.year and first_interest_payment_method == 2:
            # 借入月末に支払う
            total_interest += first_interest
            total_payment += first_interest
        
        # 年末のローン残高
        if year_payments:
            year_end_balance = year_payments[-1]['balance']
        else:
            year_end_balance = loan_amount
        
        yearly_data[year] = {
            '元本返済額': total_principal,
            '利息': total_interest,
            '返済額': total_payment,
            'ローン残高': year_end_balance
        }
    
    return yearly_data


def get_interest_rate_for_month(target_date: date, interest_schedules: list) -> Decimal:
    """
    指定された月の金利を取得
    
    Parameters:
    - target_date: 対象日
    - interest_schedules: 金利スケジュールのリスト
    
    Returns:
    - Decimal: 金利（%）
    """
    target_ym = target_date.strftime('%Y-%m')
    
    for schedule in interest_schedules:
        start_ym = schedule['開始年月']
        end_ym = schedule['終了年月']
        
        if end_ym:
            if start_ym <= target_ym <= end_ym:
                return schedule['金利']
        else:
            if start_ym <= target_ym:
                return schedule['金利']
    
    # 該当する金利が見つからない場合は最初の金利を返す
    if interest_schedules:
        return interest_schedules[0]['金利']
    
    return Decimal('0')
