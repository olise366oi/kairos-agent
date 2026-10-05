# -*- coding: utf-8 -*-
"""三 API 峰谷切换配置。

API 1 = DeepSeek 官方（主配置 api_key/base_url/model），人民币余额，兜底。
API 2 = ark 2 号（非峰谷·网页端），50w token，本地累计用完回退 API 1。
API 3 = ark 3 号（峰段·全部端口），50w 总量 + 每日 200w。
来源：网页端 web / 企微 wecom（线程局部，默认 web）。
"""
import json
import os
import threading
from pathlib import Path

DATA_DIR = Path.home() / ".kairos"
CONFIG_PATH = DATA_DIR / "config.json"
PERSONA_PATH = DATA_DIR / "persona.md"
AVATAR_PATH = DATA_DIR / "avatar.png"

# 目标时区（任意 IANA 时区，默认 UTC；状态/日程/天气均按此计算）
TIMEZONE = os.getenv("APP_TIMEZONE", "UTC")

# 线程局部：当前 LLM 调用来源（web / wecom），默认 web
_SOURCE = threading.local()


def set_llm_source(source: str) -> None:
    """设置当前线程的 LLM 调用来源（web=网页端 / wecom=企微）。"""
    _SOURCE.source = source


def get_llm_source() -> str:
    return getattr(_SOURCE, "source", "web")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_data_dir()
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_config(config: dict) -> None:
    ensure_data_dir()
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def is_configured() -> bool:
    """Return True if the user has completed initial setup."""
    config = load_config()
    if not (config.get("api_key") and config.get("name")):
        return False
    # persona 可能写在 config.json 或 persona.md 中
    if config.get("persona"):
        return True
    return PERSONA_PATH.exists()


def is_deepseek_peak_hour(now=None) -> bool:
    """DeepSeek 官方峰谷定价（2026-08-17 生效）：
    高峰 = 周一至周五 北京时间 9:00-12:00、14:00-18:00；
    其余（周六日、夜间）为闲时。节假日未单独处理。
    """
    from datetime import datetime, timezone, timedelta
    now = now or datetime.now(timezone.utc)
    bj = now.astimezone(timezone(timedelta(hours=8)))
    if bj.weekday() >= 5:  # 周六、周日
        return False
    h = bj.hour
    return (9 <= h < 12) or (14 <= h < 18)


def _api2_remaining(cfg: dict) -> int:
    """2 号剩余额度 = 50w - 本地累计已用。"""
    try:
        from api_usage import total_usage
        quota = int(cfg.get("ark2_quota", 500000))
        return max(0, quota - total_usage("api2"))
    except Exception:
        return 0


def effective_config(source: str | None = None) -> dict:
    """按峰谷 + 来源返回当前生效的 LLM 配置（含 key_id）。"""
    cfg = load_config()
    src = source or get_llm_source()

    if cfg.get("peak_enabled") and is_deepseek_peak_hour():
        # 峰段 → 3 号 ark（全部端口）
        if cfg.get("ark3_api_key"):
            return {
                "key_id": "api3",
                "api_key": cfg["ark3_api_key"],
                "base_url": cfg.get("ark3_base_url", "https://ark.cn-beijing.volces.com/api/v3"),
                "model": cfg.get("ark3_model", "deepseek-v4-flash-ga-260731"),
            }
    elif src == "web":
        # 非峰谷·网页端 → 2 号 ark（50w 用完回退 3 号 ark → 最后才兜底 1 号）
        if cfg.get("ark2_api_key") and _api2_remaining(cfg) > 0:
            return {
                "key_id": "api2",
                "api_key": cfg["ark2_api_key"],
                "base_url": cfg.get("ark2_base_url", "https://ark.cn-beijing.volces.com/api/v3"),
                "model": cfg.get("ark2_model", "deepseek-v4-1-flash-260910"),
            }
        # api2 超额 → 3 号 ark（有 key 就用）
        if cfg.get("ark3_api_key"):
            return {
                "key_id": "api3",
                "api_key": cfg["ark3_api_key"],
                "base_url": cfg.get("ark3_base_url", "https://ark.cn-beijing.volces.com/api/v3"),
                "model": cfg.get("ark3_model", "deepseek-v4-flash-ga-260731"),
            }

    # 兜底 → 1 号 DeepSeek 官方
    return {
        "key_id": "api1",
        "api_key": cfg.get("api_key", ""),
        "base_url": cfg.get("base_url", "https://api.deepseek.com/v1"),
        "model": cfg.get("model", "deepseek-chat"),
    }


def llm_model() -> str:
    """按峰谷/来源读取对话模型名，缺省回退 deepseek-chat。"""
    return effective_config().get("model", "deepseek-chat")


def llm_base_url() -> str:
    """按峰谷/来源读取 API base_url，缺省回退 DeepSeek 官方地址。"""
    return effective_config().get("base_url", "https://api.deepseek.com/v1")


def llm_api_key() -> str:
    """按峰谷/来源读取当前生效的 API Key。"""
    return effective_config().get("api_key", "")


def llm_key_id() -> str:
    """当前生效的 API 标识（api1 / api2 / api3），用于本地用量统计。"""
    return effective_config().get("key_id", "api1")


def get_thinking_enabled() -> bool:
    """深度思考总开关（三个 API 统一）。默认关闭。"""
    return bool(load_config().get("thinking_enabled", False))


def set_thinking_enabled(enabled: bool) -> None:
    cfg = load_config()
    cfg["thinking_enabled"] = bool(enabled)
    save_config(cfg)


def llm_extra_body() -> dict:
    """传给 chat.completions.create 的 extra_body：深度思考开关。
    True = 三个 API 都开启深度思考；False = 都关闭。"""
    return {"thinking": {"type": "enabled" if get_thinking_enabled() else "disabled"}}
