# -*- coding: utf-8 -*-
"""
OCR処理とデータ抽出ユーティリティ
OpenAI Vision API（GPT-4o）統合版
PDFは全ページをチャンク処理してマージ
"""

import re
import os
import json
import base64
from typing import Dict, Optional, List


def _encode_image_to_base64(image_path: str) -> str:
    """画像ファイルをBase64エンコードする"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def _pdf_to_images(pdf_path: str, dpi: int = 200) -> list:
    """PDFを全ページJPG画像リストに変換する（PyMuPDF使用）。画像ファイルはそのまま返す。"""
    ext = os.path.splitext(pdf_path)[1].lower()
    if ext != '.pdf':
        return [pdf_path]
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        tmp_paths = []
        scale = dpi / 72.0
        mat = fitz.Matrix(scale, scale)
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat)
            tmp_path = pdf_path + f'_page{i+1}.jpg'
            pix.save(tmp_path)
            tmp_paths.append(tmp_path)
        doc.close()
        return tmp_paths
    except Exception as e:
        print(f'PDF変換エラー: {e}')
        return []


def _call_openai_vision_pages(image_paths: list, api_key: str, prompt: str, max_tokens: int = 8000, retry: int = 2) -> dict:
    """指定された画像ページリストをOpenAI Vision APIに送信する（contentがnullの場合はリトライ）"""
    import requests
    import time
    system_message = (
        'あなたは日本語文書のOCR専門家です。'
        '漢字・ひらがな・カタカナを正確に読み取ってください。'
        '似た文字（例：「ー」と「一」、「0」とO、「土」と「士」など）は文脈から正しく判断してください。'
        '店名・会社名・人名の漢字は特に慎重に読み取ってください。'
        '必ずJSON形式のみで返してください。説明文は不要です。'
    )
    content = [{'type': 'text', 'text': prompt}]
    for p in image_paths:
        img_data = _encode_image_to_base64(p)
        content.append({'type': 'image_url', 'image_url': {
            'url': f'data:image/jpeg;base64,{img_data}',
            'detail': 'high'
        }})
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'gpt-4o',
        'messages': [
            {'role': 'system', 'content': system_message},
            {'role': 'user', 'content': content}
        ],
        'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'}
    }
    for attempt in range(retry + 1):
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers, json=payload, timeout=120
        )
        response.raise_for_status()
        resp_json = response.json()
        choice = resp_json.get('choices', [{}])[0]
        raw_content = choice.get('message', {}).get('content')
        finish_reason = choice.get('finish_reason', '')
        if not raw_content:
            print(f'[OCR] contentがNull: finish_reason={finish_reason}, attempt={attempt+1}/{retry+1}')
            if attempt < retry:
                time.sleep(2)
                continue
            return {'transactions': [], 'raw_text': f'[APIエラー: finish_reason={finish_reason}]'}
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError:
            transactions = []
            for m in re.finditer(r'\{[^{}]+\}', raw_content):
                try:
                    obj = json.loads(m.group())
                    if any(k in obj for k in ('date', 'store_name', 'amount', 'deposit', 'withdrawal')):
                        transactions.append(obj)
                except Exception:
                    pass
            return {'transactions': transactions, 'raw_text': raw_content[:500]}
    return {'transactions': [], 'raw_text': '[リトライ上限超過]'}


def _call_openai_vision_with_system(image_path: str, api_key: str, prompt: str, max_tokens: int = 16000) -> dict:
    """通帳用Vision API呼び出し。システムプロンプト付き、detail=high、max_tokens大。"""
    import requests
    import time
    system_message = (
        'あなたは日本の銀行通帳のOCR専門家です。'
        '画像を極めて注意深く分析し、各列（年月日・記号・お払戈し金額・お預り金額・差引残高・備考）の内容を正確に読み取ってください。'
        '手書き文字は文脈と慣用句を考慮して正確に読んでください。'
        '「*」は金額の修飾記号であり、金額の一部ではありません。「*3,413,114」は3413114です。'
        '記号列（100、900など）は取引種別コードであり、金額ではありません。'
        '必ずJSON形式のみで返してください。説明文は不要です。'
    )
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
    mime_type = mime_map.get(ext, 'image/jpeg')
    image_data = _encode_image_to_base64(image_path)
    content = [
        {'type': 'text', 'text': prompt},
        {'type': 'image_url', 'image_url': {
            'url': f'data:{mime_type};base64,{image_data}',
            'detail': 'high'
        }}
    ]
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'gpt-4o',
        'messages': [
            {'role': 'system', 'content': system_message},
            {'role': 'user', 'content': content}
        ],
        'max_tokens': max_tokens,
        'temperature': 0  # 安定した出力のためtemperature=0
        # response_formatは指定しない（自由形式の方が数値精度が高い）
    }
    for attempt in range(3):
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers, json=payload, timeout=180
        )
        response.raise_for_status()
        resp_json = response.json()
        choice = resp_json.get('choices', [{}])[0]
        raw_content = choice.get('message', {}).get('content', '')
        finish_reason = choice.get('finish_reason', '')
        print(f'[OCR] Vision応答: finish_reason={finish_reason}, 入力トークン={resp_json.get("usage", {}).get("prompt_tokens")}, 出力トークン={resp_json.get("usage", {}).get("completion_tokens")}')
        if not raw_content:
            if attempt < 2:
                time.sleep(2)
                continue
            return {'transactions': []}
        # 自由形式レスポンスからJSONを抽出（コードブロックや説明文を除去）
        # まず```json ... ```ブロックを探す
        json_match = re.search(r'```(?:json)?\s*([\s\S]+?)```', raw_content)
        if json_match:
            raw_content = json_match.group(1).strip()
        else:
            # 最初の{}または[]を探す
            brace_match = re.search(r'(\{[\s\S]+\}|\[[\s\S]+\])', raw_content)
            if brace_match:
                raw_content = brace_match.group(1).strip()
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError as e:
            print(f'[OCR] JSONパースエラー: {e}, attempt={attempt+1}')
            if attempt < 2:
                time.sleep(2)
                continue
            return {'transactions': []}
    return {'transactions': []}


def _call_openai_vision(image_path: str, api_key: str, prompt: str, max_tokens: int = 2000) -> dict:
    """単一ファイル（画像またはPDF1ページ目）のVision API呼び出し（レシート用）"""
    import requests
    ext = os.path.splitext(image_path)[1].lower()
    if ext == '.pdf':
        image_paths = _pdf_to_images(image_path)
        if not image_paths:
            raise ValueError('PDFを画像に変換できませんでした')
        result = _call_openai_vision_pages(image_paths[:4], api_key, prompt, max_tokens)
        for p in image_paths:
            try:
                os.remove(p)
            except Exception:
                pass
        return result
    else:
        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
        mime_type = mime_map.get(ext, 'image/jpeg')
        image_data = _encode_image_to_base64(image_path)
        content = [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {
                'url': f'data:{mime_type};base64,{image_data}',
                'detail': 'high'
            }}
        ]
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': 'gpt-4o',
            'messages': [{'role': 'user', 'content': content}],
            'max_tokens': max_tokens,
            'response_format': {'type': 'json_object'}
        }
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers, json=payload, timeout=120
        )
        response.raise_for_status()
        raw_content = response.json()['choices'][0]['message'].get('content')
        if not raw_content:
            return {}
        return json.loads(raw_content)


def extract_text_with_openai_vision(image_path: str, api_key: str) -> Dict:
    """
    OpenAI GPT-4o Vision APIを使用して証桯画像からデータを抜出する。
    """
    prompt = """この画像は領収書・請求書・レシートなどの証桯書類です。
