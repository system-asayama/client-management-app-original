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


def _dump_menu_items(page):
    """メニューのセクション見出し・項目名（p-menu-link/c-menu-guidance）を全列挙。"""
    try:
        js = ("() => Array.from(document.querySelectorAll("
              "'[class*=menu-guidance],[class*=menu-link__ttl],[class*=menu-link__btn]'))"
              ".filter(e => e.offsetParent !== null)"
              ".map(e => (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,28))"
              ".filter(Boolean).slice(0,30)")
        return " | ".join(page.evaluate(js))[:480]
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
    shot_path = None  # エラー時のスクリーンショット保存先

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                # Heroku（512MB Dyno）向けにメモリ使用量を抑える。
                # --single-process/--no-zygote でプロセス数を減らしOOM強制終了を回避。
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu",
                      "--single-process", "--no-zygote",
                      "--disable-extensions", "--disable-background-networking",
                      "--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
            )
            # 画像・フォント・メディアの読込を遮断（メモリ節約・高速化）。
            # SPAの動作に必要なJS/XHR/CSS/documentは通す。
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
            # JSの確認ダイアログ(confirm/alert)は自動で「OK」にする。
            # ※Playwrightの既定は自動キャンセルのため、検索・遷移時に確認が
            #   出ていると処理が無言で中断される（通信0回の一因になり得る）。
            try:
                page.on("dialog", lambda d: d.accept())
            except Exception:
                pass
            try:
                _login(page, eltax_user_id, eltax_password, request_id)
                _accept_terms(page, request_id)
                if proxy and target_user_id:
                    _select_target_taxpayer(page, target_user_id, request_id)
                _navigate_to_issue_request(page, request_id)
                payment_code = _issue_flow(page, tax_type, filing_type, fiscal_year,
                                           fiscal_end_month, amount, request_id)
            except (EltaxLoginError, EltaxSubmitError):
                # エラー時点の画面を保存（アプリからリンクで確認できるようにする）
                try:
                    shot_path = f"/tmp/eltax_error_{request_id}.png"
                    page.screenshot(path=shot_path, full_page=True)
                except Exception:
                    shot_path = None
                raise
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
        return {"status": "error", "payment_code": None, "pdf_path": shot_path,
                "error_message": f"[ログイン] {e}"}
    except EltaxSubmitError as e:
        logger.error(f"[eLTAX-RPA] request_id={request_id} 送信エラー: {e}")
        return {"status": "error", "payment_code": None, "pdf_path": shot_path,
                "error_message": f"{e}"}
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
        # お知らせ等のダイアログが被さっていたら先に閉じる
        _dismiss_dialogs(page)
        # 方式選択があれば「利用者IDを利用してログイン」を押す
        # ※「利用者ID」単体は「利用者IDをお忘れの方はこちら」に誤マッチするため使わない
        _click_text(page, ["利用者IDを利用してログイン", "利用者IDでログイン"], timeout=3000)
        pw = _first(page, ['input[type="password"]'], timeout=4000)
        if not pw:
            # 「ログイン」は完全一致のみ（部分一致は「ログインなし」等に誤爆する）
            if not _js_click_exact(page, "ログイン"):
                _click_text(page, ["PCdesk（WEB版）", "PCdesk(WEB版)", "ログインする"], timeout=3000)
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

    _dismiss_dialogs(page)
    # ログインボタンは必ず「完全一致」で押す。
    # has-text の部分一致だと「申請・届出（ログインなし）」等の別リンクを
    # 誤クリックし、未ログインのまま進んでしまう（実測で確認済みの事故）。
    clicked = False
    btn = _first(page, ['button.f-login-button', 'button[class*="login-button"]'], timeout=2500)
    if btn and _safe_click(page, btn):
        clicked = True
    if not clicked:
        clicked = _js_click_exact(page, "ログイン")
    if not clicked:
        btn = _first(page, ['button[type="submit"]', 'input[type="submit"]',
                            'input[type="image"]'], timeout=2500)
        clicked = bool(btn and _safe_click(page, btn))
    if not clicked:
        raise EltaxLoginError(f"ログインボタンが見つかりません。ボタン候補:{_list_clickables(page)} / {_diag(page)}")

    # ログイン結果が確定するまで待つ:
    #   成功 → ヘッダーに「氏名又は名称」等が出る／利用規約(同意)画面へ遷移
    #   失敗 → エラー文言が表示される
    try:
        page.wait_for_function(
            "() => { const b = document.body ? document.body.innerText : '';"
            " return b.includes('氏名又は名称') || b.includes('ログアウト')"
            " || b.includes('納税メニュー') || b.includes('同意')"
            " || b.includes('誤') || b.includes('失敗') || b.includes('ロック')"
            " || b.includes('できません'); }",
            timeout=12000)
    except Exception:
        pass
    body = page.inner_text("body")
    _check_service_hours(body)
    if any(w in body for w in ["利用者ID又は暗証番号", "利用者IDまたは暗証番号", "誤りがあります",
                               "誤っています", "パスワードが違います", "ログインできません",
                               "認証に失敗", "ロックされています"]):
        raise EltaxLoginError(f"ログインに失敗しました（利用者ID/暗証番号の誤り等）。{_diag(page)}")
    # ログイン済みの証跡（ヘッダーの氏名等）が無ければ未ログインとして停止する。
    # ※未ログインのまま進むと「申請・届出（ログインなし）」区画に流れ着き、
    #   納税メニューの無い画面で迷子になる（実測で確認済み）。
    if not any(w in body for w in ["氏名又は名称", "ログアウト", "納税メニュー", "同意", "利用規約"]):
        raise EltaxLoginError(
            f"ログイン後の画面を確認できませんでした（未ログインの可能性）。{_diag(page)}")


