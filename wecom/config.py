# -*- coding: utf-8 -*-
"""企业微信接入配置：从用户手动填写的 wecom_config.json 读取，不写死在代码里。

配置文件位置：~/.kairos/wecom_config.json
字段：
  corp_id          企业ID（企业微信管理后台 → 我的企业 → 企业ID）
  agent_id         自建应用 AgentId（应用管理 → 自建 → 应用详情）
  secret           自建应用 Secret（应用管理 → 自建 → Secret，点"查看"）
  token            回调 Token（自建应用 → 接收消息 → 设置API接收 → Token）
  encoding_aes_key 回调 EncodingAESKey（同一页面生成）
"""

from __future__ import annotations

import json
from pathlib import Path

from config import DATA_DIR

WECOM_CONFIG_PATH = DATA_DIR / "wecom_config.json"

CONFIG_TEMPLATE = {
    "corp_id": "",
    "agent_id": "",
    "secret": "",
    "token": "",
    "encoding_aes_key": "",
    "port": 8765,
}


def ensure_config_template() -> None:
    """首次运行生成配置模板（用户手动填）。"""
    if not WECOM_CONFIG_PATH.exists():
        WECOM_CONFIG_PATH.write_text(
            json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[wecom] 已生成配置模板：{WECOM_CONFIG_PATH}（请填入企业微信参数）")


def load_wecom_config() -> dict:
    ensure_config_template()
    try:
        data = json.loads(WECOM_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(CONFIG_TEMPLATE)
    cfg = dict(CONFIG_TEMPLATE)
    cfg.update({k: v for k, v in data.items() if k in CONFIG_TEMPLATE})
    return cfg


def is_configured(cfg: dict) -> bool:
    """四个核心参数是否已填全。"""
    return bool(
        cfg.get("corp_id")
        and cfg.get("agent_id")
        and cfg.get("secret")
        and cfg.get("token")
        and cfg.get("encoding_aes_key")
    )
