import sys
import time

sys.path.insert(0, r"YOUR_PATH\backend\proactive")
sys.path.insert(0, r"YOUR_PATH\backend\companion_awakening")

from companion_awakening import AwakeningService, AwakeningConfig
from adapter import ReunionAdapter, _parse_drivesoid

DRIVESOID_MAP = {
    "longing": "attachment",
    "intimacy": "joy",
    "lust": "desire",
    "anxiety": "sadness",
    "curiosity": "curiosity",
    "fatigue": "fatigue",
}


def sync_drivesoid_to_engine(engine, alpha=0.4):
    d = _parse_drivesoid()
    if not d:
        return
    for src, dst in DRIVESOID_MAP.items():
        if src in d and hasattr(engine.state, dst):
            old = getattr(engine.state, dst)
            new = (1 - alpha) * old + alpha * d[src]
            setattr(engine.state, dst, max(0.0, min(1.0, new)))


service = AwakeningService(
    adapter=ReunionAdapter(),
    state_dir=r"YOUR_PATH\backend\proactive\state",
    # 想了就全发：发送门槛去掉（speak_threshold=0），生成念头就发；
    # think_threshold 保留（控制思考频率，避免每 60 秒烧一次 token）
    config=AwakeningConfig(enabled=True, think_threshold=0.15, speak_threshold=0.0),
)

_last_watch_attempt = 0.0

print("[proactive] 心跳循环启动", flush=True)
while True:
    try:
        # 看球：companion在家工作（复盘比赛）时发起，每 30 分钟左右判断一次
        try:
            import sys as _sys2
            _sys2.path.insert(0, r"YOUR_PATH\backend\home")
            from watch_manager import get_state as _ws, start_watch, fetch_recent_finished_fixture, LINK
            from wecom.push import push_reply_to_wecom
            import json as _json, pathlib as _pl
            try:
                _hs = _json.loads(_pl.Path(r"./data\home_state.json").read_text(encoding="utf-8"))
                _status = (_hs.get("today") or {}).get("companion", {}).get("status", "")
            except Exception:
                _status = ""
            _ws_ = _ws()
            _busy = bool(_ws_.get("fixture_id")) and not _ws_.get("ended")
            if _status == "在家工作" and not _busy and (time.time() - _last_watch_attempt > 1800):
                _last_watch_attempt = time.time()
                _info = fetch_recent_finished_fixture()
                if _info:
                    start_watch(_info["fixture_id"], _info["home_team"], _info["away_team"], _info["events"])
                    push_reply_to_wecom(f"companion：来，一起复盘刚那场 {_info['home_team']} vs {_info['away_team']}。{LINK}")
                    print(f"[proactive] companion发起看球 {_info['home_team']} vs {_info['away_team']}", flush=True)
        except Exception as e:
            print(f"[proactive] 看球发起出错：{e}", flush=True)

        # 每日日记：city时间 22:00 后每天必须写（今天还没写就写第一篇）；
        # 之后companion在念头引擎里想继续记/补充今天的日记，会走 adapter 的 diary intent 随时追加，不限制次数。
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            import sys as _sysz
            _sysz.path.insert(0, r"YOUR_PATH\backend")
            from config import TIMEZONE
            now_p = datetime.now(ZoneInfo(TIMEZONE))
            import sys as _sys
            _sys.path.insert(0, r"YOUR_PATH\backend\home")
            from diary_manager import has_today, add_entry
            if now_p.hour >= 22 and not has_today():
                # 调 loop.chat 生成日记（仅保证"每天必须写"）
                _sys.path.insert(0, r"YOUR_PATH\backend")
                _sys.path.insert(0, r"YOUR_PATH\backend\agent")
                from loop import chat as loop_chat, load_config
                from chat.history import save_thought
                api_key = load_config().get("api_key", "")
                prompt = "写一篇今天的日记，第一人称，像 companion 自己写的。短，几句话说清楚今天。直接写 user，不要用「用户」这类称呼。"
                diary_text, diary_reasoning = loop_chat(prompt, api_key, return_reasoning=True)
                if diary_text:
                    add_entry(diary_text)
                    save_thought("日记", diary_text, reasoning=diary_reasoning)
                    print(f"[proactive] 日记已写 {now_p.strftime('%H:%M')}", flush=True)
        except Exception as e:
            print(f"[proactive] 日记触发出错：{e}", flush=True)

        # 赛果通知：match_results 有未通知的赛果 → companion生成赛后消息推给user。
        # 兜底：定时任务（每日补录）触发时豆包会直接调 notify_latest；这里每轮心跳
        # 再检查一次，定时任务漏了也会补。
        try:
            import sys as _sys3
            if r"YOUR_PATH\backend\home" not in _sys3.path:
                _sys3.path.insert(0, r"YOUR_PATH\backend\home")
            from match_news import unnotified_latest, notify_latest
            if unnotified_latest():
                _nr = notify_latest()
                if _nr.get("ok"):
                    print(f"[proactive] 赛果通知已发: {_nr.get('message','')[:60]}", flush=True)
                else:
                    print(f"[proactive] 赛果通知失败: {_nr.get('reason','')}", flush=True)
        except Exception as e:
            print(f"[proactive] 赛果通知出错：{e}", flush=True)

        sync_drivesoid_to_engine(service.engine)
        result = service.tick()
        print(f"[proactive] {time.strftime('%H:%M:%S')} {result}", flush=True)
        wait_min = result.get("next_wake_minutes", 30)
    except Exception as e:
        print(f"[proactive] 出错：{e}", flush=True)
        wait_min = 10
    time.sleep(max(60, wait_min * 60))
