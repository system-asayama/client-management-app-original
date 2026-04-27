# -*- coding: utf-8 -*-
"""
血統書・チップ申請書・遺伝疾患検査・股関節評価のOCR処理ユーティリティ

処理フロー:
  1. Google Cloud Vision API でテキストを取得（設定済みの場合）
  2. OpenAI GPT-4o でテキストをJSON構造化（設定済みの場合）
  ※ Google Vision のみの場合は正規表現でパース
  ※ OpenAI のみの場合は Vision API として直接画像解析

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
import logging
from pathlib import Path

_log = logging.getLogger(__name__)


def _encode_image(filepath: str) -> str:
    """画像ファイルをBase64エンコードする"""
    with open(filepath, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def extract_pedigree_info(filepath: str, scan_type: str = 'pedigree') -> dict:
    """
    各種書類の画像/PDFからOCRで情報を抽出する。

    処理フロー:
    1. Google Cloud Vision API でテキスト取得 + OpenAI GPT で構造化（両方ある場合）
    2. OpenAI Vision API で直接解析（OpenAI のみの場合）
    3. Google Cloud Vision API + 正規表現パース（Google のみの場合）
    4. どちらも未設定の場合はエラー

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
    google_api_key, openai_api_key = _resolve_api_keys()

    if not google_api_key and not openai_api_key:
        raise Exception(
            'OCR APIキーが設定されていません。'
            'アプリ設定でGoogle Cloud Vision APIキーまたはOpenAI APIキーを設定してください。'
        )

    # ── ケース1: Google Vision + OpenAI GPT（最高精度）──────────────────────
    if google_api_key and openai_api_key:
        try:
            raw_text = _get_text_with_google_vision(filepath, google_api_key)
            if raw_text:
                result = _parse_text_with_openai(raw_text, scan_type, openai_api_key)
                result['raw_text'] = raw_text
                return result
        except Exception as e:
            _log.error(f'[OCR] Google Vision + OpenAI GPT エラー: {e}')
            # フォールバック: OpenAI Vision で直接解析
            return _extract_with_openai_vision(filepath, scan_type, openai_api_key)

    # ── ケース2: OpenAI Vision のみ（画像直接解析）──────────────────────────
    if openai_api_key:
        return _extract_with_openai_vision(filepath, scan_type, openai_api_key)

    # ── ケース3: Google Vision のみ（正規表現パース）────────────────────────
    if google_api_key:
        raw_text = _get_text_with_google_vision(filepath, google_api_key)
        return _parse_pedigree_text(raw_text, scan_type)


def _resolve_api_keys() -> tuple:
    """
    APIキーを以下の優先順位で解決して返す:
    1. アプリ設定 (app_settings テーブル)
    2. 店舗設定 (T_店舗テーブル)
    3. テナント設定 (T_テナントテーブル)
    4. アプリ管理者グループ設定 (T_アプリ管理者グループテーブル)
    5. システム管理者設定 (T_管理者テーブル)
    6. 環境変数

    Returns:
        (google_vision_api_key, openai_api_key) のタプル。未設定の場合は None
    """
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
            try:
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
                    _log.info('[OCR] アプリ設定からAPIキーを取得')
                    return google_key, openai_key
            except Exception as e:
                _log.error(f'[OCR] アプリ設定取得エラー: {e}')

            # ── 2. 店舗設定 (T_店舗) ────────────────────────────────────────────
            if store_id:
                try:
                    from app.models_login import TTenpo
                    tenpo = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                    if tenpo:
                        google_key = getattr(tenpo, 'google_vision_api_key', None) or None
                        openai_key = getattr(tenpo, 'openai_api_key', None) or None
                        if google_key or openai_key:
                            _log.info('[OCR] 店舗設定からAPIキーを取得')
                            return google_key, openai_key
                except Exception as e:
                    _log.error(f'[OCR] 店舗設定取得エラー: {e}')

            # ── 3. テナント設定 (T_テナント) ─────────────────────────────────────
            if tenant_id:
                try:
                    from app.models_login import TTenant
                    tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                    if tenant:
                        google_key = getattr(tenant, 'google_vision_api_key', None) or None
                        openai_key = getattr(tenant, 'openai_api_key', None) or None
                        if google_key or openai_key:
                            _log.info('[OCR] テナント設定からAPIキーを取得')
                            return google_key, openai_key
                except Exception as e:
                    _log.error(f'[OCR] テナント設定取得エラー: {e}')

            # ── 4. アプリ管理者グループ設定 ──────────────────────────────────────
            try:
                from app.models_login import TAppManagerGroup
                groups = db.query(TAppManagerGroup).all()
                _log.info(f'[OCR] アプリ管理者グループ数: {len(groups)}')
                for group in groups:
                    gk = getattr(group, 'google_vision_api_key', None) or None
                    ok = getattr(group, 'openai_api_key', None) or None
                    if gk or ok:
                        _log.info(f'[OCR] アプリ管理者グループid={group.id}のAPIキーを使用')
                        return gk, ok
            except Exception as e:
                _log.error(f'[OCR] アプリ管理者グループ取得エラー: {e}')

            # ── 5. システム管理者設定 ─────────────────────────────────────────────
            try:
                from app.models_login import TKanrisha
                sys_admins = db.query(TKanrisha).filter(
                    TKanrisha.role == 'system_admin'
                ).all()
                _log.info(f'[OCR] システム管理者数: {len(sys_admins)}')
                for sa in sys_admins:
                    gk = getattr(sa, 'google_vision_api_key', None) or None
                    ok = getattr(sa, 'openai_api_key', None) or None
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
    _log.info(f'[OCR] 環境変数からAPIキー: google={bool(google_key)}, openai={bool(openai_key)}')
    return google_key, openai_key


