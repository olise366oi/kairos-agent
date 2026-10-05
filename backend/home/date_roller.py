import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from config import TIMEZONE

STATE_PATH = Path(r"./data\home_state.json")
APP_TZ = ZoneInfo(TIMEZONE)


def home_today() -> str:
    return datetime.now(PARIS_TZ).strftime("%Y-%m-%d")


def roll_if_needed():
    """如果 today.date 不是city今天，滚动：today→yesterday→day_before，旧的删。"""
    if not STATE_PATH.exists():
        return False
    with open(STATE_PATH, encoding="utf-8") as f:
        state = json.load(f)
    today = state.get("today") or {}
    current_date = today.get("date", "")
    real_today = home_today()
    if current_date == real_today:
        return False
    # 滚动
    _old_today = state.get("today") or {}
    _old_fridge = _old_today.get("fridge") or []
    state["day_before"] = state.get("yesterday")
    state["yesterday"] = _old_today
    state["today"] = {
        "date": real_today,
        "updated_at": "",
        "companion": {"status": "在家"},
        "next_match": {"date": "", "opponent": "", "venue": ""},
        "breakfast": {"main": "", "fruit": "", "drink": "", "placed": "", "eaten": False},
        "fridge": _old_fridge,  # 保留旧冰箱（跨天不清空）
        "brought_back": [],
        "next_date": {"date": "", "text": ""},
        "today_events": [],
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return True


if __name__ == "__main__":
    print("city今天:", home_today())
    print("滚动了吗:", roll_if_needed())