以下の情報をJSON形式で抜出してください。不明な場合はnullにしてください。
{
  "company_name": "発行会社・店舗名（文字列）",
  "date": "日付（YYYY-MM-DD形式）",
  "amount": "合計金額（数値のみ、円記号・カンマなし）",
  "phone": "電話番号（文字列）",
  "address": "住所（文字列）",
  "postal_code": "郵便番号（123-4567形式）",
  "invoice_number": "インボイス登録番号（T+13桁、例: T1234567890123）",
  "corporate_number": "法人番号（13桁の数字のみ）",
  "summary": "品目・摘要の簡潔な説明（文字列）",
  "raw_text": "画像内の全テキスト（改行区切り）"
}
JSONのみを返してください。説明文は不要です。"""

    data = _call_openai_vision(image_path, api_key, prompt, max_tokens=1000)
    if data.get('amount') is not None:
        try:
            data['amount'] = float(str(data['amount']).replace(',', '').replace('¥', '').replace('円', '').strip())
        except (ValueError, TypeError):
            data['amount'] = None
    return data


def extract_bank_statement_with_openai_vision(image_path: str, api_key: str, column_def: dict = None) -> Dict:
    """
    OpenAI GPT-4o Vision APIを使用して通帳画像からデータを抜出する。
    PDFは全ページをチャンク処理してマージ。
    """
    # 列定義をプロンプトに組み込む
    if column_def and column_def.get('columns'):
        col_lines = []
        for i, col in enumerate(column_def['columns'], 1):
            col_name = col.get('name', '')
            col_type = col.get('type', '')
            col_note = col.get('note', '')
            line = f'  列{i}: {col_name}'
            if col_note:
                line += f'（{col_note}）'
            col_lines.append(line)
        col_structure = '\n'.join(col_lines)
        col_rules = []
        for i, col in enumerate(column_def['columns'], 1):
            col_type = col.get('type', '')
            col_name = col.get('name', '')
            if col_type == 'code':
                col_rules.append(f'列{i}（{col_name}）は取引コードであり金額ではない。deposit/withdrawalに入れない。')
            elif col_type == 'withdrawal':
                col_rules.append(f'列{i}（{col_name}）に数値がある → withdrawal（出金）に記入、depositはnull')
            elif col_type == 'deposit':
                col_rules.append(f'列{i}（{col_name}）に数値がある → deposit（入金）に記入、withdrawalはnull')
        col_rules_str = '\n'.join(col_rules) if col_rules else '  列の位置（左右）で入金・出金を判断する。'
    else:
        col_structure = '  列１: 年月日（日付）\n  列２: 記号（100・900などの数字コード ← これは金額ではない）\n  列３: お払戻し金額（出金額）← 左側の金額列\n  列４: お預り金額/お利息（入金額）← 右側の金額列\n  列５: 差引残高\n  列６: 備考（手数記号など）'
        col_rules_str = '  列の位置（左右）で入金・出金を判断する。\n  記号列（100・900など）は取引コードであり金額ではない。'

    prompt_header = f"""この画像は日本の銀行通帳です。画像を極めて注意深く見て、各セルの値を正確に読み取り、JSON形式で返してください。