def _check_service_hours(body: str):
    """eLTAXの利用時間外（平日8:30〜24:00以外・土日祝等）を検知して明示エラーにする。

    誤検知防止:
    - ログイン済み画面（メニュー等）が出ていれば時間外ではないので判定しない
      （お知らせやフッターに「利用可能時間」等の案内文が常時載っているため）
    - 「現在利用できない」ことを明示する文言のみに限定する
    """
    if any(w in body for w in ["納税メニュー", "申請・届出", "メインメニュー", "ログアウト"]):
        return
    if any(w in body for w in ["利用時間外", "時間外のためご利用",
                               "ただいまの時間はご利用いただけません",
                               "ただいまの時間はサービスを停止"]):
        raise EltaxSubmitError(
            "eLTAXの利用時間外です（平日8:30〜24:00、土日祝・年末年始は原則休止）。"
            "利用時間内に再度お試しください。")


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


def _dump_clickables_rich(page):
    """可視のクリック可能要素を innerText/title/alt/aria-label 込みで列挙。
    ⊞アイコン(画像リンク)等、テキストが無いボタンも title/alt で捕捉する。"""
    try:
        js = ("() => { const sel='a,button,[role=button],[onclick],img[alt],[title],[aria-label],li';"
              "const seen=new Set(); const out=[];"
              "const vis = e => { const r=e.getBoundingClientRect();"
              "  return r.width>0 && r.height>0; };"  # fixed配置も含めて可視判定
              "for (const e of document.querySelectorAll(sel)) {"
              "  if (!vis(e)) continue;"
              "  const t=((e.innerText||'')+' '+(e.getAttribute&&e.getAttribute('title')||'')+' '"
              "    +(e.getAttribute&&e.getAttribute('alt')||'')+' '"
              "    +(e.getAttribute&&e.getAttribute('aria-label')||'')).replace(/\\s+/g,' ').trim();"
              "  if (!t) continue;"
              "  const k=e.tagName+':'+t.slice(0,18); if (seen.has(k)) continue; seen.add(k);"
              "  out.push(e.tagName.toLowerCase()+'.'+(((e.className||'')+'').trim().split(' ')[0].slice(0,14))+':'+t.slice(0,26));"
              "  if (out.length>=45) break; }"
              "return out; }")
        return " | ".join(page.evaluate(js))[:760]
    except Exception:
        return ""


def _wait_menu(page, timeout_ms=9000):
    """メニュー(申請・届出 or 納税メニュー)が描画されるまで待つ。SPAの遅延対策。"""
    try:
        page.wait_for_function(
            "() => { const b=document.body?document.body.innerText:''; "
            "return b.includes('納税メニュー')||b.includes('申請・届出')||b.includes('申請届出'); }",
            timeout=timeout_ms)
        return True
    except Exception:
        return False


