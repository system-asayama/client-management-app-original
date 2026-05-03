# -*- coding: utf-8 -*-
"""
設定ファイル管理
"""
import os
import json
from dataclasses import asdict
from ..models import Symbol, Config
from .slot_logic import recalc_probs_inverse_and_expected

# パス設定
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")


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
    save_config(cfg)
    return cfg


def load_config() -> Config:
    """設定ファイルを読み込み"""
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(DATA_DIR, exist_ok=True)
        return default_config()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    syms = [Symbol(**s) for s in raw["symbols"]]
    return Config(
        symbols=syms,
        reels=raw.get("reels", 3),
        base_bet=raw.get("base_bet", 1),
        expected_total_5=raw.get("expected_total_5", 2500.0),
        miss_probability=raw.get("miss_probability", 0.0)
    )


def save_config(cfg: Config) -> None:
    """設定ファイルを保存"""
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = asdict(cfg)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