【列構造】通帳は左から以下の列で構成されています：
{col_structure}

【最重要ルール - 必ず守ること】
1. 各列の役割に従って値を読み取る（列定義を厳守）：
{col_rules_str}
2. 1行に入金と出金が同時に存在することはない。必ずどちらか一方のみ。
3. 「*」は金額の修飾記号。「*98,800」→ 98800、「*3,413,114」→ 3413114（数値のみ、桁数を変えない）
4. 残高は差引残高列の値のみ。直後の備考数字（980・960・186・217など）は残高に含めない。
5. 金額・残高の桁数は必ず正確に読む。カンマの位置を確認して桁数を間違えないこと。
   - 「*98,800」は98800（5桁）。988000（6桁）ではない。
   - 「*3,413,114」は3413114（7桁）。34131140（8桁）ではない。
   - 「*30,000,000」は30000000（8桁）。
6. 日付は画像の各行の日付列を正確に読む。前の行の日付を引き継がない。

【摘要の読み取り】
- 印字（活字）部分 → description
- 手書き部分（カッコ内など） → note
  例: 「カード〃(植松 ノートパソコン)」→ description="カード", note="植松 ノートパソコン"
  例: 「カード〃(浅山さん3月給料)」→ description="カード", note="浅山さん3月給料"
  例: 「デントウ - 3カツ」→ description="デントウ", note="3カツ"
  例: 「オカヤマケンコクミンケンコ」→ description="オカヤマケンコクミンケンコ"（全て印字）
- 「〃」「″」は「同上」の略記符号
- 備考欄（最右列）の手数記号もnoteに含める

