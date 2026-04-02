# -*- coding: utf-8 -*-
"""
OCR処理とデータ抽出ユーティリティ
Google Cloud Vision API統合版
"""

import re
import os
from typing import Dict, Optional, List
from PIL import Image
import pytesseract


def extract_text_from_image(image_path: str, use_google_vision: bool = True) -> str:
    """
    画像からテキストを抽出
    
    Args:
        image_path: 画像ファイルのパス
        use_google_vision: Google Cloud Vision APIを使用するか（デフォルト: True）
    
    Returns:
        抽出されたテキスト
    """
    # Google Cloud Vision APIを優先的に使用
    if use_google_vision:
        try:
            return extract_text_with_google_vision(image_path)
        except Exception as e:
            print(f"Google Vision APIエラー: {e}")
            print("Tesseract OCRにフォールバック")
    
    # フォールバック: Tesseract OCR
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang='jpn')
        return text
    except Exception as e:
        print(f"Tesseract OCRエラー: {e}")
        return ""


def extract_text_with_google_vision(image_path: str) -> str:
    """
    Google Cloud Vision APIを使用して画像からテキストを抽出
    
    Args:
        image_path: 画像ファイルのパス
    
    Returns:
        抽出されたテキスト
    """
    from google.cloud import vision
    import io
    
    # 環境変数からAPIキーを取得
    google_credentials = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if not google_credentials:
        raise Exception("GOOGLE_APPLICATION_CREDENTIALS環境変数が設定されていません")
    
    # Vision APIクライアントを初期化
    client = vision.ImageAnnotatorClient()
    
    # 画像ファイルを読み込み
    with io.open(image_path, 'rb') as image_file:
        content = image_file.read()
    
    image = vision.Image(content=content)
    
    # テキスト検出を実行
    response = client.text_detection(image=image)
    texts = response.text_annotations
    
    if response.error.message:
        raise Exception(f'Google Vision API Error: {response.error.message}')
    
    # 最初の結果が全体のテキスト
    if texts:
        return texts[0].description
    
    return ""


def extract_phone_numbers(text: str) -> List[str]:
    """
    テキストから電話番号を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出された電話番号のリスト
    """
    # 日本の電話番号パターン
    patterns = [
        r'\d{2,4}-\d{2,4}-\d{4}',  # 03-1234-5678
        r'\d{3}-\d{3}-\d{4}',      # 090-1234-5678
        r'\(\d{2,4}\)\s*\d{2,4}-\d{4}',  # (03) 1234-5678
        r'\d{10,11}',              # 09012345678
    ]
    
    phone_numbers = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        phone_numbers.extend(matches)
    
    # 重複を削除
    return list(set(phone_numbers))


def extract_addresses(text: str) -> List[str]:
    """
    テキストから住所を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出された住所のリスト
    """
    # 日本の住所パターン（都道府県から始まる）
    prefectures = [
        '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
        '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
        '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
        '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
        '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
        '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
        '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
    ]
    
    addresses = []
    lines = text.split('\n')
    
    for line in lines:
        for prefecture in prefectures:
            if prefecture in line:
                # 都道府県を含む行全体を住所として抽出
                cleaned = line.strip()
                if cleaned and len(cleaned) > 5:  # 最低限の長さチェック
                    addresses.append(cleaned)
                    break
    
    return addresses


def extract_invoice_number(text: str) -> Optional[str]:
    """
    テキストからインボイス登録番号を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出されたインボイス登録番号（T + 13桁）
    """
    # インボイス登録番号パターン（T + 13桁の数字）
    patterns = [
        r'T\s*\d{13}',  # T 1234567890123
        r'T-\d{13}',    # T-1234567890123
        r'T\d{13}',     # T1234567890123
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.replace(' ', '').replace('-', ''))
        if match:
            # ハイフンとスペースを削除して正規化
            invoice_number = match.group(0).replace(' ', '').replace('-', '')
            # T + 13桁の形式に正規化
            if len(invoice_number) == 14 and invoice_number[0] == 'T':
                return invoice_number
    
    return None


