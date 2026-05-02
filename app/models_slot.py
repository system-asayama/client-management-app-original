# -*- coding: utf-8 -*-
"""
データモデル定義
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class Symbol:
    id: str
    label: str
    payout_3: float
    color: str | None = None
    prob: float = 0.0  # 保存時は [%]
    is_disabled: bool = False  # 無効化フラグ
    is_default: bool = False  # デフォルトシンボルフラグ
    is_reach: bool = False  # リーチ専用シンボルかどうか
    reach_symbol: str | None = None  # リーチ時に表示する元のシンボルID

@dataclass
class Config:
    symbols: List[Symbol]
    reels: int = 3
    base_bet: int = 1
    expected_total_5: float = 2500.0
    miss_probability: float = 0.0  # ハズレ確率 [%]
    target_probabilities: Dict[str, float] | None = None  # 目標確率設定 {"500-2500": 1.0, ...}

# ===== ユーザー関連モデル =====
@dataclass
class Admin:
    """管理者モデル"""
    id: int
    login_id: str
    name: str
    role: str  # 'system_admin', 'tenant_admin', 'admin'
    tenant_id: int | None = None
    active: int = 1
    is_owner: int = 0
    can_manage_admins: int = 0


@dataclass
class Employee:
    """従業員モデル"""
    id: int
    login_id: str
    email: str
    name: str
    tenant_id: int | None = None
    role: str = 'employee'


@dataclass
class Tenant:
    """テナントモデル"""
    id: int
    名称: str
    slug: str
    有効: int = 1
