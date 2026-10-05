# 系统架构（Architecture）

本文是 Reunion 作品集的架构速览，供面试 / 展示时单独成文使用。内容与仓库代码一一对应。

## 总体架构

```
用户（移动端 Web / 企业微信 / 桌面悬浮球）
                 │
                 ▼
┌──────────────────────────────────────────────────┐
│ 交互层  home_server(FastAPI 单页应用) │ wecom 回调服务 │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ Agent 层  loop.py 主对话循环 │ proactive runner 心跳循环 │
└───────┬──────────┬──────────┬──────────┬─────────┘
        ▼          ▼          ▼          ▼
   RAG 按需检索   情感引擎    状态机     多模型路由
   (ChromaDB)  (Drivesoid) (SQLite/JSON) (DeepSeek/方舟)
        │
        ▼
数据层  SQLite + PostgreSQL · 知识库文本 · 企业微信 API · 赛事 / 天气 API（MCP 接入）
```

## 四层说明

### 数据层：SQLite + PostgreSQL (Supabase)

- **SQLite**：承担热数据——聊天历史（`chat_history.db`）、角色状态（`home_state.json` 等 JSON 状态文件）。单机、零运维、读写快，保证移动端 Web 与企微双入口共用同一份数据、状态实时一致。
- **PostgreSQL (Supabase)**：云侧持久化与备份（知识库、跨设备同步、审计），连接串通过运行时配置注入，代码内零真实值。
- 知识库正文以本地文本文件形式存放（`~/.reunion/*.txt`），由 RAG 层按需索引。

### AI 层：RAG / 情感引擎 / 主动触发 / 多模型路由

- **RAG 按需检索**：七类知识库（足球战术 / 亲密关系 / 地理 / 营养饮食 / 爱好 / 琐事记忆 / 心理健康）+ 对话记忆向量检索（ChromaDB）。每个知识库配独立关键词表，**日常聊天完全不检索**，命中关键词才注入知识片段。
- **情感引擎（Drivesoid）**：独立 Node.js 进程（端口 24601），维护多维连续情感状态（longing / intimacy / vitality / jealousy / anxiety / contentment 等），REST + MCP 双入口；主对话循环周期性拉取注入系统提示，聊天中的情感变化回写。
- **Agent 主动触发**：`proactive/runner.py` 心跳循环周期性评估"此刻是否适合主动说一句话"，与状态机联动，带可用性门控（睡觉 / 比赛 / 会议拦截）。
- **多模型路由**：`config.py` 统一出口（`llm_model / llm_base_url / llm_api_key / llm_key_id`），按 DeepSeek 官方峰谷定价、调用来源（web / wecom）、本地 token 配额三层切换，兜底链 api3 → api2 → api1。

### 集成层：MCP / 企业微信 / 内网穿透

- **MCP 协议**：stdio + JSON-RPC 2.0。客户端适配层在 `watch_manager.py`（`npx football-api-mcp` 拉赛事数据）；服务端示例为 Drivesoid 的 `src/mcp-server.js`（`drives_sleep` / `drives_event` / `drives_context` 三个工具）。独立可复用客户端见 `integrations/mcp/mcp_stdio_client.py`。
- **企业微信**：自建应用回调（SHA1 消息签名校验、收发消息）+ 主动推送（access_token 带锁缓存、过期自动刷新）。
- **内网穿透**：将本地回调端口暴露到公网，保证企微回调可达。

### 交互层：移动端 Web / 多页面 / 悬浮球

- `home_server.py`（FastAPI）提供移动端单页应用 `home.html`：聊天、来电、朋友圈、日记、剪贴板、看球复盘、约会计划批阅、日历、冰箱、雅思学习、API 用量面板等模块。
- 桌面端为 React + Electron 悬浮球，复用同一后端 API 与状态层。
- iOS Safari 兼容：`position:fixed` + `100vh`、`-webkit-backdrop-filter` 双写、`-webkit-overflow-scrolling:touch` + `overscroll-behavior:contain`、`Intl.DateTimeFormat` 本地化时间。

## 关键设计

- **时区可配置**：环境变量 `APP_TIMEZONE`（任意 IANA 时区，默认 UTC）驱动状态滚动 / 日程 / 天气 / 前端时间（前端 `APP_TZ` 与后端对齐）。
- **多模型峰谷路由**：请求量翻倍而成本不失控——按定价时段、调用来源、用量配额三层路由 + 本地 token 计量回退。
- **RAG 按需检索**：关键词命中才注入，省 token、不干扰闲聊；向量库懒加载 + 30 分钟天气缓存 + 思考链长度上限。
- **失败静默**：所有旁路能力（日记 / 朋友圈 / 赛程 / 知识库 / 情感引擎）失败均不影响主回复。

## 进程拓扑（部署视图）

| 进程 | 入口 | 职责 |
| --- | --- | --- |
| 移动端 Web | `backend/home/home_server.py` | FastAPI 单页应用 |
| 主动触发心跳 | `backend/proactive/runner.py` | 周期性评估与发起 |
| 企微回调 | `wecom/run.py` | 消息接收 / 推送 |
| 情感引擎 | `backend/drivesoid`（`npm start`） | 多维情感状态机（REST + MCP） |

多进程独立守护、幂等启动（端口占用检查防重复拉起）、内网穿透随服务启动、可注册开机自启。
