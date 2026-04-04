# -*- coding: utf-8 -*-
"""
e-Tax 納付情報登録依頼 RPAワーカー
Playwrightを使用してe-TaxのWEB版に自動ログインし、
納付情報登録依頼を送信して納付区分番号を取得する。

【前提条件】
- e-TaxのWEB版（https://clientweb.e-tax.nta.go.jp/）を使用
- 利用者識別番号（16桁）と暗証番号でログイン
- 電子署名不要（納付情報登録依頼は電子証明書なしで送信可能）

【実行環境】
- playwright install chromium --with-deps を事前に実行すること
- Heroku上ではbuildpackの追加が必要:
    heroku buildpacks:add --index 1 https://github.com/mxschmitt/heroku-playwright-buildpack
"""

import os
import re
import time
import logging
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# e-Tax WEB版のURL
ETAX_LOGIN_URL = "https://clientweb.e-tax.nta.go.jp/UF_WEB/WP000/FCSE00001/SE00S010SCR.do"
ETAX_TOP_URL = "https://clientweb.e-tax.nta.go.jp/UF_WEB/WP000/FCSE00001/SE00S010SCR.do"

# タイムアウト設定（ミリ秒）
PAGE_TIMEOUT = 60000   # 60秒
ACTION_TIMEOUT = 30000  # 30秒


class EtaxRPAError(Exception):
    """e-Tax RPA処理中のエラー"""
    pass


class EtaxLoginError(EtaxRPAError):
    """ログインエラー"""
    pass


class EtaxSubmitError(EtaxRPAError):
    """送信エラー"""
    pass