def _get_text_with_google_vision(filepath: str, api_key: str) -> str:
    """Google Cloud Vision APIでテキストのみを取得する"""
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

    try:
        return data['responses'][0]['fullTextAnnotation']['text']
    except (KeyError, IndexError):
        return ''


def _build_text_parse_prompt(scan_type: str) -> str:
    """テキストからJSON構造化するためのプロンプトを返す"""
    if scan_type == 'pedigree':
        return (
            'You are a dog pedigree document parser. '
            'Extract information from the following OCR text of a dog pedigree certificate. '
            'The document may be in Japanese, English, Thai, or a mix of languages. '
            'A standard pedigree has 4 generations of ancestors arranged in a tree: '
            'Gen1=sire/dam, Gen2=grandparents, Gen3=great-grandparents, Gen4=great-great-grandparents. '
            'Position codes: sire=father, dam=mother, sire_sire=paternal grandfather, sire_dam=paternal grandmother, '
            'dam_sire=maternal grandfather, dam_dam=maternal grandmother, '
            'sire_sire_sire, sire_sire_dam, sire_dam_sire, sire_dam_dam, '
            'dam_sire_sire, dam_sire_dam, dam_dam_sire, dam_dam_dam (Gen3), '
            'and 16 positions for Gen4 following the same pattern. '
            'Return ONLY a JSON object with these fields (use null for unknown values):\n'
            '{\n'
            '  "pedigree_number": "registration/pedigree number (e.g. KATH116037251, JKC番号)",\n'
            '  "registration_name": "dog\'s registered name (e.g. TH.CH.PLASMA-MS\'S MACH ONE)",\n'
            '  "breed": "breed name in Japanese if possible (e.g. ミニチュアシュナウザー, ゴールデンレトリバー)",\n'
            '  "gender": "male or female (look for MALE/FEMALE/雄/雌/オス/メス)",\n'
            '  "birth_date": "YYYY-MM-DD format (look for DATE WHELPED/生年月日/วันที่เกิด)",\n'
            '  "father_name": "sire/father dog name (look for SIRE/父)",\n'
            '  "mother_name": "dam/mother dog name (look for DAM/母)",\n'
            '  "microchip_number": "15-digit microchip number if present",\n'
            '  "kennel_name": "kennel name if present",\n'
            '  "breeder_name": "breeder name (look for BREEDER/ผู้เพาะพันธุ์)",\n'
            '  "ancestors": [\n'
            '    {"generation": 1, "position": "sire", "name": "...", "registration_number": "...", "color": "..."},\n'
            '    {"generation": 1, "position": "dam", "name": "...", "registration_number": "...", "color": "..."},\n'
            '    {"generation": 2, "position": "sire_sire", "name": "...", "registration_number": "..."},\n'
            '    {"generation": 2, "position": "sire_dam", "name": "...", "registration_number": "..."},\n'
            '    {"generation": 2, "position": "dam_sire", "name": "...", "registration_number": "..."},\n'
            '    {"generation": 2, "position": "dam_dam", "name": "...", "registration_number": "..."},\n'
            '    ... (continue for all ancestors found in gen3 and gen4)\n'
            '  ]\n'
            '}\n'
            'Include ALL ancestors you can identify from the pedigree tree. '
            'For registration_number, extract codes like KATH..., JKC..., AKC RN..., FIN..., LOE..., KCU..., etc. '
            'OCR Text:\n'
        )
    elif scan_type == 'genetic':
        return (
            'You are a dog genetic test result parser. '
            'Extract information from the following OCR text of a genetic test certificate. '
            'Return ONLY a JSON object:\n'
            '{\n'
            '  "registration_name": "dog name",\n'
            '  "breed": "breed name in Japanese if possible",\n'
            '  "test_date": "YYYY-MM-DD",\n'
            '  "lab_name": "testing laboratory name",\n'
            '  "results": [{"disease_name": "disease name", "result": "clear/carrier/affected"}]\n'
            '}\n'
            'OCR Text:\n'
        )
    elif scan_type == 'hip':
        return (
            'You are a dog hip evaluation result parser. '
            'Extract information from the following OCR text. '
            'Return ONLY a JSON object:\n'
            '{\n'
            '  "registration_name": "dog name",\n'
            '  "breed": "breed name in Japanese if possible",\n'
            '  "evaluation_date": "YYYY-MM-DD",\n'
            '  "evaluator": "evaluation organization name",\n'
            '  "left_score": "left hip score",\n'
            '  "right_score": "right hip score",\n'
            '  "overall_grade": "overall grade (A/B/C/D/E)"\n'
            '}\n'
            'OCR Text:\n'
        )
    else:
        return (
            'You are a dog microchip certificate parser. '
            'Extract information from the following OCR text. '
            'Return ONLY a JSON object:\n'
            '{\n'
            '  "microchip_number": "15-digit microchip number",\n'
            '  "registration_name": "dog name",\n'
            '  "breed": "breed name in Japanese if possible",\n'
            '  "gender": "male or female",\n'
            '  "birth_date": "YYYY-MM-DD"\n'
            '}\n'
            'OCR Text:\n'
        )


