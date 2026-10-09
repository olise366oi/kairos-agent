"""loop.py 纯函数测试——不依赖外部服务。

依赖 conftest.py 里对 openai/rag/chat 等模块的 stub，
使 import agent.loop 能成功。
"""
from datetime import datetime, timezone

from agent.loop import (
    _home_tz_utc_offset,
    _is_winter,
    _parse_away_events,
    _looks_like_date_plan,
)


# ========== 导入验证 ==========

def test_import_ok():
    """验证 4 个纯函数能正常导入（stub 是否生效的关键验证）。"""
    assert _home_tz_utc_offset is not None
    assert _is_winter is not None
    assert _parse_away_events is not None
    assert _looks_like_date_plan is not None


# ========== _home_tz_utc_offset ==========

def test_utc_offset_winter_january():
    """1 月是冬令时，返回 1。"""
    dt = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert _home_tz_utc_offset(dt) == 1


def test_utc_offset_summer_july():
    """7 月是夏令时，返回 2。"""
    dt = datetime(2026, 7, 15, tzinfo=timezone.utc)
    assert _home_tz_utc_offset(dt) == 2


def test_utc_offset_dst_start_boundary():
    """夏令时起始边界：3 月最后一个周日（2026-03-29）起为夏令时。"""
    before = datetime(2026, 3, 28, tzinfo=timezone.utc)
    on_day = datetime(2026, 3, 29, tzinfo=timezone.utc)
    assert _home_tz_utc_offset(before) == 1
    assert _home_tz_utc_offset(on_day) == 2


def test_utc_offset_dst_end_boundary():
    """夏令时结束边界：10 月最后一个周日（2026-10-25）起为冬令时。"""
    before = datetime(2026, 10, 24, tzinfo=timezone.utc)
    on_day = datetime(2026, 10, 25, tzinfo=timezone.utc)
    assert _home_tz_utc_offset(before) == 2
    assert _home_tz_utc_offset(on_day) == 1


# ========== _is_winter ==========

def test_is_winter_true():
    """1 月是冬天。"""
    dt = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert _is_winter(dt) is True


def test_is_winter_false():
    """7 月不是冬天。"""
    dt = datetime(2026, 7, 15, tzinfo=timezone.utc)
    assert _is_winter(dt) is False


# ========== _parse_away_events ==========

def test_parse_away_events_basic():
    """标准格式：'X vs Y 客场 当地时间M月D日'。"""
    text = "曼城 vs 利物浦 客场 当地时间3月15日"
    events = _parse_away_events(text)
    assert len(events) == 1
    assert events[0] == {"month": 3, "day": 15, "city": "曼城"}


def test_parse_away_events_no_away_keyword():
    """没有'客场'关键词的行应被跳过。"""
    text = "曼城 vs 利物浦 主场 当地时间3月15日"
    assert _parse_away_events(text) == []


def test_parse_away_events_no_vs():
    """没有' vs '的行应被跳过。"""
    text = "曼城 客场 当地时间3月15日"
    assert _parse_away_events(text) == []


def test_parse_away_events_local_date_priority():
    """'当地时间X月X日'优先于普通日期。"""
    text = "曼城 vs 利物浦 客场 4月20日 当地时间3月15日"
    events = _parse_away_events(text)
    assert len(events) == 1
    assert events[0]["month"] == 3
    assert events[0]["day"] == 15


def test_parse_away_events_fallback_date():
    """没有'当地时间'前缀时用普通日期。"""
    text = "曼城 vs 利物浦 客场 3月15日"
    events = _parse_away_events(text)
    assert len(events) == 1
    assert events[0] == {"month": 3, "day": 15, "city": "曼城"}


def test_parse_away_events_empty():
    """空输入返回空列表。"""
    assert _parse_away_events("") == []


def test_parse_away_events_multiple():
    """多行输入：只提取含'客场'的行。"""
    text = (
        "曼城 vs 利物浦 客场 当地时间3月15日\n"
        "阿斯顿维拉 vs 阿森纳 主场 当地时间4月1日\n"
        "比利亚雷亚尔 vs 皇马 客场 当地时间5月20日"
    )
    events = _parse_away_events(text)
    assert len(events) == 2
    assert events[0]["city"] == "曼城"
    assert events[1]["city"] == "比利亚雷亚尔"


# ========== _looks_like_date_plan ==========

def test_date_plan_with_date_and_action():
    """有日期 + 有行动词 → True。"""
    assert _looks_like_date_plan("明天一起去吃饭") is True


def test_date_plan_date_only():
    """只有日期没有行动词 → False。"""
    assert _looks_like_date_plan("明天天气不错") is False


def test_date_plan_action_only():
    """只有行动词没有日期 → False。"""
    assert _looks_like_date_plan("我们去吧") is False


def test_date_plan_empty():
    """空字符串 → False。"""
    assert _looks_like_date_plan("") is False


def test_date_plan_weekend_plan():
    """周末 + 带你去 → True。"""
    assert _looks_like_date_plan("周末带你去逛展") is True


def test_date_plan_no_signal():
    """无日期无行动词 → False。"""
    assert _looks_like_date_plan("今天心情不错") is False
