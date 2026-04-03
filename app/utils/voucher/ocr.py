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


def _pdf_to_images(pdf_path: str, dpi: int = 72) -> list:
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


def extract_bank_statement_with_openai_vision(image_path: str, api_key: str) -> Dict:
    """
    OpenAI GPT-4o Vision APIを使用して通帳画像からデータを抜出する。
    PDFは全ページをチャンク処理してマージ。
    """
    prompt_header = """この画像は銀行通帳または通帳明細書です。
以下のJSON形式で情報を抜出してください。不明な場合はnullにしてください。
{
  "bank_name": "銀行名・金融機関名",
  "branch_name": "支店名",
  "account_type": "口座種別（普通・当座・定期など）",
  "account_number": "口座番号",
  "account_holder": "口座名義",
  "period_start": "明細期間開始日（YYYY-MM-DD形式）",
  "period_end": "明細期間終了日（YYYY-MM-DD形式）",
  "transactions": [
    {
      "date": "取引日付（YYYY-MM-DD形式）",
      "description": "摘要・取引内容",
      "deposit": "入金額（数値のみ、nullも可）",
      "withdrawal": "出金額（数値のみ、nullも可）",
      "balance": "残高（数値のみ、nullも可）",
      "note": "備考（nullも可）"
    }
  ],
  "raw_text": "画像内の全テキスト（改行区切り）"
}
transactionsは画像に記載されている全ての明細行を抜出してください。
JSONのみを返してください。説明文は不要です。"""

    prompt_transactions = """この画像は銀行通帳または通帳明細書の続きのページです。
明細行のみを抜出してください。以下のJSON形式で返してください。
{
  "transactions": [
    {
      "date": "取引日付（YYYY-MM-DD形式）",
      "description": "摘要・取引内容",
      "deposit": "入金額（数値のみ、nullも可）",
      "withdrawal": "出金額（数値のみ、nullも可）",
      "balance": "残高（数値のみ、nullも可）",
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


def process_bank_statement_image(image_path: str, api_key: str = None, google_vision_api_key: str = None) -> Dict:
    """通帳画像を処理して情報を抜出する（通帳モード）。
    
    処理方式（優先順）:
    1. Google Vision API（文字認識）+ GPT-4o（構造化）: 最高精度
    2. GPT-4o Vision単体: 標準精度
    3. エラー時: 空データを返す
    """
    empty = {'bank_name': None, 'branch_name': None, 'account_type': None,
             'account_number': None, 'account_holder': None,
             'period_start': None, 'period_end': None, 'transactions': [], 'raw_text': ''}
    
    if not api_key and not google_vision_api_key:
        return empty
    
    # 方式1: Google Vision + GPT-4o（最高精度）
    if google_vision_api_key and api_key:
        try:
            print(f"[OCR] Google Vision APIで文字認識中: {image_path}")
            ocr_text = extract_text_with_google_vision_api_key(image_path, google_vision_api_key)
            print(f"[OCR] Google Vision成功: {len(ocr_text)}文字")
            print(f"[OCR] OCRテキスト先頭200文字: {repr(ocr_text[:200])}")
            
            prompt_template = """以下は日本の銀行通帳または通帳明細書からOCRで読み取ったテキストです。
以下のJSON形式で情報を抜出してください。不明な場合はnullにしてください。

【通帳の列構造】
左から順に: 「年月日」 | 「記号」 | 「お払戈し金額（出金）」 | 「お預り金額／お利息（入金）」 | 「差引残高」 | 「備考」

【列の判定ルール】
① 「記号」列（100、900などの数字）は取引種別コード。入金・出金に絶対に含めない。
② 「お払戈し金額」列（左側の金額）に数値がある場合 → withdrawal（出金）に記入、depositはnull
③ 「お預り金額」列（右側の金額）に数値がある場合 → deposit（入金）に記入、withdrawalはnull
④ 1行に入金と出金の両方があることはない。必ずどちらか一方はnull。

【残高の判定ルール】
① 「差引残高」列の数値のみをbalanceに入れる
② 「*」「,」は除去して数値のみ返す
③ 残高の直後に「980」「181」「960」「217」などの3桁数字が続く場合、それは備考欄の手数記号であり残高に含めない
  例: "*30,812,649980*" → balance=30812649、noteに980を記載
④ 最後に「手1」「手2」などの手数記号が付く場合は除去

【日付の変換ルール】
① "08-03-16" → 2008年3月16日 → "2008-03-16"
② 2桁年: "00"-"29" → 2000-2029年、"30"-"99" → 1930-1999年
③ 平成: H1=1989年、H2=1990年...H31=2019年、令和: R1=2019年、R2=2020年...
④ 必ずYYYY-MM-DD形式で返す

【摘要の判定ルール】
- 摘要列に記載された文字列をそのまま description に入れる
- 備考欄（最右列）の内容は note に入れる
- 摘要と備考を混同しないこと

{{
  "bank_name": "銀行名・金融機関名",
  "branch_name": "支店名",
  "account_type": "口座種別（普通・当座・定期など）",
  "account_number": "口座番号",
  "account_holder": "口座名義",
  "period_start": "明細期間開始日（YYYY-MM-DD形式）",
  "period_end": "明細期間終了日（YYYY-MM-DD形式）",
  "transactions": [
    {{
      "date": "取引日付（YYYY-MM-DD形式）",
      "description": "摘要・取引内容",
      "deposit": "入金額（お預り金額列の値のみ、数値のみ、出金の場合はnull）",
      "withdrawal": "出金額（お払戈し金額列の値のみ、数値のみ、入金の場合はnull）",
      "balance": "差引残高（数値のみ、備考欄の手数記号を含めない）",
      "note": "備考（手数記号など）"
    }}
  ]
}}
transactionsは全ての明細行を抜出してください。一行も欠かさないようにしてください。
JSONのみを返してください。説明文は不要です。

OCRテキスト:
{OCR_TEXT}"""
            
            data = _call_openai_vision_with_text(ocr_text, api_key, prompt_template, max_tokens=16000)
            
            import re
            def to_float(val):
                if val is None:
                    return None
                try:
                    s = str(val)
                    # 「*」「¥」「円」「,」を除去
                    s = s.replace('*', '').replace(',', '').replace('¥', '').replace('円', '')
                    # 残高の最後に付く手数記号（手1、手2、手3など）を除去
                    s = re.sub(r'手\d+$', '', s.strip())
                    s = s.strip()
                    if not s:
                        return None
                    return float(s)
                except (ValueError, TypeError):
                    return None
            
            for t in data.get('transactions', []):
                t['deposit'] = to_float(t.get('deposit'))
                t['withdrawal'] = to_float(t.get('withdrawal'))
                t['balance'] = to_float(t.get('balance'))
            
            if not data.get('raw_text'):
                data['raw_text'] = ocr_text
            
            print(f"[OCR] 構造化完了: {len(data.get('transactions', []))}件の取引")
            return data
        except Exception as e:
            print(f"[OCR] Google Vision + GPT-4oエラー: {e}、GPT-4o Visionにフォールバック")
    
    # 方式2: GPT-4o Vision単体
    if api_key:
        try:
            return extract_bank_statement_with_openai_vision(image_path, api_key)
        except Exception as e:
            print(f"通帳OCRエラー: {e}")
    
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
