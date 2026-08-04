# eLTAX RPA セレクタ確認・確定手順

eLTAX RPA（`app/utils/etax/eltax_rpa_worker.py`）はセレクタ未確定のため、
既定では `SELECTORS_CONFIRMED=False` で本番実行をブロックしています。
実アカウントで画面要素を確認し、`_SELECTORS` を埋めて有効化するまでの手順です。

> 認証情報（利用者ID・暗証番号）は採取ツールに渡しません。
> ヘッド付きブラウザで**あなた自身が手入力してログイン**します。

## 1. 採取ツールを実行する（ローカルPC推奨）

```bash
pip install playwright
playwright install chromium   # 未導入の環境のみ
python tools/eltax_selector_capture.py
```

- ブラウザ（PCdesk WEB版ポータル）が開きます。
- ターミナルの案内に従い、各画面に着いたら **Enter** を押します。
- 採取対象の画面（この順で案内されます）:
  1. `login` … ログイン画面（利用者ID・暗証番号・ログインボタン）
  2. `after_login_top` … ログイン後トップ（ログアウト等）
  3. `kyotsu_nozei_menu` … 共通納税メニュー
  4. `issue_request_form` … 納付情報発行依頼の入力フォーム（税目・期別・金額）
  5. `issue_result` … 発行結果（収納機関番号・納付番号・確認番号 等）

## 2. 出力を確認する

`eltax_capture/` に以下が保存されます:

- `<step>.md` … 各画面の要素候補（ラベル・id・name・**推奨セレクタ**）の一覧表
- `<step>.json` … 同内容の機械可読データ
- `<step>.png` … 画面スクリーンショット
- `_SELECTORS_suggested.py` … `_SELECTORS` の下書き（自動生成）

## 3. `_SELECTORS` を確定する

`_SELECTORS_suggested.py` を見ながら、各画面の `.md` 表と照合して
正しいセレクタを1つずつ選び、`eltax_rpa_worker.py` の `_SELECTORS` に転記します。

必要な要素（キー）:

| キー | 対象 |
|---|---|
| `login_user_id` | 利用者ID入力欄 |
| `login_password` | 暗証番号入力欄 |
| `login_submit` | ログインボタン |
| `menu_kyotsu_nozei` | 共通納税メニュー |
| `menu_issue_request` | 納付情報発行依頼メニュー |
| `field_tax_item` | 税目 |
| `field_period` | 期別/対象期間 |
| `field_amount` | 金額 |
| `submit_issue` | 発行依頼 送信ボタン |
| `result_payment_info` | 発行結果（納付情報）表示領域 |
| `logout` | ログアウト |

## 4. 各ヘルパーの実装を仕上げる

`_SELECTORS` が埋まったら、`eltax_rpa_worker.py` の各ヘルパー
（`_login` / `_navigate_to_issue_request` / `_fill_and_submit_issue_request` /
`_get_payment_info_and_pdf` / `_logout`）内の `# TODO` を有効化し、
`raise ...`（未確定ガード）を削除します。

## 5. 有効化する

```python
SELECTORS_CONFIRMED = True
```

まず1社・1税目で少額 or テスト用途で発行を確認し、
納付情報（収納機関番号-納付番号-確認番号）が正しく取得できることを確認してから
本格運用に移してください。

> ⚠️ セレクタ未確認のまま `SELECTORS_CONFIRMED=True` にしないでください。
> 誤った画面・項目に入力して意図しない納付情報を発行するリスクがあります。
