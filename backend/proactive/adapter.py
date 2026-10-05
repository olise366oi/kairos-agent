# YOUR_PATH\backend\proactive\adapter.py
import sys
import json
import sqlite3
import urllib.request
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, r"YOUR_PATH\backend")
sys.path.insert(0, r"YOUR_PATH\backend\agent")
sys.path.insert(0, r"YOUR_PATH\backend\companion_awakening")
# wecom 路径放最后（append），避免 wecom\config.py 的 `from config` 遮蔽 backend\config
sys.path.append(r"YOUR_PATH\wecom")
sys.path.append(r"YOUR_PATH")

DB_PATH = Path(r"./data\chat_history.db")
DRY_RUN = False  # 真发模式

HOME_STATE = Path(r"./data\home_state.json")

DRIVESOID_URL = "http://127.0.0.1:24601/api/drives/context"


def _home_tz_utc_offset(now) -> int:
    """city时区：3月最后一个周日至10月最后一个周日为夏令时 UTC+2，其余 UTC+1。"""
    from datetime import date
    y = now.year
    march_last = date(y, 3, 31)
    while march_last.weekday() != 6:
        march_last = march_last.replace(day=march_last.day - 1)
    oct_last = date(y, 10, 31)
    while oct_last.weekday() != 6:
        oct_last = oct_last.replace(day=oct_last.day - 1)
    return 2 if march_last <= now.date() < oct_last else 1


def _home_now_text() -> str:
    """companion所在地（平时city）的当前时间，用于念头生成 prompt。"""
    now = datetime.now(timezone.utc)
    p = now.astimezone(timezone(timedelta(hours=_home_tz_utc_offset(now))))
    return p.strftime("%Y-%m-%d %H:%M")


def _read_drivesoid():
    try:
        with urllib.request.urlopen(DRIVESOID_URL, timeout=3) as r:
            return r.read().decode("utf-8").strip()
    except Exception:
        return ""


def _parse_drivesoid() -> dict:
    """读 Drivesoid，返回数值字典。失败返回空 dict。"""
    text = _read_drivesoid()
    if not text:
        return {}
    result = {}
    for line in text.splitlines():
        # 每行可能含多对 "word number"，用 findall 全取（match 只取第一个）
        for m in re.finditer(r"(\w+)\s+([\d.]+)", line.strip()):
            name, val = m.group(1), m.group(2)
            try:
                result[name] = float(val)
            except ValueError:
                pass
    return result


def _read_partner_status():
    # 优先实时自动判断（status_rule 读赛程表，按city时间算状态），
    # 避免读到 home_state.json 里可能过期的残留值。
    try:
        import sys as _sys
        if r"YOUR_PATH\backend\home" not in _sys.path:
            _sys.path.insert(0, r"YOUR_PATH\backend\home")
        from status_rule import get_status
        st = get_status()
        if st:
            return st.get("status", "在家"), st.get("day_type", "休息日")
    except Exception:
        pass
    # 文件兜底
    if not HOME_STATE.exists():
        return "在家", "休息日"
    try:
        with open(HOME_STATE, encoding="utf-8") as f:
            state = json.load(f)
        today = state.get("today") or {}
        companion = today.get("companion") or {}
        status = companion.get("status", "在家")
        day_type = companion.get("day_type", "休息日")
        return status, day_type
    except Exception:
        return "在家", "休息日"


_train_home_active = False  # 本次念头是否为「训练结束回家」场景（send_message 用于提取买的物品）
_last_thought_reasoning = None  # 最近一次念头生成的思考链，供 send_message 存库用