【日付変換】
- "08-03-16" → "2008-03-16"（2桁年: 00-29→2000年代、30-99→1900年代）
- 平成: H1=1989, 令和: R1=2019

{
  "bank_name": "銀行名",
  "branch_name": "支店名",
  "account_type": "口座種別",
  "account_number": "口座番号",
  "account_holder": "口座名義",
  "period_start": "YYYY-MM-DD",
  "period_end": "YYYY-MM-DD",
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "摘要（印字部分のみ）",
      "deposit": 入金額の数値またはnull,
      "withdrawal": 出金額の数値またはnull,
      "balance": 残高の数値,
      "note": "手書き部分・備考"
    }
  ]
}
全ての明細行を一行も欠かさず抜出してください。JSONのみを返してください。"""

    prompt_transactions = """この画像は日本の銀行通帳の続きのページです。
画像を直接見て、列の位置を視覚的に判断して明細行のみを抜出してください。

【列の判定ルール】
① 「記号」列（100、900など）は取引種別コード。入金・出金に絶対に含めない。
② 「お払戈し金額」列（左側の金額列）に数値がある場偈 → withdrawal（出金）、depositはnull
③ 「お預り金額」列（右側の金額列）に数値がある場偈 → deposit（入金）、withdrawalはnull
④ 1行に入金と出金の両方はありえない。必ずどちらか一方はnull。
⑤ 「*」の付いた金額は正規の金額（「*」は除去）

【残高】差引残高列の数値のみ。備考欄の数字は含めない。
【日付】"08-03-16" → "2008-03-16"（2桁年は西暦変換）

