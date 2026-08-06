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

# e-Tax WEB版のURL（受付システム/e-Taxソフト(WEB版)。順に試す）
ETAX_ENTRY_URLS = [
    "https://clientweb.e-tax.nta.go.jp/UF_WEB/WP000/FCSE00001/SE00S010SCR.do",
    "https://login.e-tax.nta.go.jp/login/reception",
    "https://www.e-tax.nta.go.jp/",
]
ETAX_LOGIN_URL = ETAX_ENTRY_URLS[0]

# タイムアウト設定（ミリ秒）
PAGE_TIMEOUT = 30000   # 30秒
ACTION_TIMEOUT = 15000  # 15秒

# ★安全フラグ: False の間は最終の「送信」を絶対に実行しない。
#   確認画面（送信手前）まで到達したら停止してテスト成功として報告する。
#   本番発行を有効化するときのみ True にすること。
SUBMIT_ISSUE = False


class EtaxRPAError(Exception):
    """e-Tax RPA処理中のエラー"""
    pass


class EtaxLoginError(EtaxRPAError):
    """ログインエラー"""
    pass


class EtaxSubmitError(EtaxRPAError):
    """送信エラー"""
    pass


# 代理送信（税理士のログインで顧問先を指定して発行）の画面手順は実地確認で確定する。
# 未確定のまま代理発行を実行しないよう、既定ではガードする。
PROXY_CONFIRMED = False


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
    target_user_id: str = None,
    proxy: bool = False,
) -> Dict[str, Any]:
    """
    e-Tax 納付情報登録依頼を実行するメイン関数。

    proxy=True の場合は etax_user_id/password を税理士（代理送信者）の認証情報とし、
    target_user_id を代理対象（顧問先）の利用者識別番号として指定する。
    代理での顧問先選択画面は未確定のため、PROXY_CONFIRMED=False の間はガードする。

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
    # 代理発行（税理士ログイン＋顧問先指定）の画面手順は未確定のためガードする
    if proxy and not PROXY_CONFIRMED:
        msg = ("e-Taxの代理発行（税理士ログインで顧問先を指定）は画面手順が未確定のため未実行です。"
               "実アカウントで代理送信の顧問先選択画面を確認し、PROXY_CONFIRMED=True にしてください。")
        logger.warning(f"[RPA] request_id={request_id} {msg}")
        return {"status": "error", "payment_code": None, "pdf_path": None, "error_message": msg}

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return {
            "status": "error",
            "payment_code": None,
            "pdf_path": None,
            "error_message": "Playwrightがインストールされていません。pip install playwright && playwright install chromium を実行してください。",
        }

    logger.info(f"[RPA] request_id={request_id} 処理開始: {'代理' if proxy else '直接'} {tax_type} {filing_type} {fiscal_year}年{fiscal_end_month}月期 {amount:,}円")

    pdf_path = None
    payment_code = None
    shot_path = None  # エラー時のスクリーンショット保存先

    try:
        with sync_playwright() as p:
            # ブラウザ起動（Heroku環境ではheadless必須）
            browser = p.chromium.launch(
                headless=True,
                # Heroku（512MB Dyno）向けのメモリ節約フラグ（OOM強制終了の回避）
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process",
                    "--no-zygote",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
            )
            # 画像・フォント・メディアの読込を遮断（メモリ節約・高速化）
            try:
                context.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in ("image", "font", "media")
                    else route.continue_(),
                )
            except Exception:
                pass
            page = context.new_page()
            page.set_default_timeout(PAGE_TIMEOUT)
            # 確認ダイアログは自動でOK（Playwright既定の自動キャンセル対策）
            try:
                page.on("dialog", lambda d: d.accept())
            except Exception:
                pass

            try:
                # ========================================
                # Step 1: e-Taxにログイン
                # ========================================
                logger.info(f"[RPA] request_id={request_id} Step1: ログイン開始")
                page = _login(page, etax_user_id, etax_password, request_id) or page
                logger.info(f"[RPA] request_id={request_id} Step1: ログイン成功")

                # ========================================
                # Step 2: 納付情報登録依頼メニューへ移動
                # ========================================
                logger.info(f"[RPA] request_id={request_id} Step2: 納付情報登録依頼メニューへ移動")
                _navigate_to_payment_request(page, request_id)

                # ========================================
                # Step 3: 納付情報を入力（SUBMIT_ISSUE=False の間は送信手前で停止）
                # ========================================
                logger.info(f"[RPA] request_id={request_id} Step3: 納付情報入力")
                note = _fill_and_submit_payment_request(
                    page=page,
                    tax_type=tax_type,
                    filing_type=filing_type,
                    fiscal_year=fiscal_year,
                    fiscal_end_month=fiscal_end_month,
                    amount=amount,
                    tax_office_name=tax_office_name,
                    request_id=request_id,
                )
                if note is not None:
                    # テストモード: 送信手前で停止した旨を結果として返す
                    payment_code = note
                else:
                    # ========================================
                    # Step 4: メッセージボックスから納付区分番号通知を取得
                    # ========================================
                    logger.info(f"[RPA] request_id={request_id} Step4: 納付区分番号通知取得")
                    payment_code, pdf_path = _get_payment_code_and_pdf(page, request_id)
                    logger.info(f"[RPA] request_id={request_id} Step4: 納付区分番号={payment_code}")

            except (EtaxLoginError, EtaxSubmitError):
                # エラー時点の画面を保存（/etax/shot/<id> で参照できる）。
                # 「法人の方」は新タブで開くため、最後に開いたタブを撮る。
                try:
                    shot_path = f"/tmp/eltax_error_{request_id}.png"
                    target = context.pages[-1] if context.pages else page
                    target.screenshot(path=shot_path, full_page=True)
                except Exception:
                    shot_path = None
                raise
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
        return {"status": "error", "payment_code": None, "pdf_path": shot_path,
                "error_message": f"[ログイン] {e}"}
    except EtaxSubmitError as e:
        logger.error(f"[RPA] request_id={request_id} 送信エラー: {e}")
        return {"status": "error", "payment_code": None, "pdf_path": shot_path,
                "error_message": f"{e}"}
    except Exception as e:
        msg = str(e)
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            logger.error(f"[RPA] request_id={request_id} ブラウザ未導入: {e}")
            return {"status": "error", "payment_code": None, "pdf_path": None,
                    "error_message": "サーバーに自動ブラウザ（Chromium）が未導入のため実行できません。"
                                     "HerokuにPlaywright用buildpackを追加してブラウザを導入してください（詳細は管理者へ）。"}
        logger.error(f"[RPA] request_id={request_id} 予期しないエラー: {e}", exc_info=True)
        return {"status": "error", "payment_code": None, "pdf_path": None, "error_message": f"予期しないエラー: {e}"}


# ============================================================
# 内部ヘルパー関数
# ============================================================

def _login(page, etax_user_id: str, etax_password: str, request_id: int):
    """e-Taxにログインする（eLTAXで実証済みの堅牢化手法を適用）。

    - 入口URLを順に試し、暗証番号欄が出た画面を使う
    - お知らせ等のダイアログは閉じる
    - 利用者識別番号が4桁×4欄に分割されている画面に対応
    - ログインボタンは完全一致優先（部分一致の誤爆防止）
    - ログイン成功の証跡を検証（未ログインのまま進む事故の防止）
    """
    from app.utils.etax.eltax_rpa_worker import (
        _dismiss_dialogs, _js_click_exact, _first, _click_text, _dump_clickables_rich)

    from app.utils.etax.eltax_rpa_worker import _js_click_text

    user_id_clean = (etax_user_id or "").replace("-", "").replace(" ", "")
    pw_el = None
    last = ""
    for url in ETAX_ENTRY_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception:
            continue
        _dismiss_dialogs(page)
        pw_el = _first(page, ['input[type="password"]'], timeout=4000)
        if not pw_el:
            # トップページ経由（実画面確認済みの動線）:
            # 「ログイン」→ モーダルで「法人の方」を選択 → 法人向けログイン画面
            _js_click_exact(page, "ログイン")
            try:
                page.wait_for_timeout(900)
            except Exception:
                pass
            before = list(page.context.pages)
            _js_click_exact(page, "法人の方")
            try:
                page.wait_for_timeout(2500)
            except Exception:
                pass
            # 新しいタブで開いた場合は操作対象を切り替える
            for pg in page.context.pages:
                if pg not in before:
                    page = pg
                    page.set_default_timeout(PAGE_TIMEOUT)
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                    break
            _dismiss_dialogs(page)
            # ログイン方式の選択（利用者識別番号・暗証番号方式）
            _click_text(page, ["利用者識別番号・暗証番号", "利用者識別番号でログイン",
                               "ID・パスワード方式"], timeout=2500)
            _js_click_text(page, "利用者識別番号")
            pw_el = _first(page, ['input[type="password"]'], timeout=6000)
        if pw_el:
            logger.info(f"[RPA] request_id={request_id} ログイン画面到達: {page.url}")
            break
        last = f"候補:{_dump_clickables_rich(page)}"
    if not pw_el:
        raise EtaxLoginError(f"ログイン画面（暗証番号欄）が見つかりません。{last} / URL:{page.url}")

    # e-Tax受付システムの「環境チェック（拡張機能）」モーダルを閉じる。
    # 次へ/閉じる/img[alt=閉じる] など複数の閉じ方に対応し、
    # モーダルの「次へ」ボタンが消える（=閉じた）まで最大5回試す。
    def _close_env_modal():
        for _ in range(5):
            closed_something = False
            for sel in ('div[role=dialog] img[alt*="閉じる"]',
                        'img.img-fluid[alt*="閉じる"]',
                        'a.btn:has-text("閉じる")', 'button:has-text("閉じる")',
                        'a:has-text("閉じる")'):
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click(timeout=2000)
                        closed_something = True
                        page.wait_for_timeout(500)
                        break
                except Exception:
                    continue
            # モーダル特有の「次へ」ボタンが消えたら閉じ切ったとみなす
            try:
                nxt = page.query_selector('a.btn:has-text("次へ")')
                if not (nxt and nxt.is_visible()):
                    return
            except Exception:
                return
            if not closed_something:
                return
    _close_env_modal()

    # 利用者識別番号: パスワード欄と同じフォーム内のテキスト入力だけを対象にする
    # （ヘッダーの検索窓など無関係な入力欄への誤入力を防ぐ。eLTAXの
    #   関与先ID誤入力事故と同種の問題の予防）
    n_inputs = 0
    try:
        n_inputs = page.evaluate(
            "() => { const pw = document.querySelector('input[type=password]');"
            " if (!pw) return 0;"
            " const form = pw.closest('form') || document.body; let k = 0;"
            " for (const i of form.querySelectorAll('input')) {"
            "   const t = (i.type || 'text').toLowerCase();"
            "   const r = i.getBoundingClientRect();"
            "   if (['text','tel','number'].includes(t) && r.width > 0 && r.height > 0) {"
            "     i.setAttribute('data-rpa-uid', String(k++)); } }"
            " return k; }")
    except Exception:
        n_inputs = 0
    def _dump_login_inputs():
        try:
            return page.evaluate(
                "() => Array.from(document.querySelectorAll('input')).filter(i => {"
                " const r = i.getBoundingClientRect(); return r.width>0 && r.height>0; })"
                ".slice(0,12).map(i => (i.type||'text')+':'+(i.name||i.id||i.placeholder||'')"
                ".slice(0,20)+':val='+((i.value||'').length))")
        except Exception:
            return []

    if n_inputs >= 4 and len(user_id_clean) == 16:
        # 4桁×4欄に分割されている場合
        for k in range(4):
            page.fill(f'input[data-rpa-uid="{k}"]', user_id_clean[k * 4:(k + 1) * 4])
    elif n_inputs >= 1:
        page.fill('input[data-rpa-uid="0"]', user_id_clean)
    else:
        uid_el = _first(page, [
            'input[name*="riyousha" i]', 'input[id*="riyousha" i]',
            'input[name*="shikibetsu" i]', 'input[id*="shikibetsu" i]',
            'input[name*="userId" i]', 'input[id*="userId" i]',
        ], timeout=4000)
        if not uid_el:
            raise EtaxLoginError(f"利用者識別番号の入力欄が見つかりません。候補:{_dump_clickables_rich(page)}")
        uid_el.fill(user_id_clean)
    pw_el.fill(etax_password or "")

    # 入力後に再度モーダルが被っていたら閉じる
    _close_env_modal()

    # 送信時の通信を計測（拡張機能ブロックでsubmitが飛ばないかの判別用）
    from app.utils.etax.eltax_rpa_worker import _install_net_probe, _read_net_probe, _dump_matching
    _install_net_probe(page)
    try:
        page.evaluate("() => { if (window.__netProbe) {"
                      " window.__netProbe.count = 0; window.__netProbe.last=''; } }")
    except Exception:
        pass
    pages_before = len(page.context.pages)

    # ログインボタンは「本物のクリック（trusted event）」で押す。
    # ※JSクリックだと送信ハンドラが発火しない（eLTAX検索ボタンと同種の事象）。
    #   タブの「個人ログイン/法人ログイン」と区別するため name 完全一致で狙う。
    login_url_before = page.url
    clicked = False
    for target in (
        lambda: page.get_by_role("button", name="ログイン", exact=True),
        lambda: page.locator('button.btn:has-text("ログイン")').filter(has_not_text="個人").filter(has_not_text="法人"),
    ):
        try:
            loc = target().first
            loc.scroll_into_view_if_needed(timeout=2000)
            loc.click(timeout=6000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        # フォールバック: パスワード欄でEnter → submit系ボタン
        try:
            pw_el.press("Enter")
            clicked = True
        except Exception:
            btn = _first(page, ['input[type="submit"][value*="ログイン"]',
                                'button[type="submit"]', 'input[type="submit"]'], timeout=3000)
            if btn:
                btn.click()
                clicked = True
    if not clicked:
        raise EtaxLoginError(f"ログインボタンが押せません。候補:{_dump_clickables_rich(page)}")
    # 送信されたか（URL遷移 or ローディング）を確認。遷移しなければ再度Enterを試す。
    try:
        page.wait_for_function("(u) => location.href !== u", arg=login_url_before, timeout=6000)
    except Exception:
        try:
            pw_el.press("Enter")
            page.wait_for_timeout(2500)
        except Exception:
            pass

    # 押下直後の状態を記録（モーダルを閉じる前に）: 通信/新タブ/表示メッセージ
    net_after = _read_net_probe(page)
    pages_after = len(page.context.pages)
    try:
        immediate_msg = _dump_matching(
            page, ["拡張", "確認できません", "できませんでした", "利用できない",
                   "誤", "してください", "エラー"])
    except Exception:
        immediate_msg = ""
    # ログイン後に別タブが開いた場合はそちらに移る
    if pages_after > pages_before:
        try:
            page = page.context.pages[-1]
            page.set_default_timeout(PAGE_TIMEOUT)
            page.wait_for_load_state("domcontentloaded", timeout=6000)
        except Exception:
            pass

    # ログイン結果の確定を待つ（成功の証跡 or エラー文言）
    try:
        page.wait_for_function(
            "() => { const b = document.body ? document.body.innerText : '';"
            " return b.includes('ログアウト') || b.includes('メインメニュー')"
            " || b.includes('メッセージボックス') || b.includes('利用者情報')"
            " || b.includes('誤') || b.includes('ロック'); }",
            timeout=12000)
    except Exception:
        pass
    # 【確定した仕様】e-Tax受付システムのログインは、押下時にブラウザ拡張機能
    # （e-Tax・eLTAX用）で環境チェックを行い、拡張機能が無いとログイン送信自体を
    # ブロックする（実測: 送信POSTは飛ばず、拡張機能エラーのみ表示）。
    # サーバー上のヘッドレスブラウザには拡張機能を導入できないため、
    # この方式での自動ログインは原理的に不可能。明示エラーで停止する。
    if ("拡張機能" in (immediate_msg or "")) or ("確認できません" in (immediate_msg or "")):
        raise EtaxLoginError(
            "e-Taxの自動ログインは実行できません。e-Tax（受付システム）のログインは"
            "『e-Tax・eLTAX用ブラウザ拡張機能』による環境チェックを必須としており、"
            "拡張機能が無い環境ではログイン送信自体がブロックされます"
            "（利用者識別番号・暗証番号は正しく入力されていますが、拡張機能の要求により先へ進めません）。"
            "サーバー上のヘッドレスブラウザには拡張機能を導入できないため、"
            "国税はブラウザ自動操作ではなく e-Tax Web-API 方式への切り替えが必要です。"
            f"画面ID:LA02 / URL:{page.url}")

    # ログイン直後にも環境チェックモーダルが再表示される場合があるので閉じる
    _close_env_modal()
    body = page.inner_text("body")
    # 拡張機能の環境チェックで止まっている場合は、その旨を明示してエラーにする
    if ("拡張機能が利用できない" in body or "確認できませんでした" in body) and \
            not any(w in body for w in ["ログアウト", "メインメニュー", "メッセージボックス"]):
        raise EtaxLoginError(
            "e-Tax（受付システム）のログイン環境チェックで「拡張機能が利用できない」ため"
            "ブロックされました。e-Taxのブラウザ操作は専用のブラウザ拡張機能"
            "（e-Tax・eLTAX用）を必要とし、サーバー上のヘッドレスブラウザには"
            "導入できないため、この方式での自動ログインは実行できません。"
            f"画面:{page.url}")
    if any(w in body for w in ["利用者識別番号又は暗証番号", "利用者識別番号または暗証番号",
                               "誤りがあります", "誤っています", "ログインできません",
                               "認証に失敗", "ロックされています", "パスワードが違います"]):
        msg = _dump_matching(page, ["誤", "できません", "失敗", "ロック"])
        raise EtaxLoginError(f"ログインに失敗しました（利用者識別番号/暗証番号の誤り等）。"
                             f"画面メッセージ:{msg} / 画面:{page.url}")
    if not any(w in body for w in ["ログアウト", "メインメニュー", "メッセージボックス", "利用者情報"]):
        msg = _dump_matching(page, ["してください", "入力", "エラー", "できません", "正しく", "半角"])
        raise EtaxLoginError(
            f"ログイン後の画面を確認できませんでした（未ログインの可能性）。"
            f"送信時通信:{net_after} / 新タブ:{pages_before}→{pages_after} / "
            f"押下直後メッセージ:{immediate_msg} / 現在メッセージ:{msg} / URL:{page.url}")
    # タブを切り替えた場合があるため、操作対象のページを呼び出し元へ返す
    return page


def _navigate_to_payment_request(page, request_id: int):
    """納付情報登録依頼メニューへ移動する。

    想定動線（e-Taxソフト(WEB版)）:
      メインメニュー →「申告・申請・納税」→「新規作成（操作に進む）」
      →「納付情報登録依頼」
    画面が異なる場合に備え、各段階は見つかったものだけ押し、
    最終的に「納付情報登録依頼」へ到達できなければ診断付きでエラーにする。
    """
    from app.utils.etax.eltax_rpa_worker import (
        _dismiss_dialogs, _nav_click, _js_click_text, _dump_clickables_rich)

    _dismiss_dialogs(page)

    def _reached():
        try:
            b = page.inner_text("body")
        except Exception:
            return False
        return ("納付情報登録依頼" in b) and ("税目" in b or "納付金額" in b or "作成" in b)

    # 中間メニューを順に辿る（存在すれば押す）
    for step in (["申告・申請・納税"], ["新規作成", "操作に進む"], ["納付情報登録依頼", "納付情報"]):
        if _nav_click(page, step) or _js_click_text(page, step[0]):
            try:
                page.wait_for_timeout(1200)
            except Exception:
                pass
            _dismiss_dialogs(page)

    # 到達確認（入力画面またはさらに一段の「納付情報登録依頼」リンク）
    if not _reached():
        _nav_click(page, ["納付情報登録依頼"])
        try:
            page.wait_for_timeout(1200)
        except Exception:
            pass
    if not _reached():
        raise EtaxSubmitError(
            f"[メニュー] 納付情報登録依頼への動線が見つかりません。"
            f"候補:{_dump_clickables_rich(page)} / 画面:{page.url}")


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
    """納付情報登録依頼フォームに入力する。

    SUBMIT_ISSUE=False の間は「送信」を絶対に実行せず、確認画面（送信手前）
    到達で停止し、テスト結果の文字列を返す。
    SUBMIT_ISSUE=True で実際に送信した場合は None を返す（Step4へ進む）。
    """
    from app.utils.etax.eltax_rpa_worker import (
        _js_select_option, _fill_period, _nav_click, _js_click_exact,
        _first, _dump_selects, _dump_clickables_rich, _dump_inputs)

    # 税目（例: 法人税、消費税及地方消費税）: 完全一致優先のセレクト選択
    tax_needles = [n for n in (tax_type, "法人税", "消費税") if n]
    picked_tax = None
    for _ in range(16):  # 描画待ち込みで最大約8秒
        for n in tax_needles:
            picked_tax = _js_select_option(page, n, 0)
            if picked_tax:
                break
        if picked_tax:
            break
        try:
            page.wait_for_timeout(500)
        except Exception:
            pass
    logger.info(f"[RPA] request_id={request_id} 税目選択: {picked_tax}")

    # 申告区分（確定/中間）: 連動populateを待って選択
    kubun = ((filing_type or "").replace("申告", "").strip()) or "確定"
    picked_kubun = None
    for _ in range(12):
        picked_kubun = _js_select_option(page, kubun, 0)
        if picked_kubun:
            break
        try:
            page.wait_for_timeout(500)
        except Exception:
            pass
    logger.info(f"[RPA] request_id={request_id} 申告区分選択: {picked_kubun}")

    # 課税期間（和暦の事業年度）: 令和セレクト＋月日入力（存在すれば）
    period_desc = _fill_period(page, fiscal_year, fiscal_end_month)

    # 納付金額
    amt_el = _first(page, ['input[name*="kingaku" i]', 'input[id*="kingaku" i]',
                           'input[name*="noufu" i]', 'input[name*="amount" i]',
                           'input[name*="kin" i]'], timeout=2500)
    if amt_el:
        try:
            amt_el.fill(str(amount))
        except Exception:
            pass

    # 「次へ」「確認」で確認画面へ進む（※「送信」はここでは絶対に押さない）
    for t in ("次へ", "確認", "入力内容の確認", "作成完了"):
        if _js_click_exact(page, t) or _nav_click(page, [t]):
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
            break

    if not SUBMIT_ISSUE:
        try:
            body = page.inner_text("body")
        except Exception:
            body = ""
        amt_str = f"{amount:,}"
        reached = (amt_str in body) or (str(amount) in body) or \
                  ("確認" in body and "送信" in body)
        if reached:
            detail = f"（金額:{amt_str}円 画面反映{'済' if (amt_str in body or str(amount) in body) else '未検出'}）"
            note = f"テスト成功: 送信直前まで到達{detail}（送信＝納付情報登録依頼は未実行）"
        else:
            note = (f"テスト: 送信手前で停止（確認画面は未検出）。"
                    f"税目:{picked_tax} / 申告区分:{picked_kubun} / 期間:{period_desc} / "
                    f"入力欄:{_dump_inputs(page)} / 選択肢:{_dump_selects(page)} / "
                    f"候補:{_dump_clickables_rich(page)} / 画面:{page.url}")
        logger.info(f"[RPA] request_id={request_id} {note}")
        return note

    # ===== SUBMIT_ISSUE=True のときのみ実際に送信する（本番用） =====
    submit_btn = _first(page, ['input[type="submit"][value*="送信"]'], timeout=3000)
    clicked = False
    if submit_btn:
        try:
            submit_btn.click()
            clicked = True
        except Exception:
            pass
    if not clicked:
        clicked = _js_click_exact(page, "送信")
    if not clicked:
        raise EtaxSubmitError(f"送信ボタンが見つかりません。候補:{_dump_clickables_rich(page)}")
    try:
        page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
    except Exception:
        pass
    page_text = page.inner_text("body")
    if any(word in page_text for word in ["送信できません", "入力に誤りがあります"]):
        raise EtaxSubmitError(f"送信エラー: {page_text[:200]}")
    logger.info(f"[RPA] request_id={request_id} 納付情報登録依頼の送信完了")
    return None


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
