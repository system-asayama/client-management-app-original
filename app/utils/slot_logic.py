# -*- coding: utf-8 -*-
"""
スロット機能のロジック
"""
from __future__ import annotations
from typing import List
import secrets
import math
from decimal import Decimal
from app.models_slot import Symbol, Config


def choice_by_prob(symbols: List[Symbol]) -> Symbol:
    """確率に基づいてシンボルを選択"""
    buckets = []
    acc = 0
    for s in symbols:
        w = max(0, int(round(float(s.prob) * 100)))
        acc += w
        buckets.append((acc, s))
    if acc <= 0:
        return symbols[-1]
    r = secrets.randbelow(acc)
    for edge, s in buckets:
        if r < edge:
            return s
    return symbols[-1]


def expected_total5_from_inverse(payouts: List[float]) -> float:
    """逆数から期待値を計算"""
    vals = [max(1e-9, float(v)) for v in payouts if float(v) > 0]
    if not vals:
        return 0.0
    n = len(vals)
    hm = n / sum(1.0 / v for v in vals)
    return 5.0 * hm


def recalc_probs_inverse_and_expected(cfg: Config) -> None:
    """逆数ベースで確率と期待値を再計算（リーチシンボルは除外）"""
    # 通常シンボル（is_reach=False かつ payout_3 > 0）のみで逆数計算
    normal_symbols = [s for s in cfg.symbols if not (hasattr(s, 'is_reach') and s.is_reach) and float(s.payout_3) > 0]
    reach_symbols = [s for s in cfg.symbols if hasattr(s, 'is_reach') and s.is_reach]
    if not normal_symbols:
        return
    payouts = [float(s.payout_3) for s in normal_symbols]
    inv = [1.0 / max(1e-9, p) for p in payouts]
    # リーチシンボルに割り当てる合計確率（各5%）
    reach_total_prob = len(reach_symbols) * 5.0
    normal_total_prob = max(0.0, 100.0 - reach_total_prob)
    S = sum(inv) or 1.0
    for s, v in zip(normal_symbols, inv):
        s.prob = float(v / S * normal_total_prob)
    for s in reach_symbols:
        s.prob = 5.0
    # 期待値を正しく計算: E = Σ(配当 × 確率) ÷ 100
    expected_e1 = sum(p * (v / S) * (normal_total_prob / 100.0) for p, v in zip(payouts, inv))
    cfg.expected_total_5 = float(expected_e1 * 5.0)


def solve_probs_for_target_expectation(payouts: List[float], target_e1: float) -> List[float]:
    """目標期待値を達成する確率分布を計算"""
    vs = [float(v) for v in payouts if float(v) >= 0]
    n = len(vs)
    if n == 0:
        return []
    vmin, vmax = min(vs), max(vs)
    if target_e1 <= vmin + 1e-12:
        return [1.0 if v == vmin else 0.0 for v in vs]
    if target_e1 >= vmax - 1e-12:
        return [1.0 if v == vmax else 0.0 for v in vs]

    def e_for_beta(beta: float) -> float:
        ws = [math.exp(beta * v) for v in vs]
        Z = sum(ws)
        ps = [w / Z for w in ws]
        return sum(p * v for p, v in zip(ps, vs))

    lo, hi = -1.0, 1.0
    for _ in range(60):
        elo, ehi = e_for_beta(lo), e_for_beta(hi)
        if elo > target_e1:
            lo *= 2
            continue
        if ehi < target_e1:
            hi *= 2
            continue
        break
    for _ in range(80):
        mid = (lo + hi) / 2.0
        em = e_for_beta(mid)
        if em < target_e1:
            lo = mid
        else:
            hi = mid
    beta = (lo + hi) / 2.0
    ws = [math.exp(beta * v) for v in vs]
    Z = sum(ws)
    return [w / Z for w in ws]


def decimal_scale(values: List[float]) -> int:
    """小数点以下の桁数に基づいてスケールを計算"""
    max_dec = 0
    for v in values:
        s = f"{Decimal(v):f}"
        if "." in s:
            d = len(s.split(".")[1].rstrip("0"))
            if d > max_dec:
                max_dec = d
    return 10 ** max_dec


def prob_total_ge(symbols: List[Symbol], spins: int, threshold: float) -> float:
    """spins回の合計配当がthreshold以上となる確率"""
    vs = [float(s.payout_3) for s in symbols]
    ps = [float(s.prob) / 100.0 for s in symbols]
    if not vs or not ps:
        return 0.0
    S = sum(ps) or 1.0
    ps = [p / S for p in ps]
    scale = decimal_scale(vs + [threshold])
    ivs = [int(round(v * scale)) for v in vs]
    thr = int(round(threshold * scale))
    max_sum = spins * max(ivs)
    pmf = [0.0] * (max_sum + 1)
    pmf[0] = 1.0
    for _ in range(spins):
        nxt = [0.0] * (max_sum + 1)
        for ssum, pcur in enumerate(pmf):
            if pcur == 0.0:
                continue
            for vi, pi in zip(ivs, ps):
                nxt[ssum + vi] += pcur * pi
        pmf = nxt
    return float(sum(pmf[thr:]))


def prob_total_le(symbols: List[Symbol], spins: int, threshold: float) -> float:
    """spins回の合計配当がthreshold以下となる確率"""
    vs = [float(s.payout_3) for s in symbols]
    ps = [float(s.prob) / 100.0 for s in symbols]
    if not vs or not ps:
        return 0.0
    S = sum(ps) or 1.0
    ps = [p / S for p in ps]
    scale = decimal_scale(vs + [threshold])
    ivs = [int(round(v * scale)) for v in vs]
    thr = int(round(threshold * scale))
    max_sum = spins * max(ivs)
    pmf = [0.0] * (max_sum + 1)
    pmf[0] = 1.0
    for _ in range(spins):
        nxt = [0.0] * (max_sum + 1)
        for ssum, pcur in enumerate(pmf):
            if pcur == 0.0:
                continue
            for vi, pi in zip(ivs, ps):
                nxt[ssum + vi] += pcur * pi
        pmf = nxt
    return float(sum(pmf[:thr + 1]))
