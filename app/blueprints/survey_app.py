# -*- coding: utf-8 -*-
"""
スロット機能 Blueprint - 元の仕様に準拠
"""
from flask import Blueprint, jsonify, request, render_template, session, redirect, url_for
from dataclasses import asdict
import os
import time
import random
from ..models import Symbol, Config
from ..utils.config import load_config, save_config
from ..utils.slot_logic import (
    choice_by_prob,
    recalc_probs_inverse_and_expected,
    prob_total_ge,
    prob_total_le
)

bp = Blueprint('slot', __name__, url_prefix='')

# パス設定
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data")


@bp.get("/slot")
def slot_page():
    """スロットページ"""
    import store_db
    import sys
    
    # store_slugからstore_idを取得
    store_slug = request.args.get('store_slug')
    sys.stderr.write(f"DEBUG slot_page: store_slug={store_slug}\n")
    sys.stderr.flush()
    store_id = None
    if store_slug:
        try:
            from app.utils.db import _sql
            conn = store_db.get_db_connection()
            cursor = store_db.get_cursor(conn)
            cursor.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE slug = %s'), (store_slug,))
            result = cursor.fetchone()
            if result:
                store_id = result[0]
            conn.close()
        except Exception as e:
            print(f"Error getting store_id: {e}")
    
    # アンケート未回答の場合はアンケートページへリダイレクト
    # セッションキーは survey_completed_{store_id} 形式
    survey_completed = session.get(f'survey_completed_{store_id}') if store_id else session.get('survey_completed')
    if not survey_completed:
        if store_slug:
            return redirect(url_for('survey.survey', store_slug=store_slug))
        return redirect('/')  # store_slugがない場合はトップへ
    
    # 設定ファイルからメッセージと景品データを読み込み
    import json
    settings_path = os.path.join(DATA_DIR, "settings.json")
    survey_complete_message = "アンケートにご協力いただきありがとうございます！スロットをお楽しみください。"
    prizes = []
    slot_spin_count = 1  # デフォルト値
    
    # データベースからslot_spin_countを取得
    if store_id:
        try:
            from app.utils.db import _sql
            conn = store_db.get_db_connection()
            cursor = store_db.get_cursor(conn)
            cursor.execute(_sql(conn, 'SELECT slot_spin_count FROM "T_店舗_Google設定" WHERE store_id = %s'), (store_id,))
            result = cursor.fetchone()
            if result and result[0]:
                slot_spin_count = result[0]
            conn.close()
        except Exception as e:
            print(f"Error getting slot_spin_count: {e}")
    
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
            survey_complete_message = settings.get("survey_complete_message", survey_complete_message)
            prizes = settings.get("prizes", [])
    
    sys.stderr.write(f"DEBUG slot_page: rendering with store_slug={store_slug}, slot_spin_count={slot_spin_count}\n")
    sys.stderr.flush()
    return render_template('slot.html', survey_complete_message=survey_complete_message, prizes=prizes, store_slug=store_slug, slot_spin_count=slot_spin_count)


