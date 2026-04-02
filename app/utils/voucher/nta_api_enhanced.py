"""
国税庁API拡張モジュール
電話番号・住所から法人番号を検索し、インボイス番号を取得する
"""

import requests
from typing import Dict, Optional, List, Tuple
import re
from .nta_api import NTAInvoiceAPI, extract_prefecture_from_address


def search_corporate_number_by_contact(
    phone_number: Optional[str] = None,
    address: Optional[str] = None,
    company_name: Optional[str] = None,
    api_id: Optional[str] = None
) -> Optional[str]:
    """
    電話番号・住所・会社名から法人番号を検索
    
    Args:
        phone_number: 電話番号
        address: 住所
        company_name: 会社名
        api_id: APIのID
    
    Returns:
        法人番号（13桁）、見つからない場合はNone
    """
    api = NTAInvoiceAPI(api_id)
    
    # 会社名がある場合、会社名で検索
    if company_name:
        prefecture = None
        if address:
            prefecture = extract_prefecture_from_address(address)
        
        results = api.search_by_name(company_name, prefecture)
        
        if results and len(results) > 0:
            # 最初の候補の法人番号を返す
            return results[0].get('法人番号')
    
    # TODO: 電話番号や住所のみでの検索は国税庁APIでは直接サポートされていないため、
    # 別の企業データベースAPIを使用するか、会社名の推定が必要
    
    return None


def search_invoice_by_corporate_number(
    corporate_number: str,
    api_id: Optional[str] = None
) -> Optional[Dict]:
    """
    法人番号からインボイス番号を検索
    
    Args:
        corporate_number: 法人番号（13桁）
        api_id: APIのID
    
    Returns:
        企業情報（インボイス番号を含む）、見つからない場合はNone
    """
    api = NTAInvoiceAPI(api_id)
    return api.search_by_corporate_number(corporate_number)


def verify_invoice_number(
    ocr_invoice_number: str,
    searched_invoice_number: Optional[str]
) -> Tuple[bool, Optional[str]]:
    """
    OCRで読み取ったインボイス番号と検索結果を照合
    
    Args:
        ocr_invoice_number: OCRで読み取ったインボイス番号
        searched_invoice_number: 検索で取得したインボイス番号
    
    Returns:
        (一致するか, 警告メッセージ)
    """
    if not ocr_invoice_number or not searched_invoice_number:
        return True, None
    
    # 正規化（T、ハイフン、スペースを削除）
    ocr_normalized = ocr_invoice_number.replace('T', '').replace('-', '').replace(' ', '')
    searched_normalized = searched_invoice_number.replace('T', '').replace('-', '').replace(' ', '')
    
    if ocr_normalized == searched_normalized:
        return True, None
    else:
        return False, f"警告: OCRで読み取ったインボイス番号（{ocr_invoice_number}）と検索結果（{searched_invoice_number}）が一致しません"


def enhanced_company_search(
    ocr_result: Dict,
    api_id: Optional[str] = None
) -> Dict:
    """
    OCR結果から企業情報を検索（拡張版）
    
    フロー:
    1. レシートにインボイス番号がある場合 → 最優先で使用
    2. 電話番号・住所・会社名から法人番号を検索
    3. 法人番号からインボイス番号を検索
    4. OCRで読み取った番号と検索結果を照合
    
    Args:
        ocr_result: OCR結果の辞書
        api_id: APIのID
    
    Returns:
        検索結果の辞書
    """
    result = {
        'company_info': None,
        'invoice_number': None,
        'corporate_number': None,
        'ocr_invoice_number': ocr_result.get('invoice_number'),
        'verification_passed': True,
        'warning_message': None,
    }
    
    # 1. OCRでインボイス番号が読み取れた場合
    ocr_invoice = ocr_result.get('invoice_number')
    if ocr_invoice:
        api = NTAInvoiceAPI(api_id)
        company_info = api.search_by_invoice_number(ocr_invoice)
        
        if company_info:
            result['company_info'] = company_info
            result['invoice_number'] = company_info.get('インボイス登録番号')
            result['corporate_number'] = company_info.get('法人番号')
    
    # 2. 電話番号・住所・会社名から法人番号を検索
    corporate_number = search_corporate_number_by_contact(
        phone_number=ocr_result.get('phone_numbers', [None])[0] if ocr_result.get('phone_numbers') else None,
        address=ocr_result.get('addresses', [None])[0] if ocr_result.get('addresses') else None,
        company_name=ocr_result.get('company_name'),
        api_id=api_id
    )
    
    if corporate_number:
        result['corporate_number'] = corporate_number
        
        # 3. 法人番号からインボイス番号を検索
        company_info = search_invoice_by_corporate_number(corporate_number, api_id)
        
        if company_info:
            if not result['company_info']:
                result['company_info'] = company_info
            
            searched_invoice = company_info.get('インボイス登録番号')
            
            # 4. OCRで読み取った番号と検索結果を照合
            if ocr_invoice and searched_invoice:
                is_match, warning = verify_invoice_number(ocr_invoice, searched_invoice)
                result['verification_passed'] = is_match
                result['warning_message'] = warning
                
                # 検索結果を優先
                result['invoice_number'] = searched_invoice
            else:
                result['invoice_number'] = searched_invoice
    
    return result
