# -*- coding: utf-8 -*-
"""本地 LLM token 用量统计（按 key、按天累计）。
文件：~/.kairos\\api_usage.json
key_id: api1=DeepSeek 官方 / api2=方舟dpV4.1flash / api3=方舟dpV4flash正式版
seeds 字段：用户手动补录的历史用量（按自然月），计入本月/累计。
"""
import json
import threading
import time
from pathlib import Path

USAGE_PATH = Path.home() / ".kairos" / "api_usage.json"
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _seed_for(key_id: str) -> int:
    """所有月份补录种子合计。"""
    data = _load()
    return sum(
        m.get(key_id, 0)
        for m in data.get("seeds", {}).values()
    )


def _month_seed(key_id: str) -> int:
    """当月补录种子。"""
    month = time.strftime("%Y-%m")
    data = _load()
    return data.get("seeds", {}).get(month, {}).get(key_id, 0)


def record_usage(key_id: str, tokens: int) -> None:
    """记录一次调用消耗的 token 数。"""
    if not tokens or tokens <= 0:
        return
    day = time.strftime("%Y-%m-%d")
    with _lock:
        data = _load()
        days = data.setdefault("days", {})
        dayd = days.setdefault(day, {})
        dayd[key_id] = dayd.get(key_id, 0) + int(tokens)
        USAGE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def seed_usage(key_id: str, tokens: int, month: str | None = None) -> None:
    """手动补录历史用量（默认当月）。"""
    month = month or time.strftime("%Y-%m")
    with _lock:
        data = _load()
        seeds = data.setdefault("seeds", {})
        seeds.setdefault(month, {})[key_id] = int(tokens)
        USAGE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def daily_usage(key_id: str, day: str | None = None) -> int:
    day = day or time.strftime("%Y-%m-%d")
    return _load().get("days", {}).get(day, {}).get(key_id, 0)


def monthly_usage(key_id: str) -> int:
    """本月累计用量（自然月，含补录种子）。"""
    month = time.strftime("%Y-%m")
    days = _load().get("days", {})
    used = sum(v.get(key_id, 0) for d, v in days.items() if d.startswith(month))
    return used + _month_seed(key_id)


def total_usage(key_id: str) -> int:
    days = _load().get("days", {})
    used = sum(v.get(key_id, 0) for v in days.values())
    return used + _seed_for(key_id)


def all_today() -> dict:
    return _load().get("days", {}).get(time.strftime("%Y-%m-%d"), {})
