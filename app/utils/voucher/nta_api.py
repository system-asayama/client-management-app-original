# -*- coding: utf-8 -*-
"""
国税庁インボイス登録番号検索API連携ユーティリティ
"""

import requests
from typing import Dict, Optional, List
import re


class NTAInvoiceAPI:
    """国税庁インボイス登録番号検索APIクライアント"""
    
    # 国税庁インボイス登録番号公表サイトWeb-API
    INVOICE_BASE_URL = "https://web-api.invoice-kohyo.nta.go.jp"
    # 国税庁法人番号システムWeb-API
    CORPORATE_BASE_URL = "https://api.houjin-bangou.nta.go.jp"
    
    def __init__(self, api_id: Optional[str] = None):
        """
        初期化
        
        Args:
            api_id: 国税庁Web-APIのアプリケーションID（任意）
        """
        self.api_id = api_id
    
    def search_by_invoice_number(self, invoice_number: str) -> Optional[Dict]:
        """
        インボイス登録番号で検索
        
        Args:
            invoice_number: インボイス登録番号（T + 13桁の数字）
        
        Returns:
            企業情報の辞書、見つからない場合はNone
        """
        # インボイス登録番号の正規化（Tを除去）
        number = invoice_number.strip().upper()
        if number.startswith('T'):
            number = number[1:]
        
        # 13桁の数字かチェック
        if not re.match(r'^\d{13}$', number):
            return None
        
        try:
            # 国税庁APIエンドポイント（実際のエンドポイントに合わせて調整）
            url = f"{self.INVOICE_BASE_URL}/4/num"
            params = {
                'id': self.api_id,
                'number': number,
                'type': '12',  # 法人番号指定
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # レスポンスデータの解析
                if data and 'count' in data and data['count'] > 0:
                    return self._parse_response(data)
            
            return None
            
        except Exception as e:
            print(f"国税庁API検索エラー: {e}")
            return None
    
    def search_by_corporate_number(self, corporate_number: str) -> Optional[Dict]:
        """
        法人番号で検索
        
        Args:
            corporate_number: 法人番号（13桁の数字）
        
        Returns:
            企業情報の辞書、見つからない場合はNone
        """
        # 法人番号の正規化
        number = corporate_number.strip()
        
        # 13桁の数字かチェック
        if not re.match(r'^\d{13}$', number):
            return None
        
        try:
            url = f"{self.INVOICE_BASE_URL}/4/num"
            params = {
                'id': self.api_id,
                'number': number,
                'type': '12',
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data and 'count' in data and data['count'] > 0:
                    return self._parse_response(data)
            
            return None
            
        except Exception as e:
            print(f"国税庁API検索エラー: {e}")
            return None
    
    def search_by_name(self, company_name: str, prefecture: Optional[str] = None) -> List[Dict]:
        """
        会社名で検索
        
        Args:
            company_name: 会社名
            prefecture: 都道府県（任意）
        
        Returns:
            企業情報のリスト
        """
        try:
            url = f"{self.INVOICE_BASE_URL}/4/name"
            params = {
                'id': self.api_id,
                'name': company_name,
                'type': '12',
            }
            
            if prefecture:
                params['address'] = prefecture
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data and 'count' in data and data['count'] > 0:
                    results = []
                    for item in data.get('corporations', []):
                        parsed = self._parse_corporation_data(item)
                        if parsed:
                            results.append(parsed)
                    return results
            
            return []
            
        except Exception as e:
            print(f"国税庁API検索エラー: {e}")
            return []
    
    def _parse_response(self, data: Dict) -> Optional[Dict]:
        """
        APIレスポンスをパース
        
        Args:
            data: APIレスポンスデータ
        
        Returns:
            パースされた企業情報
        """
        if not data or 'corporations' not in data or not data['corporations']:
            return None
        
        # 最初の結果を使用
        corp = data['corporations'][0]
        return self._parse_corporation_data(corp)
    
    def _parse_corporation_data(self, corp: Dict) -> Dict:
        """
        企業データをパース
        
        Args:
            corp: 企業データ
        
        Returns:
            パースされた企業情報
        """
        # 住所の結合
        address_parts = []
        if corp.get('prefectureName'):
            address_parts.append(corp['prefectureName'])
        if corp.get('cityName'):
            address_parts.append(corp['cityName'])
        if corp.get('streetNumber'):
            address_parts.append(corp['streetNumber'])
        
        address = ''.join(address_parts)
        
        # インボイス登録番号（Tプレフィックス付き）
        invoice_number = None
        if corp.get('registratedNumber'):
            invoice_number = f"T{corp['registratedNumber']}"
        
        return {
            '法人番号': corp.get('corporateNumber'),
            'インボイス登録番号': invoice_number,
            '会社名': corp.get('name'),
            '会社名カナ': corp.get('kana'),
            '郵便番号': corp.get('postalCode'),
            '住所': address,
            '都道府県': corp.get('prefectureName'),
            '市区町村': corp.get('cityName'),
            '番地': corp.get('streetNumber'),
            'インボイス登録有無': 1 if corp.get('registratedNumber') else 0,
            'インボイス登録日': corp.get('registrationDate'),
            '法人種別': corp.get('kind'),
        }


def normalize_phone_number(phone: str) -> str:
    """
    電話番号を正規化
    
    Args:
        phone: 電話番号
    
    Returns:
        正規化された電話番号
    """
    # ハイフンやスペースを削除
    normalized = re.sub(r'[\s\-\(\)]', '', phone)
    return normalized


def extract_invoice_number_from_text(text: str) -> Optional[str]:
    """
    テキストからインボイス登録番号を抽出
    
    Args:
        text: 検索対象のテキスト
    
    Returns:
        抽出されたインボイス登録番号
    """
    # Tから始まる13桁の数字
    pattern = r'T\d{13}'
    match = re.search(pattern, text)
    
    if match:
        return match.group(0)
    
    return None


def search_company_by_ocr_data(company_name: Optional[str] = None, 
                                address: Optional[str] = None, 
                                phone_number: Optional[str] = None,
                                api_id: Optional[str] = None) -> List[Dict]:
    """
    OCRで抽出した情報から企業情報を複合検索
    
    Args:
        company_name: 会社名
        address: 住所
        phone_number: 電話番号
        api_id: APIのID
    
    Returns:
        企業情報のリスト（インボイス番号と法人番号を含む）
    """
    api = NTAInvoiceAPI(api_id)
    results = []
    
    # 1. 会社名がある場合、会社名で検索
    if company_name:
        # 住所から都道府県を抽出
        prefecture = None
        if address:
            prefecture = extract_prefecture_from_address(address)
        
        # 会社名 + 都道府県で検索
        search_results = api.search_by_name(company_name, prefecture)
        
        if search_results:
            # 住所や電話番号でフィルタリング
            if address:
                search_results = filter_by_address(search_results, address)
            
            results.extend(search_results)
    
    # 2. 会社名がない場合、住所から都道府県・市区町村を抽出して検索
    elif address:
        prefecture = extract_prefecture_from_address(address)
        if prefecture:
            # 都道府県のみで検索（結果が多すぎる可能性あり）
            # 実際には市区町村も含めて絞り込む必要がある
            pass
    
    return results


def extract_prefecture_from_address(address: str) -> Optional[str]:
    """
    住所から都道府県を抽出
    
    Args:
        address: 住所
    
    Returns:
        都道府県名
    """
    prefectures = [
        '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
        '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
        '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
        '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
        '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
        '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
        '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
    ]
    
    for prefecture in prefectures:
        if prefecture in address:
            return prefecture
    
    return None


def filter_by_address(companies: List[Dict], target_address: str) -> List[Dict]:
    """
    住所の類似度で企業情報をフィルタリング
    
    Args:
        companies: 企業情報のリスト
        target_address: 対象住所
    
    Returns:
        フィルタリングされた企業情報のリスト
    """
    filtered = []
    
    for company in companies:
        company_address = company.get('住所', '')
        
        # 簡易的な類似度チェック（市区町村レベル）
        if company_address:
            # 都道府県を除いた住所で比較
            target_parts = target_address.split('県')[-1].split('都')[-1].split('府')[-1].split('道')[-1]
            company_parts = company_address.split('県')[-1].split('都')[-1].split('府')[-1].split('道')[-1]
            
            # 市区町村が一致するかチェック
            target_city = target_parts.split('市')[0] if '市' in target_parts else target_parts.split('区')[0] if '区' in target_parts else ''
            company_city = company_parts.split('市')[0] if '市' in company_parts else company_parts.split('区')[0] if '区' in company_parts else ''
            
            if target_city and company_city and target_city in company_city:
                filtered.append(company)
    
    return filtered if filtered else companies


def search_company_by_phone(phone_number: str, api_id: Optional[str] = None) -> Optional[Dict]:
    """
    電話番号から企業情報を検索（簡易実装）
    
    Note: 国税庁APIは電話番号検索に対応していないため、
          実際には別のデータソースやサービスが必要
    
    Args:
        phone_number: 電話番号
        api_id: APIのID
    
    Returns:
        企業情報、見つからない場合はNone
    """
    # TODO: 電話番号検索に対応した外部サービスの統合
    # 例: タウンページAPI、企業データベースサービスなど
    
    return None


def search_company_by_address(address: str, api_id: Optional[str] = None) -> List[Dict]:
    """
    住所から企業情報を検索
    
    Args:
        address: 住所
        api_id: APIのID
    
    Returns:
        企業情報のリスト
    """
    # 都道府県を抽出
    prefectures = [
        '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
        '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
        '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
        '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
        '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
        '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
        '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
    ]
    
    prefecture = None
    for pref in prefectures:
        if pref in address:
            prefecture = pref
            break
    
    # 住所から会社名を推測するのは困難なため、
    # 実際には別のアプローチが必要
    
    return []
