import json
import re as _re
import threading
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from next_match import get_next_match
from match_fetcher import last_match
from status_rule import get_status_with_location
from config import TIMEZONE


def _fold_call_prefix(text: str) -> str:
    """模型常在自己输出里模仿用户消息的 [电话] 前缀（分条时每条都写），统一折叠成一个。"""
    cleaned = _re.sub(r"^\s*(\[电话\]\s*)+", "", text or "")
    return "[电话] " + cleaned


from call_manager import (
    get_state as call_get,
    start_call,
    accept as call_accept,
    reject as call_reject,
    hangup as call_hangup,
    reset as call_reset,
    set_first_line,
)
from moments_manager import list_posts, add_post, like_post, comment_post
from diary_manager import list_entries, add_entry, has_today, archive_current, list_archive
from clipboard_manager import get_clip, set_text, set_image, clear_clip
from ielts_manager import (
    start_session as ielts_start_session,
    get_state as ielts_get_state,
    submit as ielts_submit,
    get_wrong_words as ielts_get_wrong_words,
    get_today_wrong_words as ielts_get_today_wrong,
    reset as ielts_reset,
)
from pydantic import BaseModel as _BM5
from typing import List as _List


class IeltsSubmitReq(_BM5):
    translations: _List[str]

class ClipSetReq(_BM5):
    type: str
    content: str
from date_plans_manager import list_plans, visible_plans, review_plan, active_dating_plan
from pydantic import BaseModel as _BM
from pydantic import BaseModel as _BM3


class DiaryReq(_BM3):
    content: str

class CallChatReq(_BM):
    message: str

class CallEndReq(_BM):
    duration: str = ""

class MomentPostReq(_BM):
    content: str

class MomentCommentReq(_BM):
    post_id: str
    content: str
    reply_to: str = ""

class MomentLikeReq(_BM):
    post_id: str

class PlanReviewReq(_BM):
    id: str
    decision: str
    reason: str = ""

STATE_PATH = Path(r"./data\home_state.json")
CONFIG_PATH = Path(r"./data\config.json")
HOME_TOKEN = "kairos_home_2026"
HTML_PATH = Path(__file__).parent / "home.html"
ASSETS_DIR = Path(__file__).parent / "assets"

app = FastAPI()
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


def _load_state():
    if not STATE_PATH.exists():
        return {"today": None, "yesterday": None, "day_before": None}
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _check_token(request: Request):
    token = request.query_params.get("t") or request.headers.get("X-Home-Token")
    if token != HOME_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


def _load_api_key():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("api_key", "")
    except Exception:
        return ""


@app.get("/api/home/balance")
def get_balance(request: Request):
    _check_token(request)
    api_key = _load_api_key()
    if not api_key:
        return {"error": "no api key"}
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

@app.get("/api/home/api_usage")
def get_api_usage(request: Request):
    """三 API 余额 + 每日使用量（本地累计）。1=DeepSeek 人民币余额；2/3=方舟额度估算。"""
    _check_token(request)
    from api_usage import total_usage, all_today, monthly_usage
    from config import load_config
    cfg = load_config()

    # api1：DeepSeek 人民币余额（实时查）
    balance_cny = None
    balance_err = None
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {cfg.get('api_key','')}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            infos = d.get("balance_infos", [])
            if infos:
                balance_cny = infos[0].get("total_balance")
            else:
                balance_err = d.get("error") or "无余额信息"
    except Exception as e:
        balance_err = f"{type(e).__name__}: {e}"

    # 火山引擎现金余额（AK/SK 查询）
    try:
        from volc_balance import get_balance
        volc = get_balance()
    except Exception:
        volc = None

    today = all_today()
    return {
        "volc_cash": volc,
        "apis": {
            "api1": {
                "name": "1 · DeepSeek 官方",
                "type": "cny",
                "balance_cny": balance_cny,
                "error": balance_err,
                "today_tokens": today.get("api1", 0),
                "month_tokens": monthly_usage("api1"),
                "total_tokens": total_usage("api1"),
            },
            "api2": {
                "name": "2 · 方舟dpV4.1flash",
                "type": "quota",
                "quota": int(cfg.get("ark2_quota", 500000)),
                "used": total_usage("api2"),
                "remaining": max(0, int(cfg.get("ark2_quota", 500000)) - total_usage("api2")),
                "today_tokens": today.get("api2", 0),
                "month_tokens": monthly_usage("api2"),
            },
            "api3": {
                "name": "3 · 方舟dpV4flash正式版",
                "type": "quota",
                "quota": int(cfg.get("ark3_quota", 500000)),
                "used": total_usage("api3"),
                "remaining": max(0, int(cfg.get("ark3_quota", 500000)) - total_usage("api3")),
                "daily_quota": int(cfg.get("ark3_daily_quota", 2000000)),
                "today_tokens": today.get("api3", 0),
                "month_tokens": monthly_usage("api3"),
            },
        },
        "today": today,
    }