def extract_corporate_number(text: str) -> Optional[str]:
    """
    テキストから法人番号を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出された法人番号（13桁）
    """
    # 法人番号パターン（13桁の数字）
    # インボイス番号（T付き）と区別するため、Tがないことを確認
    pattern = r'(?<!T)\b\d{13}\b'
    match = re.search(pattern, text)
    
    if match:
        return match.group(0)
    
    return None


def extract_postal_code(text: str) -> Optional[str]:
    """
    テキストから郵便番号を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出された郵便番号（最初の1件）
    """
    # 郵便番号パターン（〒123-4567 または 123-4567）
    pattern = r'〒?\s*(\d{3}-\d{4})'
    match = re.search(pattern, text)
    
    if match:
        return match.group(1)
    return None


def extract_company_name(text: str) -> Optional[str]:
    """
    テキストから会社名を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出された会社名
    """
    # 会社名のパターン（株式会社、有限会社、合同会社など）
    patterns = [
        r'株式会社[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+',
        r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+株式会社',
        r'有限会社[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+',
        r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+有限会社',
        r'合同会社[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+',
        r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+合同会社',
        r'合資会社[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+',
        r'合名会社[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+',
        # 略称対応
        r'㈱[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+',
        r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+㈱',
        r'\(株\)[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+',
        r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFa-zA-Z0-9]+\(株\)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            company_name = match.group(0)
            # 略称を正式名称に変換
            company_name = company_name.replace('㈱', '株式会社')
            company_name = company_name.replace('(株)', '株式会社')
            return company_name
    
    return None


def extract_amount(text: str) -> Optional[float]:
    """
    テキストから金額を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出された金額（最大値）
    """
    # 金額パターン（¥1,234 または 1,234円 または 1234）
    patterns = [
        r'¥\s*([\d,]+)',
        r'([\d,]+)\s*円',
        r'合計\s*[：:]\s*([\d,]+)',
        r'小計\s*[：:]\s*([\d,]+)',
    ]
    
    amounts = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # カンマを削除して数値に変換
            try:
                amount = float(match.replace(',', ''))
                amounts.append(amount)
            except ValueError:
                continue
    
    # 最大値を返す（通常、合計金額が最大）
    return max(amounts) if amounts else None


def extract_date(text: str) -> Optional[str]:
    """
    テキストから日付を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出された日付（YYYY-MM-DD形式）
    """
    # 日付パターン
    patterns = [
        r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})',  # 2024年1月1日, 2024/1/1, 2024-1-1
        r'(\d{4})\.(\d{1,2})\.(\d{1,2})',  # 2024.1.1
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            # YYYY-MM-DD形式に変換
            return f"{year}-{int(month):02d}-{int(day):02d}"
    
    return None


def process_receipt_image(image_path: str, use_google_vision: bool = True) -> Dict[str, any]:
    """
    レシート画像を処理して情報を抽出
    
    Args:
        image_path: 画像ファイルのパス
        use_google_vision: Google Cloud Vision APIを使用するか
    
    Returns:
        抽出された情報の辞書
    """
    # OCRでテキスト抽出
    text = extract_text_from_image(image_path, use_google_vision=use_google_vision)
    
    # 各種情報を抽出
    result = {
        'full_text': text,
        'raw_text': text,  # 後方互換性のため
        'company_name': extract_company_name(text),
        'phone_numbers': extract_phone_numbers(text),
        'addresses': extract_addresses(text),
        'postal_code': extract_postal_code(text),
        'amount': extract_amount(text),
        'date': extract_date(text),
        'invoice_number': extract_invoice_number(text),  # インボイス番号
        'corporate_number': extract_corporate_number(text),  # 法人番号
    }
    
    return result


def save_uploaded_file(file, upload_folder: str = 'uploads') -> str:
    """
    アップロードされたファイルを保存
    
    Args:
        file: アップロードされたファイルオブジェクト
        upload_folder: 保存先フォルダ
    
    Returns:
        保存されたファイルのパス
    """
    os.makedirs(upload_folder, exist_ok=True)
    
    # ファイル名を安全にする
    filename = file.filename
    filepath = os.path.join(upload_folder, filename)
    
    # 同名ファイルがある場合は連番を付ける
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(filepath):
        filename = f"{base}_{counter}{ext}"
        filepath = os.path.join(upload_folder, filename)
        counter += 1
    
    file.save(filepath)
    return filepath