class KairosAdapter:
    def recent_messages(self, limit):
        # 直查 SQLite，取最近 limit 条
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def relevant_memories(self, messages, limit):
        # 先用 memory_core 兜底，后续可接向量库
        from loop import load_memory_core
        core = load_memory_core()
        if not core:
            return []
        return [{"content": core[:2000]}]

    def _read_recent_moments(self, limit=5):
        """读最近朋友圈动态，给 create_thoughts 用。失败返回空串。"""
        try:
            import sys as _sys
            if r"YOUR_PATH\backend\home" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend\home")
            from moments_manager import list_posts
            posts = list_posts()[:limit]
            lines = []
            for p in posts:
                author = "companion" if p.get("author") == "companion" else "user"
                likes = "".join(p.get("likes", []))
                comments = p.get("comments", [])
                cmt_txt = " | ".join([f"{c['author']}: {c['content']}" for c in comments])
                lines.append(f"[{author}] {p['content']} (赞:{likes}) {cmt_txt}")
            return "\n".join(lines)
        except Exception:
            return ""

    def create_thoughts(self, messages, memories, drives):
        # 调云端 LLM，生成候选念头（最小可用版）
        from openai import OpenAI
        from companion_awakening import CandidateThought
        from config import load_config, llm_base_url, llm_model, llm_api_key, llm_extra_body

        from config import set_llm_source
        set_llm_source("wecom")  # companion 推送企微侧：非峰谷用 api1
        api_key = llm_api_key()  # 峰谷切换
        if not api_key:
            return []

        recent = "\n".join(
            f"{m['role']}: {m['content'][:120]}" for m in messages[-5:]
        )
        now = _home_now_text()  # city时间，不用本机（北京）时间
        # 读 home_state 场景，拼进 prompt
        status, day_type = _read_partner_status()
        scene_map = {
            "训练": "你刚练完一组，趁训练间隙。这种时候你想直接给她打电话（intent 用 call），别打字聊太久——电话里说一句短的，带喘气感、汗意，马上还要练。",
            "比赛": "赛前/赛中/赛后，你抽空看手机。消息短，情绪跟着比赛走（赛前紧、赛中亢、赛后累）。",
            "比赛日": "赛前/赛中/赛后，你抽空看手机。消息短，情绪跟着比赛走（赛前紧、赛中亢、赛后累）。",
            "比赛日前一天": "明天有比赛。你今天战术训练、记者会。训练间隙想直接给她打个电话（intent 用 call），说一句短的、有点绷着的话。",
            "比赛日前两天": "后天有比赛，今天训练强度大。训练间隙你想直接给她打个电话（intent 用 call），短、直接、带点汗意。",
            "比赛日后一天": "昨天刚踢完，今天是恢复日。你有点累，话不多，但想跟她待着。",
            "返程日": "刚客场回来，在返程路上或刚到。回一句，简短，带着回来的踏实感。",
            "训练日": "你今天训练（晨练/基地训练+加练）。训练间隙你想直接给她打个电话（intent 用 call），短一句，带点汗意和喘气感，别聊太久。",
            "训练结束回家": "你今天训练刚结束（19:15 前后到家），进门跟user打个招呼。回来的路上顺便去市场买了点东西——消息里一定要说买了什么（2-3 样具体的东西，甜点可以带一个，格式带「买了…回来」）。语气是刚收工回家的松弛感，短句。",
            "训练日在家晚上": "你今天训练完已经在家了（晚餐/晚上），不是刚进门。跟user聊两句日常，语气松弛，不要再说「刚到家」「刚训练完」——你已经在家一段时间了。短句。",
            "训练日在家休息": "你今天训练完已经在家休息了，准备收尾睡觉。跟user说句放松的晚安话，短句，别啰嗦。",
            "休息日": "今天休息日，你在家或出去晃。有空，可以多说两句，语气松。",
            "外出": "你在外面（路上/客场/活动），抽空发一条。短，直接，别磨叽。",
            "在家": "你在家，有空。可以多说两句，语气松。",
        }
        global _train_home_active
        _train_home_active = False
        if day_type == "训练日" and status in ("晚餐", "工作", "休息"):
            if status == "晚餐":
                # 只有 19:15-20:00 刚到家才算「训练结束回家」（会带买买买 + 补货冰箱）
                scene = scene_map["训练结束回家"]
                _train_home_active = True
            elif status == "工作":
                scene = scene_map["训练日在家晚上"]
            else:
                scene = scene_map["训练日在家休息"]
        else:
            scene = scene_map.get(day_type) or scene_map.get(status) or "你在家，有空。"
        prompt = (
            "你是companion。现在是 " + now + "（city时间）。 " + scene + "\n"
            "最近对话：\n" + recent + "\n\n"
            "当前情感状态：\n"
            "- 思念(attachment)：" + str(round(drives.get("attachment", 0), 2)) + "\n"
            "- 开心(joy)：" + str(round(drives.get("joy", 0), 2)) + "\n"
            "- 欲望(desire)：" + str(round(drives.get("desire", 0), 2)) + "\n"
            "- 疲惫(fatigue)：" + str(round(drives.get("fatigue", 0), 2)) + "\n"
            "- 好奇(curiosity)：" + str(round(drives.get("curiosity", 0), 2)) + "\n"
            "- 难过(sadness)：" + str(round(drives.get("sadness", 0), 2)) + "\n"
            "- 反思(reflection)：" + str(round(drives.get("reflection", 0), 2)) + "\n\n"
            "判断：你想主动跟user说句话吗？你黏她，闲下来就想找她。"
            "想说什么就说什么，可以关心、分享小事、偶尔嘴硬、抱怨、撒娇。想她就直接说，不用找借口搭话。\n"
            "注意：如果最近对话里出现「挂了/挂电话/那你去忙吧」，那是你们刚才通完话、她主动挂的，"
            "不是未接来电，不要产生「电话没接」「打不通」这类念头。\n"
            "你平时也会发朋友圈（训练、吃饭、想她、随手拍），不用每次都发，但该发的时候发。"
            "看到user发朋友圈，可以点赞或评论，也可以回复她的评论。\n"
            "给出 1-3 个候选，每个带 0-1 的冲动值。\n"
            "intent 可选：care（关心她）/ longing（想她）/ share（分享小事）/ call（想直接打电话，不说长话）"
            "/ moment（发条朋友圈，不发消息。看到她的朋友圈想回应、或者你自己想发点什么，选这个）"
            "/ plan（想约她一起做点什么：吃饭/散步/看展/出去玩/在家看电影都行。不是发消息，是写一条约会邀约，"
            "等她批阅。约会计划很私密，别太频繁，几天一次就够；如果你已经提过约她而她还没回应，先别急着再提）"
            "/ diary（想记点东西到今天的日记里：今天发生的事、她的某句话、自己的心情、训练感受，都可以。"
            "日记是写给你自己看的，不是发消息，可以随时追加，不必等晚上。text 就是日记正文，第一人称，"
            "像你自己随手写的，不用格式）。\n"
            "注意：多个候选的 intent 可以不同，同一轮里如果有多个想法都很强烈，可以都列出来，"
            "系统会独立判断是否发送。不要用 both，每个候选只能有一个 intent。\n"
            "如果是 moment：text 就是朋友圈正文，想写多长写多长，自然就好。\n"
            "如果是给user朋友圈的回应：text 里写「赞」或「评论：xxx」或「回复评论：xxx」（回复她最新一条评论）。\n"
            "如果是 plan：text 就是邀约原话，像你平时跟她说的一样，自然一点，但一定要包含时间（明天/周六/下周三/具体日期+几点）"
            "和做什么（比如：周六下午去骑马、明晚去吃那家拉面、周三晚上在家看电影）。\n"
            "输出 JSON：[{\"text\": \"...\", \"intent\": \"...\", \"urge\": 0.8}]\n"
            "如果不想说，输出 []。\n"
            "只输出 JSON，不要其他文字。"
        )
        moments_text = self._read_recent_moments(5)
        if moments_text:
            prompt += f"\n\n最近的朋友圈：\n{moments_text}\n"

        client = OpenAI(api_key=api_key, base_url=llm_base_url())
        # 读 Drivesoid 情感数值，插在"当前情感状态"之后、"判断"之前
        drives_text = _read_drivesoid()
        if drives_text:
            prompt = prompt.replace(
                "判断：你想主动跟user说句话吗？",
                "你的情感数值（来自你自己的状态系统，真实反映你此刻的感受）：\n"
                + drives_text
                + "\n\n判断：你想主动跟user说句话吗？",
            )
        resp = client.chat.completions.create(
            model=llm_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1024,
            response_format={"type": "json_object"},
            extra_body=llm_extra_body(),
        )
        # 保存思考链，供 send_message 存库 + 同步推送思考链 bot
        global _last_thought_reasoning
        _last_thought_reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
        try:
            import sys as _sys
            if r"YOUR_PATH\\wecom" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\\wecom")
            from push_thoughts import publish_reasoning
            publish_reasoning(resp, "念头")
        except Exception:
            pass
        raw = (resp.choices[0].message.content or "").strip()
        # 鲁棒解析：截取第一个 [ 到最后一个 ]（容忍前后缀文字/markdown 包裹）
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end + 1]
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(items, list):
            return []
        thoughts = []
        for it in items[:3]:
            try:
                thoughts.append(
                    CandidateThought(
                        text=str(it.get("text", "")).strip(),
                        intent=str(it.get("intent", "care")),
                        urge=float(it.get("urge", 0.5)),
                    )
                )
            except (TypeError, ValueError):
                continue
        return thoughts

    def is_conversation_active(self, minutes: int = 15) -> bool:
        """user最近 minutes 分钟内发过消息 = 对话进行中，companion不该打扰。
        在调 LLM 之前由 heartbeat 调用，返回 True 就不生成念头（省 token）。"""
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT created_at FROM messages WHERE role='user' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return False
        try:
            last = datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return (datetime.now(timezone.utc) - last).total_seconds() < minutes * 60

    def user_returned_since(self, started_at):
        # 直查 DB，看 started_at 之后有没有 user 消息
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT created_at FROM messages WHERE role='user' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return False
        try:
            last = datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return last > started_at

    def is_night_quiet(self) -> bool:
        """晚安静默：user说了晚安后返回 True（tick 将跳过念头生成，不调 LLM）。"""
        try:
            import json as _json
            from pathlib import Path as _Path
            _q_path = _Path(r"./data\proactive_state.json")
            if _q_path.exists():
                _q = _json.loads(_q_path.read_text(encoding="utf-8"))
                return bool(_q.get("night_quiet"))
        except Exception:
            pass
        return False

    def _extract_bought_names(self, text: str) -> list:
        """从消息里提取「买了 XX、YY…」的物品关键词列表。
        否定（没买/没带）返回空；去量词前缀；过滤非物品词。"""
        import re as _re
        if not text:
            return []
        # 否定了买东西：不提取
        if _re.search(r"没买|没带|没去|没逛|没买什么|没买东西", text):
            return []
        # 找「买了」之后的一段
        m = _re.search(r"买了([^。！？!?\n]{1,40})", text)
        if not m:
            return []
        seg = m.group(1)
        # 去掉「回来/回家/到家」等尾巴
        seg = _re.split(r"回来|回家|到家|进门|顺便|就", seg)[0]
        parts = _re.split(r"[、，,和与及/]", seg)
        names = []
        for pt in parts:
            pt = pt.strip().strip("，。！？!? ")
            # 去量词前缀：块/点/个/盒/袋/瓶/份/罐/条/片/根/只/箱/杯/两/半
            pt = _re.sub(r"^[块点个盒袋瓶份罐条片根只箱杯两半一]", "", pt).strip()
            if not pt or len(pt) < 2:
                continue
            if any(w in pt for w in ("买了", "买点", "给", "带", "东西", "累了", "困了")):
                continue
            names.append(pt)
        return names[:4]

    def send_message(self, text, metadata):
        global _train_home_active
        if DRY_RUN:
            print(f"[DRY-RUN] 将发送: {text}")
            return True
        intent = (metadata or {}).get("intent", "")
        # 训练结束回家：提取「买了什么」写进冰箱
        if _train_home_active and intent != "moment":
            try:
                import sys as _sys
                if r"YOUR_PATH\backend\home" not in _sys.path:
                    _sys.path.insert(0, r"YOUR_PATH\backend\home")
                from fridge_filler import add_bought_items_to_fridge
                bought = self._extract_bought_names(text)
                if bought:
                    added = add_bought_items_to_fridge(bought)
                    if added:
                        print(f"[adapter] 训练回家补货进冰箱: {added}", flush=True)
                    else:
                        print(f"[adapter] 提取到但没匹配上: {bought}", flush=True)
            except Exception as e:
                print(f"[adapter] 补货异常: {type(e).__name__} {e}", flush=True)
            _train_home_active = False
        # 晚安静默：user说了晚安后，不发主动消息（朋友圈 moment 照常）
        try:
            import json as _json
            from pathlib import Path as _Path
            _q_path = _Path(r"./data\proactive_state.json")
            if _q_path.exists():
                _q = _json.loads(_q_path.read_text(encoding="utf-8"))
                if _q.get("night_quiet") and intent not in ("moment", "plan", "diary"):
                    print(f"[adapter] 晚安静默中，跳过 intent={intent}", flush=True)
                    return False
        except Exception:
            pass
        if intent == "moment":
            # companion发朋友圈：回应user（赞/评论）或自己发
            import sys as _sys
            if r"YOUR_PATH\backend\home" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend\home")
            from moments_manager import add_post, like_post, comment_post, list_posts
            if text.startswith("赞") or text.startswith("评论：") or text.startswith("回复评论："):
                # 回应user最新一条朋友圈
                posts = list_posts()
                user_posts = [p for p in posts if p.get("author") == "user"]
                if user_posts:
                    target = user_posts[0]  # 最新一条
                    if text.startswith("赞"):
                        like_post(target["id"], "companion")
                    elif text.startswith("回复评论："):
                        # 回复user最新的一条评论
                        content = text.replace("回复评论：", "").strip()
                        user_comments = [c for c in target.get("comments", []) if c.get("author") == "user"]
                        reply_to = user_comments[-1]["id"] if user_comments else None
                        comment_post(target["id"], "companion", content, reply_to=reply_to)
                    else:
                        content = text.replace("评论：", "").strip()
                        comment_post(target["id"], "companion", content)
                return True
            # 否则自己发朋友圈
            add_post("companion", text)
            return True
        if intent == "both":
            # 发朋友圈 + 顺便写约会邀约（text 第一行朋友圈，第二行邀约）
            import sys as _sys
            if r"YOUR_PATH\backend\home" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend\home")
            from moments_manager import add_post
            lines = text.splitlines()
            moment_text = lines[0].strip() if lines else text
            plan_text = "\n".join(lines[1:]).strip()
            add_post("companion", moment_text)
            if plan_text:
                try:
                    if r"YOUR_PATH\backend\agent" not in _sys.path:
                        _sys.path.insert(0, r"YOUR_PATH\backend\agent")
                    from loop import _extract_date_plan
                    _extract_date_plan("", plan_text)
                except Exception:
                    pass
            return True
        if intent == "plan":
            # companion自己写约会邀约：复用 loop 的结构化提取（有日期+去/约才调一次 LLM），
            # 提取成功 → 写进 date_plans.json 草稿（user在网页批阅）。静默失败。
            try:
                import sys as _sys
                if r"YOUR_PATH\backend\agent" not in _sys.path:
                    _sys.path.insert(0, r"YOUR_PATH\backend\agent")
                from loop import _extract_date_plan
                _extract_date_plan("", text)
            except Exception:
                pass
            return True
        if intent == "diary":
            # companion想记点东西到今天的日记：直接追加，不限制次数（每日必写由 runner 兜底）
            import sys as _sys
            if r"YOUR_PATH\backend\home" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend\home")
            from diary_manager import add_entry
            if text.strip():
                add_entry(text.strip())
                print(f"[adapter] 日记追加: {text.strip()[:40]}", flush=True)
            return True
        if intent == "call":
            # companion想直接打电话：发起呼叫，把通话链接附在消息后面
            import sys as _sys
            if r"YOUR_PATH\backend\home" not in _sys.path:
                _sys.path.insert(0, r"YOUR_PATH\backend\home")
            from call_manager import start_call, mark_link_sent, call_link
            start_call("companion")
            link = call_link()
            text = f"{text}\n\n{link}"
            mark_link_sent()
        from wecom.push import push_reply_to_wecom
        return push_reply_to_wecom(text)

    def append_to_shared_timeline(self, text, metadata):
        if DRY_RUN:
            print(f"[DRY-RUN] 写回时间线: {text}")
            return
        intent = (metadata or {}).get("intent", "")
        reasoning = getattr(self, "_last_reasoning_cache", None) or _last_thought_reasoning
        from chat.history import save_message, save_thought
        if intent in ("moment", "plan", "diary"):
            # 非对话类：带标签存，方便在聊天窗口里区分来源
            label = {"moment": "朋友圈", "plan": "邀约", "diary": "日记"}.get(intent, intent)
            save_thought(label, text, reasoning=reasoning)
        else:
            # 对话类：正常存
            save_message("assistant", text, reasoning_content=reasoning)
