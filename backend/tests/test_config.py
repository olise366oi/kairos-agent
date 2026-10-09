"""config.py 测试——配置读写 + 峰谷定价判断 + 线程局部来源。

覆盖策略：
- 纯函数（is_deepseek_peak_hour）：now 参数可注入，无文件 IO
- 线程局部状态（set/get_llm_source）：单线程内验证
- 文件 IO（load/save_config）：用 tmp_path 隔离

conftest 已把 HOME 重定向到临时目录，本测试再用 tmp_path 进一步隔离。
"""
import json
from datetime import datetime, timezone, timedelta

import pytest

import config


# ========== fixtures ==========

@pytest.fixture
def isolated_config_path(tmp_path, monkeypatch):
    """把 config.DATA_DIR / CONFIG_PATH 指向 tmp_path，隔离文件系统。"""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    return tmp_path / "config.json"


@pytest.fixture(autouse=True)
def reset_llm_source():
    """每个测试前把线程局部 source 重置为默认值。"""
    config.set_llm_source("web")
    yield
    config.set_llm_source("web")


# ========== is_deepseek_peak_hour ==========
# 高峰：周一至周五，北京时间 9:00-12:00 或 14:00-18:00
# 判断方式：转北京时间后再看 weekday 和 hour

def _bj_dt(year, month, day, hour, minute=0):
    """构造一个北京时间，转为 UTC datetime 传入函数。

    北京时间 = UTC+8，所以 UTC 时间 = 北京时间 - 8h。
    """
    bj = datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=8)))
    return bj.astimezone(timezone.utc)


def test_peak_monday_morning():
    """周一上午 10 点（北京）→ 高峰。2026-10-12 是周一。"""
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 10)) is True


def test_peak_monday_afternoon():
    """周一下午 15 点（北京）→ 高峰。"""
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 15)) is True


def test_off_peak_noon_gap():
    """工作日 12:00-14:00 之间的午休时段 → 闲时。"""
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 12, 30)) is False
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 13, 59)) is False


def test_off_peak_night():
    """工作日晚间 22 点 → 闲时。"""
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 22)) is False


def test_off_peak_early_morning():
    """工作日早上 8 点 → 闲时（早于 9 点）。"""
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 8)) is False


def test_boundary_9am():
    """9:00 是高峰起点，8:59 不是。"""
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 9, 0)) is True
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 8, 59)) is False


def test_boundary_12pm():
    """12:00 不在高峰内（半开区间 [9, 12)）。"""
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 11, 59)) is True
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 12, 12, 0)) is False


def test_off_peak_weekend():
    """周末任何时间都是闲时。2026-10-10 是周六。"""
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 10, 10)) is False
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 10, 15)) is False
    assert config.is_deepseek_peak_hour(_bj_dt(2026, 10, 11, 10)) is False  # 周日


# ========== set_llm_source / get_llm_source ==========

def test_default_llm_source():
    """默认 source 是 web。"""
    config.set_llm_source("web")
    assert config.get_llm_source() == "web"


def test_set_llm_source_wecom():
    """设置为 wecom 后能读回。"""
    config.set_llm_source("wecom")
    assert config.get_llm_source() == "wecom"


def test_set_llm_source_switch():
    """连续切换 source 都能正确读取。"""
    config.set_llm_source("wecom")
    assert config.get_llm_source() == "wecom"
    config.set_llm_source("web")
    assert config.get_llm_source() == "web"


# ========== load_config / save_config ==========

def test_load_config_missing_file(isolated_config_path):
    """config.json 不存在时，返回空 dict。"""
    assert config.load_config() == {}


def test_save_then_load_round_trip(isolated_config_path):
    """保存后再读取，内容一致。"""
    data = {"api_key": "sk-test", "model": "deepseek-chat", "peak_enabled": True}
    config.save_config(data)
    assert config.load_config() == data


def test_save_config_creates_file(isolated_config_path):
    """save_config 应真正创建文件。"""
    config.save_config({"k": "v"})
    assert isolated_config_path.exists()
    raw = isolated_config_path.read_text(encoding="utf-8")
    assert json.loads(raw) == {"k": "v"}


def test_save_config_utf8_chinese(isolated_config_path):
    """中文值应正确保存（ensure_ascii=False）。"""
    config.save_config({"name": "小助手"})
    raw = isolated_config_path.read_text(encoding="utf-8")
    assert "小助手" in raw
    assert config.load_config()["name"] == "小助手"


def test_load_config_corrupt_json_raises(isolated_config_path):
    """损坏的 JSON 应抛异常（当前实现没有容错，测试锁定这一行为）。"""
    isolated_config_path.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        config.load_config()