@bp.get("/store/<slug>/slot/result")
def slot_result_page(slug):
    """スロット結果表示ページ"""
    import store_db
    import sys
    
    # セッションから結果データを取得
    total_score = session.get('slot_total_score', 0)
    prize = session.get('slot_prize')
    history = session.get('slot_history', [])
    set_scores = session.get('slot_set_scores', [])
    
    # store_slugからstore情報を取得（有効フラグをチェックしない）
    from db_config import get_db_connection, get_cursor, execute_query
    conn = get_db_connection()
    cur = get_cursor(conn)
    execute_query(cur, """
        SELECT id, tenant_id, 名称 as name, slug, 有効 as active
        FROM "T_店舗"
        WHERE slug = ?
    """, (slug,))
    row = cur.fetchone()
    conn.close()
    
    store = None
    if row:
        # SQLite Rowオブジェクトを辞書に変換
        if hasattr(row, 'keys'):
            store = {key: row[key] for key in row.keys()}
        else:
            # タプルの場合（フォールバック）
            store = {
                'id': row[0],
                'tenant_id': row[1],
                'name': row[2],
                'slug': row[3],
                'active': row[4]
            }
    
    if store:
        sys.stderr.write(f"DEBUG: Store found - id: {store['id']}, name: {store['name']}, slug: {store['slug']}\n")
        sys.stderr.flush()
    else:
        sys.stderr.write(f"DEBUG: No store found for slug: {slug}\n")
        sys.stderr.flush()
    
    # 結果データをクリア
    session.pop('slot_total_score', None)
    session.pop('slot_prize', None)
    session.pop('slot_history', None)
    session.pop('slot_set_scores', None)
    
    if not store:
        sys.stderr.write(f"ERROR: Store not found for slug '{slug}', redirecting to 404\n")
        sys.stderr.flush()
        return f"店舗が見つかりません (slug: {slug})", 404
    
    # Google口コミURLを取得
    google_review_url = store_db.get_google_review_url(store['id'])
    
    # 口コミ投稿促進設定を取得
    conn = store_db.get_db_connection()
    cur = store_db.get_cursor(conn)
    store_db.execute_query(cur, '''
        SELECT review_prompt_mode
        FROM "T_店舗_口コミ投稿促進設定"
        WHERE store_id = ?
    ''', (store['id'],))
    review_prompt_row = cur.fetchone()
    conn.close()
    review_prompt_mode = review_prompt_row['review_prompt_mode'] if review_prompt_row else 'all'
    
    # アンケートの星評価を取得
    survey_rating = session.get(f'survey_rating_{store["id"]}', 0)
    
    # Google口コミボタンを表示するかどうかを判定
    show_slot_review_button = False
    if google_review_url:
        if review_prompt_mode == 'all':
            show_slot_review_button = True
        elif review_prompt_mode == 'high_rating_only' and survey_rating >= 4:
            show_slot_review_button = True
    
    return render_template('slot_result.html', 
                         total_score=total_score, 
                         prize=prize, 
                         store=store,
                         history=history,
                         set_scores=set_scores,
                         google_review_url=google_review_url,
                         show_slot_review_button=show_slot_review_button)


