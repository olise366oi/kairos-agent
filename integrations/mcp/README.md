# MCP 集成层

系统通过 MCP（Model Context Protocol）接入外部数据工具，采用 **stdio + JSON-RPC 2.0** 传输。

## 组成

| 角色 | 位置 | 说明 |
| --- | --- | --- |
| 客户端适配层 | `backend/home/watch_manager.py`（`_mcp_call`） | 拉起 MCP server 并调用工具（看球复盘场景） |
| 客户端独立模块 | `mcp_stdio_client.py`（本目录） | 从 watch_manager 提取的可复用实现 |
| 服务端示例 | `backend/drivesoid/src/mcp-server.js` | 情感引擎的 MCP 服务入口（`npm run mcp`） |

## 协议流程

1. `initialize`（protocolVersion `2024-11-05`）
2. `notifications/initialized`
3. `tools/call(name, arguments)`，逐行 JSON 经子进程 stdin/stdout 收发

带超时控制与静默失败兜底，任何环节失败都不影响主对话。

## 实际接入

- **赛事数据**：`npx -y football-api-mcp`（第三方 MCP server），工具 `get_league_fixtures`；
  API Key 经环境变量 `FIVEDOLLARFOOTBALL_API_KEY` 注入，仓库内零真实值。
- **情感状态**：情感引擎的 MCP 服务端（`backend/drivesoid/src/mcp-server.js`）
  可被任意 MCP 客户端调用，与 REST 入口（`src/server.js`）互为补充。