def run_etax_payment_request(
    etax_user_id: str,
    etax_password: str,
    tax_type: str,
    filing_type: str,
    fiscal_year: int,
    fiscal_end_month: int,
    amount: int,
    tax_office_name: str,
    request_id: int,
) -> Dict[str, Any]:
    """
    e-Tax 納付情報登録依頼を実行するメイン関数。

    Args:
        etax_user_id: e-Tax 利用者識別番号（16桁）
        etax_password: e-Tax 暗証番号
        tax_type: 税目（例: "消費税及地方消費税", "法人税"）
        filing_type: 申告区分（例: "確定申告", "中間申告"）
        fiscal_year: 対象決算年度（例: 2025）
        fiscal_end_month: 対象決算月（例: 3）
        amount: 納付金額（円）
        tax_office_name: 提出先税務署名
        request_id: TEtaxRequest.id（ログ用）

    Returns:
        dict: {
            "status": "completed" or "error",
            "payment_code": "収納機関番号-納付番号-確認番号" or None,
            "pdf_path": "/tmp/etax_xxx.pdf" or None,
            "error_message": str or None,
        }
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return {
            "status": "error",
            "payment_code": None,
            "pdf_path": None,
            "error_message": "Playwrightがインストールされていません。pip install playwright && playwright install chromium を実行してください。",
        }

    logger.info(f"[RPA] request_id={request_id} 処理開始: {tax_type} {filing_type} {fiscal_year}年{fiscal_end_month}月期 {amount:,}円")

    pdf_path = None
    payment_code = None

    try:
        with sync_playwright() as p:
            # ブラウザ起動（Heroku環境ではheadless必須）
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ja-JP",
            )
            page = context.new_page()
            page.set_default_timeout(PAGE_TIMEOUT)

            try:
                # ========================================
                # Step 1: e-Taxにログイン
                # ========================================
                logger.info(f"[RPA] request_id={request_id} Step1: ログイン開始")
                _login(page, etax_user_id, etax_password, request_id)
                logger.info(f"[RPA] request_id={request_id} Step1: ログイン成功")

                # ========================================
                # Step 2: 納付情報登録依頼メニューへ移動
                # ========================================
                logger.info(f"[RPA] request_id={request_id} Step2: 納付情報登録依頼メニューへ移動")
                _navigate_to_payment_request(page, request_id)

                # ========================================
                # Step 3: 納付情報を入力して送信
                # ========================================
                logger.info(f"[RPA] request_id={request_id} Step3: 納付情報入力・送信")
                _fill_and_submit_payment_request(
                    page=page,
                    tax_type=tax_type,
                    filing_type=filing_type,
                    fiscal_year=fiscal_year,
                    fiscal_end_month=fiscal_end_month,
                    amount=amount,
                    tax_office_name=tax_office_name,
                    request_id=request_id,
                )

                # ========================================
                # Step 4: メッセージボックスから納付区分番号通知を取得
                # ========================================
                logger.info(f"[RPA] request_id={request_id} Step4: 納付区分番号通知取得")
                payment_code, pdf_path = _get_payment_code_and_pdf(page, request_id)
                logger.info(f"[RPA] request_id={request_id} Step4: 納付区分番号={payment_code}")

            finally:
                # ========================================
                # Step 5: ログアウト
                # ========================================
                try:
                    _logout(page)
                    logger.info(f"[RPA] request_id={request_id} ログアウト完了")
                except Exception as logout_err:
                    logger.warning(f"[RPA] request_id={request_id} ログアウト中にエラー（無視）: {logout_err}")

                context.close()
                browser.close()

        return {
            "status": "completed",
            "payment_code": payment_code,
            "pdf_path": pdf_path,
            "error_message": None,
        }

    except EtaxLoginError as e:
        logger.error(f"[RPA] request_id={request_id} ログインエラー: {e}")
        return {"status": "error", "payment_code": None, "pdf_path": None, "error_message": f"ログインエラー: {e}"}
    except EtaxSubmitError as e:
        logger.error(f"[RPA] request_id={request_id} 送信エラー: {e}")
        return {"status": "error", "payment_code": None, "pdf_path": None, "error_message": f"送信エラー: {e}"}
    except Exception as e:
        logger.error(f"[RPA] request_id={request_id} 予期しないエラー: {e}", exc_info=True)
        return {"status": "error", "payment_code": None, "pdf_path": None, "error_message": f"予期しないエラー: {e}"}


# ============================================================
# 内部ヘルパー関数
# ============================================================

def _login(page, etax_user_id: str, etax_password: str, request_id: int):
    """e-Taxにログインする"""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        page.goto(ETAX_LOGIN_URL, wait_until="networkidle")
    except Exception:
        page.goto(ETAX_LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")

    # 利用者識別番号の入力（ハイフンなし16桁）
    user_id_clean = etax_user_id.replace("-", "").replace(" ", "")

    try:
        # 利用者識別番号フィールドを探す（複数のセレクタを試みる）
        user_id_selectors = [
            'input[name="userId"]',
            'input[name="riyoushaShikibetsubangou"]',
            'input[id*="userId"]',
            'input[id*="shikibetsu"]',
            'input[type="text"]:first-of-type',
        ]
        user_id_input = None
        for selector in user_id_selectors:
            try:
                user_id_input = page.wait_for_selector(selector, timeout=5000)
                if user_id_input:
                    break
            except PlaywrightTimeout:
                continue

        if not user_id_input:
            raise EtaxLoginError("利用者識別番号の入力フィールドが見つかりません")

        user_id_input.fill(user_id_clean)

        # 暗証番号フィールド
        password_selectors = [
            'input[name="password"]',
            'input[name="anshougou"]',
            'input[type="password"]',
        ]
        password_input = None
        for selector in password_selectors:
            try:
                password_input = page.wait_for_selector(selector, timeout=5000)
                if password_input:
                    break
            except PlaywrightTimeout:
                continue

        if not password_input:
            raise EtaxLoginError("暗証番号の入力フィールドが見つかりません")

        password_input.fill(etax_password)

        # ログインボタンをクリック
        login_selectors = [
            'input[type="submit"][value*="ログイン"]',
            'button:has-text("ログイン")',
            'input[type="submit"]',
            'button[type="submit"]',
        ]
        login_btn = None
        for selector in login_selectors:
            try:
                login_btn = page.wait_for_selector(selector, timeout=3000)
                if login_btn:
                    break
            except PlaywrightTimeout:
                continue

        if not login_btn:
            raise EtaxLoginError("ログインボタンが見つかりません")

        login_btn.click()
        page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)

        # ログイン失敗チェック
        page_text = page.inner_text("body")
        if any(word in page_text for word in ["エラー", "利用者識別番号又は暗証番号が違います", "ログインできません"]):
            raise EtaxLoginError("利用者識別番号または暗証番号が正しくありません")

    except EtaxLoginError:
        raise
    except Exception as e:
        raise EtaxLoginError(f"ログイン処理中にエラーが発生しました: {e}")


def _navigate_to_payment_request(page, request_id: int):
    """納付情報登録依頼メニューへ移動する"""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        # メインメニューから「申告・申請・納税」→「納付情報登録依頼」へ
        # e-TaxのWEB版のメニュー構造に合わせてセレクタを調整
        menu_selectors = [
            'a:has-text("納付情報登録依頼")',
            'a:has-text("納付情報")',
            'input[value*="納付情報登録依頼"]',
        ]
        for selector in menu_selectors:
            try:
                link = page.wait_for_selector(selector, timeout=5000)
                if link:
                    link.click()
                    page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                    return
            except PlaywrightTimeout:
                continue

        # 直接URLで移動を試みる（e-TaxのWEB版の実際のURLに合わせて調整が必要）
        logger.warning(f"[RPA] request_id={request_id} 納付情報登録依頼メニューが見つかりません。URLで直接移動を試みます。")
        raise EtaxSubmitError("納付情報登録依頼メニューへの移動に失敗しました。e-TaxのUI変更の可能性があります。")

    except EtaxSubmitError:
        raise
    except Exception as e:
        raise EtaxSubmitError(f"メニュー移動中にエラー: {e}")


def _fill_and_submit_payment_request(
    page,
    tax_type: str,
    filing_type: str,
    fiscal_year: int,
    fiscal_end_month: int,
    amount: int,
    tax_office_name: str,
    request_id: int,
):
    """納付情報登録依頼フォームに入力して送信する"""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        # 税目の選択
        tax_type_selectors = [
            'select[name*="zeiMoku"]',
            'select[name*="taxType"]',
            'select[name*="税目"]',
        ]
        for selector in tax_type_selectors:
            try:
                select_el = page.wait_for_selector(selector, timeout=5000)
                if select_el:
                    select_el.select_option(label=tax_type)
                    break
            except PlaywrightTimeout:
                continue

        page.wait_for_timeout(500)

        # 申告区分の選択
        filing_type_selectors = [
            'select[name*="shinkokuKubun"]',
            'select[name*="filingType"]',
            'select[name*="申告区分"]',
        ]
        for selector in filing_type_selectors:
            try:
                select_el = page.wait_for_selector(selector, timeout=5000)
                if select_el:
                    select_el.select_option(label=filing_type)
                    break
            except PlaywrightTimeout:
                continue

        page.wait_for_timeout(500)

        # 課税期間（年度・月）の入力
        year_selectors = [
            'input[name*="nendo"]',
            'input[name*="year"]',
            'input[name*="年度"]',
        ]
        for selector in year_selectors:
            try:
                input_el = page.wait_for_selector(selector, timeout=3000)
                if input_el:
                    input_el.fill(str(fiscal_year))
                    break
            except PlaywrightTimeout:
                continue

        month_selectors = [
            'select[name*="tsuki"]',
            'input[name*="month"]',
            'select[name*="月"]',
        ]
        for selector in month_selectors:
            try:
                el = page.wait_for_selector(selector, timeout=3000)
                if el:
                    tag = el.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        el.select_option(value=str(fiscal_end_month))
                    else:
                        el.fill(str(fiscal_end_month))
                    break
            except PlaywrightTimeout:
                continue

        # 納付金額の入力
        amount_selectors = [
            'input[name*="noufuKingaku"]',
            'input[name*="amount"]',
            'input[name*="金額"]',
            'input[type="text"][name*="kin"]',
        ]
        for selector in amount_selectors:
            try:
                input_el = page.wait_for_selector(selector, timeout=3000)
                if input_el:
                    input_el.fill(str(amount))
                    break
            except PlaywrightTimeout:
                continue

        page.wait_for_timeout(500)

        # 送信ボタンをクリック
        submit_selectors = [
            'input[type="submit"][value*="送信"]',
            'button:has-text("送信")',
            'input[value*="登録"]',
            'button:has-text("登録")',
        ]
        submit_btn = None
        for selector in submit_selectors:
            try:
                submit_btn = page.wait_for_selector(selector, timeout=3000)
                if submit_btn:
                    break
            except PlaywrightTimeout:
                continue

        if not submit_btn:
            raise EtaxSubmitError("送信ボタンが見つかりません")

        submit_btn.click()
        page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)

        # 送信結果の確認
        page_text = page.inner_text("body")
        if any(word in page_text for word in ["エラー", "送信できません", "入力に誤りがあります"]):
            raise EtaxSubmitError(f"送信エラー: {page_text[:200]}")

        logger.info(f"[RPA] request_id={request_id} 納付情報登録依頼の送信完了")

    except EtaxSubmitError:
        raise
    except Exception as e:
        raise EtaxSubmitError(f"フォーム入力・送信中にエラー: {e}")


def _get_payment_code_and_pdf(page, request_id: int):
    """
    メッセージボックスから納付区分番号通知を取得し、
    PDFとして保存して納付区分番号を返す。

    Returns:
        (payment_code: str, pdf_path: str)
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    payment_code = None
    pdf_path = None

    try:
        # メッセージボックスへ移動
        msg_box_selectors = [
            'a:has-text("メッセージボックス")',
            'a:has-text("受信通知")',
            'input[value*="メッセージボックス"]',
        ]
        for selector in msg_box_selectors:
            try:
                link = page.wait_for_selector(selector, timeout=5000)
                if link:
                    link.click()
                    page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                    break
            except PlaywrightTimeout:
                continue

        # 納付区分番号通知を探す
        notice_selectors = [
            'a:has-text("納付区分番号通知")',
            'td:has-text("納付区分番号通知")',
        ]
        for selector in notice_selectors:
            try:
                notice_link = page.wait_for_selector(selector, timeout=10000)
                if notice_link:
                    notice_link.click()
                    page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                    break
            except PlaywrightTimeout:
                continue

        # ページテキストから納付区分番号を抽出
        page_text = page.inner_text("body")

        # 収納機関番号（5桁）- 納付番号（20桁）- 確認番号（6桁）のパターンを探す
        # 実際のフォーマットはe-Taxの通知書に準拠
        patterns = [
            r'収納機関番号[：:\s]*(\d{5})',
            r'納付番号[：:\s]*(\d{20})',
            r'確認番号[：:\s]*(\d{6})',
            r'(\d{5}[-\s]\d{20}[-\s]\d{6})',  # 一括パターン
        ]

        parts = []
        for pattern in patterns[:3]:
            match = re.search(pattern, page_text)
            if match:
                parts.append(match.group(1))

        if len(parts) == 3:
            payment_code = f"{parts[0]}-{parts[1]}-{parts[2]}"
        elif len(parts) > 0:
            payment_code = "-".join(parts)
        else:
            # 一括パターンで試みる
            match = re.search(patterns[3], page_text)
            if match:
                payment_code = match.group(1)
            else:
                logger.warning(f"[RPA] request_id={request_id} 納付区分番号を自動抽出できませんでした")
                payment_code = "要確認（メッセージボックスを直接確認してください）"

        # PDFとして保存
        try:
            pdf_path = os.path.join(tempfile.gettempdir(), f"etax_payment_{request_id}_{int(time.time())}.pdf")
            page.pdf(path=pdf_path, format="A4", print_background=True)
            logger.info(f"[RPA] request_id={request_id} PDF保存完了: {pdf_path}")
        except Exception as pdf_err:
            logger.warning(f"[RPA] request_id={request_id} PDF保存に失敗しました: {pdf_err}")
            pdf_path = None

    except Exception as e:
        logger.warning(f"[RPA] request_id={request_id} 納付区分番号取得中にエラー（処理は継続）: {e}")

    return payment_code, pdf_path


def _logout(page):
    """e-Taxからログアウトする"""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    logout_selectors = [
        'a:has-text("ログアウト")',
        'input[value*="ログアウト"]',
        'button:has-text("ログアウト")',
    ]
    for selector in logout_selectors:
        try:
            btn = page.wait_for_selector(selector, timeout=3000)
            if btn:
                btn.click()
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                return
        except PlaywrightTimeout:
            continue