@app.get("/api/home/thinking")
def api_thinking_get(request: Request):
    _check_token(request)
    from config import get_thinking_enabled
    return {"enabled": get_thinking_enabled()}


class ThinkingReq(BaseModel):
    enabled: bool


@app.post("/api/home/thinking")
def api_thinking_set(req: ThinkingReq, request: Request):
    _check_token(request)
    from config import set_thinking_enabled
    set_thinking_enabled(req.enabled)
    return {"enabled": req.enabled}


@app.get("/api/home/state")
def get_state(request: Request):
    _check_token(request)
    from date_roller import roll_if_needed
    roll_if_needed()  # 确保 today.date 是city今天
    state = _load_state()
    if state.get("today"):
        state["today"]["next_match"] = get_next_match()
        state["today"]["last_match"] = last_match()
        state["today"]["companion"] = get_status_with_location()
        # next_date：从 plans 里找最近一条已准许的约会
        from date_plans_manager import list_plans as _lp
        from datetime import datetime as _dt
        _now = _dt.now()
        _upcoming = [p for p in _lp() if p.get("status") == "准许" and p.get("date") >= _now.strftime("%Y-%m-%d")]
        if _upcoming:
            _upcoming.sort(key=lambda x: x.get("date", ""))
            _p = _upcoming[0]
            _tm = (_p.get("start") or "") + ("-" + _p["end"] if _p.get("end") else "")
            state["today"]["next_date"] = {
                "date": _p.get("date", ""),
                "text": (_tm + " " if _tm else "") + (_p.get("location", "") + " · " if _p.get("location") else "") + _p.get("event", ""),
            }
        # 晚上带回：在家 + city时间 19:15 后（他到家了）+ 今天还没带回来。
        st = state["today"]["companion"]
        if st.get("status") == "在家":
            from datetime import datetime
            from zoneinfo import ZoneInfo
            now_p = datetime.now(ZoneInfo(TIMEZONE))
            minutes = now_p.hour * 60 + now_p.minute
            if minutes >= 19 * 60 + 15 and not state["today"].get("brought_back"):
                from fridge_filler import generate_brought_back
                generate_brought_back()
                state = _load_state()  # 写了文件，重读
        if not state["today"].get("breakfast", {}).get("main"):
            from meal_planner import build_breakfast
            bf = build_breakfast(state["today"].get("fridge", []))
            if bf:
                # 早餐从冰箱抽，build_breakfast 不改 fridge；直接存 breakfast
                state2 = _load_state()
                state2["today"]["breakfast"] = bf
                _save_state(state2)
                state = state2
    return state


# ---------- 电话 ----------


def _gen_first_line_async():
    """接通后companion先开口：把「接通了」反馈给模型，生成companion的第一句话并存入历史。
    后台线程执行，不阻塞接口。生成结果写入 call_state.first_line 供前端显示。
    """
    def worker():
        try:
            import sys as _sys
            if r"YOUR_PATH\backend" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend")
            if r"YOUR_PATH\backend\agent" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend\agent")
            from chat.history import save_message
            from loop import chat as loop_chat, llm_api_key
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            _home_now = _dt.now(_tz.utc) + _td(hours=2)
            save_message("user", "[电话] 接通了（city时间 " + _home_now.strftime("%H:%M") + "）")
            api_key = llm_api_key()
            first = loop_chat("[电话] 接通了", api_key)
            if first:
                save_message("assistant", _fold_call_prefix(first))
                set_first_line(first)
                print("[call] companion已开口", flush=True)
        except Exception as e:
            print(f"[call] 接通首句生成失败: {type(e).__name__} {e}", flush=True)

    threading.Thread(target=worker, daemon=True).start()


@app.get("/api/call/state")
def api_call_state(request: Request):
    _check_token(request)
    s = call_get()
    # 拨号后：ringing_from_asu 挂起超过 2.5 秒 → 按companion状态自动接通/拒接（模拟真实等待）
    if s.get("status") == "ringing_from_asu":
        from datetime import datetime, timezone
        try:
            t0 = datetime.fromisoformat(s.get("started_at", ""))
            age = (datetime.now(timezone.utc) - t0).total_seconds()
        except Exception:
            age = 99.0
        if age >= 2.5:
            rin_status = _rin_status()
            if rin_status == "外出":
                call_reject(reason="他在外面")
            else:
                call_accept()
                _gen_first_line_async()
            s = call_get()
    return s