@bp.get("/store/<slug>/slot")
def slot_page_with_slug(slug):
    """店舗別スロットページ (デモプレイ用)"""
    import store_db
    import sys
    import json
    
    # demoパラメータを確認
    is_demo = request.args.get('demo', '').lower() == 'true'
    
    sys.stderr.write(f"DEBUG slot_page_with_slug: slug={slug}, is_demo={is_demo}\n")
    sys.stderr.flush()
    
    # store_slugからstore_idを取得
    store_id = None
    try:
        conn = store_db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT "id" FROM "T_店舗" WHERE "slug" = %s', (slug,))
        result = cursor.fetchone()
        if result:
            store_id = result[0]
        conn.close()
    except Exception as e:
        sys.stderr.write(f"Error getting store_id: {e}\n")
        sys.stderr.flush()
    
    # デモモードの場合はアンケートチェックをスキップ
    if not is_demo:
        # アンケート未回答の場合はアンケートページへリダイレクト
        survey_completed = session.get(f'survey_completed_{store_id}') if store_id else session.get('survey_completed')
        if not survey_completed:
            return redirect(url_for('survey', store_slug=slug))
    
    # 店舗固有の景品設定をデータベースから読み込み
    survey_complete_message = "ご来店ありがとうございます！アンケートに回答いただいた感謝を込めて、スロットゲームをプレゼント🎁"
    prizes = []
    slot_spin_count = 1  # デフォルト値
    
    # 店舗IDが取得できた場合、データベースから景品設定とslot_spin_countを読み込む
    if store_id:
        try:
            conn = store_db.get_db_connection()
            cursor = conn.cursor()
            
            # slot_spin_countを取得
            cursor.execute('SELECT slot_spin_count FROM "T_店舗_Google設定" WHERE store_id = %s', (store_id,))
            spin_count_row = cursor.fetchone()
            if spin_count_row and spin_count_row[0]:
                slot_spin_count = spin_count_row[0]
            
            # 景品設定を取得
            cursor.execute('SELECT prizes_json FROM "T_店舗_景品設定" WHERE store_id = %s', (store_id,))
            prizes_row = cursor.fetchone()
            
            if prizes_row and prizes_row[0]:
                prizes = json.loads(prizes_row[0])
                sys.stderr.write(f"DEBUG: Loaded prizes from DB: {prizes}\n")
                sys.stderr.flush()
            else:
                # デフォルトの景品設定
                prizes = [
                    {"min_score": 500, "rank": "🏆 特賞", "name": "コース料理・ドリンク飲み放題"},
                    {"min_score": 300, "max_score": 499, "rank": "🏆 1等", "name": "人気メニュー3品セット"},
                    {"min_score": 200, "max_score": 299, "rank": "🏆 2等", "name": "人気メニュー2品セット"},
                    {"min_score": 100, "max_score": 199, "rank": "🏆 3等", "name": "お肉一品・ドリンク1杯"},
                    {"min_score": 50, "max_score": 99, "rank": "🏆 4等", "name": "お肉一品"},
                    {"min_score": 0, "max_score": 49, "rank": "🏆 5等", "name": "ドリンクまたはアイス"}
                ]
            
            conn.close()
        except Exception as e:
            sys.stderr.write(f"Error loading prizes from DB: {e}\n")
            sys.stderr.flush()
            # エラー時はデフォルトの景品設定を使用
            prizes = [
                {"min_score": 500, "rank": "🏆 特賞", "name": "コース料理・ドリンク飲み放題"},
                {"min_score": 300, "max_score": 499, "rank": "🏆 1等", "name": "人気メニュー3品セット"},
                {"min_score": 200, "max_score": 299, "rank": "🏆 2等", "name": "人気メニュー2品セット"},
                {"min_score": 100, "max_score": 199, "rank": "🏆 3等", "name": "お肉一品・ドリンク1杯"},
                {"min_score": 50, "max_score": 99, "rank": "🏆 4等", "name": "お肉一品"},
                {"min_score": 0, "max_score": 49, "rank": "🏆 5等", "name": "ドリンクまたはアイス"}
            ]
    
    sys.stderr.write(f"DEBUG slot_page_with_slug: rendering with slug={slug}, slot_spin_count={slot_spin_count}\n")
    sys.stderr.flush()
    return render_template('slot.html', survey_complete_message=survey_complete_message, prizes=prizes, store_slug=slug, is_demo=is_demo, slot_spin_count=slot_spin_count)

@bp.get("/config")
def get_config():
    """スロット設定を取得"""
    cfg = load_config()
    return jsonify({
        "symbols": [asdict(s) for s in cfg.symbols],
        "reels": cfg.reels,
        "base_bet": cfg.base_bet,
        "expected_total_5": cfg.expected_total_5
    })


@bp.post("/config")
def set_config():
    """スロット設定を更新"""
    body = request.get_json(silent=True) or {}
    reels = int(body.get("reels", 3))
    base_bet = int(body.get("base_bet", 1))
    symbols_in = body.get("symbols", [])
    if not isinstance(symbols_in, list) or len(symbols_in) == 0:
        return jsonify({"ok": False, "error": "symbolsを1件以上送信してください"}), 400
    
    parsed = [Symbol(**s) for s in symbols_in]
    cfg = load_config()
    cfg.symbols = parsed
    cfg.reels = reels
    cfg.base_bet = base_bet
    
    # 確率を逆算して期待値を再計算
    recalc_probs_inverse_and_expected(cfg)
    save_config(cfg)
    
    return jsonify({"ok": True})


