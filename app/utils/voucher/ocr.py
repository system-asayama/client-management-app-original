# -*- coding: utf-8 -*-
"""
OCR処理とデータ抽出ユーティリティ
OpenAI Vision API（GPT-4o）統合版
PDFは全ページをチャンク処理してマージ

【OCR精度改善のポイント】
1. DPIを72→200に引き上げ（漢字の細部を鮮明に）
2. Pillowで画像をシャープ化・コントラスト強化（前処理）
3. プロンプトに「日本語の漢字・カタカナ・ひらがなを正確に読む」よう明示
4. 1ページずつ処理（チャンクサイズ1）して各ページに集中
5. system_messageでOCR専門家として振る舞うよう指示
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


def _enhance_image(image_path: str) -> str:
    """
    Pillowで画像をシャープ化・コントラスト強化して漢字認識精度を上げる。
    処理済み画像のパスを返す（元ファイルは上書き）。
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        img = Image.open(image_path)

        # グレースケール変換（カラー情報は不要、文字認識に集中）
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # シャープネス強化（漢字の細い線を鮮明に）
        img = img.filter(ImageFilter.SHARPEN)
        img = img.filter(ImageFilter.SHARPEN)  # 2回適用

        # コントラスト強化（文字と背景のコントラストを上げる）
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        # 明度調整（明るすぎる場合に文字を見やすく）
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.05)

        img.save(image_path, 'JPEG', quality=85)
    except Exception as e:
        print(f'画像前処理エラー（スキップ）: {e}')
    return image_path


def _pdf_to_images(pdf_path: str, dpi: int = 150) -> list:
    """
    PDFを全ページJPG画像リストに変換する（PyMuPDF使用）。
    DPI=150で漢字の細部まで鮮明に変換しつつファイルサイズを抑える。
    画像ファイルはそのまま返す。
    """
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
            pix.save(tmp_path, jpg_quality=85)
            # 画像前処理（シャープ化・コントラスト強化）
            _enhance_image(tmp_path)
            tmp_paths.append(tmp_path)
        doc.close()
        return tmp_paths
    except Exception as e:
        print(f'PDF変換エラー: {e}')
        return []


def _call_openai_vision_pages(image_paths: list, api_key: str, prompt: str,
                               max_tokens: int = 8000, system_message: str = None) -> dict:
    """指定された画像ページリストをOpenAI Vision APIに送信する"""
    import requests

    messages = []

    # systemメッセージ（OCR専門家として振る舞う）
    if system_message:
        messages.append({'role': 'system', 'content': system_message})

    content = [{'type': 'text', 'text': prompt}]
    for p in image_paths:
        img_data = _encode_image_to_base64(p)
        content.append({'type': 'image_url', 'image_url': {
            'url': f'data:image/jpeg;base64,{img_data}',
            'detail': 'high'
        }})

    messages.append({'role': 'user', 'content': content})

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'gpt-4o',
        'messages': messages,
        'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'}
    }
    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers=headers, json=payload, timeout=120
    )
    response.raise_for_status()
    raw_content = response.json()['choices'][0]['message']['content']
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        # JSONが途中で切れている場合、transactionsリストを安全に抽出する
        transactions = []
        for m in re.finditer(r'\{[^{}]+\}', raw_content):
            try:
                obj = json.loads(m.group())
                if any(k in obj for k in ('date', 'store_name', 'amount', 'deposit', 'withdrawal', 'description')):
                    transactions.append(obj)
            except Exception:
                pass
        return {'transactions': transactions, 'raw_text': raw_content[:1000]}


def _call_openai_vision(image_path: str, api_key: str, prompt: str,
                         max_tokens: int = 2000, system_message: str = None) -> dict:
    """単一ファイル（画像またはPDF1ページ目）のVision API呼び出し（レシート用）"""
    import requests
    ext = os.path.splitext(image_path)[1].lower()
    if ext == '.pdf':
        image_paths = _pdf_to_images(image_path)
        if not image_paths:
            raise ValueError('PDFを画像に変換できませんでした')
        result = _call_openai_vision_pages(image_paths[:4], api_key, prompt, max_tokens, system_message)
        for p in image_paths:
            try:
                os.remove(p)
            except Exception:
                pass
        return result
    else:
        # 画像ファイルの場合も前処理を適用（コピーして処理）
        import shutil
        tmp_path = image_path + '_enhanced.jpg'
        shutil.copy2(image_path, tmp_path)
        _enhance_image(tmp_path)

        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
        mime_type = mime_map.get(ext, 'image/jpeg')
        image_data = _encode_image_to_base64(tmp_path)

        try:
            os.remove(tmp_path)
        except Exception:
            pass

        content = [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {
                'url': f'data:image/jpeg;base64,{image_data}',
                'detail': 'high'
            }}
        ]

        messages = []
        if system_message:
            messages.append({'role': 'system', 'content': system_message})
        messages.append({'role': 'user', 'content': content})

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': 'gpt-4o',
            'messages': messages,
            'max_tokens': max_tokens,
            'response_format': {'type': 'json_object'}
        }
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers, json=payload, timeout=120
        )
        response.raise_for_status()
        return json.loads(response.json()['choices'][0]['message']['content'])


