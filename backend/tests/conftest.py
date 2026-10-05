import os
import tempfile
import sys
from pathlib import Path

# 创建临时 HOME，隔离 ~/.kairos，防止污染真实配置（必须在 import 前设置）
_tmp_home = tempfile.mkdtemp(prefix="kairos_test_home_")
os.environ["HOME"] = _tmp_home
os.environ["USERPROFILE"] = _tmp_home  # Windows 兼容

# 必须在 import home_server 之前设置，否则 RuntimeError
os.environ.setdefault("HOME_TOKEN", "test-token-for-pytest")

# 让 backend/ 进 sys.path，保证 `from home import home_server` 可行
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# home_server 内部用绝对导入引用同目录模块（call_manager 等），需把 backend/home/ 也加入
HOME_DIR = BACKEND_DIR / "home"
if str(HOME_DIR) not in sys.path:
    sys.path.insert(0, str(HOME_DIR))
