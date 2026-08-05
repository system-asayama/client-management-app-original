# -*- coding: utf-8 -*-
"""
eLTAX（地方税）共通納税 納付情報発行依頼 RPAワーカー【ヒューリスティック試験実行版】

PCdesk（WEB版）に自動ログインし、共通納税の「納付情報発行依頼」を送信して
納付情報（収納機関番号・納付番号・確認番号 等）を取得する。

方針:
- e-Tax 版と同様に、画面要素は「候補セレクタを順に試す」ヒューリスティックで探す。
  事前のセレクタ確定なしでも動かせる代わりに、実画面と合わない箇所で停止し得る。
- 停止時は「どのステップで・どのURL・どの画面か」を error_message に含めて返し、
  実アカウントでの試験実行から不足箇所を特定できるようにする。
- proxy=True のときは eltax_user_id/password を税理士（代理送信者）の認証情報とし、
  target_user_id を代理対象（顧問先）の利用者IDとして指定する。

【前提】
- 「納付情報発行依頼」は署名省略手続きのため電子証明書は不要。
- playwright install chromium --with-deps を事前に実行すること。
"""

import os
import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# PCdesk のログイン入口候補（順に試して最初にログイン画面が出たものを使う）
ENTRY_URLS = [
    "https://www.portal.eltax.lta.go.jp/apa/web/webindexb",   # PCdesk(WEB版)
    "https://portal.pcdesknext.eltax.lta.go.jp/group-u/",     # PCdesk Next（新）
    "https://www.eltax.lta.go.jp/",                            # メインサイト→ログイン導線
]
PCDESK_WEB_TOP_URL = ENTRY_URLS[0]

PAGE_TIMEOUT = 25000
ACTION_TIMEOUT = 12000
FIND_TIMEOUT = 3500

# 試験実行の有効/無効。Falseにすると即ガードで停止する。
ELTAX_RPA_ENABLED = True

# 発行依頼を実際に実行するか。False の間は「納入金確認」まで進めて停止し、
# 発行依頼（納付情報の確定発行）は行わない（安全なテストモード）。
SUBMIT_ISSUE = False


class EltaxRPAError(Exception):
    pass


class EltaxLoginError(EltaxRPAError):
    pass


class EltaxSubmitError(EltaxRPAError):
    pass


def _diag(page):
    """現在ページの診断情報（URL・タイトル・本文抜粋）を返す。"""
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    try:
        body = (page.inner_text("body") or "").strip()
        body = re.sub(r"\s+", " ", body)[:160]
    except Exception:
        body = ""
    try:
        url = page.url
    except Exception:
        url = ""
    return f"URL:{url} / 画面:{title} / 抜粋:{body}"


def _first(page, selectors, timeout=FIND_TIMEOUT):
    """候補セレクタを順に試し、最初に見つかった要素を返す。無ければNone。"""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                return el
        except PlaywrightTimeout:
            continue
        except Exception:
            continue
    return None


def _list_clickables(page):
    """画面上の可視な操作要素のラベルを列挙（診断用。div/li等の擬似ボタンも含む）。"""
    try:
        js = ("els => Array.from(new Set(els.filter(e => e.offsetParent !== null)"
              ".map(e => (e.innerText || e.value || e.getAttribute('alt') || "
              "e.getAttribute('aria-label') || '').replace(/\\s+/g,' ').trim())"
              ".filter(t => t && t.length <= 24))).slice(0, 24)")
        items = page.eval_on_selector_all(
            "button, input[type=submit], input[type=button], input[type=image], a, "
            "[role=button], [role=menuitem], [role=tab], li, [onclick]", js)
        return " | ".join(items)[:300]
    except Exception:
        return ""


def _dump_matching(page, keywords):
    """キーワードを含む可視要素を tag.class:text 形式で列挙（メニュー構造の特定用）。"""
    try:
        js = ("(kw) => Array.from(document.querySelectorAll('body *'))"
              ".filter(e => e.offsetParent !== null)"
              ".map(e => ({t:(e.innerText||'').replace(/\\s+/g,' ').trim(), "
              "tag:e.tagName.toLowerCase(), cls:((e.className||'')+'').trim().split(' ')[0].slice(0,16)}))"
              ".filter(o => o.t && o.t.length<=26 && kw.some(k => o.t.includes(k)))"
              ".slice(0,22).map(o => o.tag+(o.cls?('.'+o.cls):'')+':'+o.t)")
        items = page.evaluate(js, keywords)
        return " | ".join(items)[:420]
    except Exception:
        return ""


