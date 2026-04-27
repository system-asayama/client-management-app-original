# -*- coding: utf-8 -*-
"""
血統書・チップ申請書・遺伝疾患検査・股関節評価のOCR処理ユーティリティ
Google Cloud Vision API（設定済みの場合）またはOpenAI Vision APIを使用して
PDFや画像から情報を抽出する。

対応スキャンタイプ:
  - pedigree  : 血統書
  - chip      : マイクロチップ申請書
  - genetic   : 遺伝疾患検査結果書
  - hip       : 股関節評価書
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
    各種書類の画像/PDFからOCRで情報を抽出する。

    優先順位:
    1. Google Cloud Vision API（GOOGLE_CLOUD_VISION_API_KEY が設定されている場合）
    2. OpenAI Vision API（OPENAI_API_KEY が設定されている場合）
    3. どちらも未設定の場合はエラーを発生させる

    Args:
        filepath: 画像またはPDFのパス
        scan_type: 'pedigree' | 'chip' | 'genetic' | 'hip'

    Returns:
        dict: 抽出された情報（scan_typeによって異なる）
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

    # APIキーを階層順に取得
    # 1. アプリ設定 → 2. 店舗設定 → 3. テナント設定 → 4. システム管理者設定 → 5. 環境変数
    google_api_key, openai_api_key = _resolve_api_keys()

    # Google Cloud Vision APIを試みる
    if google_api_key:
        return _extract_with_google_vision(filepath, scan_type, google_api_key)

    # OpenAI Vision APIを試みる
    if openai_api_key:
        return _extract_with_openai_vision(filepath, scan_type, openai_api_key)

    raise Exception(
        'OCR APIキーが設定されていません。'
        'アプリ設定でGoogle Cloud Vision APIキーまたはOpenAI APIキーを設定してください。'
    )


def _resolve_api_keys() -> tuple:
    """
    APIキーを以下の優先順位で解決して返す:
    1. アプリ設定 (app_settings テーブル: key='google_vision_api_key' / 'openai_api_key')
    2. 店舗設定 (T_店舗テーブル: store_id はセッションから)
    3. テナント設定 (T_テナントテーブル)
    4. アプリ管理者グループ設定 (T_アプリ管理者グループテーブル)
    5. システム管理者設定 (T_管理者テーブル)
    6. 環境変数

    Returns:
        (google_vision_api_key, openai_api_key) のタプル。未設定の場合は None
    """
    import logging
    _log = logging.getLogger(__name__)
    google_key = None
    openai_key = None

    try:
        from flask import session as flask_session
        from app.db import SessionLocal

        db = SessionLocal()
        try:
            tenant_id = flask_session.get('tenant_id')
            store_id = flask_session.get('store_id')
            user_id = flask_session.get('user_id')
            _log.info(f'[OCR] _resolve_api_keys: tenant_id={tenant_id}, store_id={store_id}, user_id={user_id}')

            # ── 1. アプリ設定 (app_settings key-value) ──────────────────────────
            from app.models_breeder import AppSetting
            q = db.query(AppSetting)
            if tenant_id:
                q = q.filter(AppSetting.tenant_id == tenant_id)
            if store_id:
                q = q.filter(AppSetting.store_id == store_id)
            for row in q.all():
                if row.key == 'google_vision_api_key' and row.value:
                    google_key = row.value
                elif row.key == 'openai_api_key' and row.value:
                    openai_key = row.value
            if google_key or openai_key:
                return google_key, openai_key

            # ── 2. 店舗設定 (T_店舗) ────────────────────────────────────────────
            if store_id:
                from app.models_login import TTenpo
                tenpo = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                if tenpo:
                    google_key = getattr(tenpo, 'google_vision_api_key', None) or None
                    openai_key = getattr(tenpo, 'openai_api_key', None) or None
                    if google_key or openai_key:
                        return google_key, openai_key

            # ── 3. テナント設定 (T_テナント) ─────────────────────────────────────
            if tenant_id:
                from app.models_login import TTenant
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                if tenant:
                    google_key = getattr(tenant, 'google_vision_api_key', None) or None
                    openai_key = getattr(tenant, 'openai_api_key', None) or None
                    if google_key or openai_key:
                        return google_key, openai_key

            # ── 4. アプリ管理者グループ設定 (T_アプリ管理者グループ) ──────────────
            try:
                from app.models_login import TAppManagerGroup, TKanrisha
                groups = db.query(TAppManagerGroup).all()
                _log.info(f'[OCR] アプリ管理者グループ数: {len(groups)}')
                for group in groups:
                    gk = getattr(group, 'google_vision_api_key', None) or None
                    ok = getattr(group, 'openai_api_key', None) or None
                    _log.info(f'[OCR] グループid={group.id}: gvision={bool(gk)}, openai={bool(ok)}')
                    if gk or ok:
                        return gk, ok
            except Exception as e:
                _log.error(f'[OCR] アプリ管理者グループ取得エラー: {e}')

            # ── 5. システム管理者設定 (T_管理者 role='system_admin') ───────────────
            try:
                from app.models_login import TKanrisha
                sys_admins = db.query(TKanrisha).filter(
                    TKanrisha.role == 'system_admin'
                ).all()
                _log.info(f'[OCR] システム管理者数: {len(sys_admins)}')
                for sa in sys_admins:
                    gk = getattr(sa, 'google_vision_api_key', None) or None
                    ok = getattr(sa, 'openai_api_key', None) or None
                    _log.info(f'[OCR] システム管理者id={sa.id}: gvision={bool(gk)}, openai={bool(ok)}')
                    if gk or ok:
                        _log.info(f'[OCR] システム管理者id={sa.id}のAPIキーを使用')
                        return gk, ok
            except Exception as e:
                _log.error(f'[OCR] システム管理者取得エラー: {e}')

        finally:
            db.close()
    except Exception as e:
        _log.error(f'[OCR] _resolve_api_keys 全体エラー: {e}')

    # ── 6. 環境変数 ──────────────────────────────────────────────────────────
    google_key = os.environ.get('GOOGLE_CLOUD_VISION_API_KEY') or os.environ.get('GOOGLE_API_KEY') or None
    openai_key = os.environ.get('OPENAI_API_KEY') or None
    return google_key, openai_key


def _build_prompt(scan_type: str) -> str:
    """スキャンタイプに応じたプロンプトを返す"""
    if scan_type == 'pedigree':
        return (
            '以下の血統書画像から情報を抽出してください。'
            'JSON形式で返してください（値が不明な場合はnullにしてください）: '
            '{"pedigree_number": "血統書番号", "registration_name": "登録名", '
            '"breed": "犬種", "gender": "male/female/null", "birth_date": "YYYY-MM-DD or null", '
            '"father_name": "父犬名", "mother_name": "母犬名", '
            '"microchip_number": "マイクロチップ番号", '
            '"kennel_name": "犬舎名", "breeder_name": "ブリーダー名", '
            '"raw_text": "読み取ったテキスト全文"}'
        )
    elif scan_type == 'genetic':
        return (
            '以下の遺伝疾患検査結果書類の画像から情報を抽出してください。'
            'JSON形式で返してください（値が不明な場合はnullにしてください）: '
            '{"registration_name": "登録名または犬名", "breed": "犬種", '
            '"test_date": "検査日YYYY-MM-DD or null", "lab_name": "検査機関名", '
            '"results": [{"disease_name": "疾患名", "result": "clear/carrier/affected/null"}], '
            '"raw_text": "読み取ったテキスト全文"}'
        )
    elif scan_type == 'hip':
        return (
            '以下の股関節評価書類の画像から情報を抽出してください。'
            'JSON形式で返してください（値が不明な場合はnullにしてください）: '
            '{"registration_name": "登録名または犬名", "breed": "犬種", '
            '"evaluation_date": "評価日YYYY-MM-DD or null", "evaluator": "評価機関名", '
            '"left_score": "左股関節スコア", "right_score": "右股関節スコア", '
            '"overall_grade": "総合評価（A/B/C/D/E等）", '
            '"raw_text": "読み取ったテキスト全文"}'
        )
    else:
        # chip / その他
        return (
            '以下のマイクロチップ申請書画像から情報を抽出してください。'
            'JSON形式で返してください（値が不明な場合はnullにしてください）: '
            '{"microchip_number": "マイクロチップ番号", "registration_name": "登録名", '
            '"breed": "犬種", "gender": "male/female/null", "birth_date": "YYYY-MM-DD or null", '
            '"raw_text": "読み取ったテキスト全文"}'
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
    prompt = _build_prompt(scan_type)

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
        'max_tokens': 1500,
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
    OCRで読み取ったテキストから書類情報を正規表現で抽出する。
    Google Vision APIのテキスト結果をパースする際に使用。
    """
    import re

    if scan_type == 'genetic':
        return {
            'registration_name': None,
            'breed': None,
            'test_date': None,
            'lab_name': None,
            'results': [],
            'raw_text': text,
        }

    if scan_type == 'hip':
        result = {
            'registration_name': None,
            'breed': None,
            'evaluation_date': None,
            'evaluator': None,
            'left_score': None,
            'right_score': None,
            'overall_grade': None,
            'raw_text': text,
        }
        m = re.search(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})日?', text)
        if m:
            result['evaluation_date'] = f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
        for grade in ['A', 'B', 'C', 'D', 'E']:
            if f'総合{grade}' in text or f'評価{grade}' in text:
                result['overall_grade'] = grade
                break
        return result

    # pedigree / chip 共通
    result = {
        'pedigree_number': None,
        'microchip_number': None,
        'registration_name': None,
        'breed': None,
        'gender': None,
        'birth_date': None,
        'father_name': None,
        'mother_name': None,
        'kennel_name': None,
        'breeder_name': None,
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


def apply_scan_result_to_dog(dog, result: dict, scan_type: str) -> list[str]:
    """
    OCR結果をDogオブジェクトに適用する。
    変更されたフィールド名のリストを返す。
    """
    changed = []
    if scan_type == 'pedigree':
        if result.get('pedigree_number') and not dog.pedigree_number:
            dog.pedigree_number = result['pedigree_number']
            changed.append('血統書番号')
        if result.get('microchip_number') and not dog.microchip_number:
            dog.microchip_number = result['microchip_number']
            changed.append('マイクロチップ番号')
        if result.get('registration_name') and not dog.registration_name:
            dog.registration_name = result['registration_name']
            changed.append('登録名')
        if result.get('birth_date') and not dog.birth_date:
            from datetime import date
            try:
                y, mo, d = result['birth_date'].split('-')
                dog.birth_date = date(int(y), int(mo), int(d))
                changed.append('生年月日')
            except Exception:
                pass
        if result.get('gender') and not dog.gender:
            dog.gender = result['gender']
            changed.append('性別')
    elif scan_type == 'chip':
        if result.get('microchip_number') and not dog.microchip_number:
            dog.microchip_number = result['microchip_number']
            changed.append('マイクロチップ番号')
    return changed
