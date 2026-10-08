import hmac
import json
import logging
import os
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
try:
    from next_match import get_next_match
    from match_fetcher import last_match
    from status_rule import get_status_with_location
    HAS_MATCH_MODULES = True
except ImportError:
    get_next_match = last_match = get_status_with_location = None
    HAS_MATCH_MODULES = False
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
try:
    from date_plans_manager import list_plans, visible_plans, review_plan, active_dating_plan
    HAS_PLANS_MODULES = True
except ImportError:
    list_plans = visible_plans = review_plan = active_dating_plan = None
    HAS_PLANS_MODULES = False
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

logger = logging.getLogger(__name__)

if not HAS_MATCH_MODULES:
    logger.warning("next_match / match_fetcher / status_rule 模块缺失，看球相关功能不可用")
if not HAS_PLANS_MODULES:
    logger.warning("date_plans_manager 模块缺失，约会计划功能不可用")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


STATE_PATH = Path("./data/home_state.json")
CONFIG_PATH = Path("./data/config.json")
HOME_TOKEN = os.environ.get("HOME_TOKEN")
if not HOME_TOKEN:
    raise RuntimeError("HOME_TOKEN 环境变量必须设置，不能为空")
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
    token = request.query_params.get("t") or request.headers.get("X-Home-Token", "")
    if not hmac.compare_digest(token, HOME_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


def _load_api_key():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("api_key", "")
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        logger.warning("读取 config.json 失败: %s", e)
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
        logger.warning("余额查询失败: %s", e)
        return {"error": "余额查询服务暂时不可用"}

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
        logger.warning("余额查询失败: %s", e)
        balance_err = "用量查询服务暂时不可用"

    # 火山引擎现金余额（AK/SK 查询）
    try:
        from volc_balance import get_balance
        volc = get_balance()
    except (ImportError, OSError, ValueError, TypeError, KeyError) as e:
        logger.warning("火山余额查询失败: %s", e)
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


DEFAULT_PERSONA_PATH = Path(__file__).resolve().parent.parent / "data" / "persona_default.md"


@app.get("/api/setup/status")
def get_setup_status(request: Request):
    _check_token(request)
    from config import PERSONA_PATH, load_config
    cfg = load_config() or {}
    persona = ""
    if PERSONA_PATH.exists():
        try:
            persona = PERSONA_PATH.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("读取 persona 失败: %s", e)
    default_persona = ""
    if DEFAULT_PERSONA_PATH.exists():
        try:
            default_persona = DEFAULT_PERSONA_PATH.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("读取默认 persona 失败: %s", e)
    return {
        "configured": bool(cfg.get("api_key")),
        "name": cfg.get("name", ""),
        "has_api_key": bool(cfg.get("api_key")),
        "persona": persona,
        "default_persona": default_persona,
    }


@app.post("/api/setup/save")
async def save_setup(request: Request):
    _check_token(request)
    data = await request.json()
    from config import PERSONA_PATH, load_config, save_config
    cfg = load_config() or {}
    name = (data.get("name") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    persona = data.get("persona") or ""
    if name:
        cfg["name"] = name
    if api_key:
        cfg["api_key"] = api_key
    save_config(cfg)
    if persona.strip():
        PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
        PERSONA_PATH.write_text(persona, encoding="utf-8")
    return {"ok": True}


@app.get("/api/home/state")
def get_state(request: Request):
    _check_token(request)
    from date_roller import roll_if_needed
    roll_if_needed()  # 确保 today.date 是city今天
    state = _load_state()
    if state.get("today"):
        if HAS_MATCH_MODULES:
            state["today"]["next_match"] = get_next_match()
            state["today"]["last_match"] = last_match()
            state["today"]["companion"] = get_status_with_location()
        # next_date：从 plans 里找最近一条已准许的约会
        if HAS_PLANS_MODULES:
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
        st = state["today"].get("companion") or {}
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
                logger.info("companion 已开口")
        except Exception as e:
            logger.warning("接通首句生成失败: %s", e)

    threading.Thread(target=worker, daemon=True).start()


@app.get("/api/call/state")
def api_call_state(request: Request):
    _check_token(request)
    s = call_get()
    # 拨号后：ringing_from_user 挂起超过 2.5 秒 → 按companion状态自动接通/拒接（模拟真实等待）
    if s.get("status") == "ringing_from_user":
        from datetime import datetime, timezone
        try:
            t0 = datetime.fromisoformat(s.get("started_at", ""))
            age = (datetime.now(timezone.utc) - t0).total_seconds()
        except (ValueError, TypeError) as e:
            logger.debug("解析通话开始时间失败: %s", e)
            age = 99.0
        if age >= 2.5:
            partner_status = _partner_status()
            if partner_status == "外出":
                call_reject(reason="他在外面")
            else:
                call_accept()
                _gen_first_line_async()
            s = call_get()
    return s


def _partner_status() -> str:
    """读 home_state.json 里companion的当前状态。"""
    from pathlib import Path as _P
    import json as _json
    state_p = _P("./data/home_state.json")
    try:
        with open(state_p, encoding="utf-8") as f:
            st = _json.load(f)
        return (st.get("today") or {}).get("companion", {}).get("status", "在家")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError) as e:
        logger.warning("读取状态文件失败: %s", e)
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
        from chat.history import save_message
        if req.duration:
            save_message("user", f"（通话结束，时长 {req.duration}）")
        else:
            save_message("user", "（通话结束）")
    except Exception:
        logger.exception("通话结束消息保存失败")
    if req.duration:
        try:
            import sys as _sys
            from wecom.push import push_reply_to_wecom
            push_reply_to_wecom(f"通话结束，时长 {req.duration}")
        except Exception as e:
            logger.warning("企微推送通话结束失败: %s", e)
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
    partner_status = _partner_status()
    if partner_status == "外出":
        call_reject(reason="他在外面")
        return {"accepted": False, "status": "rejected", "reason": "他在外面训练/比赛，稍后回你"}
    s = start_call("user")
    return {"accepted": False, "status": "ringing", "call_id": s.get("call_id", "")}


@app.post("/api/call/chat")
def api_call_chat(req: CallChatReq, request: Request):
    _check_token(request)
    # 调 loop.chat() 生成回复
    import sys as _sys
    from loop import chat as loop_chat, load_config, llm_api_key
    api_key = llm_api_key()  # 峰谷切换
    # 通话场景的 system 提示由 loop.py 内部处理；这里直接调
    from chat.history import save_message
    reasoning = None
    try:
        reply, reasoning = loop_chat(req.message, api_key, return_reasoning=True)
    except Exception as e:
        logger.warning("来电对话失败: %s", e)
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
    from chat.history import get_history
    # 网页端显示 = 归档历史（清记忆前导出，后台不再参与记忆） + 当前新对话
    archive = []
    try:
        with open("./data/chat_display_archive.json", encoding="utf-8") as _f:
            _data = json.load(_f)
        archive = _data.get("messages", []) if isinstance(_data, dict) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.warning("读取聊天归档失败: %s", e)
        archive = []
    current = get_history(80)
    return {"messages": archive + current, "archive_count": len(archive)}


@app.post("/api/home/chat")
def api_home_chat(req: CallChatReq, request: Request):
    _check_token(request)
    import sys as _sys
    from loop import chat as loop_chat, llm_api_key
    from chat.history import save_message
    api_key = llm_api_key()  # 峰谷切换
    save_message("user", req.message)
    reasoning = None
    try:
        reply, reasoning = loop_chat(req.message, api_key, return_reasoning=True)
    except Exception as e:
        logger.warning("聊天回复失败: %s", e)
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
            from call_manager import start_call, call_link, mark_link_sent
            start_call("companion")
            call_link_text = "\n\n" + call_link()
            mark_link_sent()
            reply_full = reply + call_link_text
            save_message("assistant", reply_full, reasoning_content=reasoning)
        except Exception as _ce:
            logger.warning("触发电话失败: %s", _ce)
            reply_full = reply
            msg_id = save_message("assistant", reply_full, reasoning_content=reasoning)
    else:
        reply_full = reply
        msg_id = save_message("assistant", reply_full, reasoning_content=reasoning)
    try:
        import sys as _sys
        from wecom.push import push_pair_async
        push_pair_async(req.message, reply_full)
    except Exception as _e:
        logger.warning("同步企微失败: %s", _e)
    return {"reply": reply_full, "id": msg_id}


@app.post("/api/home/new_chat")
def api_home_new_chat(request: Request):
    """一键清空：companion后台记忆全部重置（聊天/亲密/早餐/日记/朋友圈当前/看球残留），
    网页端历史（chat_display_archive + moments_archive）保留，冰箱保留。
    清空前自动备份到 ./backups/一键清空_时间戳/。
    """
    _check_token(request)
    import time as _t
    import shutil as _shutil
    import os as _os
    import sqlite3 as _sq
    _now = _t.time()
    _data = r"./data"
    _bak = Path("./backups") / ("一键清空_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
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
                logger.warning("备份失败: %s %s", _f, _e)

    # 2. 清空聊天记录
    _deleted = 0
    try:
        _conn = _sq.connect(_os.path.join(_data, "chat_history.db"))
        _deleted = _conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        _conn.execute("DELETE FROM messages")
        _conn.commit()
        _conn.close()
    except Exception as _e:
        logger.warning("清聊天记录失败: %s", _e)

    # 3. 重置亲密状态（基线 15，无会话计时）
    try:
        open(_os.path.join(_data, "intimacy_state.txt"), "w", encoding="utf-8").write(
            json.dumps({"arousal": 15.0, "ts": _now, "enter_ts": None})
        )
    except Exception as _e:
        logger.warning("重置亲密状态失败: %s", _e)

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
        logger.warning("清早餐记录失败: %s", _e)

    # 5. 清日记 / 朋友圈当前动态（日记先归档到历史，朋友圈历史归档保留）
    try:
        arch = archive_current()
        open(_os.path.join(_data, "moments.json"), "w", encoding="utf-8", newline="").write(
            json.dumps({"posts": []}, ensure_ascii=False)
        )
    except Exception as _e:
        logger.warning("清日记/朋友圈失败: %s", _e)

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
        logger.warning("重置看球状态失败: %s", _e)

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
    from chat.history import get_reasoning
    r = get_reasoning(int(msg_id))
    return {"reasoning": r}


@app.get("/call")
def call_page(request: Request):
    _check_token(request)
    # 返回同一个 home.html，前端 JS 检测 URL 决定是否弹来电窗
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).resolve().parent / "home.html")