@bp.post("/spin")
def spin():
    """スロット実行 - 元の仕様に準拠"""
    from prize_logic import get_prize_for_score
    import copy
    
    cfg = load_config()
    
    # 確率の正規化
    psum = sum(float(s.prob) for s in cfg.symbols) or 100.0
    for s in cfg.symbols:
        s.prob = float(s.prob) / psum * 100.0
    
    spins = []
    total_payout = 0.0
    miss_rate = cfg.miss_probability / 100.0
    
    # 通常シンボルとリーチ専用シンボルを分類
    normal_symbols = [s for s in cfg.symbols if not (hasattr(s, 'is_reach') and s.is_reach)]
    reach_symbols = [s for s in cfg.symbols if hasattr(s, 'is_reach') and s.is_reach]
    
    # 5回スピン
    for _ in range(5):
        # まずハズレかどうかを判定
        if random.random() < miss_rate:
            # ハズレ：1コマ目と2コマ目は必ず異なるシンボル
            reel1 = random.choice(normal_symbols)
            # reel2はreel1と異なるものを選ぶ
            other_symbols = [s for s in normal_symbols if s.id != reel1.id]
            if other_symbols:
                reel2 = random.choice(other_symbols)
            else:
                reel2 = reel1  # シンボルが1つしかない場合
            reel3 = random.choice(normal_symbols)
            
            spins.append({
                "reels": [
                    {"id": reel1.id, "label": reel1.label, "color": reel1.color},
                    {"id": reel2.id, "label": reel2.label, "color": reel2.color},
                    {"id": reel3.id, "label": reel3.label, "color": reel3.color}
                ],
                "matched": False,
                "is_reach": False,
                "payout": 0
            })
        else:
            # 当たりまたはリーチハズレ：シンボルを確率で抽選
            symbol = choice_by_prob(cfg.symbols)
            
            # リーチ専用シンボルの場合
            is_reach_symbol = hasattr(symbol, 'is_reach') and symbol.is_reach
            
            if is_reach_symbol:
                # リーチハズレ：1,2コマ目は同じ、3コマ目は必ず異なる
                reach_symbol_id = symbol.reach_symbol if hasattr(symbol, 'reach_symbol') else symbol.id
                # 元のシンボルを探す
                original_symbol = next((s for s in normal_symbols if s.id == reach_symbol_id), symbol)
                
                # リール3用に異なるシンボルを選ぶ（リーチ専用シンボルも除外）
                other_symbols = [s for s in normal_symbols if s.id != reach_symbol_id]
                if other_symbols:
                    reel3_symbol = random.choice(other_symbols)
                else:
                    reel3_symbol = original_symbol
                
                spins.append({
                    "reels": [
                        {"id": original_symbol.id, "label": original_symbol.label, "color": original_symbol.color},
                        {"id": original_symbol.id, "label": original_symbol.label, "color": original_symbol.color},
                        {"id": reel3_symbol.id, "label": reel3_symbol.label, "color": reel3_symbol.color}
                    ],
                    "matched": False,
                    "is_reach": True,
                    "reach_symbol": {"id": original_symbol.id, "label": original_symbol.label, "color": original_symbol.color},
                    "payout": 0
                })
            else:
                # 通常の当たり：3つ揃い
                payout = symbol.payout_3
                total_payout += payout
                
                spins.append({
                    "reels": [
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color}
                    ],
                    "matched": True,
                    "is_reach": False,
                    "symbol": {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                    "payout": payout
                })
    
    # 景品判定
    settings_path = os.path.join(DATA_DIR, "settings.json")
    prize = get_prize_for_score(int(total_payout), settings_path)
    
    result = {
        "ok": True, 
        "spins": spins, 
        "total_payout": total_payout,
        "expected_total_5": cfg.expected_total_5, 
        "ts": int(time.time())
    }
    
    if prize:
        result["prize"] = prize
    
    return jsonify(result)