{
  "transactions": [
    {
      "date": "取引日付（YYYY-MM-DD形式）",
      "description": "摘要・取引内容（摘要列のみ）",
      "deposit": "入金額（お預り金額列の値のみ、数値のみ、出金の場偈はnull）",
      "withdrawal": "出金額（お払戈し金額列の値のみ、数値のみ、入金の場偈はnull）",
      "balance": "差引残高（数値のみ、備考欄の手数記号を含めない）",
      "note": "備考（手数記号など）"
    }
  ],
  "raw_text": "このページの全テキスト"
}
transactionsは画像の全明細行を抜出してください。一行も欠かさないようにしてください。
JSONのみを返してください。説明文は不要です。"""

    def to_float(val):
        if val is None:
            return None
        try:
            return float(str(val).replace(',', '').replace('¥', '').replace('円', '').replace('*', '').strip())
        except (ValueError, TypeError):
            return None

    def fix_transactions_by_balance(transactions: list) -> list:
        """
        残高チェックにより入出金の誤りを自動修正する。
        前行残高 + 入金 - 出金 = 今行残高 が成立するか検証し、
        成立しない場合は入出金の入れ替えを試みる。
        """
        TOLERANCE = 5  # 丸め誤差許容（円）
        fixed_count = 0

        for i in range(1, len(transactions)):
            prev = transactions[i - 1]
            curr = transactions[i]

            prev_balance = prev.get('balance')
            curr_balance = curr.get('balance')
            deposit = curr.get('deposit') or 0
            withdrawal = curr.get('withdrawal') or 0

            # 残高が両方ある場合のみチェック
            if prev_balance is None or curr_balance is None:
                continue

            expected = prev_balance + deposit - withdrawal
            diff = abs(expected - curr_balance)

            if diff <= TOLERANCE:
                continue  # 正しい

            # 入出金を入れ替えて再チェック
            expected_swapped = prev_balance + withdrawal - deposit
            diff_swapped = abs(expected_swapped - curr_balance)

            if diff_swapped <= TOLERANCE:
                # 入れ替えで合う → 修正
                old_dep = curr.get('deposit')
                old_wit = curr.get('withdrawal')
                curr['deposit'] = old_wit if old_wit else None
                curr['withdrawal'] = old_dep if old_dep else None
                fixed_count += 1
                print(f'[残高チェック] {i+1}行目 入出金を入れ替え修正: 摘要={curr.get("description")}, 入金={curr["deposit"]}, 出金={curr["withdrawal"]}')
            else:
                print(f'[残高チェック] {i+1}行目 不一致（自動修正不可）: 摘要={curr.get("description")}, 期待残高={expected:.0f}, 実際残高={curr_balance:.0f}, 差={diff:.0f}')

        if fixed_count > 0:
            print(f'[残高チェック] 合計{fixed_count}行を自動修正しました')
        return transactions

    ext = os.path.splitext(image_path)[1].lower()
    if ext != '.pdf':
        # JPEG/PNG: max_tokensを16000に増やして全明細を確実に出力
        data = _call_openai_vision_with_system(image_path, api_key, prompt_header, max_tokens=16000)
        for t in data.get('transactions', []):
            t['deposit'] = to_float(t.get('deposit'))
            t['withdrawal'] = to_float(t.get('withdrawal'))
            t['balance'] = to_float(t.get('balance'))
        return data

    # PDF: 全ページをチャンク処理（4ページずつ）
    image_paths = _pdf_to_images(image_path)
    if not image_paths:
        raise ValueError('PDFを画像に変換できませんでした')

    try:
        all_transactions = []
        base_data = None
        raw_texts = []
        CHUNK = 2

        for chunk_start in range(0, len(image_paths), CHUNK):
            chunk = image_paths[chunk_start:chunk_start + CHUNK]
            if chunk_start == 0:
                data = _call_openai_vision_pages(chunk, api_key, prompt_header, max_tokens=8000)
                base_data = data
                raw_texts.append(data.get('raw_text', ''))
                for t in data.get('transactions', []):
                    t['deposit'] = to_float(t.get('deposit'))
                    t['withdrawal'] = to_float(t.get('withdrawal'))
                    t['balance'] = to_float(t.get('balance'))
                    all_transactions.append(t)
            else:
                data = _call_openai_vision_pages(chunk, api_key, prompt_transactions, max_tokens=8000)
                raw_texts.append(data.get('raw_text', ''))
                for t in data.get('transactions', []):
                    t['deposit'] = to_float(t.get('deposit'))
                    t['withdrawal'] = to_float(t.get('withdrawal'))
                    t['balance'] = to_float(t.get('balance'))
                    all_transactions.append(t)

        result = base_data or {}
        result['transactions'] = all_transactions
        result['raw_text'] = '\n'.join(raw_texts)
        return result
    finally:
        for p in image_paths:
            try:
                os.remove(p)
            except Exception:
                pass


def extract_credit_statement_with_openai_vision(image_path: str, api_key: str) -> Dict:
    """
    OpenAI GPT-4o Vision APIを使用してクレジット明細画像からデータを抜出する。
    PDFは全ページをチャンク処理してマージ。
    """
    prompt_header = """この画像はクレジットカードの利用明細書です。
以下のJSON形式で情報を抜出してください。不明な場合はnullにしてください。
{
  "card_company": "カード会社名（例: American Express, JCB, VISA, 楽天カードなど）",
  "card_name": "カード名・品名",
  "member_name": "会員名義",
  "statement_month": "明細年月（YYYY-MM形式）",
  "payment_date": "支払日（YYYY-MM-DD形式）",
  "total_amount": "利用総額（数値のみ）",
  "transactions": [
    {
      "date": "利用日（YYYY-MM-DD形式）",
      "store_name": "利用店名・内容",
      "user_name": "利用者名（nullも可）",
      "amount": "利用金額（数値のみ）",
      "installment": "分割回数・支払方法（nullも可）",
      "note": "備考（nullも可）"
    }
  ],
  "raw_text": "画像内の全テキスト（改行区切り）"
}
transactionsは画像に記載されている全ての利用明細行を抜出してください。
JSONのみを返してください。説明文は不要です。"""

    prompt_transactions = """この画像はクレジットカード利用明細書の続きのページです。
