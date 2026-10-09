"""_suppress_intimate_state 的防回归测试。

这个 context manager 修复了一个真实 bug：
原实现在 monkey-patch 后如果 get_status 抛异常，恢复语句不会执行，
导致 status_rule 的模块状态被永久污染。

测试策略：注入假的 status_rule 模块（真实的不在仓库里），
验证正常/异常退出后状态都能恢复。
"""
import sys
import types

import pytest

from agent.loop import _suppress_intimate_state


@pytest.fixture
def fake_status_rule(monkeypatch):
    """注入假 status_rule 模块，提供被 monkey-patch 的两个函数。

    使用 monkeypatch.setitem 自动在测试后恢复 sys.modules，不污染其他测试。
    """
    mod = types.ModuleType("status_rule")
    mod._intimate_now = lambda: True
    mod._said_goodnight = lambda x: True
    monkeypatch.setitem(sys.modules, "status_rule", mod)
    return mod


def test_normal_exit_restores(fake_status_rule):
    """正常退出 with 后，两个函数应恢复为原值。"""
    # 进入前：真实函数返回 True
    assert fake_status_rule._intimate_now() is True
    assert fake_status_rule._said_goodnight(None) is True

    with _suppress_intimate_state():
        # 进入后：被替换为永远返回 False
        assert fake_status_rule._intimate_now() is False
        assert fake_status_rule._said_goodnight(None) is False

    # 退出后：恢复原值
    assert fake_status_rule._intimate_now() is True
    assert fake_status_rule._said_goodnight(None) is True


def test_exception_exit_restores(fake_status_rule):
    """with 块内抛异常时，finally 仍应恢复原值（核心防回归）。"""
    with pytest.raises(RuntimeError, match="模拟 get_status 抛异常"):
        with _suppress_intimate_state():
            assert fake_status_rule._intimate_now() is False
            assert fake_status_rule._said_goodnight(None) is False
            raise RuntimeError("模拟 get_status 抛异常")

    # 关键断言：异常后仍然恢复，说明 try/finally 起作用了
    assert fake_status_rule._intimate_now() is True
    assert fake_status_rule._said_goodnight(None) is True


def test_multiple_uses(fake_status_rule):
    """连续两次使用 context manager，各自正常恢复，不累积副作用。"""
    with _suppress_intimate_state():
        assert fake_status_rule._intimate_now() is False
    assert fake_status_rule._intimate_now() is True

    with _suppress_intimate_state():
        assert fake_status_rule._intimate_now() is False
    assert fake_status_rule._intimate_now() is True