@bp.post("/calc_prob")
def calc_prob():
    """
    確率計算
    body: {"threshold_min":200, "threshold_max":500, "spins":5}
    - threshold_maxがNoneまたは未指定なら上限なし（∞）
    """
    body = request.get_json(silent=True) or {}
    tmin = float(body.get("threshold_min", 0))
    tmax = body.get("threshold_max")
    tmax = None if tmax in (None, "", "null") else float(tmax)
    spins = int(body.get("spins", 5))
    spins = max(1, spins)

    # リクエストボディにsymbolsが含まれている場合はそれを使用
    if "symbols" in body and body["symbols"]:
        symbols_data = body["symbols"]
        symbols = [Symbol(
            id=s.get("id", ""),
            label=s.get("label", ""),
            payout_3=float(s.get("payout_3", 0)),
            prob=float(s.get("prob", 0)),
            color=s.get("color", "#000000")
        ) for s in symbols_data]
        miss_rate = float(body.get("miss_probability", 0.0))
    else:
        # ファイルから設定を読み込む
        cfg = load_config()
        symbols = list(cfg.symbols)
        miss_rate = cfg.miss_probability
    
    # ハズレ確率を考慮するため、ハズレ（0点）をシンボルリストに追加
    symbols_with_miss = list(symbols)
    
    # ハズレシンボルを追加
    miss_symbol = Symbol(
        id="miss",
        label="ハズレ",
        payout_3=0.0,
        prob=miss_rate,
        color="#000000"
    )
    symbols_with_miss.append(miss_symbol)
    
    # 確率を正規化（ハズレ確率 + シンボル確率の合計 = 100%）
    psum = sum(float(s.prob) for s in symbols_with_miss)
    for s in symbols_with_miss:
        s.prob = float(s.prob) * 100.0 / psum

    prob_ge = prob_total_ge(symbols_with_miss, spins, tmin)
    prob_le = 1.0 if tmax is None else prob_total_le(symbols_with_miss, spins, tmax)
    prob_range = max(0.0, prob_le - (1.0 - prob_ge))

    return jsonify({
        "ok": True,
        "prob_ge": prob_ge,
        "prob_le": prob_le,
        "prob_range": prob_range,
        "tmin": tmin,
        "tmax": tmax,
        "spins": spins
    })


# 店舗別ルート（デモプレイ用）
@bp.get("/store/<slug>/config")
def get_config_with_slug(slug):
    """店舗別スロット設定を取得"""
    import store_db
    import sys
    
    # store_slugからstore_idを取得
    store_id = None
    try:
        conn = store_db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT "id" FROM "T_店舗" WHERE "slug" = %s', (slug,))
        result = cursor.fetchone()
        if result:
            store_id = result[0]
        conn.close()
    except Exception as e:
        sys.stderr.write(f"Error getting store_id: {e}\n")
        sys.stderr.flush()
    
    # 店舗固有のスロット設定をデータベースから読み込む
    if store_id:
        config_dict = store_db.get_slot_config(store_id)
        sys.stderr.write(f"DEBUG: Loaded slot config from DB for store_id={store_id}\n")
        sys.stderr.flush()
        
        # Configオブジェクトに変換
        from ..models import Config, Symbol
        # Symbolクラスに定義されているフィールドのみを抽出
        symbol_fields = {'id', 'label', 'payout_3', 'color', 'prob', 'is_reach', 'reach_symbol'}
        symbols = [Symbol(**{k: v for k, v in s.items() if k in symbol_fields}) for s in config_dict.get('symbols', [])]
        cfg = Config(
            symbols=symbols,
            reels=config_dict.get('reels', 3),
            base_bet=config_dict.get('base_bet', 1),
            expected_total_5=config_dict.get('expected_total_5', 100.0),
            miss_probability=config_dict.get('miss_probability', 0.0)
        )
    else:
        # 店舗IDが取得できない場合はデフォルト設定を使用
        cfg = load_config()
    
    return jsonify({
        "symbols": [asdict(s) for s in cfg.symbols],
        "reels": cfg.reels,
        "base_bet": cfg.base_bet,
        "expected_total_5": cfg.expected_total_5
    })