# ============================================================
# システムメッセージ（OCR専門家として振る舞う）
# ============================================================
_SYSTEM_OCR_JA = """あなたは日本語文書のOCR専門家です。
以下のルールを厳守してください：
- 漢字・ひらがな・カタカナ・英数字を正確に読み取ること
- 似た文字（例：「ー」と「一」、「口」と「0」、「l」と「1」、「O」と「0」）を文脈から正しく判断すること
- 日本語の金融・会計書類に特有の表記（円、¥、△（マイナス）、▲（マイナス））を正しく解釈すること
- 店名・会社名・人名の漢字は特に慎重に読み取ること
- 数字はカンマ区切りを除いた純粋な数値として返すこと
- 不明な文字は推測せず、読み取れた文字のみを返すこと
- 必ずJSON形式のみを返し、説明文は一切含めないこと"""


def extract_text_with_openai_vision(image_path: str, api_key: str) -> Dict:
    """
    OpenAI GPT-4o Vision APIを使用して証憑画像からデータを抽出する。
    """
    prompt = """この画像は領収書・請求書・レシートなどの証憑書類です。
日本語の漢字・カタカナ・ひらがな・英数字を正確に読み取り、以下の情報をJSON形式で抽出してください。
不明な場合はnullにしてください。

{
  "company_name": "発行会社・店舗名（文字列、漢字を正確に）",
  "date": "日付（YYYY-MM-DD形式）",
  "amount": "合計金額（数値のみ、円記号・カンマなし）",
  "phone": "電話番号（文字列）",
  "address": "住所（文字列、都道府県から正確に）",
  "postal_code": "郵便番号（123-4567形式）",
  "invoice_number": "インボイス登録番号（T+13桁、例: T1234567890123）",
  "corporate_number": "法人番号（13桁の数字のみ）",
  "summary": "品目・摘要の簡潔な説明（文字列）",
  "raw_text": "画像内の全テキスト（改行区切り、漢字を正確に）"
}
JSONのみを返してください。説明文は不要です。"""

    data = _call_openai_vision(image_path, api_key, prompt, max_tokens=2000, system_message=_SYSTEM_OCR_JA)
    if data.get('amount') is not None:
        try:
            data['amount'] = float(str(data['amount']).replace(',', '').replace('¥', '').replace('円', '').strip())
        except (ValueError, TypeError):
            data['amount'] = None
    return data