class AteRequest(BaseModel):
    index: int
    eaten_qty: float
    eaten_at: str = ""


class FridgeAddRequest(BaseModel):
    name: str
    qty: float = 1
    unit: str = "份"


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


@app.post("/api/home/fridge/add")
def fridge_add(req: FridgeAddRequest, request: Request):
    _check_token(request)
    name = (req.name or "").strip()
    if not name:
        return {"ok": False, "error": "名称不能为空"}
    qty = req.qty if req.qty > 0 else 1
    unit = (req.unit or "份").strip()
    state = _load_state()
    if not state.get("today"):
        state["today"] = {}
    today = state["today"]
    fridge = today.setdefault("fridge", [])
    # 已存在同名则累加数量
    for item in fridge:
        if item.get("name") == name:
            item["qty"] = item.get("qty", 0) + qty
            _save_state(state)
            return {"ok": True, "item": item}
    fridge.append({"name": name, "qty": qty, "unit": unit})
    _save_state(state)
    return {"ok": True, "item": {"name": name, "qty": qty, "unit": unit}}


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
        with open("./data/moments_archive.json", encoding="utf-8") as _f:
            _data = json.load(_f)
        return {"posts": _data.get("posts", []) if isinstance(_data, dict) else []}
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.warning("读取朋友圈归档失败: %s", e)
        return {"posts": []}


