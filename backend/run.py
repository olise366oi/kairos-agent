import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
HOME_DIR = BACKEND_DIR / "home"
AGENT_DIR = BACKEND_DIR / "agent"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(HOME_DIR))
sys.path.insert(0, str(AGENT_DIR))

if not os.environ.get("HOME_TOKEN"):
    print("错误：请先设置 HOME_TOKEN 环境变量")
    print("  Windows cmd:        set HOME_TOKEN=your-secret-token")
    print("  Windows PowerShell: $env:HOME_TOKEN=\"your-secret-token\"")
    print("  macOS/Linux:        export HOME_TOKEN=your-secret-token")
    sys.exit(1)

import uvicorn
from home.home_server import app

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5971))
    uvicorn.run(app, host="0.0.0.0", port=PORT)
