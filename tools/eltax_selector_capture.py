# -*- coding: utf-8 -*-
"""
eLTAX PCdesk(WEB版) セレクタ採取ツール（対話式）

目的:
  eLTAX RPA（app/utils/etax/eltax_rpa_worker.py）の _SELECTORS を確定するために、
  実際のPCdesk(WEB版)の各画面から入力欄・ボタン・リンクの候補セレクタを自動採取する。

方針（安全）:
  - 認証情報は本ツールに一切渡さない。ヘッド付きブラウザが開くので、
    利用者ID・暗証番号は「あなた自身がその画面に手入力」してログインする。
  - 各画面に着いたらターミナルで Enter を押すと、その画面の要素候補を
    JSON / 見やすいMarkdown表 / スクリーンショットに保存する。
  - 最後に _SELECTORS の下書き（eltax_capture/_SELECTORS_suggested.py）を出力する。

前提:
  pip install playwright  （chromiumは環境にプリインストール済み: /opt/pw-browsers）

使い方:
  python tools/eltax_selector_capture.py
  → ブラウザが開く → 手動でログイン/画面遷移 → 各ステップでEnter
  → eltax_capture/ に結果が保存される → 中身を確認して _SELECTORS に転記
"""

import os
import re
import json
import sys

OUT_DIR = os.environ.get("ELTAX_CAPTURE_DIR", "eltax_capture")
PORTAL_LOGIN_URL = "https://www.portal.eltax.lta.go.jp/"

# 採取したい画面ステップ（この順で対話的に案内する）
STEPS = [
    ("login", "PCdesk(WEB版)のログイン画面（利用者ID・暗証番号・ログインボタン）"),
    ("after_login_top", "ログイン後のトップ/メインメニュー"),
    ("kyotsu_nozei_menu", "共通納税メニュー"),
    ("issue_request_form", "納付情報発行依頼の入力フォーム（税目・期別・金額 等）"),
    ("issue_result", "発行結果（納付情報：収納機関番号・納付番号・確認番号 等）"),
]

# 各要素の候補を集めるJS（ラベル・id・name・placeholder・推奨セレクタ）
_EXTRACT_JS = r"""
() => {
  function labelFor(el){
    if(el.id){
      try { const l=document.querySelector('label[for="'+CSS.escape(el.id)+'"]'); if(l) return (l.innerText||'').trim(); } catch(e){}
    }
    const p = el.closest('label');
    if(p) return (p.innerText||'').trim();
    const al = el.getAttribute('aria-label');
    if(al) return al.trim();
    return '';
  }
  function suggest(el){
    if(el.id){ try { return '#'+CSS.escape(el.id); } catch(e){ return '#'+el.id; } }
    const nm = el.getAttribute('name');
    if(nm) return el.tagName.toLowerCase()+'[name="'+nm+'"]';
    return '';
  }
  const els = Array.prototype.slice.call(document.querySelectorAll('input,select,textarea,button,a'));
  return els.map(function(el){
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      id: el.id || '',
      name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
      aria: el.getAttribute('aria-label') || '',
      text: ((el.innerText || el.value || '')).trim().slice(0, 50),
      label: labelFor(el),
      selector: suggest(el),
      visible: !!(r.width && r.height)
    };
  }).filter(function(e){ return e.visible; });
}
"""


def extract_candidates(page):
    """現在のページから可視の入力/ボタン/リンク候補を返す。"""
    return page.evaluate(_EXTRACT_JS)


def _md_table(cands):
    rows = ["| # | tag/type | ラベル/テキスト | id | name | 推奨セレクタ |",
            "|---|---|---|---|---|---|"]
    for i, c in enumerate(cands):
        label = c["label"] or c["text"] or c["placeholder"] or c["aria"]
        label = re.sub(r"\s+", " ", label)[:40]
        rows.append("| {i} | {tag}/{type} | {label} | {id} | {name} | `{sel}` |".format(
            i=i, tag=c["tag"], type=c["type"] or "-", label=label or "-",
            id=c["id"] or "-", name=c["name"] or "-", sel=c["selector"] or "?"))
    return "\n".join(rows)


def save_step(page, key, desc):
    os.makedirs(OUT_DIR, exist_ok=True)
    cands = extract_candidates(page)
    with open(os.path.join(OUT_DIR, key + ".json"), "w", encoding="utf-8") as f:
        json.dump(cands, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, key + ".md"), "w", encoding="utf-8") as f:
        f.write("# {key} — {desc}\n\nURL: {url}\n\n".format(key=key, desc=desc, url=page.url))
        f.write(_md_table(cands))
        f.write("\n")
    try:
        page.screenshot(path=os.path.join(OUT_DIR, key + ".png"), full_page=True)
    except Exception:
        pass
    print("  → {n}件の候補を保存: {d}/{k}.md / .json / .png".format(n=len(cands), d=OUT_DIR, k=key))
    return cands


def write_suggested_selectors(all_cands):
    """採取結果から _SELECTORS の下書きを出力（候補はコメントで併記）。"""
    path = os.path.join(OUT_DIR, "_SELECTORS_suggested.py")
    lines = ["# eltax_rpa_worker._SELECTORS 下書き（採取結果から自動生成）",
             "# 各値は候補です。画面と照合して正しいセレクタを1つ選んでください。",
             "_SELECTORS = {"]
    hint = {
        "login_user_id": ("login", ("利用者", "id", "user")),
        "login_password": ("login", ("暗証", "password", "pass")),
        "login_submit": ("login", ("ログイン", "login")),
        "menu_kyotsu_nozei": ("kyotsu_nozei_menu", ("共通納税", "納税")),
        "menu_issue_request": ("issue_request_form", ("発行依頼", "納付情報")),
        "field_tax_item": ("issue_request_form", ("税目",)),
        "field_period": ("issue_request_form", ("期別", "期間", "対象")),
        "field_amount": ("issue_request_form", ("金額", "納付額")),
        "submit_issue": ("issue_request_form", ("発行", "送信", "依頼")),
        "result_payment_info": ("issue_result", ("納付番号", "収納機関", "確認番号")),
        "logout": ("after_login_top", ("ログアウト",)),
    }
    for field, (step, kws) in hint.items():
        cand_sel = ""
        for c in all_cands.get(step, []):
            hay = " ".join([c["label"], c["text"], c["placeholder"], c["name"], c["id"]])
            if any(k in hay for k in kws) and c["selector"]:
                cand_sel = c["selector"]
                break
        lines.append('    "{f}": {s},'.format(f=field, s=repr(cand_sel)))
    lines.append("}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("  → _SELECTORS 下書きを出力: " + path)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwrightが未インストールです。 pip install playwright を実行してください。")
        sys.exit(1)

    print("=" * 60)
    print("eLTAX PCdesk(WEB版) セレクタ採取ツール")
    print("・ブラウザが開いたら、あなた自身の利用者ID・暗証番号でログインしてください。")
    print("・各画面に着いたらこのターミナルでEnterを押すと要素を採取します。")
    print("=" * 60)

    all_cands = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 手動操作するのでheadedで起動
        context = browser.new_context(locale="ja-JP", viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.goto(PORTAL_LOGIN_URL)
        for key, desc in STEPS:
            input("\n[{k}] {d}\n  → その画面を開いたらEnter: ".format(k=key, d=desc))
            all_cands[key] = save_step(page, key, desc)
        write_suggested_selectors(all_cands)
        print("\n完了。 {d}/ を確認し、_SELECTORS に転記してください。".format(d=OUT_DIR))
        input("Enterでブラウザを閉じます: ")
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
