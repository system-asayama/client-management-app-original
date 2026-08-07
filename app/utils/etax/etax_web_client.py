# -*- coding: utf-8 -*-
"""
e-Tax（国税）受付システム 送受信クライアント（純Python実装）

【背景】
e-Taxのブラウザ・ログイン（login.e-tax.nta.go.jp）は専用ブラウザ拡張機能を必須とし、
サーバー上のヘッドレスブラウザでは突破できないことが判明した。
そこで、国税庁「送受信モジュール」が使うのと同じ、機械通信専用エンドポイント
（uketsuke.e-tax.nta.go.jp）への HTTPS フォームPOST＋XML電文プロトコルを
純Pythonで再実装する。ブラウザ・拡張機能・電子証明書を使わない。
納付情報登録依頼（TEZ500）は電子署名不要のため、この方式で送信できる。

【設計根拠】docs/etax_webapi_design.md（受付if仕様書・資料2-1/資料3・送受信モジュール仕様）

【安全装置】
- ETAX_WEB_LIVE_ENABLED=False の間は、実際のネットワーク送信を一切行わない。
  本番の受付システムに接続してよいと確認できるまで False のままにする。
- 認証（ログイン）はデータ送信を伴わない（顧問先本人のログイン→ログアウトのみ）。
- 納付情報登録依頼（TEZ500）の実送信は、送信試験環境が整うまで実装・実行しない。
"""

import logging
import re
from typing import Dict, Any, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# ============================================================
# 安全フラグ（本番接続の可否）
# ============================================================
# False の間は _post() が実際の通信を行わず、明示エラーを返す。
# 本番疎通テストの許可が出たら True にする（まずは認証のみ）。
ETAX_WEB_LIVE_ENABLED = False

# ============================================================
# 接続先（送受信モジュール CLCommunication.ini より）
# ============================================================
ETAX_UKETSUKE_BASE = "https://uketsuke.e-tax.nta.go.jp"
EP_LOGIN = "/UF_APP/lnk/Menu"                      # 認証→メインメニュー
EP_DATASEND = "/UF_APP/lnk/datasend"               # 申告等データ送信
EP_MSGBOX = "/UF_APP/lnk/MsgboxItrnViewGmnPage"    # メッセージボックス一覧

# タイムアウト（秒）
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 60

# 受付システムに送信する際の User-Agent（送受信モジュール相当のクライアント名）
# ※正式な値は送信試験時に調整する。
USER_AGENT = "e-Tax-Client/1.0 (uketsuke; python-requests)"


class EtaxWebError(Exception):
    """e-Tax受付システム通信の基底例外。"""


class EtaxWebLoginError(EtaxWebError):
    """認証（ログイン）エラー。"""