def _js_click_text(page, needle):
    """JSで正規化テキスト一致の要素を直接クリックする。

    下部固定バーの「戻る」や左端の縦書き「メインメニュー」タブは
    position:fixed のため offsetParent が null になり、通常の探索から漏れる。
    ここでは配置に関係なく、テキスト（alt/title/aria含む）が一致する
    最小の要素を選んで click() を発火させる。
    """
    js = (
        "(needle) => {"
        "  const norm = s => (s||'').replace(/\\s+/g,'');"
        "  const els = Array.from(document.querySelectorAll("
        "    'a,button,[role=button],li,p,span,div,img'));"
        "  const txt = e => norm(e.innerText) || norm((e.getAttribute&&("
        "    (e.getAttribute('alt')||'')+(e.getAttribute('title')||'')+"
        "    (e.getAttribute('aria-label')||''))) || '');"
        "  const cands = els.filter(e => {"
        "    const t = txt(e);"
        "    return t && t.includes(needle) && t.length <= needle.length + 8;"
        "  }).sort((a,b) => txt(a).length - txt(b).length);"
        "  if (!cands.length) return false;"
        "  const el = cands[0];"
        "  try { el.scrollIntoView({block:'center'}); } catch(e) {}"
        "  el.click();"
        "  return true;"
        "}"
    )
    try:
        return bool(page.evaluate(js, needle))
    except Exception:
        return False


def _js_click_exact(page, text):
    """正規化テキストが text と完全一致する要素をJSでクリック（button優先）。

    has-text の部分一致は「ログイン」が「申請・届出（ログインなし）」に
    マッチする等の誤爆があるため、完全一致でのみ押したい場面で使う。
    """
    js = (
        "(text) => {"
        "  const norm = s => (s||'').replace(/\\s+/g,'');"
        "  const prio = e => e.tagName==='BUTTON'?0:(e.tagName==='INPUT'?1:"
        "    (e.tagName==='A'?2:3));"
        "  const els = Array.from(document.querySelectorAll("
        "    'button,input[type=submit],input[type=button],a,[role=button],li,span,div,p'));"
        "  const cands = els.filter(e => norm(e.innerText || e.value || '') === text)"
        "    .sort((a,b) => prio(a) - prio(b));"
        "  if (!cands.length) return false;"
        "  try { cands[0].scrollIntoView({block:'center'}); } catch(e) {}"
        "  cands[0].click();"
        "  return true;"
        "}"
    )
    try:
        return bool(page.evaluate(js, text))
    except Exception:
        return False


def _dismiss_dialogs(page):
    """お知らせ・事前準備等のモーダルダイアログを閉じる（クリック遮蔽の解消）。

    実画面確認: ログイン画面等に「閉じる」「Close」「事前準備へ」を持つ
    ダイアログ(dlog-button/ui-button)が出てクリックを遮ることがある。
    「事前準備へ」は別ページへ飛ぶため押さず、閉じる系のみ押す。
    """
    for sel in ('a.dlog-button:has-text("閉じる")', 'button:has-text("Close")',
                'a:has-text("閉じる")', 'button:has-text("閉じる")'):
        try:
            el = _first(page, [sel], timeout=700)
            if el and el.is_visible():
                _safe_click(page, el)
                try:
                    page.wait_for_timeout(400)
                except Exception:
                    pass
        except Exception:
            pass


def _open_main_menu(page):
    """左端の⊞「メインメニュー」ランチャーを押して主メニュー(全タイル)を開く。

    ログイン直後は「申請・届出」ワークスペースが表示され、納税メニューは
    メインメニュー(オーバーレイ)を開かないと出ない。「メインメニュー」という
    アクセシブル名(title/alt/aria/テキスト)を持つ要素だけを厳密に狙う
    （誤クリックで別画面へ飛ばないよう、広すぎるセレクタは使わない）。
    """
    for sel in ['a[title*="メインメニュー"]', 'button[title*="メインメニュー"]',
                'div[title*="メインメニュー"]', '[aria-label*="メインメニュー"]',
                'img[alt*="メインメニュー"]',
                'a:has-text("メインメニュー")', 'button:has-text("メインメニュー")']:
        try:
            el = _first(page, [sel], timeout=1000)
        except Exception:
            el = None
        if el and _safe_click(page, el):
            _wait_menu(page)
            try:
                if "納税メニュー" in page.inner_text("body"):
                    return True
            except Exception:
                pass
    # 「メインメニュー」テキストの擬似ボタン(div/span)も試す
    if _nav_click(page, ["メインメニュー"]):
        _wait_menu(page)
        return True
    return False