@app.post("/api/moments/post")
def api_moments_post(req: MomentPostReq, request: Request):
    _check_token(request)
    return add_post("user", req.content)


@app.post("/api/moments/like")
def api_moments_like(req: MomentLikeReq, request: Request):
    _check_token(request)
    like_post(req.post_id, "user")
    return {"ok": True}


@app.post("/api/moments/comment")
def api_moments_comment(req: MomentCommentReq, request: Request):
    _check_token(request)
    reply_to = req.reply_to if req.reply_to else None
    return comment_post(req.post_id, "user", req.content, reply_to=reply_to)


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




# ---------- 约会计划 ----------


@app.get("/api/plans/list")
def api_plans_list(request: Request):
    _check_token(request)
    if not HAS_PLANS_MODULES:
        return {"error": "约会计划功能需要额外配置，当前不可用", "plans": []}
    return {"plans": visible_plans()}


@app.post("/api/plans/review")
def api_plans_review(req: PlanReviewReq, request: Request):
    _check_token(request)
    if not HAS_PLANS_MODULES:
        return {"error": "约会计划功能需要额外配置，当前不可用"}
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
    except Exception as e:
        logger.warning("plans 缓存写入失败: %s", e)
    # user留了理由 → 自动让companion生成回复并推给她
    if req.reason and req.reason.strip():
        try:
            import sys as _sys
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
                except Exception as e:
                    logger.warning("保存批阅思考链失败: %s", e)
        except Exception as _e:
            logger.warning("批阅回复生成失败: %s", _e)
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
        logger.warning("看球聊天失败: %s", e)
        reply = f"（我这边出了点问题：{type(e).__name__}）"
    if not (reply or "").strip():
        reply = "……"
    append_message("companion", reply)
    return {"reply": reply}


@app.get("/watch")
def watch_page(request: Request):
    _check_token(request)
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).resolve().parent / "home.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5971)
