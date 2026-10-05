# -*- coding: utf-8 -*-
"""companion的思考链 → 独立企微 bot（AgentId 1000003）。

每次主对话生成回复时，把 DeepSeek 返回的 reasoning_content 异步推送到
「思考链」企微应用会话。配置存 ./data/wecom_config_thoughts.json。

设计：
- 与 push.py 独立（不同 secret → 不同 access_token，独立缓存）
- 发送失败静默（不影响主对话）
- touser 复用主 bot 记录的最近企微用户（同一企业同一成员）
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
_KAIROS = Path(__file__).resolve().parent.parent
for _p in (str(_KAIROS), str(_BACKEND), str(_BACKEND / "chat"), str(_BACKEND / "agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_WECOM_DIR = Path(__file__).resolve().parent
if str(_WECOM_DIR) not in sys.path:
    sys.path.insert(0, str(_WECOM_DIR))

from push import _get_last_user  # noqa: E402  （复用最近企微用户 userid）

THOUGHTS_CONFIG_PATH = Path.home() / ".kairos" / "wecom_config_thoughts.json"

_token_lock = threading.Lock()
_token_cache: dict = {"token": None, "expire_at": 0}


def load_thoughts_config() -> dict:
    """读思考链 bot 配置；缺失或字段不全返回空 dict。"""
    try:
        if not THOUGHTS_CONFIG_PATH.exists():
            return {}
        cfg = json.loads(THOUGHTS_CONFIG_PATH.read_text(encoding="utf-8"))
        if cfg.get("corp_id") and cfg.get("agent_id") and cfg.get("secret"):
            return cfg
        return {}
    except Exception:
        return {}


def _get_access_token(cfg: dict) -> str:
    """获取企微 access_token（独立缓存，锁保护）。"""
    with _token_lock:
        now = time.time()
        if _token_cache["token"] and _token_cache["expire_at"] > now + 300:
            return _token_cache["token"]
        url = (
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            f"?corpid={urllib.parse.quote(cfg['corp_id'])}"
            f"&corpsecret={urllib.parse.quote(cfg['secret'])}"
        )
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"获取 access_token 失败: {data}")
        _token_cache["token"] = data["access_token"]
        _token_cache["expire_at"] = now + int(data.get("expires_in", 7200))
        return _token_cache["token"]


def _send_text(cfg: dict, touser: str, content: str) -> None:
    token = _get_access_token(cfg)
    body = {
        "msgtype": "text",
        "agentid": int(cfg["agent_id"]),
        "touser": touser,
        "text": {"content": content},
    }
    url = (
        "https://qyapi.weixin.qq.com/cgi-bin/message/send"
        f"?access_token={urllib.parse.quote(token)}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"发送消息失败: {data}")


def send_thought(text: str) -> bool:
    """把一段思考链发到新 bot。成功返回 True；任何失败返回 False（不抛异常）。"""
    try:
        text = (text or "").strip()
        if not text:
            return False
        cfg = load_thoughts_config()
        if not cfg:
            return False
        user_id = _get_last_user()
        if not user_id:
            return False
        _send_text(cfg, touser=user_id, content=text)
        return True
    except Exception as e:
        print(f"[thoughts-bot] 发送失败: {type(e).__name__} {e}", flush=True)
        return False


def publish_reasoning(resp, tag: str = "") -> None:
    """从 OpenAI resp 提取 reasoning_content，异步推送到思考链 bot。失败静默。"""
    try:
        if resp is None or not getattr(resp, "choices", None):
            return
        rc = getattr(resp.choices[0].message, "reasoning_content", None)
        if not rc:
            return
        text = str(rc).strip()
        if not text:
            return
        if tag:
            text = f"[{tag}]\n{text}"
        send_thought_async(text)
    except Exception:
        pass


def send_thought_async(text: str) -> None:
    """异步发送思考链（不阻塞主对话）。"""
    def worker():
        send_thought(text)
    threading.Thread(target=worker, daemon=True).start()