def _navigate_to_issue_request(page, request_id: int):
    """メインメニュー →「納税メニュー」→「電子申告連動」(納付対象申告一覧) へ遷移。

    実画面（PCdesk WEB版）確認済みの動線:
      (ログイン後は「申請・届出」ワークスペース表示)
      左端⊞「メインメニュー」を開く
        → メインメニューの「納税メニュー」タイル
        → 納税メニュー画面の「納付情報発行依頼」欄「電子申告連動」タイル
        → 納付対象申告一覧（①〜④のウィザード）
    """
    # SPAの描画完了を待ってから操作する
    _wait_menu(page)

    def _has_nozei():
        try:
            return "納税メニュー" in page.inner_text("body")
        except Exception:
            return False

    # ログイン直後は「申請・届出メニュー」(GWB01020)に直行する。
    # ユーザー確認済みの正しい動線: 画面下部の「戻る」を押すとメインメニュー
    # （納税メニュータイルがある画面）へ遷移する。
    # 注意: ヘッダーの「終了する」は完全ログアウト（実測で確認）なので絶対に押さない。
    #       SPAルート再読込もログイン画面に戻ってしまうため行わない（実測で確認）。
    def _wait_nozei():
        try:
            page.wait_for_function(
                "() => { const b = document.body ? document.body.innerText : '';"
                " return b.includes('納税メニュー') || b.includes('代理人メニュー'); }",
                timeout=15000)
        except Exception:
            pass

    if not _has_nozei():
        _dismiss_dialogs(page)
        # 「戻る」（下部固定バー）→ ⊞「メインメニュー」（左端固定タブ）の順に
        # JSクリック込みで最大2周試す。fixed配置のため通常探索では見えない。
        for _ in range(2):
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
            # ※has-text部分一致は「eLTAX トップページへ戻る」等に誤マッチするため
            #   文字数上限付きのJSクリックのみ使う
            if _js_click_text(page, "戻る"):
                _wait_nozei()
            if _has_nozei():
                break
            if _js_click_text(page, "メインメニュー"):
                _wait_nozei()
            if _has_nozei():
                break
            _dismiss_dialogs(page)
    if not _has_nozei():
        # 予備: 「メインメニュー」という名前の要素（左端⊞タブ等）があれば開く
        _open_main_menu(page)

    if not _nav_click(page, ["納税メニュー"]):
        try:
            body = page.inner_text("body")
        except Exception:
            body = ""
        _check_service_hours(body)
        # ログイン画面に戻されていないか（セッション切れ/誤操作の検知）
        try:
            if _first(page, ['input[type="password"]'], timeout=800):
                raise EltaxSubmitError(
                    "[メニュー] メインメニューへ移動する途中でログイン画面に戻されました。"
                    "再実行してください（連続する場合はお知らせダイアログや画面構成の変更が原因の可能性）。")
        except EltaxSubmitError:
            raise
        except Exception:
            pass
        login_state = "ログイン済" if ("氏名又は名称" in body or "ログアウト" in body) else "未ログインの疑い"
        raise EltaxSubmitError(
            f"[メニュー]「納税メニュー」が見つかりません（状態:{login_state}）。"
            f"クリック候補:{_dump_clickables_rich(page)} / 画面:{page.url}")
    try:
        page.wait_for_timeout(1200)
    except Exception:
        pass
    # 納税メニューの「納付情報発行依頼」欄「電子申告連動」タイル
    # （電子申告を行った申告＝法人二税等の確定/中間の納付情報発行）
    if not _nav_click(page, ["電子申告連動"]):
        raise EltaxSubmitError(
            f"[メニュー]「電子申告連動」が見つかりません。"
            f"メニュー項目:{_dump_menu_items(page)} / 画面:{page.url}")
    try:
        page.wait_for_timeout(1200)
    except Exception:
        pass


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


def _visible_selects(page):
    out = []
    try:
        for s in page.query_selector_all("select"):
            try:
                if s.is_visible():
                    out.append(s)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _visible_text_inputs(page):
    out = []
    try:
        for i in page.query_selector_all("input"):
            try:
                t = (i.get_attribute("type") or "text").lower()
                if t in ("text", "number", "tel") and i.is_visible():
                    out.append(i)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _select_option_partial(select_el, needles):
    """select要素の選択肢からneedlesのいずれかを含むものを選ぶ。成功でTrue。"""
    try:
        opts = select_el.query_selector_all("option")
    except Exception:
        return False
    for n in needles:
        if not n:
            continue
        for o in opts:
            try:
                if n in (o.inner_text() or ""):
                    select_el.select_option(value=o.get_attribute("value"))
                    return True
            except Exception:
                continue
    return False


