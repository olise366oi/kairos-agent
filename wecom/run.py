# -*- coding: utf-8 -*-
"""启动企业微信接入服务：0.0.0.0:8765（可改 wecom_config.json 里的 port）。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from wecom.config import load_wecom_config, ensure_config_template, is_configured


def main() -> None:
    import uvicorn

    ensure_config_template()
    cfg = load_wecom_config()
    port = int(cfg.get("port", 8765))
    host = "0.0.0.0"

    if not is_configured(cfg):
        print("=" * 60)
        print("企业微信参数未配置完整，请编辑：")
        print("  ./data\\wecom_config.json")
        print("填入 corp_id / agent_id / secret / token / encoding_aes_key 后重启。")
        print("=" * 60)

    print(f"[wecom] 监听 {host}:{port}（回调路径 /wecom/callback）")
    uvicorn.run("wecom.server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
