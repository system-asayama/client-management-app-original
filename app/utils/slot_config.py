# -*- coding: utf-8 -*-
"""
スロット設定ファイル管理（store_idごとに管理）
"""
import os
import json
from dataclasses import asdict
from app.models_slot import Symbol, Config
from app.utils.slot_logic import recalc_probs_inverse_and_expected

# パス設定
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data", "slot")


def _config_path(store_id: int) -> str:
    d = os.path.join(DATA_DIR, str(store_id))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "config.json")


def default_config() -> Config:
    """デフォルト設定を生成"""
    defaults = [
        {"id": "seven", "label": "7", "payout_3": 100, "color": "#ff0000"},
        {"id": "bell", "label": "🔔", "payout_3": 50, "color": "#fbbf24"},
        {"id": "bar", "label": "BAR", "payout_3": 25, "color": "#ffffff"},
        {"id": "grape", "label": "🍇", "payout_3": 20, "color": "#7c3aed"},
        {"id": "cherry", "label": "🍒", "payout_3": 12.5, "color": "#ef4444"},
        {"id": "lemon", "label": "🍋", "payout_3": 12.5, "color": "#fde047"},
    ]
    cfg = Config(symbols=[Symbol(**d) for d in defaults])
    recalc_probs_inverse_and_expected(cfg)
    return cfg


def load_config(store_id: int) -> Config:
    """店舗のスロット設定を読み込み"""
    path = _config_path(store_id)
    if not os.path.exists(path):
        return default_config()
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    syms = [Symbol(**s) for s in raw["symbols"]]
    return Config(
        symbols=syms,
        reels=raw.get("reels", 3),
        base_bet=raw.get("base_bet", 1),
        expected_total_5=raw.get("expected_total_5", 2500.0),
        miss_probability=raw.get("miss_probability", 0.0)
    )


def save_config(store_id: int, cfg: Config) -> None:
    """店舗のスロット設定を保存"""
    path = _config_path(store_id)
    payload = asdict(cfg)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
