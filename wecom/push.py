# -*- coding: utf-8 -*-
"""电脑端「重逢」回复 → 企业微信主动推送。

当桌面版「重逢」生成新的 assistant 回复时调用本模块，把回复主动推送到用户的企业微信。

设计要点：
- 与企微回调共用同一个 chat_history.db（backend/chat/history.py），两边看到的是同一份记忆；
- 企微回调路径（wecom/server.py）不经过本模块，回复已通过回调 send 回发，天然避免重复推送；
- 未配置企微参数、查不到成员、发送失败时静默跳过/记录日志，不影响桌面版聊天。
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
for _p in (str(_BACKEND), str(_BACKEND / "chat"), str(_BACKEND / "agent"), str(_BACKEND / "persona")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from wecom.config import load_wecom_config, is_configured  # noqa: E402

_token_lock = threading.Lock()
_token_cache: dict = {"token": None, "expire_at": 0}

_LAST_USER_PATH = Path.home() / ".kairos" / "wecom_last_user.txt"


def record_last_user(userid: str) -> None:
    """记录最近一次从企业微信发消息的 userid（供电脑端回复精确推送）。"""
    try:
        _LAST_USER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LAST_USER_PATH.write_text(userid.strip(), encoding="utf-8")
    except Exception as e:
        print(f"[wecom-push] 记录 userid 失败: {e}", flush=True)


def _get_last_user() -> str:
    """读取最近一次从企业微信发消息的 userid；没有记录返回空串。"""
    try:
        if _LAST_USER_PATH.exists():
            return _LAST_USER_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _get_access_token(cfg: dict) -> str:
    """获取企业微信 access_token，带缓存 + 锁，过期自动刷新。"""
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


def _get_member_userids(cfg: dict, token: str) -> list[str]:
    """查询通讯录成员 userid（含子部门），用于确定推送接收人。"""
    url = (
        "https://qyapi.weixin.qq.com/cgi-bin/user/simplelist"
        f"?access_token={urllib.parse.quote(token)}"
        f"&department_id=1&fetch_child=1"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"查询成员失败: {data}")
    return [u.get("userid", "") for u in data.get("userlist", []) if u.get("userid")]


def _send_text(cfg: dict, touser: str, toparty: str, content: str) -> None:
    """通过企业微信 message/send 发送文本消息。

    touser / toparty 至少传一个：
    - touser   成员 userid（可用 | 分隔多个）
    - toparty  部门 ID（传 1 = 根部门，覆盖全部成员，无需通讯录权限）
    """
    token = _get_access_token(cfg)
    body = {
        "msgtype": "text",
        "agentid": int(cfg["agent_id"]),
        "text": {"content": content},
    }
    if touser:
        body["touser"] = touser
    if toparty:
        body["toparty"] = toparty
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


def push_reply_to_wecom(content: str) -> bool:
    """把电脑端产生的 assistant 回复推送到企业微信。返回是否推送成功。

    - 企微未配置 → 跳过（返回 False）
    - 只发给最近一次从企微发消息的用户（精确 userid，不对全员广播）
    - 还没有企微用户记录 → 跳过并提示（先在企微发一条消息即可）
    - 发送失败 → 记录日志，不影响桌面版聊天
    """
    try:
        cfg = load_wecom_config()
        if not is_configured(cfg):
            return False

        user_id = _get_last_user()
        if not user_id:
            print("[wecom-push] 还没有企微用户记录，跳过推送（先在企微发一条消息即可）", flush=True)
            return False

        try:
            _send_text(cfg, touser=user_id, toparty="", content=content)
            return True
        except Exception as e:
            print(f"[wecom-push] 推送失败: {e}", flush=True)
            return False
    except Exception as e:
        print(f"[wecom-push] 推送异常: {e}", flush=True)
        return False


def push_reply_async(content: str) -> None:
    """后台线程推送（不阻塞桌面版聊天）。"""
    threading.Thread(target=push_reply_to_wecom, args=(content,), daemon=True).start()


def push_pair_to_wecom(user_content: str, assistant_content: str) -> bool:
    """把电脑端的一轮对话推送到企业微信：先推「你在电脑端说：xxx」，再推 AI 回复。

    串行发送保证顺序（先用户消息后回复），这样手机企微能看到完整对话，
    而不是只有 AI 单方面的回复。
    """
    try:
        cfg = load_wecom_config()
        if not is_configured(cfg):
            return False

        user_id = _get_last_user()
        if not user_id:
            print("[wecom-push] 还没有企微用户记录，跳过推送（先在企微发一条消息即可）", flush=True)
            return False

        # 1) 用户自己的消息（标注来源，避免误以为 AI 说了一句用户的话）
        user_line = f"你在电脑端说：{user_content}"
        try:
            _send_text(cfg, touser=user_id, toparty="", content=user_line)
        except Exception as e:
            print(f"[wecom-push] 推送用户消息失败: {e}", flush=True)

        # 2) AI 回复
        try:
            _send_text(cfg, touser=user_id, toparty="", content=assistant_content)
        except Exception as e:
            print(f"[wecom-push] 推送回复失败: {e}", flush=True)
            return False
        return True
    except Exception as e:
        print(f"[wecom-push] 推送异常: {e}", flush=True)
        return False


def push_pair_async(user_content: str, assistant_content: str) -> None:
    """后台线程推送一对消息（不阻塞桌面版聊天）。"""
    threading.Thread(
        target=push_pair_to_wecom, args=(user_content, assistant_content), daemon=True
    ).start()