def _rin_status() -> str:
    """读 home_state.json 里companion的当前状态。"""
    from pathlib import Path as _P
    import json as _json
    state_p = _P(r"./data\home_state.json")
    try:
        with open(state_p, encoding="utf-8") as f:
            st = _json.load(f)
        return (st.get("today") or {}).get("companion", {}).get("status", "在家")
    except Exception:
        return "在家"


@app.post("/api/call/accept")
def api_call_accept(request: Request):
    _check_token(request)
    call_accept()
    _gen_first_line_async()
    return call_get()


@app.post("/api/call/reject")
def api_call_reject(request: Request):
    _check_token(request)
    return call_reject()


@app.post("/api/call/hangup")
def api_call_hangup(req: CallEndReq, request: Request):
    _check_token(request)
    call_hangup()
    # 写进聊天历史：代码显示的「通话结束」，不触发回复；模型读上下文时能看到通话已结束
    try:
        import sys as _sys
        if r"YOUR_PATH\backend" not in _sys.path:
            _sys.path.insert(0, r"YOUR_PATH\backend")
        from chat.history import save_message
        if req.duration:
            save_message("user", f"（通话结束，时长 {req.duration}）")
        else:
            save_message("user", "（通话结束）")
    except Exception:
        pass
    if req.duration:
        try:
            import sys as _sys
            if r"YOUR_PATH" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH")
            from wecom.push import push_reply_to_wecom
            push_reply_to_wecom(f"通话结束，时长 {req.duration}")
        except Exception:
            pass
    return {"ok": True}


@app.post("/api/call/reset")
def api_call_reset(request: Request):
    _check_token(request)
    call_reset()
    return {"ok": True}


@app.post("/api/call/dial")
def api_call_dial(request: Request):
    _check_token(request)
    # user打给companion：外出（训练/比赛）→ 拒接；在家 → 接通
    rin_status = _rin_status()
    if rin_status == "外出":
        call_reject(reason="他在外面")
        return {"accepted": False, "status": "rejected", "reason": "他在外面训练/比赛，稍后回你"}
    s = start_call("asu")
    return {"accepted": False, "status": "ringing", "call_id": s.get("call_id", "")}


@app.post("/api/call/chat")
def api_call_chat(req: CallChatReq, request: Request):
    _check_token(request)
    # 调 loop.chat() 生成回复
    import sys as _sys
    _sys.path.insert(0, r"YOUR_PATH\backend")
    _sys.path.insert(0, r"YOUR_PATH\backend\agent")
    from loop import chat as loop_chat, load_config, llm_api_key
    api_key = llm_api_key()  # 峰谷切换
    # 通话场景的 system 提示由 loop.py 内部处理；这里直接调
    from chat.history import save_message
    reasoning = None
    try:
        reply, reasoning = loop_chat(req.message, api_key, return_reasoning=True)
    except Exception as e:
        reply = f"（我这边出了点问题：{type(e).__name__}）"
    if not (reply or "").strip():
        reply = "……"
    # 存进历史（分开会话，但记忆一起）
    save_message("user", f"[电话] {req.message}")
    msg_id = save_message("assistant", _fold_call_prefix(reply), reasoning_content=reasoning)
    return {"reply": reply, "id": msg_id}


@app.get("/api/home/chat_history")
def api_home_chat_history(request: Request):
    _check_token(request)
    import sys as _sys
    _sys.path.insert(0, r"YOUR_PATH\backend")
    _sys.path.insert(0, r"YOUR_PATH\backend\chat")
    from chat.history import get_history
    # 网页端显示 = 归档历史（清记忆前导出，后台不再参与记忆） + 当前新对话
    archive = []
    try:
        with open(r"./data\chat_display_archive.json", encoding="utf-8") as _f:
            _data = json.load(_f)
        archive = _data.get("messages", []) if isinstance(_data, dict) else []
    except Exception:
        archive = []
    current = get_history(80)
    return {"messages": archive + current, "archive_count": len(archive)}