def _js_select_option(page, needle, skip=0):
    """needle を含む選択肢を持つ可視selectを内容ベースで特定し、
    JSで value 設定＋input/change イベント発火で確実に選択する。

    - select_option() だとAngularのモデルに反映されないことがある（実測:
      税目区分が[選択中:空]のままになった）ため、イベントを明示発火する。
    - skip: needleを含むselectが複数ある場合に読み飛ばす数
      （例: 期間の「令和NN」は開始・終了の2つあるので終了側は skip=1）。
    成功時は選択後の表示テキスト、失敗時は None を返す。
    """
    js = (
        "(arg) => {"
        "  const needle = arg.needle, skip = arg.skip;"
        "  const norm = t => (t||'').replace(/\\s+/g,'');"
        "  const sels = Array.from(document.querySelectorAll('select')).filter(s => {"
        "    const r = s.getBoundingClientRect(); return r.width > 0 && r.height > 0; });"
        "  let k = 0;"
        "  for (const s of sels) {"
        "    const opts = Array.from(s.options);"
        #  完全一致を優先（「確定」が「退職確定」に誤マッチするのを防ぐ）、
        #  無ければ部分一致（「法人都道府県民税」→正式名称の長い選択肢）
        "    const opt = opts.find(o => norm(o.text) === needle)"
        "             || opts.find(o => (o.text||'').includes(needle));"
        "    if (!opt) continue;"
        "    if (k++ < skip) continue;"
        "    s.value = opt.value;"
        "    s.dispatchEvent(new Event('input', {bubbles: true}));"
        "    s.dispatchEvent(new Event('change', {bubbles: true}));"
        "    const cur = s.options[s.selectedIndex];"
        "    return cur ? (cur.text||'').trim() : '';"
        "  }"
        "  return null;"
        "}"
    )
    try:
        return page.evaluate(js, {"needle": needle, "skip": skip})
    except Exception:
        return None


def _js_fill_inputs(page, vals):
    """可視のテキスト系input（text/number/tel）へ順に値を設定し、
    input/change/blurイベントを発火してAngularへ確実に反映させる。
    設定後の実際の値をカンマ区切りで返す（検証用）。"""
    js = ("(vals) => {"
          "  const ins = Array.from(document.querySelectorAll('input')).filter(i => {"
          "    const t = (i.type||'text').toLowerCase();"
          "    if (!['text','number','tel'].includes(t)) return false;"
          "    const r = i.getBoundingClientRect(); return r.width>0 && r.height>0; });"
          "  const n = Math.min(ins.length, vals.length);"
          "  for (let k = 0; k < n; k++) {"
          "    ins[k].value = String(vals[k]);"
          "    ins[k].dispatchEvent(new Event('input', {bubbles:true}));"
          "    ins[k].dispatchEvent(new Event('change', {bubbles:true}));"
          "    ins[k].dispatchEvent(new Event('blur', {bubbles:true}));"
          "  }"
          "  return ins.slice(0, n).map(i => i.value).join(',');"
          "}")
    try:
        return page.evaluate(js, [str(v) for v in vals])
    except Exception:
        return None


def _dump_inputs(page):
    """可視テキスト系inputの現在値を列挙（0件時の入力検証用）。"""
    try:
        js = ("() => Array.from(document.querySelectorAll('input')).filter(i => {"
              "  const t = (i.type||'text').toLowerCase();"
              "  if (!['text','number','tel'].includes(t)) return false;"
              "  const r = i.getBoundingClientRect(); return r.width>0 && r.height>0; })"
              ".slice(0,10).map(i => '[' + (i.value || '空') + ']').join(' ')")
        return page.evaluate(js)[:200]
    except Exception:
        return ""


def _install_net_probe(page):
    """fetch/XHRをフックし、通信回数と最後の応答（URL/状態/本文冒頭）を記録する。
    「検索ボタンを押しても実は通信していない」ケースの判別用。"""
    js = (
        "() => {"
        "  if (window.__netProbe) return;"
        "  window.__netProbe = {count: 0, last: ''};"
        "  const record = (url, status, body) => {"
        "    window.__netProbe.count++;"
        "    window.__netProbe.last = String(url||'').slice(-60) + ' status:' + status"
        "      + ' body:' + String(body||'').replace(/\\s+/g,' ').slice(0, 240);"
        "  };"
        "  const of = window.fetch;"
        "  if (of) window.fetch = function(...a) {"
        "    return of.apply(this, a).then(r => {"
        "      try { r.clone().text().then(t => record("
        "        (a[0] && a[0].url) || String(a[0]), r.status, t)).catch(() => {}); }"
        "      catch(e) {}"
        "      return r; });"
        "  };"
        "  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;"
        "  XMLHttpRequest.prototype.open = function(m, u, ...r) {"
        "    this.__u = u; return oo.call(this, m, u, ...r); };"
        "  XMLHttpRequest.prototype.send = function(...a) {"
        "    this.addEventListener('loadend', () => {"
        "      try { record(this.__u || '', this.status, this.responseText); } catch(e) {} });"
        "    return os.apply(this, a); };"
        "}"
    )
    try:
        page.evaluate(js)
    except Exception:
        pass


