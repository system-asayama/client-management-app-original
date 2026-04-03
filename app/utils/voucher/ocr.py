# -*- coding: utf-8 -*-
"""
OCR処理とデータ抽出ユーティリティ
OpenAI Vision API（GPT-4o）統合版
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


def extract_text_with_openai_vision(image_path: str, api_key: str) -> Dict:
    """
    OpenAI GPT-4o Vision APIを使用して証憑画像からデータを抽出する。
    テキスト抽出だけでなく、構造化データとして直接返す。

    Returns:
        抽出された情報の辞書
    """
    import requests

    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
    mime_type = mime_map.get(ext, 'image/jpeg')

    image_data = _encode_image_to_base64(image_path)

    prompt = """この画像は領収書・請求書・レシートなどの証憑書類です。
以下の情報をJSON形式で抽出してください。不明な場合はnullにしてください。

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

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'gpt-4o',
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {
                        'url': f'data:{mime_type};base64,{image_data}',
                        'detail': 'high'
                    }}
                ]
            }
        ],
        'max_tokens': 1000,
        'response_format': {'type': 'json_object'}
    }

    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers=headers,
        json=payload,
        timeout=60
    )
    response.raise_for_status()
    content = response.json()['choices'][0]['message']['content']
    data = json.loads(content)

    # amountを数値に変換
    if data.get('amount') is not None:
        try:
            data['amount'] = float(str(data['amount']).replace(',', '').replace('¥', '').replace('円', '').strip())
        except (ValueError, TypeError):
            data['amount'] = None

    return data


def process_receipt_image(image_path: str, api_key: str = None) -> Dict:
    """
    レシート画像を処理して情報を抽出する。
    api_keyが指定されている場合はOpenAI Vision APIを使用。
    指定がない場合は手動入力モード（空データ）を返す。

    Args:
        image_path: 画像ファイルのパス
        api_key: OpenAI APIキー（省略可）

    Returns:
        抽出された情報の辞書
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

    Args:
        file: アップロードされたファイルオブジェクト
        upload_folder: 保存先フォルダ

    Returns:
        保存されたファイルのパス
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