@app.post("/api/home/chat")
def api_home_chat(req: CallChatReq, request: Request):
    _check_token(request)
    import sys as _sys
    _sys.path.insert(0, r"YOUR_PATH\backend")
    _sys.path.insert(0, r"YOUR_PATH\backend\agent")
    from loop import chat as loop_chat, llm_api_key
    from chat.history import save_message
    api_key = llm_api_key()  # 峰谷切换
    save_message("user", req.message)
    reasoning = None
    try:
        reply, reasoning = loop_chat(req.message, api_key, return_reasoning=True)
    except Exception as e:
        reply = f"（我这边出了点问题：{type(e).__name__}）"
    if not (reply or "").strip():
        reply = "……"
    # 检测：companion说现在要打电话 → 真触发来电 + 拼链接
    import re as _re
    call_now = bool(_re.search(r"(拨电话|打过来|拨通了|拨了过去|拨了|等接通|接通|接一下|我打了|给你打过去了|电话接起来|打过来了|拨过去)", reply or ""))
    call_link_text = ""
    if call_now:
        try:
            import sys as _cs
            _cs.path.insert(0, r"YOUR_PATH\backend\home")
            from call_manager import start_call, call_link, mark_link_sent
            start_call("companion")
            call_link_text = "\n\n" + call_link()
            mark_link_sent()
            reply_full = reply + call_link_text
            save_message("assistant", reply_full, reasoning_content=reasoning)
        except Exception as _ce:
            print("[home] 触发电话失败:", _ce, flush=True)
            reply_full = reply
            msg_id = save_message("assistant", reply_full, reasoning_content=reasoning)
    else:
        reply_full = reply
        msg_id = save_message("assistant", reply_full, reasoning_content=reasoning)
    try:
        import sys as _sys
        if r"YOUR_PATH" not in _sys.path:
            _sys.path.insert(0, r"YOUR_PATH")
        from wecom.push import push_pair_async
        push_pair_async(req.message, reply_full)
    except Exception as _e:
        print("[home] 同步企微失败:", _e, flush=True)
    return {"reply": reply_full, "id": msg_id}


@app.post("/api/home/new_chat")
def api_home_new_chat(request: Request):
    """一键清空：companion后台记忆全部重置（聊天/亲密/早餐/日记/朋友圈当前/看球残留），
    网页端历史（chat_display_archive + moments_archive）保留，冰箱保留。
    清空前自动备份到 YOUR_PATH\一键清空_时间戳\。
    """
    _check_token(request)
    import time as _t
    import shutil as _shutil
    import os as _os
    import sqlite3 as _sq
    _now = _t.time()
    _data = r"./data"
    _bak = r"YOUR_PATH\一键清空_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    _os.makedirs(_bak, exist_ok=True)

    # 1. 备份（备份完成前不清任何东西）
    _files = ["chat_history.db", "intimacy_state.txt", "home_state.json", "diary.json", "moments.json", "watch_state.json"]
    _backed = []
    for _f in _files:
        _p = _os.path.join(_data, _f)
        if _os.path.exists(_p):
            try:
                _shutil.copy2(_p, _os.path.join(_bak, _f))
                _backed.append(_f)
            except Exception as _e:
                print("[home] 备份失败:", _f, _e, flush=True)

    # 2. 清空聊天记录
    _deleted = 0
    try:
        _conn = _sq.connect(_os.path.join(_data, "chat_history.db"))
        _deleted = _conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        _conn.execute("DELETE FROM messages")
        _conn.commit()
        _conn.close()
    except Exception as _e:
        print("[home] 清聊天失败:", _e, flush=True)

    # 3. 重置亲密状态（基线 15，无会话计时）
    try:
        open(_os.path.join(_data, "intimacy_state.txt"), "w", encoding="utf-8").write(
            json.dumps({"arousal": 15.0, "ts": _now, "enter_ts": None})
        )
    except Exception as _e:
        print("[home] 重置亲密失败:", _e, flush=True)

    # 4. 清早餐 / 今天吃了什么（保留冰箱）
    try:
        _st = json.load(open(_os.path.join(_data, "home_state.json"), encoding="utf-8"))
        _td = _st.get("today", {})
        _td["breakfast"] = {"main": "", "fruit": "", "drink": "", "placed": "", "eaten": False, "fridge_updated": False}
        _td["today_events"] = []
        open(_os.path.join(_data, "home_state.json"), "w", encoding="utf-8", newline="").write(
            json.dumps(_st, ensure_ascii=False, indent=2)
        )
    except Exception as _e:
        print("[home] 清早餐失败:", _e, flush=True)

    # 5. 清日记 / 朋友圈当前动态（日记先归档到历史，朋友圈历史归档保留）
    try:
        arch = archive_current()
        open(_os.path.join(_data, "moments.json"), "w", encoding="utf-8", newline="").write(
            json.dumps({"posts": []}, ensure_ascii=False)
        )
    except Exception as _e:
        print("[home] 清日记/朋友圈失败:", _e, flush=True)

    # 6. 重置看球残留（watch_state）
    try:
        _wp = _os.path.join(_data, "watch_state.json")
        if _os.path.exists(_wp):
            _w = json.load(open(_wp, encoding="utf-8"))
            _w["active"] = False
            _w["fixture_id"] = None
            _w["home_team"] = ""
            _w["away_team"] = ""
            _w["started_at"] = ""
            _w["paused"] = False
            _w["paused_at"] = ""
            _w["typing"] = False
            _w["events"] = []
            _w["ended"] = False
            open(_wp, "w", encoding="utf-8", newline="").write(json.dumps(_w, ensure_ascii=False, indent=2))
    except Exception as _e:
        print("[home] 重置看球失败:", _e, flush=True)

    # 7. 更新新对话时间戳（兼容 LLM 上下文过滤）
    open(_os.path.join(_data, "last_clear.txt"), "w").write(str(_now))

    return {"ok": True, "deleted": _deleted, "backup": _bak, "backed_files": _backed}