def _read_net_probe(page):
    try:
        return page.evaluate(
            "() => window.__netProbe"
            " ? (window.__netProbe.count + '回 | ' + window.__netProbe.last) : '未計測'")[:340]
    except Exception:
        return "取得失敗"


def _dump_search_button(page):
    """「検索」ボタンの実体（タグ・クラス・disabled状態）を列挙。"""
    try:
        js = ("() => Array.from(document.querySelectorAll("
              "'button,a,[role=button],input[type=button],input[type=submit]'))"
              ".filter(e => ((e.innerText || e.value || '')).replace(/\\s+/g,'') === '検索')"
              ".map(e => e.tagName.toLowerCase() + '.'"
              "  + (((e.className||'')+'').trim().split(' ').slice(0,2).join('.').slice(0,30))"
              "  + ' disabled:' + (e.disabled === true"
              "    || e.getAttribute('disabled') !== null"
              "    || e.getAttribute('aria-disabled') === 'true'))"
              ".join(' | ')")
        return page.evaluate(js)[:200]
    except Exception:
        return ""


def _dump_selects(page):
    """可視selectの「選択中の値」と選択肢を列挙（0件時の条件診断用）。"""
    try:
        js = ("() => Array.from(document.querySelectorAll('select'))"
              ".filter(s => { const r = s.getBoundingClientRect();"
              "  return r.width > 0 && r.height > 0; }).slice(0,6)"
              ".map(s => {"
              "  if (!s.options.length) return '[選択肢なし]';"
              "  const cur = s.selectedIndex >= 0 && s.options[s.selectedIndex]"
              "    ? (s.options[s.selectedIndex].text||'').trim() : '(未選択)';"
              "  const opts = Array.from(s.options).map(o => (o.text||'').trim())"
              "    .filter(Boolean).slice(0,8).join('/');"
              "  return '[選択中:' + cur + '] ' + opts;"
              "})")
        return " || ".join(page.evaluate(js))[:480]
    except Exception:
        return ""


def _fill_period(page, fiscal_year, fiscal_end_month):
    """事業年度・期別等（和暦の期間）を埋める。

    実画面（確認済み）: [令和07▼]年 [6]月 [1]日 〜 [令和08▼]年 [5]月 [31]日
    → 「令和NN」は年込みのセレクト（税目区分・申告区分の後ろ2つ）、
      月・日はテキスト入力4つ [月,日(期首), 月,日(期末)]。
    """
    import calendar
    try:
        end_y, end_m = int(fiscal_year), int(fiscal_end_month)
    except Exception:
        return ""
    try:
        end_d = calendar.monthrange(end_y, end_m)[1]
    except Exception:
        end_d = 31
    if end_m == 12:
        start_y, start_m, start_d = end_y, 1, 1
    else:
        start_y, start_m, start_d = end_y - 1, end_m + 1, 1
    r_start, r_end = start_y - 2018, end_y - 2018  # 令和 = 西暦-2018

    # 「令和NN」セレクト（例: 令和07）。開始=最初の一致select、終了=2つ目(skip=1)。
    # ゼロ埋め/非ゼロ埋め両対応。JSのイベント発火で確実に反映させる。
    if _js_select_option(page, f"令和{r_start:02d}", 0) is None:
        _js_select_option(page, f"令和{r_start}", 0)
    if _js_select_option(page, f"令和{r_end:02d}", 1) is None:
        _js_select_option(page, f"令和{r_end}", 1)

    # 月日テキスト入力を埋める（4つ=月日のみ / 6つ=年月日の場合に対応）。
    # JSでvalue設定＋イベント発火し、Angularのモデルに確実に反映させる。
    texts = _visible_text_inputs(page)
    if len(texts) >= 6:
        vals = [r_start, start_m, start_d, r_end, end_m, end_d]
    elif len(texts) >= 4:
        vals = [start_m, start_d, end_m, end_d]
    else:
        vals = []
    if vals:
        filled = _js_fill_inputs(page, vals)
        logger.info(f"[eLTAX-RPA] 期間入力: {filled}")
    return (f"令和{r_start:02d}年{start_m}月{start_d}日〜"
            f"令和{r_end:02d}年{end_m}月{end_d}日")