def _parse_text_with_openai(raw_text: str, scan_type: str, api_key: str) -> dict:
    """OpenAI GPTでテキストをJSON構造化する"""
    import requests

    prompt = _build_text_parse_prompt(scan_type) + raw_text

    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'gpt-4o-mini',
        'messages': [{
            'role': 'user',
            'content': prompt
        }],
        'max_tokens': 1000,
        'temperature': 0,
    }
    resp = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()['choices'][0]['message']['content']
    _log.info(f'[OCR] OpenAI GPT応答: {content[:200]}')

    # JSONブロックを抽出
    try:
        # ```json ... ``` ブロックを除去
        if '```' in content:
            start = content.find('{')
            end = content.rfind('}') + 1
        else:
            start = content.find('{')
            end = content.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except (json.JSONDecodeError, ValueError) as e:
        _log.error(f'[OCR] JSON解析エラー: {e}, content={content[:200]}')

    return {}


def _build_prompt(scan_type: str) -> str:
    """OpenAI Vision API用プロンプトを返す（画像直接解析用）"""
    if scan_type == 'pedigree':
        return (
            'You are a dog pedigree document parser. '
            'Extract information from this pedigree certificate image. '
            'The document may be in Japanese, English, Thai, or a mix of languages. '
            'Return ONLY a JSON object with these fields (use null for unknown values):\n'
            '{\n'
            '  "pedigree_number": "registration/pedigree number",\n'
            '  "registration_name": "dog\'s registered name",\n'
            '  "breed": "breed name in Japanese if possible",\n'
            '  "gender": "male or female",\n'
            '  "birth_date": "YYYY-MM-DD format",\n'
            '  "father_name": "sire/father dog name",\n'
            '  "mother_name": "dam/mother dog name",\n'
            '  "microchip_number": "15-digit microchip number if present",\n'
            '  "kennel_name": "kennel name if present",\n'
            '  "breeder_name": "breeder name",\n'
            '  "raw_text": "all text visible in the image"\n'
            '}'
        )
    elif scan_type == 'genetic':
        return (
            'You are a dog genetic test result parser. '
            'Extract information from this genetic test certificate image. '
            'Return ONLY a JSON object:\n'
            '{\n'
            '  "registration_name": "dog name",\n'
            '  "breed": "breed name in Japanese if possible",\n'
            '  "test_date": "YYYY-MM-DD",\n'
            '  "lab_name": "testing laboratory name",\n'
            '  "results": [{"disease_name": "disease name", "result": "clear/carrier/affected"}],\n'
            '  "raw_text": "all text visible"\n'
            '}'
        )
    elif scan_type == 'hip':
        return (
            'You are a dog hip evaluation result parser. '
            'Extract information from this evaluation certificate image. '
            'Return ONLY a JSON object:\n'
            '{\n'
            '  "registration_name": "dog name",\n'
            '  "breed": "breed name in Japanese if possible",\n'
            '  "evaluation_date": "YYYY-MM-DD",\n'
            '  "evaluator": "evaluation organization name",\n'
            '  "left_score": "left hip score",\n'
            '  "right_score": "right hip score",\n'
            '  "overall_grade": "overall grade (A/B/C/D/E)",\n'
            '  "raw_text": "all text visible"\n'
            '}'
        )
    else:
        return (
            'You are a dog microchip certificate parser. '
            'Extract information from this certificate image. '
            'Return ONLY a JSON object:\n'
            '{\n'
            '  "microchip_number": "15-digit microchip number",\n'
            '  "registration_name": "dog name",\n'
            '  "breed": "breed name in Japanese if possible",\n'
            '  "gender": "male or female",\n'
            '  "birth_date": "YYYY-MM-DD",\n'
            '  "raw_text": "all text visible"\n'
            '}'
        )