@app.get("/api/home/chat_reasoning")
def api_home_chat_reasoning(request: Request):
    _check_token(request)
    msg_id = request.query_params.get("id")
    if not msg_id or not msg_id.isdigit():
        raise HTTPException(status_code=400, detail="bad id")
    import sys as _sys
    _sys.path.insert(0, r"YOUR_PATH\backend")
    from chat.history import get_reasoning
    r = get_reasoning(int(msg_id))
    return {"reasoning": r}


@app.get("/call")
def call_page(request: Request):
    _check_token(request)
    # 返回同一个 home.html，前端 JS 检测 URL 决定是否弹来电窗
    from fastapi.responses import FileResponse
    return FileResponse(r"YOUR_PATH\backend\home\home.html")


class AteRequest(BaseModel):
    index: int
    eaten_qty: float
    eaten_at: str = ""


@app.post("/api/home/ate")
def ate(req: AteRequest, request: Request):
    _check_token(request)
    state = _load_state()
    day = state.get("today")
    if not day:
        raise HTTPException(status_code=404, detail="no today")
    fridge = day.get("fridge") or []
    if req.index < 0 or req.index >= len(fridge):
        raise HTTPException(status_code=400, detail="bad index")
    item = fridge[req.index]
    if req.eaten_qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")
    current = float(item.get("qty", 1.0))
    if req.eaten_qty > current:
        raise HTTPException(status_code=400, detail="not enough")
    new_qty = round(current - req.eaten_qty, 1)
    name = item.get("name", "")
    unit = item.get("unit", "")
    if new_qty <= 0:
        fridge.pop(req.index)
    else:
        item["qty"] = new_qty
    ts = req.eaten_at or datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M")  # city时间
    day["today_events"].append({"time": ts, "text": f"user吃了{req.eaten_qty}{unit}{name}"})
    _save_state(state)
    return {"ok": True, "name": name, "remain": new_qty}


@app.get("/api/home/calendar")
def get_calendar(request: Request, year: int = 0, month: int = 0):
    _check_token(request)
    from calendar_builder import load_or_rebuild
    cache = load_or_rebuild()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now_p = datetime.now(ZoneInfo(TIMEZONE))
    y = year or now_p.year
    m = month or now_p.month
    for mo in cache["months"]:
        if mo["year"] == y and mo["month"] == m:
            return mo
    return {"year": y, "month": m, "days": []}


@app.get("/home", response_class=HTMLResponse)
def home(request: Request):
    _check_token(request)
    if HTML_PATH.exists():
        return HTML_PATH.read_text(encoding="utf-8")
    return "<h1>home.html not found</h1>"


# ---------- 朋友圈 ----------


@app.get("/api/moments/list")
def api_moments_list(request: Request):
    _check_token(request)
    return {"posts": list_posts()}


@app.get("/api/moments/archive")
def api_moments_archive(request: Request):
    _check_token(request)
    try:
        with open(r"./data\moments_archive.json", encoding="utf-8") as _f:
            _data = json.load(_f)
        return {"posts": _data.get("posts", []) if isinstance(_data, dict) else []}
    except Exception:
        return {"posts": []}


@app.post("/api/moments/post")
def api_moments_post(req: MomentPostReq, request: Request):
    _check_token(request)
    return add_post("asu", req.content)


@app.post("/api/moments/like")
def api_moments_like(req: MomentLikeReq, request: Request):
    _check_token(request)
    like_post(req.post_id, "asu")
    return {"ok": True}