def _issue_flow(page, tax_type, filing_type, fiscal_year, fiscal_end_month, amount, request_id):
    """納付情報発行依頼フロー（電子申告連動）。
    ① 納付対象申告一覧: 税目区分・申告区分・事業年度を指定→検索→対象選択→次へ
    ② 納入金一覧: 次へ
    ③ 納入金確認: ここで停止（SUBMIT_ISSUE=False の間は発行依頼を実行しない）
    """
    # ① 検索条件（すべて必須）
    # 実画面の正式名称（確認済み）:
    #   都道府県税: 法人都道府県民税・事業税・特別法人事業税又は地方法人特別税
    #   市町村税:   法人市町村民税
    # selectは描画・連動populateが非同期のため、目的の選択肢を持つselectを
    # 内容ベースで特定し、JSのvalue設定＋イベント発火で確実に選ぶ。
    if tax_type and ("市町村" in tax_type or "市民税" in tax_type
                     or ("市" in tax_type and "都道府県" not in tax_type and "都" not in tax_type)):
        tax_needles = ["法人市町村民税", "市町村民税", "法人住民税"]
    else:
        tax_needles = ["法人都道府県民税", "都道府県民税", "事業税"]
    picked_tax = None
    for _ in range(20):  # 画面描画待ち込みで最大約10秒
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
    logger.info(f"[eLTAX-RPA] request_id={request_id} 税目区分選択: {picked_tax}")
    # 申告区分: 税目区分に連動して選択肢が非同期で入るため、入るまで待って選ぶ
    kubun = ((filing_type or "").replace("申告", "").strip()) or "確定"
    picked_kubun = None
    for _ in range(16):  # 最大約8秒
        picked_kubun = _js_select_option(page, kubun, 0)
        if picked_kubun:
            break
        try:
            page.wait_for_timeout(500)
        except Exception:
            pass
    logger.info(f"[eLTAX-RPA] request_id={request_id} 申告区分選択: {picked_kubun}")
    # 事業年度・期別等（和暦の期間）
    period_desc = _fill_period(page, fiscal_year, fiscal_end_month)
    # 発行依頼状況「全て」（既発行も表示）
    _nav_click(page, ["全て"])
    # 入力反映が落ち着くのを待ってから検索（ボタンは完全一致で確実に押す）
    try:
        page.wait_for_timeout(600)
    except Exception:
        pass
    # 通信計測を仕込んでから検索（本当に検索リクエストが飛んだか判別する）
    _install_net_probe(page)
    try:
        page.evaluate("() => { if (window.__netProbe) {"
                      " window.__netProbe.count = 0; window.__netProbe.last = ''; } }")
    except Exception:
        pass
    search_btn_state = _dump_search_button(page)

    def _probe_reset():
        try:
            page.evaluate("() => { if (window.__netProbe) {"
                          " window.__netProbe.count = 0; window.__netProbe.last = ''; } }")
        except Exception:
            pass

    def _probe_fired(wait_ms=3000):
        """クリック後に通信が発生したかを最大wait_msミリ秒待って確認。"""
        try:
            page.wait_for_function(
                "() => window.__netProbe && window.__netProbe.count > 0",
                timeout=wait_ms)
            return True
        except Exception:
            return False

    def _attempt_ok():
        """検索が実行されたか: 通信発生 または 件数が1以上に変化で判定。
        （検索がローカルフィルタ実装の場合は通信が起きないため件数でも見る）"""
        if _probe_fired(2500):
            return True
        try:
            b = page.inner_text("body")
            m2 = re.search(r'検索結果[：:\s]*(\d+)\s*件', b)
            return bool(m2 and int(m2.group(1)) > 0)
        except Exception:
            return False

    # クリック方式を段階的に試し、実行の証跡（通信 or 件数変化）を毎回検証。
    # 要素ハンドルはAngular再描画で陳腐化するため、クリック時点で再解決される
    # locator方式を最優先にする。各方式の失敗理由も記録する。
    click_method = "なし"
    click_errors = []
    # 1) locatorクリック（自動待機・自動スクロール・本物のイベント列）
    try:
        page.locator('button:text-is("検索")').first.click(timeout=8000)
        if _attempt_ok():
            click_method = "locator"
    except Exception as e:
        click_errors.append(f"locator:{re.sub(chr(10), ' ', str(e))[:70]}")
    # 2) locatorフォーカス→Enter
    if click_method == "なし":
        _probe_reset()
        try:
            btn_loc = page.locator('button:text-is("検索")').first
            btn_loc.focus(timeout=4000)
            page.keyboard.press("Enter")
            if _attempt_ok():
                click_method = "keyboard"
        except Exception as e:
            click_errors.append(f"enter:{re.sub(chr(10), ' ', str(e))[:70]}")
    # 3) 期間の日付入力欄でEnter（フォーム送信の標準経路）
    if click_method == "なし":
        _probe_reset()
        try:
            texts = _visible_text_inputs(page)
            if len(texts) >= 4:
                texts[3].focus()
                page.keyboard.press("Enter")
                if _attempt_ok():
                    click_method = "input-enter"
        except Exception as e:
            click_errors.append(f"input-enter:{re.sub(chr(10), ' ', str(e))[:70]}")
    # 4) JSクリック（最後の手段）
    if click_method == "なし":
        _probe_reset()
        if _js_click_exact(page, "検索"):
            click_method = "js" if _attempt_ok() else "js(証跡なし)"
    # 検索は非同期実行のため、結果件数が入るまで待つ（画面は検索前から
    # 「検索結果:0件」を表示しており、待たずに読むと誤って0件と判定する）
    try:
        page.wait_for_function(
            "() => { const b = document.body ? document.body.innerText : '';"
            " const m = b.match(/検索結果[：:\\s]*([0-9]+)\\s*件/);"
            " return m && parseInt(m[1]) > 0; }",
            timeout=12000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(500)
    except Exception:
        pass

    # 検索結果の件数を確認
    try:
        body = page.inner_text("body")
    except Exception:
        body = ""
    m = re.search(r'検索結果[：:\s]*(\d+)\s*件', body)
    if m and int(m.group(1)) == 0:
        # どのアカウントでログインしているか（ヘッダーの利用者ID）を表示。
        # 方式B(税理士ID)でログインしていると、税理士自身の申告は無いため
        # 検索は正当に0件になる（本人IDでのログインが必要）。
        uid_m = re.search(r'利用者ID\s*[:：]?\s*([A-Za-z0-9]+)', body)
        uid_info = uid_m.group(1) if uid_m else "不明"
        msg_txt = _dump_matching(page, ["してください", "エラー", "できません", "ありません"])
        raise EltaxSubmitError(
            "[入力] 該当する納付対象申告が0件でした。"
            f"クリック方式:{click_method} / クリック失敗理由:{' | '.join(click_errors) or 'なし'} / "
            f"検索ボタン:{search_btn_state} / 検索後の通信:{_read_net_probe(page)} / "
            f"ログイン中の利用者ID:{uid_info} / 入力期間:{period_desc} / "
            f"入力欄:{_dump_inputs(page)} / 画面メッセージ:{msg_txt}")

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
    # ② 納付・納入金額一覧（名称・住所・金額は自動転記済み）→ 次へ（→ ③確認画面）
    _nav_click(page, ["次へ"])
    # ③「納付・納入金額確認」画面の描画待ち。
    # ③固有の文言（実画面確認済み）:
    #   見出し「納付・納入金額確認」／案内文「納付情報発行を依頼します」
    # ※上部ステップ表示の「納入金確認」は全画面共通のため判定に使わない。
    _confirm_js = ("() => { const b = document.body ? document.body.innerText : '';"
                   " return b.includes('納付情報発行を依頼します')"
                   " || b.includes('納入金額確認'); }")
    try:
        page.wait_for_function(_confirm_js, timeout=9000)
    except Exception:
        try:
            page.wait_for_timeout(1800)
        except Exception:
            pass

    # ③ 確認画面に到達していることを検証して停止（「送信」は絶対に押さない）
    try:
        body = page.inner_text("body")
    except Exception:
        body = ""
    if not SUBMIT_ISSUE:
        try:
            reached = bool(page.evaluate(_confirm_js))
        except Exception:
            reached = ("納付情報発行を依頼します" in body) or ("納入金額確認" in body)
        amt = re.search(r'合計額[：:\s]*([0-9][0-9,]{2,})\s*円', body)
        if not amt:
            amt = re.search(r'([0-9][0-9,]{2,})\s*円', body)
        detail = f"（画面金額:{amt.group(1)}円）" if amt else ""
        note = (f"テスト成功: 納付・納入金額確認まで到達{detail}（送信＝発行依頼は未実行）" if reached
                else f"テスト: 送信手前まで到達（確認画面は未検出）。{_diag(page)}")
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