def _extract_with_google_vision(filepath: str, scan_type: str, api_key: str) -> dict:
    """Google Cloud Vision APIでOCRを実行する（正規表現パース）"""
    raw_text = _get_text_with_google_vision(filepath, api_key)
    return _parse_pedigree_text(raw_text, scan_type)


def _extract_with_openai_vision(filepath: str, scan_type: str, api_key: str) -> dict:
    """OpenAI Vision APIで画像を直接解析する"""
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
        'temperature': 0,
    }
    resp = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()['choices'][0]['message']['content']
    _log.info(f'[OCR] OpenAI Vision応答: {content[:200]}')

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
    Google Vision APIのみ使用時のフォールバック。
    英語・日本語・タイ語の血統書フォーマットに対応。
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

    # 血統書番号（KATH/TH形式: 英字2-4文字 + 数字）
    m = re.search(r'\b(KATH|JKC|AKC|FCI|KCU|LOE|AKC\s*RN)\s*[\d/]+', text, re.IGNORECASE)
    if m:
        result['pedigree_number'] = m.group(0).replace(' ', '')
    else:
        # JKC形式: 英字2文字 + 数字6-8桁
        m = re.search(r'\b[A-Z]{2}\s*\d{6,8}\b', text)
        if m:
            result['pedigree_number'] = m.group(0).replace(' ', '')

    # REG. NO. / 登録番号
    m = re.search(r'REG\.?\s*NO\.?\s*[:\s]*([A-Z0-9]+)', text, re.IGNORECASE)
    if m and not result['pedigree_number']:
        result['pedigree_number'] = m.group(1)

    # マイクロチップ番号（15桁数字）
    m = re.search(r'\b\d{15}\b', text)
    if m:
        result['microchip_number'] = m.group(0)

    # MICROCHIP NO. の後の番号
    m = re.search(r'MICROCHIP\s*NO\.?\s*[:\s]*(\d+)', text, re.IGNORECASE)
    if m and not result['microchip_number']:
        result['microchip_number'] = m.group(1)

    # 犬名（NAME の後）
    m = re.search(r'NAME\s+([A-Z][A-Z0-9\.\'\-\s]+?)(?:\n|BREED|SEX|DATE)', text, re.IGNORECASE)
    if m:
        result['registration_name'] = m.group(1).strip()

    # 犬種（BREED の後）
    m = re.search(r'BREED\s+([A-Z][A-Z\s]+?)(?:\n|DATE|SEX|COLOR)', text, re.IGNORECASE)
    if m:
        breed_en = m.group(1).strip()
        # 英語犬種名を日本語に変換
        breed_map = {
            'MINIATURE SCHNAUZER': 'ミニチュアシュナウザー',
            'STANDARD SCHNAUZER': 'スタンダードシュナウザー',
            'GIANT SCHNAUZER': 'ジャイアントシュナウザー',
            'GOLDEN RETRIEVER': 'ゴールデンレトリバー',
            'LABRADOR RETRIEVER': 'ラブラドールレトリバー',
            'GERMAN SHEPHERD': 'ジャーマンシェパード',
            'POODLE': 'プードル',
            'TOY POODLE': 'トイプードル',
            'STANDARD POODLE': 'スタンダードプードル',
            'SHIH TZU': 'シーズー',
            'MALTESE': 'マルチーズ',
            'CHIHUAHUA': 'チワワ',
            'YORKSHIRE TERRIER': 'ヨークシャーテリア',
            'DACHSHUND': 'ダックスフンド',
            'BEAGLE': 'ビーグル',
            'BORDER COLLIE': 'ボーダーコリー',
            'SIBERIAN HUSKY': 'シベリアンハスキー',
            'POMERANIAN': 'ポメラニアン',
            'FRENCH BULLDOG': 'フレンチブルドッグ',
            'ENGLISH BULLDOG': 'イングリッシュブルドッグ',
            'BOXER': 'ボクサー',
            'DOBERMAN': 'ドーベルマン',
            'ROTTWEILER': 'ロットワイラー',
            'GREAT DANE': 'グレートデーン',
            'SAINT BERNARD': 'セントバーナード',
            'SAMOYED': 'サモエド',
            'AKITA': '秋田犬',
            'SHIBA': '柴犬',
        }
        result['breed'] = breed_map.get(breed_en.upper(), breed_en)

    # 生年月日（DATE WHELPED / 生年月日）
    # 英語形式: August 29, 2022 / Aug 29 2022
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }
    m = re.search(
        r'(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})',
        text, re.IGNORECASE
    )
    if m:
        mon = months.get(m.group(1).lower(), 1)
        result['birth_date'] = f'{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}'
    else:
        # 日本語形式
        m = re.search(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})日?', text)
        if m:
            result['birth_date'] = f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'

    # 性別（MALE/FEMALE/雄/雌）
    if re.search(r'\bMALE\b', text, re.IGNORECASE) and not re.search(r'\bFEMALE\b', text, re.IGNORECASE):
        result['gender'] = 'male'
    elif re.search(r'\bFEMALE\b', text, re.IGNORECASE):
        result['gender'] = 'female'
    elif '雄' in text or 'オス' in text or '♂' in text:
        result['gender'] = 'male'
    elif '雌' in text or 'メス' in text or '♀' in text:
        result['gender'] = 'female'

    # SIRE（父犬）
    m = re.search(r'SIRE\s+([A-Z][A-Z0-9\.\'\-\s]+?)(?:\n|DAM|$)', text, re.IGNORECASE)
    if m:
        result['father_name'] = m.group(1).strip()

    # DAM（母犬）
    m = re.search(r'DAM\s+([A-Z][A-Z0-9\.\'\-\s]+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        result['mother_name'] = m.group(1).strip()

    # BREEDER
    m = re.search(r'BREEDER\s+([A-Z][A-Z\s]+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        result['breeder_name'] = m.group(1).strip()

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
        if result.get('breed') and not dog.breed:
            dog.breed = result['breed']
            changed.append('犬種')
        if result.get('gender') and not dog.gender:
            dog.gender = result['gender']
            changed.append('性別')
    elif scan_type == 'chip':
        if result.get('microchip_number') and not dog.microchip_number:
            dog.microchip_number = result['microchip_number']
            changed.append('マイクロチップ番号')
    return changed