@app.post("/api/moments/comment")
def api_moments_comment(req: MomentCommentReq, request: Request):
    _check_token(request)
    reply_to = req.reply_to if req.reply_to else None
    return comment_post(req.post_id, "asu", req.content, reply_to=reply_to)


# ---------- 日记 ----------


@app.get("/api/diary/list")
def api_diary_list(request: Request):
    _check_token(request)
    return {"entries": list_entries()}


@app.post("/api/diary/write")
def api_diary_write(req: DiaryReq, request: Request):
    _check_token(request)
    return add_entry(req.content)


@app.get("/api/diary/has_today")
def api_diary_has_today(request: Request):
    _check_token(request)
    return {"has_today": has_today()}


@app.get("/api/diary/archive")
def api_diary_archive(request: Request):
    _check_token(request)
    return {"batches": list_archive()}


@app.get("/api/clip/get")
def api_clip_get(request: Request):
    _check_token(request)
    return get_clip()

@app.post("/api/clip/set")
def api_clip_set(req: ClipSetReq, request: Request):
    _check_token(request)
    if req.type == "image":
        set_image(req.content)
    else:
        set_text(req.content)
    return {"ok": True}

@app.post("/api/clip/clear")
def api_clip_clear(request: Request):
    _check_token(request)
    clear_clip()
    return {"ok": True}

@app.get("/api/clip/image")
def api_clip_image(request: Request):
    _check_token(request)
    from fastapi.responses import FileResponse
    p = r"./data\clipboard_image.png"
    if not Path(p).exists():
        raise HTTPException(status_code=404, detail="no image")
    return FileResponse(p)

@app.get("/clip")
def clip_page(request: Request):
    _check_token(request)
    from fastapi.responses import HTMLResponse
    html = open(r"YOUR_PATH\backend\home\clip_page.html", encoding="utf-8").read()
    return HTMLResponse(html.replace("TOKEN", HOME_TOKEN))


# ---------- 雅思翻译练习 ----------


@app.get("/api/ielts/start")
def api_ielts_start(request: Request):
    _check_token(request)
    return ielts_start_session(10)


@app.get("/api/ielts/state")
def api_ielts_state(request: Request):
    _check_token(request)
    return ielts_get_state()


@app.post("/api/ielts/submit")
def api_ielts_submit(req: IeltsSubmitReq, request: Request):
    _check_token(request)
    return ielts_submit(req.translations)


@app.get("/api/ielts/wrong_words")
def api_ielts_wrong_words(request: Request):
    _check_token(request)
    return {"words": ielts_get_wrong_words(50)}


@app.get("/api/ielts/today_wrong")
def api_ielts_today_wrong(request: Request):
    _check_token(request)
    return {"words": ielts_get_today_wrong()}


@app.post("/api/ielts/reset")
def api_ielts_reset(request: Request):
    _check_token(request)
    ielts_reset()
    return {"ok": True}


@app.get("/ielts", response_class=HTMLResponse)
def ielts_page(request: Request):
    _check_token(request)
    from fastapi.responses import HTMLResponse
    html = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>雅思翻译</title>