利用明細行のみを抜出してください。以下のJSON形式で返してください。
{
  "transactions": [
    {
      "date": "利用日（YYYY-MM-DD形式）",
      "store_name": "利用店名・内容",
      "user_name": "利用者名（nullも可）",
      "amount": "利用金額（数値のみ）",
      "installment": "分割回数・支払方法（nullも可）",
      "note": "備考（nullも可）"
    }
  ],
  "raw_text": "このページの全テキスト"
}
JSONのみを返してください。説明文は不要です。"""

    def to_float(val):
        if val is None:
            return None
        try:
            return float(str(val).replace(',', '').replace('¥', '').replace('円', '').strip())
        except (ValueError, TypeError):
            return None

    ext = os.path.splitext(image_path)[1].lower()
    if ext != '.pdf':
        data = _call_openai_vision(image_path, api_key, prompt_header, max_tokens=4000)
        data['total_amount'] = to_float(data.get('total_amount'))
        for t in data.get('transactions', []):
            t['amount'] = to_float(t.get('amount'))
        return data

    # PDF: 全ページをチャンク処理（4ページずつ）
    image_paths = _pdf_to_images(image_path)
    if not image_paths:
        raise ValueError('PDFを画像に変換できませんでした')

    try:
        all_transactions = []
        base_data = None
        raw_texts = []
        CHUNK = 2

        for chunk_start in range(0, len(image_paths), CHUNK):
            chunk = image_paths[chunk_start:chunk_start + CHUNK]
            if chunk_start == 0:
                data = _call_openai_vision_pages(chunk, api_key, prompt_header, max_tokens=8000)
                base_data = data
                raw_texts.append(data.get('raw_text', ''))
                for t in data.get('transactions', []):
                    t['amount'] = to_float(t.get('amount'))
                    all_transactions.append(t)
            else:
                data = _call_openai_vision_pages(chunk, api_key, prompt_transactions, max_tokens=8000)
                raw_texts.append(data.get('raw_text', ''))
                for t in data.get('transactions', []):
                    t['amount'] = to_float(t.get('amount'))
                    all_transactions.append(t)

        result = base_data or {}
        result['total_amount'] = to_float(result.get('total_amount'))
        result['transactions'] = all_transactions
        result['raw_text'] = '\n'.join(raw_texts)
        return result
    finally:
        for p in image_paths:
            try:
                os.remove(p)
            except Exception:
                pass


def _call_google_vision_single(image_path: str, api_key: str) -> str:
    """単一画像ファイルをGoogle Cloud Vision APIに送信してテキストを取得する"""
    import requests
    import base64
    with open(image_path, 'rb') as f:
        image_content = base64.b64encode(f.read()).decode('utf-8')
    url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
    payload = {
        'requests': [{
            'image': {'content': image_content},
            'features': [{'type': 'DOCUMENT_TEXT_DETECTION', 'maxResults': 1}],
            'imageContext': {'languageHints': ['ja', 'en']}
        }]
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    if 'error' in result:
        raise Exception(f"Vision API Error: {result['error']}")
    responses = result.get('responses', [])
    if not responses:
        return ''
    first_response = responses[0]
    if 'error' in first_response:
        raise Exception(f"Vision API Response Error: {first_response['error']}")
    full_text_annotation = first_response.get('fullTextAnnotation', {})
    text = full_text_annotation.get('text', '')
    if not text:
        text_annotations = first_response.get('textAnnotations', [])
        if text_annotations:
            text = text_annotations[0].get('description', '')
    return text


def extract_text_with_google_vision_api_key(image_path: str, api_key: str) -> str:
    """
    Google Cloud Vision API（REST APIキー認証）で画像またはPDFからテキストを抽出する。
    PDFの場合は全ページを画像変換して各ページを処理する。
    日本語漢字の認識精度が高い。
    """
    ext = os.path.splitext(image_path)[1].lower()
    if ext == '.pdf':
        # PDFは全ページを画像変換して各ページをGoogle Visionで処理
        image_paths = _pdf_to_images(image_path, dpi=150)
        if not image_paths:
            raise ValueError('PDFを画像に変換できませんでした')
        try:
            all_texts = []
            for i, page_path in enumerate(image_paths):
                try:
                    print(f'[OCR] Google Vision: ページ{i+1}/{len(image_paths)}処理中')
                    page_text = _call_google_vision_single(page_path, api_key)
                    if page_text:
                        all_texts.append(page_text)
                except Exception as e:
                    print(f'[OCR] ページ{i+1}エラー: {e}')
            return '\n'.join(all_texts)
        finally:
            for p in image_paths:
                try:
                    os.remove(p)
                except Exception:
                    pass
    else:
        return _call_google_vision_single(image_path, api_key)


def _call_openai_vision_with_text(text: str, api_key: str, prompt_template: str, max_tokens: int = 4000) -> dict:
    """
    Google Visionで抜出したテキストをOpenAIに渡してJSON構造化する。
    """
    import requests
    import time
    
    system_message = (
        'あなたは日本語文書のOCR専門家です。'
        '漢字・ひらがな・カタカナを正確に読み取ってください。'
        '必ずJSON形式のみで返してください。説明文は不要です。'
    )
    
    prompt = prompt_template.replace('{OCR_TEXT}', text)
    print(f'[OCR] GPT-4oに送信するプロンプト長: {len(prompt)}文字, max_tokens={max_tokens}')
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'gpt-4o',
        'messages': [
            {'role': 'system', 'content': system_message},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'}
    }
    
    for attempt in range(3):
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers, json=payload, timeout=120
        )
        response.raise_for_status()
        resp_json = response.json()
        choice = resp_json.get('choices', [{}])[0]
        raw_content = choice.get('message', {}).get('content')
        finish_reason = choice.get('finish_reason', '')
        usage = resp_json.get('usage', {})
        print(f'[OCR] GPT-4oレスポンス: finish_reason={finish_reason}, 入力トークン={usage.get("prompt_tokens")}, 出力トークン={usage.get("completion_tokens")}')
        if not raw_content:
            print(f'[OCR] GPT-4oレスポンスが空: attempt={attempt+1}')
            if attempt < 2:
                time.sleep(2)
                continue
            return {}
        print(f'[OCR] GPT-4o生レスポンス先頭300文字: {raw_content[:300]}')
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError as e:
            print(f'[OCR] JSONパースエラー: {e}, レスポンス: {raw_content[:200]}')
            return {'raw_text': raw_content[:500]}
    return {}


def process_bank_statement_image(image_path: str, api_key: str = None, google_vision_api_key: str = None, column_def: dict = None) -> Dict:
    """通帳画像を処理して情報を抜出する（通帳モード）。
    
    処理方式（優先順）:
    1. GPT-4o Vision直接（画像を直接渡す）: 最高精度（列構造を視覚的に判断）
    2. エラー時: 空データを返す
    """
    empty = {'bank_name': None, 'branch_name': None, 'account_type': None,
             'account_number': None, 'account_holder': None,
             'period_start': None, 'period_end': None, 'transactions': [], 'raw_text': ''}
    
    if not api_key:
        return empty
    
    # GPT-4o Vision直接（画像を直接渡して列構造を視覚的に判断）
    try:
        print(f"[OCR] GPT-4o Vision直接処理開始: {image_path}")
        result = extract_bank_statement_with_openai_vision(image_path, api_key, column_def=column_def)
        print(f"[OCR] GPT-4o Vision完了: {len(result.get('transactions', []))}件の取引")
        return result
    except Exception as e:
        print(f"[OCR] GPT-4o Visionエラー: {e}")
    
    return empty


def process_credit_statement_image(image_path: str, api_key: str = None, google_vision_api_key: str = None) -> Dict:
    """クレジット明細画像を処理して情報を抜出する（クレジット明細モード）。
    
    処理方式（優先順）:
    1. Google Vision API（文字認識）+ GPT-4o（構造化）: 最高精度
    2. GPT-4o Vision単体: 標準精度
    3. エラー時: 空データを返す
    """
    empty = {'card_company': None, 'card_name': None, 'member_name': None,
             'statement_month': None, 'payment_date': None,
             'total_amount': None, 'transactions': [], 'raw_text': ''}
    
    if not api_key and not google_vision_api_key:
        return empty
    
    # 方式1: Google Vision + GPT-4o（最高精度）
    if google_vision_api_key and api_key:
        try:
            print(f"[OCR] Google Vision APIで文字認識中: {image_path}")
            ocr_text = extract_text_with_google_vision_api_key(image_path, google_vision_api_key)
            print(f"[OCR] Google Vision成功: {len(ocr_text)}文字")
            print(f"[OCR] OCRテキスト先頭200文字: {repr(ocr_text[:200])}")
            
            prompt_template = """以下はクレジットカードの利用明細書からOCRで読み取ったテキストです。