class EtaxWebClient:
    """受付システムとのステートフルなHTTPセッションを保持するクライアント。

    プロトコル（受付if仕様書）:
      各リクエストのレスポンスは画面XML。ヘッダー部の「引継ぎ情報」(oStHktgInf)と
      ボディー部の「リンク情報」(次のPOST先URL)を辿って遷移する。

    使い方（想定）:
      c = EtaxWebClient()
      c.login(user_id, password)     # → メインメニュー到達（引継ぎ情報を保持）
      # c.send_payment_request(...)  # ← 送信試験環境が整うまで未実装/未実行
      c.logout()
    """

    def __init__(self, live: bool = False):
        # requests.Session は遅延生成（Playwrightのように未導入環境でも import 可能に）
        self._session = None
        self.carryover: Optional[str] = None      # 引継ぎ情報 oStHktgInf
        self.current_screen_id: Optional[str] = None
        self.menu_links: Dict[str, str] = {}      # 業務名 → 業務リンクURL
        # 呼び出し単位の本番許可（グローバルフラグを立てずに1回だけ通信したい時に使う）。
        # 認証ロックを避けるため、リトライは一切しない設計（1コール=1試行）。
        self.live = bool(live)
        # 診断用: 各リクエストの実応答を記録（無駄な試行を避け1回で原因を掴むため）
        self.trace = []

    # ---------------- 低レベル通信 ----------------
    def _ensure_session(self):
        if self._session is None:
            import requests
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT})
            self._session = s
        return self._session

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return ETAX_UKETSUKE_BASE + path

    def _post(self, path: str, data: Dict[str, str], method: str = "POST") -> "ET.Element":
        """フォームPOST（またはGET）してレスポンスXMLのルート要素を返す。

        ETAX_WEB_LIVE_ENABLED=False の間は通信せず例外にする（安全装置）。
        """
        if not (ETAX_WEB_LIVE_ENABLED or self.live):
            raise EtaxWebError(
                "e-Tax受付システムへの実通信は無効化されています"
                "（ETAX_WEB_LIVE_ENABLED=False / live=False）。本番疎通の許可後に有効化してください。")
        sess = self._ensure_session()
        url = self._url(path)
        # 送信値は日本語を含み得るが、利用者識別番号・暗証番号は半角。
        # 文字コードは受付システム仕様に合わせる（既定 UTF-8、必要なら調整）。
        # ※認証情報の値そのものはtraceに残さない（キー名のみ記録）。
        if method.upper() == "GET":
            resp = sess.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=True)
        else:
            resp = sess.post(url, data=data, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                             allow_redirects=True)
        body = resp.content or b""
        text = body.decode("utf-8", "replace")
        root = None
        root_tag = None
        try:
            root = self._parse_xml(body)
            root_tag = root.tag.rsplit("}", 1)[-1]
        except Exception as e:
            root_tag = f"(XML解析不可: {type(e).__name__})"
        snippet = " ".join(text.split())[:900]
        # 画面に表示されるメッセージ（タイトル・サブタイトル）とボタン/リンクを抽出。
        # メッセージ共通(XU00S190)や認証エラーの原因文言を掴むため。
        msg_parts = []
        for suf in ("XOC010", "XOC020", "XAC010", "XAC020", "XHC010"):
            for el in (root.iter() if root is not None else []):
                if el.tag.rsplit("}", 1)[-1] == suf and (el.text or "").strip():
                    msg_parts.append((el.text or "").strip())
        btn = None
        link = None
        if root is not None:
            for el in root.iter():
                t = el.tag.rsplit("}", 1)[-1]
                if t == "XOC040" and (el.text or "").strip():
                    btn = (el.text or "").strip()
                elif t == "XOC050" and (el.text or "").strip():
                    link = (el.text or "").strip()
        self.trace.append({
            "url": f"[{method.upper()}] {url}",
            "sent_keys": sorted(data.keys()),
            "http_status": resp.status_code,
            "content_type": resp.headers.get("Content-Type", ""),
            "final_url": resp.url,
            "root_tag": root_tag,
            "message": " / ".join(msg_parts)[:500],
            "button": btn,
            "link": link,
            "body_snippet": snippet,
        })
        resp.raise_for_status()
        if root is None:
            raise EtaxWebError(f"応答をXMLとして解析できませんでした（{root_tag}）。")
        return root

    @staticmethod
    def _parse_xml(content: bytes) -> "ET.Element":
        # 受付システムのレスポンスはXML。名前空間や文字コードに配慮してパースする。
        try:
            return ET.fromstring(content)
        except ET.ParseError:
            # BOMや前後ゴミがある場合に備えて最初の<から切り出す
            text = content.decode("utf-8", "replace")
            i = text.find("<")
            return ET.fromstring(text[i:] if i >= 0 else text)

    # ---------------- XML抽出ヘルパー ----------------
    @staticmethod
    def _find_text(root: "ET.Element", tag_suffix: str) -> Optional[str]:
        """名前空間を無視して、末尾がtag_suffixに一致する最初の要素のテキストを返す。

        受付システムのタグ（XAB020, XAC090 等）は一意なので末尾一致で拾える。
        """
        for el in root.iter():
            tag = el.tag.rsplit("}", 1)[-1]  # 名前空間除去
            if tag == tag_suffix:
                return (el.text or "").strip()
        return None

    # ---------------- 認証（ログイン） ----------------
    def login(self, user_id: str, password: str) -> Dict[str, Any]:
        """利用者識別番号＋暗証番号で受付システムにログインする。

        フロー（資料3 XSL構造設計書 SU00S010 認証）:
          POST /UF_APP/lnk/Menu
            oStHktgInf     = 初期認証画面の引継ぎ情報（XAB020）
            oStInputUserId = 利用者識別番号
            oStInputPwd    = 暗証番号
          → SU00S020 メインメニュー（status=空/正常）。引継ぎ情報(XBB020)を更新。

        ※初期認証画面（初回の引継ぎ情報の取得＝ブートストラップ）の正確な手順は、
          送信試験環境での実観測で確定する。ここでは想定実装とし、失敗時は
          原因を明示する。
        """
        uid = (user_id or "").replace("-", "").replace(" ", "")
        pwd = password or ""
        if not uid or not pwd:
            raise EtaxWebLoginError("利用者識別番号または暗証番号が未設定です。")

        # (1) ブートストラップ: GETで認証画面を取得し、初期の引継ぎ情報(XAB020)と
        #     ログイン送信先(XAC090=リンク_実行)を得る。
        boot = self._bootstrap_auth_screen()
        boot_carryover = boot.get("carryover")
        login_action = boot.get("action") or EP_LOGIN
        # 診断: 認証画面から抽出した値（値の中身確認用。識別番号・暗証番号は含まない）
        self.boot_info = {
            "carryover_len": len(boot_carryover or ""),
            "carryover_head": (boot_carryover or "")[:24],
            "action": (boot.get("action") or "(なし→/Menuに fallback)")[:120],
        }

        # (2) 認証実行（XU00S010_1）: 認証画面のAction URLへPOST
        root = self._post(login_action, {
            "oStHktgInf": boot_carryover or "",
            "oStInputUserId": uid,
            "oStInputPwd": pwd,
        })

        # ログイン後、お知らせ系メッセージ画面(XU00S190)が挟まる場合のみ「次へ」を辿る。
        # ※ログアウト/ログイン画面へ戻すリンクは辿らない（本当のメッセージを保持し、
        #   セッション破棄を避ける）。暗証番号は再送しない（ロック回避）。
        screen = self._screen_of(root)
        if screen == "SU00S190":
            msg = self._message_of(root)
            link = self._find_text(root, "XOC050")
            carry = self._find_text(root, "XOB020")
            is_logout_link = bool(link and re.search(r"LogOut|loginCtl|login", link, re.I))
            is_logout_msg = bool(msg and ("ログアウト" in msg or "終了" in msg))
            if link and not is_logout_link and not is_logout_msg:
                logger.info(f"[etax-web] ログイン後メッセージ画面。次へ遷移: {msg}")
                root = self._post(link, {"oStHktgInf": carry or ""})
                screen = self._screen_of(root)

        status = self._find_text(root, "status")
        self.current_screen_id = screen

        # 認証画面(SU00S010)に戻された＝認証失敗
        if screen == "SU00S010":
            raise EtaxWebLoginError(
                f"認証に失敗しました（利用者識別番号または暗証番号の誤りの可能性）。"
                f"メッセージ:{self._message_of(root) or '(なし)'} status={status}")

        # メインメニュー(SU00S020)到達＝成功
        if screen == "SU00S020":
            self.carryover = self._find_text(root, "XBB020")
            self._collect_menu_links(root)
            logger.info(f"[etax-web] ログイン成功 screen={screen}")
            return {"screen_id": screen, "status": status, "links": list(self.menu_links.keys())}

        # それ以外（想定外の画面）＝メッセージを付けて報告
        raise EtaxWebLoginError(
            f"ログイン後にメインメニューへ到達できませんでした。到達画面:{screen} "
            f"メッセージ:{self._message_of(root) or '(なし)'} status={status}")

    def _screen_of(self, root: "ET.Element") -> Optional[str]:
        """レスポンス画面IDを判定する。各画面のヘッダー画面IDタグを順に見る。
        取れない場合はルートタグ(XU00Sxxx)から SU00Sxxx を推定して返す。"""
        for suf in ("XOB010", "XBB010", "XAB010", "XGB010", "XHB010"):
            v = self._find_text(root, suf)
            if v:
                return v
        rt = root.tag.rsplit("}", 1)[-1]  # 例 XU00S020 → SU00S020
        if rt.startswith("XU00S"):
            return "SU00S" + rt[5:]
        return rt

    def _message_of(self, root: "ET.Element") -> str:
        """画面のタイトル・サブタイトル（表示メッセージ）を連結して返す。"""
        parts = []
        for suf in ("XOC010", "XOC020", "XAC010", "XAC020", "XHC010"):
            for el in root.iter():
                if el.tag.rsplit("}", 1)[-1] == suf and (el.text or "").strip():
                    parts.append((el.text or "").strip())
        return " / ".join(parts)[:500]

    def _bootstrap_auth_screen(self) -> Dict[str, Optional[str]]:
        """GETで認証画面（SU00S010）を取得し、初期の引継ぎ情報(XAB020)と
        ログイン送信先URL(XAC090=リンク_実行)を返す。

        受付if仕様: 直前レスポンスと同一の引継ぎ情報でなければ自動ログアウトされる。
        そのため、認証画面をGETで取得し、そのXAB020/XAC090を用いてログインする。
        """
        try:
            root = self._post(EP_LOGIN, {}, method="GET")
        except EtaxWebError:
            raise
        except Exception as e:
            logger.warning(f"[etax-web] 認証画面ブートストラップ失敗: {e}")
            return {"carryover": None, "action": None}
        return {
            "carryover": self._find_text(root, "XAB020"),
            "action": self._find_text(root, "XAC090"),
        }

    def _collect_menu_links(self, root: "ET.Element"):
        """メインメニューの業務名(XBC040)→業務リンク(XBC050)を対応づけて保持する。"""
        self.menu_links = {}
        names, links = [], []
        for el in root.iter():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "XBC040":
                names.append((el.text or "").strip())
            elif tag == "XBC050":
                links.append((el.text or "").strip())
        for n, l in zip(names, links):
            if n:
                self.menu_links[n] = l

    # ---------------- ログアウト ----------------
    def logout(self):
        """セッションを終了する（受付システムは一定時間で自動ログアウトもする）。"""
        try:
            if self._session is not None:
                self._session.close()
        except Exception:
            pass
        self._session = None
        self.carryover = None

    # ---------------- 疎通テスト（1回・リトライなし・データ送信なし） ----------------
    @staticmethod
    def login_probe(user_id: str, password: str) -> Dict[str, Any]:
        """本番へ「ログインのみ」を1回だけ試す疎通テスト。

        ・データ送信は一切行わない（認証→結果確認→ログアウトのみ）。
        ・リトライしない（認証失敗の連続によるアカウントロックを避ける）。
        ・成功/失敗にかかわらず、原因診断に使える情報を辞書で返す（例外を投げない）。
        戻り値: {"ok": bool, "screen_id":..., "status":..., "links":[...], "error":...}
        """
        c = EtaxWebClient(live=True)  # この呼び出しだけ本番許可
        out = {"ok": False, "error": None, "trace": [], "boot": None}
        try:
            info = c.login(user_id, password)
            out.update({"ok": True, "screen_id": info.get("screen_id"),
                        "status": info.get("status"), "links": info.get("links", [])})
        except EtaxWebLoginError as e:
            out["error"] = f"[認証] {e}"
        except EtaxWebError as e:
            out["error"] = f"[通信] {e}"
        except Exception as e:
            out["error"] = f"[想定外] {type(e).__name__}: {str(e)[:200]}"
        finally:
            out["trace"] = c.trace  # 実応答の診断（HTTP状態・Content-Type・ルートタグ・本文冒頭）
            out["boot"] = getattr(c, "boot_info", None)  # 認証画面から抽出した引継ぎ情報/Action URL
            c.logout()
        return out

    # ---------------- 納付情報登録依頼（TEZ500）送信：未実装 ----------------
    def send_payment_request(self, *args, **kwargs):
        """納付情報登録依頼（TEZ500）を送信する。

        送信試験環境が整い、電文フォーマット（TEZ500 XML・圧縮/包装）と
        申告等データ送信(SU00S070)の正確な手順を実観測で確定してから実装する。
        現時点では未実装として明示する。
        """
        raise NotImplementedError(
            "納付情報登録依頼(TEZ500)の実送信は未実装です。"
            "送信試験環境での検証後に実装します（本番への誤送信防止）。")
