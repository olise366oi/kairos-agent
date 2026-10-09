import os
import tempfile
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ========== 1. 临时 HOME，隔离 ~/.kairos ==========
_tmp_home = tempfile.mkdtemp(prefix="kairos_test_home_")
os.environ["HOME"] = _tmp_home
os.environ["USERPROFILE"] = _tmp_home  # Windows 兼容
os.environ.setdefault("HOME_TOKEN", "test-token-for-pytest")

# ========== 2. sys.path 设置 ==========
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

HOME_DIR = BACKEND_DIR / "home"
if str(HOME_DIR) not in sys.path:
    sys.path.insert(0, str(HOME_DIR))


# ========== 3. stub 缺失的私有模块 / 重依赖模块 ==========
# 这些模块在公开仓库里不存在，或其依赖（chromadb/sentence-transformers/openai）
# 在本地无法安装。stub 让 import agent.loop 能成功，且本地与 CI 行为一致。

def _make_stub(name, **attrs):
    """创建 stub 模块，挂到 sys.modules。如果已存在则复用。"""
    if name in sys.modules:
        mod = sys.modules[name]
    else:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        if "." in name:
            parent_name, _, child = name.rpartition(".")
            parent = sys.modules.get(parent_name)
            if parent is not None:
                setattr(parent, child, mod)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# 顶层重依赖
_make_stub("openai", OpenAI=MagicMock)

# rag 包 + 所有子模块
_make_stub("rag")
_make_stub("rag.embedder", embed_texts=MagicMock(return_value=[]))
_make_stub("rag.store", query_collection=MagicMock(return_value=[]))
_make_stub("rag.football_kb", search_football=MagicMock(return_value=[]))
_make_stub("rag.intimacy_kb", search_intimacy=MagicMock(return_value=[]))
_make_stub("rag.intimacy_engine", search_intimacy_engine=MagicMock(return_value=[]))
_make_stub("rag.geography_kb", search_geography=MagicMock(return_value=[]))
_make_stub("rag.nutrition_kb", search_nutrition=MagicMock(return_value=[]))
_make_stub("rag.hobbies_kb", search_hobbies=MagicMock(return_value=[]))
_make_stub("rag.trivia_kb", search_trivia=MagicMock(return_value=[]))
_make_stub("rag.psych_kb", search_psych_kb=MagicMock(return_value=[]))

# 私有模块（脱敏时排除）
_make_stub("chat")
_make_stub("chat.history", get_history=MagicMock(return_value=[]))

_make_stub("availability",
           get_availability=MagicMock(),
           auto_reply=MagicMock())

_make_stub("agent.arousal",
           get_current_arousal=MagicMock(),
           state_text=MagicMock(return_value=""),
           after_intimate_session=MagicMock(),
           begin_intimate_session=MagicMock(),
           min_duration_text=MagicMock(return_value=""),
           ENTRY_PATTERN=MagicMock())
