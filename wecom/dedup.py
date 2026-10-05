# -*- coding: utf-8 -*-
"""企业微信消息 MsgId 去重。

企业微信推送回调可能因网络抖动/超时对同一条消息重复 POST（同一条 MsgId）。
这里用本地文件记录已处理过的 MsgId：重复推送直接跳过，避免同一条消息
被重复写入对话历史、重复调用 agent、重复回发。

去重记录持久化在 ~/.reunion/wecom_processed_msgids.json，重启后依然生效。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

_PROCESSED_PATH = Path.home() / ".reunion" / "wecom_processed_msgids.json"
_lock = threading.Lock()
_MAX = 2000


def _load() -> list:
    try:
        if _PROCESSED_PATH.exists():
            data = json.loads(_PROCESSED_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save(data: list) -> None:
    try:
        _PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PROCESSED_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def is_processed(msg_id: str) -> bool:
    """MsgId 已处理过返回 True；未处理则记录并返回 False（调用方继续处理）。"""
    if not msg_id:
        return False
    with _lock:
        data = _load()
        if msg_id in data:
            return True
        data.append(msg_id)
        if len(data) > _MAX:
            data = data[-_MAX:]
        _save(data)
        return False
