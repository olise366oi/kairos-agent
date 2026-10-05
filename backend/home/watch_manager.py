"""看球（一起复盘比赛）状态管理器。
状态存 ./data/watch_state.json。
事件流从 football-api-mcp（5DollarFootballAPI）拉取；companion解说调 loop.chat()。
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(r"./data\watch_state.json")
LEAGUE_ID = 3614399544      # France Ligue 1
PSG_TEAM_ID = 3976425434    # PSG
HOME_TOKEN = os.environ.get("HOME_TOKEN")
if not HOME_TOKEN:
    raise RuntimeError("HOME_TOKEN 环境变量必须设置，不能为空")
LINK = f"https://foreverlove.tunnel.YOUR_DOMAIN/watch?t={HOME_TOKEN}"


def _load_api_key() -> str:
    """读 5DollarFootballAPI Key：优先环境变量 FIVEDOLLARFOOTBALL_API_KEY，
    未设则读同目录 .env（KEY=VALUE 行）。都没有返回空串。"""
    key = os.environ.get("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if key:
        return key
    try:
        env_path = Path(__file__).resolve().parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("FIVEDOLLARFOOTBALL_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


FIVEDOLLAR_API_KEY = _load_api_key()

_LOCK = threading.RLock()


def _empty():
    return {
        "active": False,
        "fixture_id": None,
        "home_team": "",
        "away_team": "",
        "started_at": "",
        "paused": False,
        "paused_at": "",
        "typing": False,
        "events": [],
        "last_event_index": 0,
        "messages": [],
        "ended": False,
    }


def get_state():
    if not STATE_PATH.exists():
        return _empty()
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _empty()


def save_state(s):
    with _LOCK:
        STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def start_watch(fixture_id, home_team, away_team, events):
    """companion发起新一场看球：清掉上一场全部状态，从头计时。"""
    s = _empty()
    s["fixture_id"] = fixture_id
    s["home_team"] = home_team
    s["away_team"] = away_team
    s["events"] = events or []
    s["started_at"] = datetime.now(timezone.utc).isoformat()
    s["messages"] = [{"role": "companion", "content": f"我把比赛录像倒好了：{home_team} vs {away_team}。边看边跟你讲，你在就一起。"}]
    save_state(s)
    return s


def end_watch():
    s = get_state()
    s["ended"] = True
    s["active"] = False
    save_state(s)
    return s


def pause_watch():
    s = get_state()
    if not s.get("paused"):
        s["paused"] = True
        s["paused_at"] = datetime.now(timezone.utc).isoformat()
        save_state(s)
    return s


def resume_watch():
    s = get_state()
    if s.get("paused") and s.get("paused_at"):
        start = datetime.fromisoformat(s["started_at"])
        pause = datetime.fromisoformat(s["paused_at"])
        s["started_at"] = (start + (datetime.now(timezone.utc) - pause)).isoformat()
        s["paused"] = False
        s["paused_at"] = ""
        save_state(s)
    return s


def set_typing(typing: bool):
    s = get_state()
    s["typing"] = bool(typing)
    save_state(s)
    return s


def set_active(active: bool):
    s = get_state()
    s["active"] = bool(active)
    save_state(s)
    return s


def current_minute():
    s = get_state()
    if not s.get("started_at"):
        return 0
    try:
        start = datetime.fromisoformat(s["started_at"])
    except Exception:
        return 0
    if s.get("paused") and s.get("paused_at"):
        try:
            pause = datetime.fromisoformat(s["paused_at"])
            return min(90, max(0, int((pause - start).total_seconds() // 60)))
        except Exception:
            return 0
    now = datetime.now(timezone.utc)
    return min(90, max(0, int((now - start).total_seconds() // 60)))


def _event_minute(ev):
    m = ev.get("minute")
    if m is not None:
        return m
    if ev.get("period") == "first_half":
        return 45
    if ev.get("period") == "second_half":
        return 90
    return None


def _fmt_event(ev, s):
    t = ev.get("type", "")
    team = ev.get("team", "")
    label = ""
    if team == "away":
        label = s.get("away_team", "客队")
    elif team == "home":
        label = s.get("home_team", "主队")
    m = _event_minute(ev)
    mm = f"第{m}分钟" if m else ""
    if t == "goal":
        sc = ev.get("score")
        sstr = f"，比分 {sc['home']}:{sc['away']}" if sc else ""
        return f"{mm}{label}进球{sstr}"
    if t == "corner":
        return f"{mm}{label}角球（本场第{ev.get('count', 1)}个）"
    if t == "yellow_card":
        return f"{mm}{label}吃黄牌"
    if t == "red_card":
        return f"{mm}{label}被红牌罚下"
    if t == "substitution":
        return f"{mm}{label}换人：{ev.get('player_in', '')} 替下 {ev.get('player_out', '')}"
    if t == "period_score":
        p = "上半场" if ev.get("period") == "first_half" else "下半场"
        sc = ev.get("score") or {}
        return f"{p}结束，比分 {sc.get('home', 0)}:{sc.get('away', 0)}"
    return f"{mm}{label} {t}"


def append_message(role, content):
    s = get_state()
    s["messages"].append({"role": role, "content": content})
    save_state(s)
    return s


def release_events():
    """把当前分钟之前、还没释放的事件释放；有新事件且 active 且未暂停/未打字时生成解说。
    关着页面（active=False）时事件静默推进（跳过不补解说）；打字时同样跳过解说。
    """
    s = get_state()
    if not s.get("fixture_id") or s.get("ended"):
        return []
    cur = current_minute()
    released = []
    with _LOCK:
        events = s.get("events") or []
        idx = s.get("last_event_index", 0)
        for i in range(idx, len(events)):
            ev = events[i]
            m = _event_minute(ev)
            if m is None or m > cur:
                continue
            released.append(ev)
        if released:
            s["last_event_index"] = idx + len(released)
            save_state(s)
    if released and s.get("active") and not s.get("paused") and not s.get("typing"):
        threading.Thread(target=_gen_commentaries, args=(list(released),), daemon=True).start()
    if cur >= 90:
        end_watch()
    return released


def _gen_commentaries(events):
    s = get_state()
    if not s.get("active") or s.get("paused") or s.get("typing"):
        return
    try:
        sys.path.insert(0, r"YOUR_PATH\backend")
        sys.path.insert(0, r"YOUR_PATH\backend\agent")
        from loop import watch_chat
        for ev in events:
            s = get_state()
            if not s.get("active") or s.get("paused") or s.get("typing"):
                break
            desc = _fmt_event(ev, s)
            prompt = (
                f"你在和user一起复盘你刚踢完的比赛："
                f"{s.get('home_team')} vs {s.get('away_team')}。刚刚场上发生：{desc}。\n"
                "用你自己的口吻给她解说：球员视角、像教练拆解那样专业但讲人话，"
                "让她这个不太懂球的也听得懂。一两句话就好，自然，别报流水账，别叫她'用户'。"
            )
            reply = watch_chat(prompt)
            if reply and reply.strip():
                append_message("companion", reply.strip())
    except Exception as e:
        print(f"[watch] 解说生成失败: {type(e).__name__}: {e}", flush=True)


def public_state():
    """给前端的精简状态（事件转中文 + 消息）。"""
    s = get_state()
    if not s.get("fixture_id"):
        return {"started": False}
    released = []
    for ev in (s.get("events") or [])[: s.get("last_event_index", 0)]:
        released.append({
            "minute": _event_minute(ev),
            "type": ev.get("type"),
            "team": ev.get("team"),
            "text": _fmt_event(ev, s),
        })
    return {
        "started": True,
        "active": s.get("active", False),
        "paused": s.get("paused", False),
        "typing": s.get("typing", False),
        "ended": s.get("ended", False),
        "fixture_id": s.get("fixture_id"),
        "home_team": s.get("home_team"),
        "away_team": s.get("away_team"),
        "current_minute": current_minute(),
        "events_released": released,
        "messages": s.get("messages", []),
    }


# ---------- MCP（5DollarFootballAPI） ----------
# 说明：本段为 MCP stdio 客户端（JSON-RPC 2.0 over stdio）；独立可复用副本见 integrations/mcp/mcp_stdio_client.py


def _mcp_call(name, args):
    child = subprocess.Popen(
        ["cmd.exe", "/c", "npx", "-y", "football-api-mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "FIVEDOLLARFOOTBALL_API_KEY": FIVEDOLLAR_API_KEY},
    )
    result = {}

    def reader():
        for line in child.stdout:
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                continue
            result[j.get("id")] = j

    threading.Thread(target=reader, daemon=True).start()

    def send(obj):
        child.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        child.stdin.flush()

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "watch", "version": "1.0"}}})
    deadline = time.time() + 10
    while time.time() < deadline and 1 not in result:
        time.sleep(0.05)
    if 1 not in result:
        child.kill()
        raise TimeoutError("mcp initialize timeout")
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args}})
    deadline = time.time() + 20
    while time.time() < deadline and 2 not in result:
        time.sleep(0.05)
    child.kill()
    j = result.get(2)
    if not j:
        raise TimeoutError(f"mcp call {name} timeout")
    if j.get("error"):
        raise RuntimeError(json.dumps(j["error"], ensure_ascii=False))
    content = j["result"]["content"]
    text = content[0]["text"]
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    return text


def fetch_recent_finished_fixture():
    """从 MCP 拉一场最近已结束的比赛（优先 PSG 的），返回 {fixture_id, home_team, away_team, events}。
    Key 未配置时安静返回 None（companion没有比赛可看，不报错不崩溃）。"""
    if not FIVEDOLLAR_API_KEY:
        print("[watch] 未配置 FIVEDOLLARFOOTBALL_API_KEY，跳过看球发起", flush=True)
        return None
    data = _mcp_call("get_league_fixtures", {"league_id": LEAGUE_ID})
    results = (data or {}).get("results") or []
    finished = [f for f in results if f.get("status") == "finished"]
    if not finished:
        return None
    finished.sort(key=lambda f: f.get("kickoff_ts") or 0, reverse=True)
    psg = None
    for f in finished:
        teams = f.get("teams") or {}
        ids = {teams.get("home", {}).get("id"), teams.get("away", {}).get("id")}
        if PSG_TEAM_ID in ids:
            psg = f
            break
    f = psg or finished[0]
    detail = _mcp_call("get_fixture", {"fixture_id": f["id"], "include_events": True, "include_stats": False})
    if not isinstance(detail, dict) or not detail.get("events"):
        print("[watch] get_fixture 返回异常（限流或数据缺失），跳过本次发起", flush=True)
        return None
    teams = f.get("teams") or {}
    return {
        "fixture_id": f["id"],
        "home_team": teams.get("home", {}).get("name", ""),
        "away_team": teams.get("away", {}).get("name", ""),
        "events": detail.get("events") or [],
    }
