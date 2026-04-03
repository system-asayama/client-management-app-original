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
    """PDFを全ページJPG画像リストに変換する。画像ファイルはそのまま返す。"""
    ext = os.path.splitext(pdf_path)[1].lower()
    if ext != '.pdf':
        return [pdf_path]
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=dpi)
        tmp_paths = []
        for i, img in enumerate(images):
            tmp_path = pdf_path + f'_page{i+1}.jpg'
            img.save(tmp_path, 'JPEG', quality=80)
            tmp_paths.append(tmp_path)
        return tmp_paths
    except Exception as e:
        print(f'PDF変換エラー: {e}')
        return []


def _call_openai_vision_pages(image_paths: list, api_key: str, prompt: str, max_tokens: int = 4000) -> dict:
    """指定された画像ページリスト（最大4枚）をOpenAI Vision APIに送信する"""
    import requests
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
        'messages': [{'role': 'user', 'content': content}],
        'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'}
    }
    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers=headers, json=payload, timeout=120
    )
    response.raise_for_status()
    return json.loads(response.json()['choices'][0]['message']['content'])


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
        return json.loads(response.json()['choices'][0]['message']['content'])


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
        CHUNK = 3

        for chunk_start in range(0, len(image_paths), CHUNK):
            chunk = image_paths[chunk_start:chunk_start + CHUNK]
            if chunk_start == 0:
                data = _call_openai_vision_pages(chunk, api_key, prompt_header, max_tokens=4000)
                base_data = data
                raw_texts.append(data.get('raw_text', ''))
                for t in data.get('transactions', []):
                    t['deposit'] = to_float(t.get('deposit'))
                    t['withdrawal'] = to_float(t.get('withdrawal'))
                    t['balance'] = to_float(t.get('balance'))
                    all_transactions.append(t)
            else:
                data = _call_openai_vision_pages(chunk, api_key, prompt_transactions, max_tokens=4000)
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
        CHUNK = 3

        for chunk_start in range(0, len(image_paths), CHUNK):
            chunk = image_paths[chunk_start:chunk_start + CHUNK]
            if chunk_start == 0:
                data = _call_openai_vision_pages(chunk, api_key, prompt_header, max_tokens=4000)
                base_data = data
                raw_texts.append(data.get('raw_text', ''))
                for t in data.get('transactions', []):
                    t['amount'] = to_float(t.get('amount'))
                    all_transactions.append(t)
            else:
                data = _call_openai_vision_pages(chunk, api_key, prompt_transactions, max_tokens=4000)
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
    """通帳画像を処理して情報を抜出する（通帳モード）。"""
    empty = {'bank_name': None, 'branch_name': None, 'account_type': None,
             'account_number': None, 'account_holder': None,
             'period_start': None, 'period_end': None, 'transactions': [], 'raw_text': ''}
    if not api_key:
        return empty
    try:
        return extract_bank_statement_with_openai_vision(image_path, api_key)
    except Exception as e:
        print(f"通帳OCRエラー: {e}")
        return empty


def process_credit_statement_image(image_path: str, api_key: str = None) -> Dict:
    """クレジット明細画像を処理して情報を抜出する（クレジット明細モード）。"""
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
