# -*- coding: utf-8 -*-
"""
血統書・チップ申請書のOCR処理ユーティリティ
Google Cloud Vision API（設定済みの場合）またはOpenAI Vision APIを使用して
PDFや画像から情報を抽出する。
"""
from __future__ import annotations
import os
import json
import base64
from pathlib import Path


def _encode_image(filepath: str) -> str:
    """画像ファイルをBase64エンコードする"""
    with open(filepath, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def extract_pedigree_info(filepath: str, scan_type: str = 'pedigree') -> dict:
    """
    血統書またはチップ申請書の画像/PDFからOCRで情報を抽出する。

    優先順位:
    1. Google Cloud Vision API（GOOGLE_CLOUD_VISION_API_KEY が設定されている場合）
    2. OpenAI Vision API（OPENAI_API_KEY が設定されている場合）
    3. どちらも未設定の場合はエラーを発生させる

    Returns:
        dict: 抽出された情報
            - pedigree_number: 血統書番号
            - microchip_number: マイクロチップ番号
            - registration_name: 登録名
            - breed: 犬種
            - gender: 性別
            - birth_date: 生年月日
            - father_name: 父犬名
            - mother_name: 母犬名
            - raw_text: OCRで読み取ったテキスト全文
    """
    filepath = str(filepath)
    ext = Path(filepath).suffix.lower()

    # PDFの場合は最初のページを画像に変換
    if ext == '.pdf':
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(filepath, first_page=1, last_page=1)
            if images:
                img_path = filepath.replace('.pdf', '_page1.jpg')
                images[0].save(img_path, 'JPEG')
                filepath = img_path
        except ImportError:
            raise Exception('PDFの処理にはpdf2imageが必要です。画像ファイル（JPG/PNG）でアップロードしてください。')

    # Google Cloud Vision APIを試みる
    google_api_key = os.environ.get('GOOGLE_CLOUD_VISION_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if google_api_key:
        return _extract_with_google_vision(filepath, scan_type, google_api_key)

    # OpenAI Vision APIを試みる
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    if openai_api_key:
        return _extract_with_openai_vision(filepath, scan_type, openai_api_key)

    raise Exception(
        'OCR APIキーが設定されていません。'
        'アプリ設定でGoogle Cloud Vision APIキーまたはOpenAI APIキーを設定してください。'
    )


def _extract_with_google_vision(filepath: str, scan_type: str, api_key: str) -> dict:
    """Google Cloud Vision APIでOCRを実行する"""
    import requests

    image_b64 = _encode_image(filepath)
    url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
    payload = {
        'requests': [{
            'image': {'content': image_b64},
            'features': [{'type': 'TEXT_DETECTION'}]
        }]
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    raw_text = ''
    try:
        raw_text = data['responses'][0]['fullTextAnnotation']['text']
    except (KeyError, IndexError):
        pass

    return _parse_pedigree_text(raw_text, scan_type)


def _extract_with_openai_vision(filepath: str, scan_type: str, api_key: str) -> dict:
    """OpenAI Vision APIでOCRを実行する"""
    import requests

    image_b64 = _encode_image(filepath)
    ext = Path(filepath).suffix.lower()
    mime = 'image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/png'

    if scan_type == 'pedigree':
        prompt = (
            '以下の血統書画像から情報を抽出してください。'
            'JSON形式で返してください: '
            '{"pedigree_number": "血統書番号", "registration_name": "登録名", '
            '"breed": "犬種", "gender": "male/female", "birth_date": "YYYY-MM-DD", '
            '"father_name": "父犬名", "mother_name": "母犬名", "microchip_number": "マイクロチップ番号", '
            '"raw_text": "読み取ったテキスト全文"}'
        )
    else:
        prompt = (
            '以下のマイクロチップ申請書画像から情報を抽出してください。'
            'JSON形式で返してください: '
            '{"microchip_number": "マイクロチップ番号", "registration_name": "登録名", '
            '"breed": "犬種", "gender": "male/female", "birth_date": "YYYY-MM-DD", '
            '"raw_text": "読み取ったテキスト全文"}'
        )

    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'gpt-4o',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{image_b64}'}}
            ]
        }],
        'max_tokens': 1000,
    }
    resp = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()['choices'][0]['message']['content']

    # JSONブロックを抽出
    try:
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    return {'raw_text': content, 'pedigree_number': None, 'microchip_number': None}


def _parse_pedigree_text(text: str, scan_type: str) -> dict:
    """
    OCRで読み取ったテキストから血統書情報を正規表現で抽出する。
    Google Vision APIのテキスト結果をパースする際に使用。
    """
    import re

    result = {
        'pedigree_number': None,
        'microchip_number': None,
        'registration_name': None,
        'breed': None,
        'gender': None,
        'birth_date': None,
        'father_name': None,
        'mother_name': None,
        'raw_text': text,
    }

    # 血統書番号（JKC形式: 英字2文字 + 数字）
    m = re.search(r'[A-Z]{2}\s*\d{6,8}', text)
    if m:
        result['pedigree_number'] = m.group(0).replace(' ', '')

    # マイクロチップ番号（15桁数字）
    m = re.search(r'\b\d{15}\b', text)
    if m:
        result['microchip_number'] = m.group(0)

    # 生年月日
    m = re.search(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})日?', text)
    if m:
        result['birth_date'] = f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'

    # 性別
    if '雄' in text or 'オス' in text or '♂' in text:
        result['gender'] = 'male'
    elif '雌' in text or 'メス' in text or '♀' in text:
        result['gender'] = 'female'

    return result
