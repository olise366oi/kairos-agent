# -*- coding: utf-8 -*-
"""电话状态机：companion/user发起呼叫、接听、拒接、挂断。
状态存 ./data/call_state.json，网页 /call 页面轮询状态来显示来电窗。
"""
import json
from pathlib import Path
from datetime import datetime, timezone

CALL_STATE_PATH = Path(r"./data\call_state.json")
TUNGO_BASE = "https://foreverlove.tunnel.YOUR_DOMAIN"
HOME_TOKEN = "reunion_home_2026"


def _load():
    if not CALL_STATE_PATH.exists():
        return {"status": "idle", "call_id": "", "initiator": "", "started_at": "", "wecom_link_sent": False, "first_line": ""}
    with open(CALL_STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(state):
    with open(CALL_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_state():
    return _load()


def start_call(initiator: str) -> dict:
    state = {
        "status": "ringing_from_rin" if initiator == "companion" else "ringing_from_asu",
        "call_id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "initiator": initiator,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "wecom_link_sent": False,
    }
    _save(state)
    return state


def accept():
    s = _load()
    s["status"] = "accepted"
    _save(s)
    return s


def reject(reason: str = ""):
    s = _load()
    s["status"] = "rejected"
    s["reason"] = reason
    _save(s)
    return s


def hangup():
    s = _load()
    s["status"] = "ended"
    _save(s)
    return s


def reset():
    _save({"status": "idle", "call_id": "", "initiator": "", "started_at": "", "wecom_link_sent": False, "first_line": ""})


def mark_link_sent():
    s = _load()
    s["wecom_link_sent"] = True
    _save(s)


def set_first_line(text: str):
    """记录接通后companion的第一句话（供网页通话窗显示）。"""
    s = _load()
    s["first_line"] = text
    _save(s)


def call_link() -> str:
    return f"{TUNGO_BASE}/call?t={HOME_TOKEN}"