def _dump_nav(page):
    """クラス名に nav/menu/tab/gnav/header 等を含む可視要素を列挙（カテゴリ切替の特定用）。"""
    try:
        js = ("() => { const kw=['gnav','global','header','nav','menu','tab','category','p-head'];"
              "return Array.from(document.querySelectorAll('body *'))"
              ".filter(e => e.offsetParent!==null && kw.some(k => (((e.className||'')+'').toLowerCase()).includes(k)))"
              ".slice(0,26)"
              ".map(e => e.tagName.toLowerCase()+'.'+(((e.className||'')+'').trim().split(' ')[0].slice(0,18))"
              "+':'+((e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,16))); }")
        items = page.evaluate(js)
        return " | ".join([x for x in items if x])[:440]
    except Exception:
        return ""


def _nav_click(page, texts):
    """任意要素（div/li/span等の擬似ボタン含む）をテキストで探してクリック。"""
    if _click_text(page, texts, timeout=2500):
        return True
    for t in texts:
        for getter in (lambda: page.get_by_text(t, exact=True), lambda: page.get_by_text(t)):
            try:
                loc = getter()
                n = min(loc.count(), 4)
            except Exception:
                n = 0
            for i in range(n):
                try:
                    h = loc.nth(i).element_handle()
                    if h and _safe_click(page, h):
                        return True
                except Exception:
                    continue
    return False


def _safe_click(page, el):
    """通常クリック→遮られたらJSクリックで確実に発火させる。成功でTrue。"""
    try:
        el.click(timeout=6000)
        clicked = True
    except Exception:
        try:
            el.evaluate("e => e.click()")  # オーバーレイの遮蔽を回避
            clicked = True
        except Exception:
            clicked = False
    if clicked:
        try:
            page.wait_for_load_state("networkidle", timeout=2500)
        except Exception:
            pass
    return clicked


def _click_text(page, texts, timeout=FIND_TIMEOUT):
    """リンク/ボタンのテキストで探してクリック。成功でTrue。"""
    for t in texts:
        for sel in (f'a:has-text("{t}")', f'button:has-text("{t}")',
                    f'input[type="submit"][value*="{t}"]', f'input[type="button"][value*="{t}"]',
                    f'[role="button"]:has-text("{t}")'):
            el = _first(page, [sel], timeout=2000)
            if el and _safe_click(page, el):
                return True
    return False


def run_eltax_payment_request(
    eltax_user_id: str,
    eltax_password: str,
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
    """eLTAX 共通納税「納付情報発行依頼」を実行する。戻り値はe-Tax版と同一契約。"""
    if not ELTAX_RPA_ENABLED:
        return {"status": "error", "payment_code": None, "pdf_path": None,
                "error_message": "eLTAX RPAは無効化されています（ELTAX_RPA_ENABLED=False）。"}

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return {"status": "error", "payment_code": None, "pdf_path": None,
                "error_message": "Playwrightがインストールされていません。"}

    logger.info(
        f"[eLTAX-RPA] request_id={request_id} 開始: {'代理' if proxy else '直接'} "
        f"{tax_type} {fiscal_year}年{fiscal_end_month}月期 {amount:,}円 target={target_user_id}"
    )
    payment_code = None
    pdf_path = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu",
                      "--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
            )
            page = context.new_page()
            page.set_default_timeout(PAGE_TIMEOUT)
            try:
                _login(page, eltax_user_id, eltax_password, request_id)
                _accept_terms(page, request_id)
                if proxy and target_user_id:
                    _select_target_taxpayer(page, target_user_id, request_id)
                _navigate_to_issue_request(page, request_id)
                payment_code = _issue_flow(page, tax_type, filing_type, fiscal_year,
                                           fiscal_end_month, amount, request_id)
            finally:
                try:
                    _click_text(page, ["ログアウト"], timeout=2000)
                except Exception:
                    pass
                context.close()
                browser.close()

        return {"status": "completed", "payment_code": payment_code,
                "pdf_path": pdf_path, "error_message": None}

    except EltaxLoginError as e:
        logger.error(f"[eLTAX-RPA] request_id={request_id} ログインエラー: {e}")
        return {"status": "error", "payment_code": None, "pdf_path": None, "error_message": f"[ログイン] {e}"}
    except EltaxSubmitError as e:
        logger.error(f"[eLTAX-RPA] request_id={request_id} 送信エラー: {e}")
        return {"status": "error", "payment_code": None, "pdf_path": None, "error_message": f"{e}"}
    except Exception as e:
        msg = str(e)
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            logger.error(f"[eLTAX-RPA] request_id={request_id} ブラウザ起動エラー: {e}")
            path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "(未設定)")
            detail = re.sub(r"\s+", " ", msg)[:260]
            return {"status": "error", "payment_code": None, "pdf_path": None,
                    "error_message": f"[ブラウザ起動] BROWSERS_PATH={path} / {detail}"}
        logger.error(f"[eLTAX-RPA] request_id={request_id} 予期しないエラー: {e}", exc_info=True)
        return {"status": "error", "payment_code": None, "pdf_path": None, "error_message": f"予期しないエラー: {e}"}