def extract_bank_statement_with_openai_vision(image_path: str, api_key: str) -> Dict:
    """
    OpenAI GPT-4o Vision APIを使用して通帳画像からデータを抽出する。
    PDFは1ページずつ処理してマージ。
    """
    prompt_header = """この画像は銀行通帳または通帳明細書です。
日本語の漢字・カタカナ・ひらがなを正確に読み取り、以下のJSON形式で情報を抽出してください。
不明な場合はnullにしてください。

重要：
- 摘要欄の漢字（振込、引落、ATM、給与、家賃など）を正確に読み取ること
- 銀行名・支店名・口座名義の漢字を正確に読み取ること
- 金額は△や▲がついている場合はマイナス値として扱うこと
- 日付は年・月・日の漢字表記も含めてYYYY-MM-DD形式に変換すること

{
  "bank_name": "銀行名・金融機関名（漢字を正確に）",
  "branch_name": "支店名（漢字を正確に）",
  "account_type": "口座種別（普通・当座・定期など）",
  "account_number": "口座番号",
  "account_holder": "口座名義（漢字・カタカナを正確に）",
  "period_start": "明細期間開始日（YYYY-MM-DD形式）",
  "period_end": "明細期間終了日（YYYY-MM-DD形式）",
  "transactions": [
    {
      "date": "取引日付（YYYY-MM-DD形式）",
      "description": "摘要・取引内容（漢字・カタカナを正確に）",
      "deposit": "入金額（数値のみ、nullも可）",
      "withdrawal": "出金額（数値のみ、nullも可）",
      "balance": "残高（数値のみ、nullも可）",
      "note": "備考（nullも可）"
    }
  ],
  "raw_text": "画像内の全テキスト（改行区切り、漢字を正確に）"
}
transactionsは画像に記載されている全ての明細行を抽出してください。
JSONのみを返してください。説明文は不要です。"""

    prompt_transactions = """この画像は銀行通帳または通帳明細書のページです。
日本語の漢字・カタカナ・ひらがなを正確に読み取り、明細行のみを抽出してください。

重要：
- 摘要欄の漢字（振込、引落、ATM、給与、家賃など）を正確に読み取ること
- 金額は△や▲がついている場合はマイナス値として扱うこと
- 日付は年・月・日の漢字表記も含めてYYYY-MM-DD形式に変換すること

{
  "transactions": [
    {
      "date": "取引日付（YYYY-MM-DD形式）",
      "description": "摘要・取引内容（漢字・カタカナを正確に）",
      "deposit": "入金額（数値のみ、nullも可）",
      "withdrawal": "出金額（数値のみ、nullも可）",
      "balance": "残高（数値のみ、nullも可）",
      "note": "備考（nullも可）"
    }
  ],
  "raw_text": "このページの全テキスト（漢字を正確に）"
}
JSONのみを返してください。説明文は不要です。"""

    def to_float(val):
        if val is None:
            return None
        try:
            s = str(val).replace(',', '').replace('¥', '').replace('円', '').strip()
            # △▲はマイナス
            if s.startswith('△') or s.startswith('▲'):
                s = '-' + s[1:]
            return float(s)
        except (ValueError, TypeError):
            return None

    ext = os.path.splitext(image_path)[1].lower()
    if ext != '.pdf':
        # 画像ファイルの場合
        data = _call_openai_vision(image_path, api_key, prompt_header,
                                    max_tokens=8000, system_message=_SYSTEM_OCR_JA)
        for t in data.get('transactions', []):
            t['deposit'] = to_float(t.get('deposit'))
            t['withdrawal'] = to_float(t.get('withdrawal'))
            t['balance'] = to_float(t.get('balance'))
        return data

    # PDF: 1ページずつ処理してマージ（精度優先）
    image_paths = _pdf_to_images(image_path)
    if not image_paths:
        raise ValueError('PDFを画像に変換できませんでした')

    try:
        all_transactions = []
        base_data = None
        raw_texts = []

        for i, page_path in enumerate(image_paths):
            if i == 0:
                # 最初のページ：ヘッダー情報＋明細を取得
                data = _call_openai_vision_pages(
                    [page_path], api_key, prompt_header,
                    max_tokens=8000, system_message=_SYSTEM_OCR_JA
                )
                base_data = data
                raw_texts.append(data.get('raw_text', ''))
                for t in data.get('transactions', []):
                    t['deposit'] = to_float(t.get('deposit'))
                    t['withdrawal'] = to_float(t.get('withdrawal'))
                    t['balance'] = to_float(t.get('balance'))
                    all_transactions.append(t)
            else:
                # 2ページ目以降：明細のみ取得
                data = _call_openai_vision_pages(
                    [page_path], api_key, prompt_transactions,
                    max_tokens=8000, system_message=_SYSTEM_OCR_JA
                )
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
    OpenAI GPT-4o Vision APIを使用してクレジット明細画像からデータを抽出する。
    PDFは1ページずつ処理してマージ。
    """
    prompt_header = """この画像はクレジットカードの利用明細書です。
日本語の漢字・カタカナ・ひらがなを正確に読み取り、以下のJSON形式で情報を抽出してください。
不明な場合はnullにしてください。

重要：
- 利用店名の漢字・カタカナを正確に読み取ること（例：「スターバックス」「吉野家」「ヤマダ電機」）
- 会員名の漢字・カタカナを正確に読み取ること
- カード会社名を正確に読み取ること（例：アメリカン・エキスプレス、三井住友カード、楽天カード）
- 金額は△や▲がついている場合はマイナス値として扱うこと
- 日付は年・月・日の漢字表記も含めてYYYY-MM-DD形式に変換すること