@bp.post("/store/<slug>/spin")
def spin_with_slug(slug):
    """店舗別スロット実行"""
    import store_db
    import sys
    import json
    import copy
    
    # store_slugからstore_idを取得
    store_id = None
    try:
        conn = store_db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT "id" FROM "T_店舗" WHERE "slug" = %s', (slug,))
        result = cursor.fetchone()
        if result:
            store_id = result[0]
        conn.close()
    except Exception as e:
        sys.stderr.write(f"Error getting store_id: {e}\n")
        sys.stderr.flush()
    
    # 店舗固有のスロット設定をデータベースから読み込む
    if store_id:
        config_dict = store_db.get_slot_config(store_id)
        sys.stderr.write(f"DEBUG: Loaded slot config from DB for store_id={store_id}: {config_dict}\n")
        sys.stderr.flush()
        
        # Configオブジェクトに変換
        from ..models import Config, Symbol
        # Symbolクラスに定義されているフィールドのみを抽出
        symbol_fields = {'id', 'label', 'payout_3', 'color', 'prob', 'is_reach', 'reach_symbol'}
        symbols = [Symbol(**{k: v for k, v in s.items() if k in symbol_fields}) for s in config_dict.get('symbols', [])]
        cfg = Config(
            symbols=symbols,
            reels=config_dict.get('reels', 3),
            base_bet=config_dict.get('base_bet', 1),
            expected_total_5=config_dict.get('expected_total_5', 100.0),
            miss_probability=config_dict.get('miss_probability', 0.0)
        )
    else:
        # 店舗IDが取得できない場合はデフォルト設定を使用
        cfg = load_config()
    
    # 確率の正規化
    psum = sum(float(s.prob) for s in cfg.symbols) or 100.0
    for s in cfg.symbols:
        s.prob = float(s.prob) / psum * 100.0
    
    spins = []
    total_payout = 0.0
    miss_rate = cfg.miss_probability / 100.0
    
    # 通常シンボルとリーチ専用シンボルを分類
    normal_symbols = [s for s in cfg.symbols if not (hasattr(s, 'is_reach') and s.is_reach)]
    reach_symbols = [s for s in cfg.symbols if hasattr(s, 'is_reach') and s.is_reach]
    
    # 5回スピン
    for _ in range(5):
        # まずハズレかどうかを判定
        if random.random() < miss_rate:
            # ハズレ：1コマ目と2コマ目は必ず異なるシンボル
            reel1 = random.choice(normal_symbols)
            # reel2はreel1と異なるものを選ぶ
            other_symbols = [s for s in normal_symbols if s.id != reel1.id]
            if other_symbols:
                reel2 = random.choice(other_symbols)
            else:
                reel2 = reel1  # シンボルが1つしかない場合
            reel3 = random.choice(normal_symbols)
            
            spins.append({
                "reels": [
                    {"id": reel1.id, "label": reel1.label, "color": reel1.color},
                    {"id": reel2.id, "label": reel2.label, "color": reel2.color},
                    {"id": reel3.id, "label": reel3.label, "color": reel3.color}
                ],
                "matched": False,
                "is_reach": False,
                "payout": 0
            })
        else:
            # 当たりまたはリーチハズレ：シンボルを確率で抽選
            symbol = choice_by_prob(cfg.symbols)
            
            # リーチ専用シンボルの場合
            is_reach_symbol = hasattr(symbol, 'is_reach') and symbol.is_reach
            
            if is_reach_symbol:
                # リーチハズレ：1,2コマ目は同じ、3コマ目は必ず異なる
                reach_symbol_id = symbol.reach_symbol if hasattr(symbol, 'reach_symbol') else symbol.id
                # 元のシンボルを探す
                original_symbol = next((s for s in normal_symbols if s.id == reach_symbol_id), symbol)
                
                # リール3用に異なるシンボルを選ぶ（リーチ専用シンボルも除外）
                other_symbols = [s for s in normal_symbols if s.id != reach_symbol_id]
                if other_symbols:
                    reel3_symbol = random.choice(other_symbols)
                else:
                    reel3_symbol = original_symbol
                
                spins.append({
                    "reels": [
                        {"id": original_symbol.id, "label": original_symbol.label, "color": original_symbol.color},
                        {"id": original_symbol.id, "label": original_symbol.label, "color": original_symbol.color},
                        {"id": reel3_symbol.id, "label": reel3_symbol.label, "color": reel3_symbol.color}
                    ],
                    "matched": False,
                    "is_reach": True,
                    "reach_symbol": {"id": original_symbol.id, "label": original_symbol.label, "color": original_symbol.color},
                    "payout": 0
                })
            else:
                # 通常の当たり：3つ揃い
                payout = symbol.payout_3
                total_payout += payout
                
                spins.append({
                    "reels": [
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color}
                    ],
                    "matched": True,
                    "is_reach": False,
                    "symbol": {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                    "payout": payout
                })
    
    # 店舗固有の景品設定をデータベースから読み込んで景品判定
    prize = None
    try:
        # store_slugからstore_idを取得
        conn = store_db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT "id" FROM "T_店舗" WHERE "slug" = %s', (slug,))
        result = cursor.fetchone()
        
        if result:
            store_id = result[0]
            
            # 景品設定を取得
            cursor.execute('SELECT prizes_json FROM "T_店舗_景品設定" WHERE store_id = %s', (store_id,))
            prizes_row = cursor.fetchone()
            
            if prizes_row and prizes_row[0]:
                prizes = json.loads(prizes_row[0])
                
                # 点数範囲に該当する景品を探す
                for p in prizes:
                    min_score = p["min_score"]
                    max_score = p.get("max_score")
                    
                    # max_scoreがNoneの場合は上限なし
                    if max_score is None:
                        if total_payout >= min_score:
                            prize = {
                                "rank": p["rank"],
                                "name": p["name"]
                            }
                            break
                    else:
                        # min_score <= total_payout <= max_scoreの範囲内か確認
                        if min_score <= total_payout <= max_score:
                            prize = {
                                "rank": p["rank"],
                                "name": p["name"]
                            }
                            break
        
        conn.close()
    except Exception as e:
        sys.stderr.write(f"Error loading prizes for spin: {e}\n")
        sys.stderr.flush()
    
    result = {
        "ok": True, 
        "spins": spins, 
        "total_payout": total_payout,
        "expected_total_5": cfg.expected_total_5, 
        "ts": int(time.time())
    }
    
    if prize:
        result["prize"] = prize
    
    return jsonify(result)


@bp.post("/store/<slug>/calc_prob")
def calc_prob_with_slug(slug):
    """店舗別確率計算"""
    # 既存の calc_prob() 関数と同じロジックを使用
    return calc_prob()


@bp.post("/store/<slug>/slot/save_result")
def save_slot_result(slug):
    """スロット結果をセッションに保存"""
    import sys
    
    try:
        data = request.get_json()
        total_score = data.get('total_score', 0)
        prize = data.get('prize')
        history = data.get('history', [])
        set_scores = data.get('set_scores', [])
        
        # セッションに保存
        session['slot_total_score'] = total_score
        session['slot_prize'] = prize
        session['slot_history'] = history
        session['slot_set_scores'] = set_scores
        
        sys.stderr.write(f"DEBUG: Saved slot result - score: {total_score}, prize: {prize}\n")
        sys.stderr.flush()
        
        return jsonify({"ok": True})
    except Exception as e:
        sys.stderr.write(f"Error saving slot result: {e}\n")
        sys.stderr.flush()
        return jsonify({"ok": False, "error": str(e)}), 500
