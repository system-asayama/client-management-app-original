# -*- coding: utf-8 -*-
"""
Google Cloud Vision API ヘルパー関数
"""

import os
import json
import base64
import tempfile


def setup_google_credentials():
    """
    環境変数からGoogle Cloud認証情報を設定
    
    Heroku環境では、JSONファイルをbase64エンコードした文字列を
    GOOGLE_APPLICATION_CREDENTIALS_JSON環境変数に設定する
    """
    # 既にGOOGLE_APPLICATION_CREDENTIALSが設定されている場合はスキップ
    if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        return
    
    # GOOGLE_APPLICATION_CREDENTIALS_JSON環境変数からJSONを取得
    credentials_json_base64 = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    
    if not credentials_json_base64:
        print("Warning: GOOGLE_APPLICATION_CREDENTIALS_JSON環境変数が設定されていません")
        print("Google Cloud Vision APIは使用できません。Tesseract OCRにフォールバックします。")
        return
    
    try:
        # base64デコード
        credentials_json = base64.b64decode(credentials_json_base64).decode('utf-8')
        
        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(credentials_json)
            temp_path = f.name
        
        # 環境変数に設定
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_path
        
        print(f"Google Cloud認証情報を設定しました: {temp_path}")
        
    except Exception as e:
        print(f"Google Cloud認証情報の設定に失敗しました: {e}")
        print("Tesseract OCRにフォールバックします。")


def is_google_vision_available() -> bool:
    """
    Google Cloud Vision APIが利用可能かチェック
    
    Returns:
        利用可能な場合True
    """
    return bool(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