以下のJSON形式で情報を抜出してください。不明な場合はnullにしてください。
{{
  "card_company": "カード会社名（例: American Express, JCB, VISA, 楽天カードなど）",
  "card_name": "カード名・品名",
  "member_name": "会員名義",
  "statement_month": "明細年月（YYYY-MM形式）",
  "payment_date": "支払日（YYYY-MM-DD形式）",
  "total_amount": "利用総額（数値のみ）",
  "transactions": [
    {{
      "date": "利用日（YYYY-MM-DD形式）",
      "store_name": "利用店名・内容",
      "user_name": "利用者名",
      "amount": "利用金額（数値のみ）",
      "installment": "分割回数・支払い方法",
      "note": "備考"
    }}
  ]
}}
transactionsは全ての利用明細行を抜出してください。
JSONのみを返してください。説明文は不要です。

OCRテキスト:
{OCR_TEXT}"""
            
            data = _call_openai_vision_with_text(ocr_text, api_key, prompt_template, max_tokens=16000)
            
            def to_float(val):
                if val is None:
                    return None
                try:
                    return float(str(val).replace(',', '').replace('¥', '').replace('円', '').strip())
                except (ValueError, TypeError):
                    return None
            
            data['total_amount'] = to_float(data.get('total_amount'))
            for t in data.get('transactions', []):
                t['amount'] = to_float(t.get('amount'))
            
            if not data.get('raw_text'):
                data['raw_text'] = ocr_text
            
            print(f"[OCR] 構造化完了: {len(data.get('transactions', []))}件の明細")
            print(f"[OCR] GPT-4oレスポンス先頭500文字: {str(data)[:500]}")
            return data
        except Exception as e:
            import traceback
            print(f"[OCR] Google Vision + GPT-4oエラー: {e}\n{traceback.format_exc()}、GPT-4o Visionにフォールバック")
    
    # 方式2: GPT-4o Vision単体
    if api_key:
        try:
            return extract_credit_statement_with_openai_vision(image_path, api_key)
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            print(f"クレジット明細OCRエラー: {e}\n{err_detail}")
            empty['_error'] = str(e)
    
    return empty


def process_receipt_image(image_path: str, api_key: str = None) -> Dict:
    """
    レシート画像を処理して情報を抽出する。
    api_keyが指定されている場合はOpenAI Vision APIを使用。
    指定がない場合は手動入力モード（空データ）を返す。
    """
    empty_result = {
        'full_text': '',
        'raw_text': '',
        'company_name': None,
        'phone_numbers': [],
        'addresses': [],
        'postal_code': None,
        'amount': None,
        'date': None,
        'invoice_number': None,
        'corporate_number': None,
        'summary': None,
    }

    if not api_key:
        return empty_result

    try:
        data = extract_text_with_openai_vision(image_path, api_key)
        result = {
            'full_text': data.get('raw_text', ''),
            'raw_text': data.get('raw_text', ''),
            'company_name': data.get('company_name'),
            'phone_numbers': [data['phone']] if data.get('phone') else [],
            'addresses': [data['address']] if data.get('address') else [],
            'postal_code': data.get('postal_code'),
            'amount': data.get('amount'),
            'date': data.get('date'),
            'invoice_number': data.get('invoice_number'),
            'corporate_number': data.get('corporate_number'),
            'summary': data.get('summary'),
        }
        return result
    except Exception as e:
        print(f"OpenAI Vision APIエラー: {e}")
        return empty_result


def save_uploaded_file(file, upload_folder: str = 'uploads') -> str:
    """
    アップロードされたファイルを保存する。
    """
    os.makedirs(upload_folder, exist_ok=True)

    filename = file.filename
    filepath = os.path.join(upload_folder, filename)

    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(filepath):
        filename = f"{base}_{counter}{ext}"
        filepath = os.path.join(upload_folder, filename)
        counter += 1

    file.save(filepath)
    return filepath