<style>
html,body{margin:0;padding:0;min-height:100%;background:#f5f5f5;color:#222;font-family:-apple-system,sans-serif;}
#top{padding:12px 16px;display:flex;justify-content:space-between;align-items:center;background:#fff;border-bottom:1px solid #eee;position:sticky;top:0;z-index:10;}
#top a{color:#4a90d9;text-decoration:none;font-size:16px;}
#wrap{padding:16px;max-width:680px;margin:0 auto;}
.q{background:#fff;border-radius:10px;padding:14px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,0.05);}
.q .en{font-size:16px;line-height:1.6;margin-bottom:10px;color:#111;}
.q .word{display:inline-block;background:#eef4ff;color:#3b6fc4;font-size:12px;padding:2px 8px;border-radius:4px;margin-bottom:8px;}
.q textarea{width:100%;box-sizing:border-box;min-height:60px;padding:10px;border:1px solid #ddd;border-radius:8px;font-size:15px;font-family:inherit;resize:vertical;}
.q .result{margin-top:10px;padding:10px;border-radius:8px;font-size:14px;display:none;}
.q .result.ok{background:#e8f8ee;color:#1e7a3e;display:block;}
.q .result.bad{background:#fdecea;color:#b53a2a;display:block;}
.q .result .ref{font-weight:600;margin-top:4px;}
#btns{position:sticky;bottom:0;padding:12px 16px;background:#fff;border-top:1px solid #eee;display:flex;gap:10px;max-width:680px;margin:0 auto;}
#btns button{flex:1;padding:14px;border:none;border-radius:10px;font-size:16px;background:#4a90d9;color:#fff;cursor:pointer;}
#btns button.ghost{background:#eee;color:#333;}
#btns button:disabled{opacity:0.5;}
</style>
</head>
<body>
<div id="top">
  <a href="/home?t=TOKEN">&#8592; 返回</a>
  <span id="title">雅思翻译</span>
  <a href="#" onclick="resetSession();return false;" style="font-size:14px;">换一篇</a>
</div>
<div id="wrap"></div>
<div id="btns">
  <button class="ghost" onclick="showWords()">错词本</button>
  <button id="submitBtn" onclick="submitAll()">提交批改</button>
</div>
<script>
const TOKEN = new URLSearchParams(location.search).get('t') || 'kairos_home_2026';
let state = null;

async function api(path, opts={}) {
  const sep = path.includes('?') ? '&' : '?';
  return fetch(path + sep + 't=' + TOKEN, opts).then(r=>r.json());
}

async function loadSession(){
  let s = await api('/api/ielts/state');
  if (!s || !s.sentences) {
    s = await api('/api/ielts/start');
  }
  state = s;
  render();
}

function esc(x){return String(x==null?'':x).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

function render(){
  const wrap = document.getElementById('wrap');
  wrap.innerHTML = '';
  if (state.article_title) document.getElementById('title').textContent = state.article_title;
  if (!state.sentences) { wrap.innerHTML='<p>加载中…</p>'; return; }
  state.sentences.forEach((s, i) => {
    const q = document.createElement('div');
    q.className = 'q';
    let resultHtml = '';
    if (state.results && state.results[i]) {
      const r = state.results[i];
      resultHtml = r.correct
        ? '<div class="result ok">✓ 意思对了' + (r.comment ? '：' + esc(r.comment) : '') + '</div>'
        : '<div class="result bad">✗ ' + esc(r.comment || '') + '<div class="ref">参考：' + esc(r.reference || '') + '</div></div>';
    }
    q.innerHTML =
      '<div class="word">目标词：' + esc(s.target_word) + '</div>' +
      '<div class="en">' + esc(s.sentence) + '</div>' +
      '<textarea id="ta-' + i + '" ' + (state.submitted?'disabled':'') + ' placeholder="输入中文翻译…"></textarea>' +
      resultHtml;
    wrap.appendChild(q);
    if (state.user_translations && state.user_translations[i]) {
      document.getElementById('ta-'+i).value = state.user_translations[i];
    }
  });
  if (state.submitted) document.getElementById('submitBtn').disabled = true;
}

async function submitAll(){
  const trans = state.sentences.map((_, i) => document.getElementById('ta-'+i).value);
  if (trans.some(t => !t.trim())) {
    if (!confirm('有未填的句子，确定提交？')) return;
  }
  document.getElementById('submitBtn').disabled = true;
  document.getElementById('submitBtn').textContent = '批改中…';
  const r = await api('/api/ielts/submit', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({translations: trans})
  });
  if (r.error) { alert('批改失败：' + r.error); document.getElementById('submitBtn').disabled=false; document.getElementById('submitBtn').textContent='提交批改'; return; }
  state = await api('/api/ielts/state');
  state.user_translations = trans;
  document.getElementById('submitBtn').textContent = '已批改';
  render();
}

async function resetSession(){
  await api('/api/ielts/reset', {method:'POST'});
  state = await api('/api/ielts/start');
  document.getElementById('submitBtn').disabled = false;
  document.getElementById('submitBtn').textContent = '提交批改';
  render();
  window.scrollTo(0,0);
}

async function showWords(){
  const r = await api('/api/ielts/wrong_words');
  const list = r.words.map(w => (w.date||'') + '  ' + w.word).join('\\n') || '还没有错词';
  alert('错词本：\\n' + list);
}

loadSession();
</script>
</body>
</html>"""
    return HTMLResponse(html.replace("TOKEN", HOME_TOKEN))


# ---------- 约会计划 ----------


@app.get("/api/plans/list")
def api_plans_list(request: Request):
    _check_token(request)
    return {"plans": visible_plans()}


@app.post("/api/plans/review")
def api_plans_review(req: PlanReviewReq, request: Request):
    _check_token(request)
    result = review_plan(req.id, req.decision, req.reason)
    if isinstance(result, str):
        raise HTTPException(status_code=400, detail=result)
    # 准许的约会进月历（重建缓存）
    try:
        from calendar_builder import build_cache, CACHE_PATH
        CACHE_PATH.write_text(
            __import__("json").dumps(build_cache(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    # user留了理由 → 自动让companion生成回复并推给她
    if req.reason and req.reason.strip():
        try:
            import sys as _sys
            if r"YOUR_PATH" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH")
            if r"YOUR_PATH\backend" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend")
            if r"YOUR_PATH\backend\agent" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend\agent")
            from loop import chat as loop_chat, load_config
            from wecom.push import push_reply_to_wecom
            _p = result
            _decision_txt = {"准许": "准许了", "拒绝": "拒绝了", "再议": "说再议"}.get(req.decision, req.decision)
            _prompt = (
                "user刚刚批阅了你提的约会计划：「" + _p.get("event", "") + "」（"
                + _p.get("date", "") + " " + _p.get("start", "") + "）。她" + _decision_txt
                + "，留了句话：" + req.reason.strip() + "。你回她。用你平时跟她说话的语气，自然一点。"
            )
            _api_key = load_config().get("api_key", "")
            _reply, _reasoning = loop_chat(_prompt, _api_key, return_reasoning=True)
            if _reply and _reply.strip():
                push_reply_to_wecom(_reply)
                try:
                    from chat.history import save_thought
                    save_thought("批阅回复", _reply, reasoning=_reasoning)
                except Exception:
                    pass
        except Exception as _e:
            print("批阅回复生成失败:", _e)
    return result


# ---------- 看球（一起复盘比赛） ----------


class WatchStartReq(BaseModel):
    fixture_id: int
    home_team: str
    away_team: str
    events: list = []


class WatchChatReq(BaseModel):
    message: str


class WatchFlagReq(BaseModel):
    value: bool


@app.get("/api/watch/state")
def api_watch_state(request: Request):
    _check_token(request)
    from watch_manager import get_state as _ws, set_active, release_events, public_state
    s = _ws()
    if s.get("fixture_id") and not s.get("ended"):
        set_active(True)  # 用户打开页面 → active
        release_events()
    return public_state()


@app.post("/api/watch/start")
def api_watch_start(req: WatchStartReq, request: Request):
    _check_token(request)
    from watch_manager import start_watch, public_state
    start_watch(req.fixture_id, req.home_team, req.away_team, req.events)
    return public_state()


@app.post("/api/watch/end")
def api_watch_end(request: Request):
    _check_token(request)
    from watch_manager import end_watch, public_state
    end_watch()
    return public_state()


@app.post("/api/watch/pause")
def api_watch_pause(request: Request):
    _check_token(request)
    from watch_manager import pause_watch, public_state
    pause_watch()
    return public_state()


@app.post("/api/watch/resume")
def api_watch_resume(request: Request):
    _check_token(request)
    from watch_manager import resume_watch, public_state
    resume_watch()
    return public_state()


@app.post("/api/watch/typing")
def api_watch_typing(req: WatchFlagReq, request: Request):
    _check_token(request)
    from watch_manager import set_typing, public_state
    set_typing(req.value)
    return public_state()


@app.post("/api/watch/presence")
def api_watch_presence(req: WatchFlagReq, request: Request):
    """用户打开/离开页面的信号：active=false 时停止调 API，计时继续。"""
    _check_token(request)
    from watch_manager import set_active, public_state
    set_active(req.value)
    return {"ok": True}


@app.post("/api/watch/chat")
def api_watch_chat(req: WatchChatReq, request: Request):
    _check_token(request)
    import sys as _sys
    _sys.path.insert(0, r"YOUR_PATH\backend")
    _sys.path.insert(0, r"YOUR_PATH\backend\agent")
    from watch_manager import get_state, set_typing, append_message
    from loop import watch_chat
    s = get_state()
    if not s.get("fixture_id") or s.get("ended"):
        raise HTTPException(status_code=400, detail="watch not active")
    set_typing(False)  # 发送消息即停止打字
    append_message("user", req.message)
    # 带上 watch 内最近几句对话，companion能接上（不进正式历史）
    recent = [m for m in (s.get("messages") or []) if m.get("content") != req.message][-6:]
    ctx = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in recent)
    try:
        reply = watch_chat(req.message, context=ctx)
    except Exception as e:
        reply = f"（我这边出了点问题：{type(e).__name__}）"
    if not (reply or "").strip():
        reply = "……"
    append_message("companion", reply)
    return {"reply": reply}


@app.get("/watch")
def watch_page(request: Request):
    _check_token(request)
    from fastapi.responses import FileResponse
    return FileResponse(r"YOUR_PATH\backend\home\home.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5971)