# ============================================================
# ステップ実装（ヒューリスティック）
# ============================================================

def _login(page, user_id: str, password: str, request_id: int):
    # 候補URLを順に開き、最初にログイン画面（暗証番号欄）が出たものを使う。
    # PCdeskはSPAで「ログイン方式選択（利用者IDを利用してログイン）」を挟むため先に押す。
    pw = None
    last = ""
    for url in ENTRY_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception:
            continue
        # 方式選択があれば「利用者IDを利用してログイン」を押す
        _click_text(page, ["利用者IDを利用してログイン", "利用者IDでログイン", "利用者ID"], timeout=3000)
        pw = _first(page, ['input[type="password"]'], timeout=4000)
        if not pw:
            _click_text(page, ["ログイン", "PCdesk（WEB版）", "PCdesk(WEB版)", "ログインする", "PCdesk"], timeout=3000)
            _click_text(page, ["利用者IDを利用してログイン", "利用者IDでログイン"], timeout=3000)
            pw = _first(page, ['input[type="password"]'], timeout=4000)
        if pw:
            logger.info(f"[eLTAX-RPA] request_id={request_id} ログイン画面到達: {url}")
            break
        last = f"{_diag(page)} / ボタン候補:{_list_clickables(page)}"
    if not pw:
        raise EltaxLoginError(f"ログイン画面（暗証番号欄）が見つかりません。{last}")

    uid = _first(page, [
        'input[name*="riyousha" i]', 'input[id*="riyousha" i]',
        'input[name*="userId" i]', 'input[id*="userId" i]',
        'input[name*="loginId" i]', 'input[id*="loginId" i]',
        'input[name*="user" i]', 'input[type="text"]',
    ], timeout=4000)
    if not uid:
        raise EltaxLoginError(f"利用者ID入力欄が見つかりません。{_diag(page)}")

    uid.fill((user_id or "").replace("-", "").replace(" ", ""))
    pw.fill(password or "")

    if not _click_text(page, ["ログイン", "ログオン", "認証", "送信"], timeout=6000):
        btn = _first(page, ['button[type="submit"]', 'input[type="submit"]',
                            'input[type="image"]', 'button'], timeout=3000)
        if not btn or not _safe_click(page, btn):
            raise EltaxLoginError(f"ログインボタンが見つかりません。ボタン候補:{_list_clickables(page)} / {_diag(page)}")

    body = page.inner_text("body")
    if any(w in body for w in ["利用者ID又は暗証番号", "パスワードが違います", "ログインできません", "認証に失敗"]):
        raise EltaxLoginError(f"利用者IDまたは暗証番号が正しくない可能性があります。{_diag(page)}")


def _accept_terms(page, request_id: int):
    """ログイン直後の利用規約/お知らせ等の同意画面を進める（複数回出る場合に対応）。"""
    for _ in range(4):
        try:
            body = page.inner_text("body")
        except Exception:
            body = ""
        # 同意系の画面かどうか（利用規約・同意）。通常メニューでの誤クリックを避ける。
        if ("利用規約" not in body) and ("同意" not in body):
            break
        # 同意ボタンが下部にある場合に備えて末尾までスクロール
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        # 「同意します」等のチェックボックスがあればチェック
        try:
            cbs = page.query_selector_all('input[type="checkbox"]')
            for cb in cbs:
                try:
                    cb.check()
                except Exception:
                    pass
        except Exception:
            pass
        if _click_text(page, ["同意する", "同意して次へ", "承諾する", "同意", "承諾", "次へ", "OK", "はい"], timeout=4000):
            try:
                page.wait_for_timeout(1200)
            except Exception:
                pass
            continue
        break


def _select_target_taxpayer(page, target_user_id: str, request_id: int):
    """代理送信: 代理人メニュー → 代理行為の実施 → 関与先(顧問先)を利用者IDで選択。"""
    # 代理人メニュータブへ
    _nav_click(page, ["代理人メニュー"])
    try:
        page.wait_for_timeout(1000)
    except Exception:
        pass
    # 代理行為の実施（関与先の納税者へ切替）
    if not _nav_click(page, ["代理行為の実施"]):
        logger.warning(f"[eLTAX-RPA] request_id={request_id} 代理行為の実施が見つからず。{_diag(page)}")
    try:
        page.wait_for_timeout(1200)
    except Exception:
        pass
    # 関与先選択: 利用者IDで検索して選択
    field = _first(page, [
        'input[name*="riyousha" i]', 'input[id*="riyousha" i]',
        'input[name*="userId" i]', 'input[placeholder*="利用者"]', 'input[type="text"]',
    ], timeout=3000)
    if field:
        try:
            field.fill(target_user_id)
            _nav_click(page, ["検索", "表示", "絞り込み"])
            page.wait_for_timeout(800)
        except Exception:
            pass
    # 該当関与先の行を選択して切替
    _nav_click(page, [target_user_id, "選択", "切替", "決定", "確定", "この納税者"])
    try:
        page.wait_for_timeout(1000)
    except Exception:
        pass


