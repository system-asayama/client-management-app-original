# -*- coding: utf-8 -*-
"""ログイン試行のレート制限（ブルートフォース対策）。インメモリ実装。"""
import time
import threading

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60

_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def _recent(key: str, now: float) -> list[float]:
    return [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]


def lockout_remaining(key: str) -> int:
    now = time.time()
    with _lock:
        recent = _recent(key, now)
        if recent:
            _failures[key] = recent
        else:
            _failures.pop(key, None)
        if len(recent) >= MAX_ATTEMPTS:
            return max(int(WINDOW_SECONDS - (now - min(recent))), 1)
        return 0


def record_failure(key: str) -> None:
    now = time.time()
    with _lock:
        recent = _recent(key, now)
        recent.append(now)
        _failures[key] = recent


def clear(key: str) -> None:
    with _lock:
        _failures.pop(key, None)