{
  "card_company": "カード会社名（漢字・カタカナを正確に）",
  "card_name": "カード名・品名（漢字・カタカナを正確に）",
  "member_name": "会員名義（漢字・カタカナを正確に）",
  "statement_month": "明細年月（YYYY-MM形式）",
  "payment_date": "支払日（YYYY-MM-DD形式）",
  "total_amount": "利用総額（数値のみ）",
  "transactions": [
    {
      "date": "利用日（YYYY-MM-DD形式）",
      "store_name": "利用店名・内容（漢字・カタカナを正確に）",
      "user_name": "利用者名（漢字・カタカナを正確に、nullも可）",
      "amount": "利用金額（数値のみ）",
      "installment": "分割回数・支払方法（nullも可）",
      "note": "備考（nullも可）"
    }
  ],
  "raw_text": "画像内の全テキスト（改行区切り、漢字を正確に）"
}
transactionsは画像に記載されている全ての利用明細行を抽出してください。
JSONのみを返してください。説明文は不要です。"""

    prompt_transactions = """この画像はクレジットカード利用明細書のページです。
日本語の漢字・カタカナ・ひらがなを正確に読み取り、利用明細行のみを抽出してください。

重要：
- 利用店名の漢字・カタカナを正確に読み取ること（例：「スターバックス」「吉野家」「ヤマダ電機」）
- 利用者名の漢字・カタカナを正確に読み取ること
- 金額は△や▲がついている場合はマイナス値として扱うこと
- 日付は年・月・日の漢字表記も含めてYYYY-MM-DD形式に変換すること

{
  "transactions": [
    {
      "date": "利用日（YYYY-MM-DD形式）",
      "store_name": "利用店名・内容（漢字・カタカナを正確に）",
      "user_name": "利用者名（漢字・カタカナを正確に、nullも可）",
      "amount": "利用金額（数値のみ）",
      "installment": "分割回数・支払方法（nullも可）",
      "note": "備考（nullも可）"
    }
  ],
  "raw_text": "このページの全テキスト（漢字を正確に）"
}
JSONのみを返してください。説明文は不要です。"""

    def to_float(val):
        if val is None:
            return None
        try:
            s = str(val).replace(',', '').replace('¥', '').replace('円', '').strip()
            # △▲はマイナス
            if s.startswith('△') or s.startswith('▲'):
                s = '-' + s[1:]
            return float(s)
        except (ValueError, TypeError):
            return None

    ext = os.path.splitext(image_path)[1].lower()
    if ext != '.pdf':
        data = _call_openai_vision(image_path, api_key, prompt_header,
                                    max_tokens=8000, system_message=_SYSTEM_OCR_JA)
        data['total_amount'] = to_float(data.get('total_amount'))
        for t in data.get('transactions', []):
            t['amount'] = to_float(t.get('amount'))
        return data

    # PDF: 1ページずつ処理してマージ（精度優先）
    image_paths = _pdf_to_images(image_path)
    if not image_paths:
        raise ValueError('PDFを画像に変換できませんでした')

    try:
        all_transactions = []
        base_data = None
        raw_texts = []

        for i, page_path in enumerate(image_paths):
            if i == 0:
                data = _call_openai_vision_pages(
                    [page_path], api_key, prompt_header,
                    max_tokens=8000, system_message=_SYSTEM_OCR_JA
                )
                base_data = data
                raw_texts.append(data.get('raw_text', ''))
                for t in data.get('transactions', []):
                    t['amount'] = to_float(t.get('amount'))
                    all_transactions.append(t)
            else:
                data = _call_openai_vision_pages(
                    [page_path], api_key, prompt_transactions,
                    max_tokens=8000, system_message=_SYSTEM_OCR_JA
                )
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


def process_bank_statement_image(image_path: str, api_key: str = None) -> Dict:
    """通帳画像を処理して情報を抽出する（通帳モード）。"""
    empty = {'bank_name': None, 'branch_name': None, 'account_type': None,
             'account_number': None, 'account_holder': None,
             'period_start': None, 'period_end': None, 'transactions': [], 'raw_text': ''}
    if not api_key:
        return empty
    try:
        return extract_bank_statement_with_openai_vision(image_path, api_key)
    except Exception as e:
        import traceback
        err_detail = traceback.format_exc()
        print(f"通帳OCRエラー: {e}\n{err_detail}")
        empty['_error'] = str(e)
        return empty


def process_credit_statement_image(image_path: str, api_key: str = None) -> Dict:
    """クレジット明細画像を処理して情報を抽出する（クレジット明細モード）。"""
    empty = {'card_company': None, 'card_name': None, 'member_name': None,
             'statement_month': None, 'payment_date': None,
             'total_amount': None, 'transactions': [], 'raw_text': ''}
    if not api_key:
        return empty
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