def _navigate_to_issue_request(page, request_id: int):
    """上部メニュー「納税」→ 共通納税 → 納付情報発行依頼 へ遷移。"""
    # まず上部カテゴリ「納税」へ（div等の擬似ボタンの可能性があるため _nav_click）
    _nav_click(page, ["納税", "地方税共通納税", "共通納税", "納税メニュー"])
    try:
        page.wait_for_timeout(1000)
    except Exception:
        pass
    # 共通納税の区分へ
    _nav_click(page, ["共通納税", "地方税共通納税"])
    try:
        page.wait_for_timeout(1000)
    except Exception:
        pass
    if not _nav_click(page, ["納付情報発行依頼", "発行依頼", "納付情報の発行",
                             "納付情報登録", "納付情報作成", "納付情報"]):
        raise EltaxSubmitError(
            f"[メニュー] 納付情報発行依頼メニューが見つかりません。"
            f"ナビ:{_dump_nav(page)} / 画面:{page.url}")


def _select_by_partial(page, needle):
    """画面内のセレクトから、ラベルに needle を含む選択肢を選ぶ。"""
    if not needle:
        return
    try:
        sels = page.query_selector_all("select")
    except Exception:
        sels = []
    for s in sels:
        try:
            opts = s.query_selector_all("option")
            for o in opts:
                t = (o.inner_text() or "").strip()
                if needle in t:
                    s.select_option(value=o.get_attribute("value"))
                    return
        except Exception:
            continue


def _issue_flow(page, tax_type, filing_type, fiscal_year, fiscal_end_month, amount, request_id):
    """納付情報発行依頼フロー。
    ① 納付対象申告一覧: 申告区分選択→検索→対象選択→次へ
    ② 納入金一覧: 次へ
    ③ 納入金確認: ここで停止（SUBMIT_ISSUE=False の間は発行依頼を実行しない）
    """
    # ① 申告区分（確定/中間/予定）をセレクトから選ぶ
    kubun = (filing_type or "").replace("申告", "").strip()  # 確定申告→確定
    if kubun:
        _select_by_partial(page, kubun)
    # 検索
    _nav_click(page, ["検索"])
    try:
        page.wait_for_timeout(1800)
    except Exception:
        pass
    # 対象申告を選択（全選択 または 一覧のチェックボックス）
    if not _nav_click(page, ["全選択"]):
        try:
            cb = _first(page, ['table input[type="checkbox"]', 'tbody input[type="checkbox"]',
                               'input[type="checkbox"]'], timeout=3000)
            if cb:
                cb.check()
        except Exception:
            pass
    # 次へ（→ 納入金一覧）
    if not _nav_click(page, ["次へ"]):
        raise EltaxSubmitError(
            f"[入力] 納付対象一覧の「次へ」が押せません。ボタン候補:{_list_clickables(page)} / {_diag(page)}")
    try:
        page.wait_for_timeout(1800)
    except Exception:
        pass
    # ② 納入金一覧 → 次へ（→ 納入金確認）
    _nav_click(page, ["次へ"])
    try:
        page.wait_for_timeout(1800)
    except Exception:
        pass

    # ③ 納入金確認に到達しているか確認して停止（発行依頼はしない）
    try:
        body = page.inner_text("body")
    except Exception:
        body = ""
    if not SUBMIT_ISSUE:
        reached = ("納入金確認" in body) or ("確認" in body and "発行依頼" in body)
        note = "テスト成功: 納入金確認まで到達（発行依頼は未実行）" if reached \
            else f"テスト: 発行依頼手前まで到達（納入金確認の確定は未検出）。{_diag(page)}"
        logger.info(f"[eLTAX-RPA] request_id={request_id} {note}")
        return note

    # SUBMIT_ISSUE=True のときのみ、実際に発行依頼を実行する（将来の本番用）
    _nav_click(page, ["発行依頼", "実行", "確定", "送信"])
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass
    body = page.inner_text("body")
    shuno = re.search(r'収納機関番号[：:\s]*(\d{4,6})', body)
    nofu = re.search(r'納付番号[：:\s]*([0-9\- ]{6,30})', body)
    kakunin = re.search(r'確認番号[：:\s]*([0-9]{4,8})', body)
    parts = [m.group(1) for m in (shuno, nofu, kakunin) if m]
    if parts:
        return "-".join(re.sub(r'\s', '', p) for p in parts)
    return "発行依頼を送信（納付情報の自動抽出は失敗）"
