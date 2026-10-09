"""effective_config 测试——三路 API 路由逻辑。

effective_config 是项目成本控制的核心：按峰谷时段 + 请求来源 + 剩余额度，
决定走 DeepSeek 官方（api1）/ ark2 免费池（api2）/ ark3（api3）。

测试策略：mock 掉三个依赖（load_config / is_deepseek_peak_hour / _api2_remaining），
使每个分支的判断条件可控，逐个分支验证路由结果。
"""
import pytest

import config


# ========== fixtures ==========

@pytest.fixture
def mock_deps(monkeypatch):
    """返回一个 setter，用于设置 effective_config 的三个依赖。

    用法：mock_deps(cfg={...}, is_peak=True, api2_remaining=1000)
    """
    def _set(cfg=None, is_peak=False, api2_remaining=0):
        monkeypatch.setattr(config, "load_config", lambda: cfg or {})
        monkeypatch.setattr(config, "is_deepseek_peak_hour", lambda *a, **kw: is_peak)
        monkeypatch.setattr(config, "_api2_remaining", lambda c: api2_remaining)
    return _set


# ========== 分支 1：峰谷 → api3 ==========

def test_peak_hour_prefers_api3(mock_deps):
    """峰谷时段 + peak_enabled + ark3 有 key → api3。"""
    mock_deps(
        cfg={"peak_enabled": True, "ark3_api_key": "ark3-key"},
        is_peak=True,
    )
    result = config.effective_config(source="web")
    assert result["key_id"] == "api3"
    assert result["api_key"] == "ark3-key"


def test_peak_hour_no_ark3_falls_through_to_api1(mock_deps):
    """峰谷 + peak_enabled 但没 ark3 key → 跳过 elif 直接兜底 api1。

    这是容易忽略的边界：if 分支进入后没 return，elif 不会被评估。
    """
    mock_deps(
        cfg={"peak_enabled": True, "ark2_api_key": "ark2-key", "ark3_api_key": None},
        is_peak=True,
        api2_remaining=99999,
    )
    result = config.effective_config(source="web")
    assert result["key_id"] == "api1"


# ========== 分支 2：web 非峰谷 → api2 ==========

def test_web_non_peak_uses_api2(mock_deps):
    """非峰谷 + web 来源 + api2 有额度 → api2。"""
    mock_deps(
        cfg={"peak_enabled": False, "ark2_api_key": "ark2-key"},
        is_peak=False,
        api2_remaining=1000,
    )
    result = config.effective_config(source="web")
    assert result["key_id"] == "api2"
    assert result["api_key"] == "ark2-key"


def test_web_peak_disabled_uses_api2(mock_deps):
    """peak_enabled=False 时即便在峰段，也走 web 分支（api2）。"""
    mock_deps(
        cfg={"peak_enabled": False, "ark2_api_key": "ark2-key"},
        is_peak=True,
        api2_remaining=1000,
    )
    result = config.effective_config(source="web")
    assert result["key_id"] == "api2"


# ========== 分支 3：web api2 用尽 → api3 ==========

def test_web_api2_exhausted_uses_api3(mock_deps):
    """非峰谷 + web + api2 额度=0 + ark3 有 key → 回退 api3。"""
    mock_deps(
        cfg={"peak_enabled": False, "ark2_api_key": "ark2-key", "ark3_api_key": "ark3-key"},
        is_peak=False,
        api2_remaining=0,
    )
    result = config.effective_config(source="web")
    assert result["key_id"] == "api3"
    assert result["api_key"] == "ark3-key"


def test_web_no_api2_key_uses_api3(mock_deps):
    """非峰谷 + web + 没有 api2 key + ark3 有 key → 走 api3。"""
    mock_deps(
        cfg={"peak_enabled": False, "ark3_api_key": "ark3-key"},
        is_peak=False,
        api2_remaining=99999,
    )
    result = config.effective_config(source="web")
    assert result["key_id"] == "api3"


# ========== 分支 4：兜底 api1 ==========

def test_web_api2_exhausted_no_api3_uses_api1(mock_deps):
    """api2 用尽 + 没 api3 → 兜底 api1。"""
    mock_deps(
        cfg={"peak_enabled": False, "ark2_api_key": "ark2-key"},
        is_peak=False,
        api2_remaining=0,
    )
    result = config.effective_config(source="web")
    assert result["key_id"] == "api1"


def test_wecom_source_skips_api2_and_api3(mock_deps):
    """wecom 来源跳过 web 分支——即便 ark2/ark3 有 key 也走 api1。"""
    mock_deps(
        cfg={"peak_enabled": False, "ark2_api_key": "ark2-key", "ark3_api_key": "ark3-key"},
        is_peak=False,
        api2_remaining=99999,
    )
    result = config.effective_config(source="wecom")
    assert result["key_id"] == "api1"


def test_empty_config_returns_api1_defaults(mock_deps):
    """空配置 → api1 + 默认 base_url / model。"""
    mock_deps(cfg={}, is_peak=False)
    result = config.effective_config(source="web")
    assert result["key_id"] == "api1"
    assert result["api_key"] == ""
    assert "deepseek.com" in result["base_url"]
    assert result["model"] == "deepseek-chat"


def test_api1_uses_config_values_when_present(mock_deps):
    """api1 分支应读取 cfg 里的自定义 base_url / model。"""
    mock_deps(
        cfg={"api_key": "sk-x", "base_url": "https://custom/v1", "model": "my-model"},
        is_peak=False,
    )
    result = config.effective_config(source="web")
    assert result["key_id"] == "api1"
    assert result["api_key"] == "sk-x"
    assert result["base_url"] == "https://custom/v1"
    assert result["model"] == "my-model"


def test_source_param_overrides_llm_source(mock_deps):
    """source 参数覆盖 get_llm_source()——传 wecom 时不走 api2。"""
    # 线程局部默认 web，但显式传 wecom
    config.set_llm_source("web")
    mock_deps(
        cfg={"peak_enabled": False, "ark2_api_key": "ark2-key"},
        is_peak=False,
        api2_remaining=99999,
    )
    result = config.effective_config(source="wecom")
    assert result["key_id"] == "api1"
