# AI Companion System

一个基于 LLM 的长期陪伴型 AI 应用系统。包含角色状态管理、情感引擎、主动消息触发、多知识库 RAG 检索、外部数据集成、移动端 Web 交互。

系统以「常驻 Agent + 周期性主动触发」的方式运行：主对话循环负责被动聊天（按需注入记忆与知识库），心跳循环负责主动发消息（训练间隙、比赛日、睡前等场景），移动端 Web 与企业微信提供双入口，所有状态统一落在本地数据层。

## 架构

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

- **数据层**：SQLite + Supabase (PostgreSQL)
- **AI 层**：RAG 按需检索 / 情感引擎 / Agent 主动触发 / 多模型路由
- **集成层**：MCP 协议 / 企业微信推送 / 内网穿透
- **交互层**：移动端 Web / 多页面 / 悬浮球系统

## 关键设计

- **时区可配置**：目标时区由环境变量 `APP_TIMEZONE` 指定（支持任意 IANA 时区），默认 `UTC`；状态滚动、日程、天气、前端时间显示均按该时区计算。前端（`home.html`）用 `APP_TZ` 常量与后端保持一致，部署时同步修改即可。
- **多模型峰谷路由**：DeepSeek 官方 + 火山方舟双/三 API，按峰谷定价与来源（web / wecom）动态切换，本地累计 token 用量做配额回退；API Key 全部来自运行时外部配置，代码内零真实值。
- **RAG 按需检索**：日常聊天不检索，命中关键词才注入知识片段，省 token、不干扰闲聊。
- **失败静默**：所有旁路能力（日记 / 朋友圈 / 赛程 / 知识库 / 情感引擎）失败均不影响主回复。

## 核心模块

### 1. 状态机与 Agent 主动触发

- **心跳循环**：`proactive/runner.py` 常驻 tick 循环，周期性评估「此刻是否适合主动说一句话」。`adapter.py` 按场景（训练间隙 / 比赛日 / 训练结束回家 / 在家晚上 / 返程日等）拼接场景上下文，调 LLM 生成候选「念头」，再决定推送企微消息、写日记或发朋友圈。
- **状态机**：`home_state.json` 记录当天状态（在家 / 外出 / 约会 / 比赛 / 休息 / 亲密等），`date_roller.py` 按目标时区日期自动滚动，过期状态自动失效；聊天中模型提到「回家了」等信号会回写状态覆盖，保证「状态一致、不穿帮」。
- **情感引擎（Drivesoid 同步）**：本地情感引擎服务（127.0.0.1:24601）维护连续的情感状态，主对话循环周期性拉取并注入系统提示；聊天中涉及情感变化时回写，形成「聊天 ↔ 情感状态」闭环。
- **可用性门控**：睡觉 / 比赛 / 会议等场景直接拦截回复并走自动回复，训练间隙可回短消息；连续未回时触发安抚兜底，避免打扰与出戏。

### 2. RAG 按需检索

- **多知识库检索**：足球战术 / 亲密关系 / 地理 / 营养饮食 / 爱好 / 琐事记忆 / 心理健康七类知识库，加上对话历史记忆检索（embedding 相似查询，ChromaDB 向量库）。
- **关键词触发**：每个知识库配独立关键词表（`frozenset`），**日常聊天完全不检索**；只有用户消息命中关键词才注入对应知识片段——省 token、不干扰闲聊。
- **上下文成本控制**：按需注入 + 向量库懒加载（文件变更按 mtime 自动重建）+ 30 分钟天气缓存 + 思考链 120 字上限 + 逐请求 token 用量日志；所有旁路能力（日记 / 朋友圈 / 赛程 / 知识库）失败静默，绝不影响主回复。

### 3. 外部数据集成

- **体育赛事数据（MCP）**：外部赛事数据接口经 MCP 协议接入（stdio JSON-RPC，适配层见 `integrations/mcp/` 与 `watch_manager.py`）→ 本地 `schedule.txt` / `match_results.json`；比赛日自动置状态并注入赛程，赛后生成赛果消息，进球数据可改写成角色事件。
- **天气**：Open-Meteo（免 API Key），按所在地时区与客场城市返回实时天气，30 分钟缓存。
- **企业微信**：自建应用回调（SHA1 消息签名校验、收发消息、媒体文件处理）+ 主动推送（access_token 带锁缓存、过期自动刷新）；思考链通过独立 bot 同步。
- **内网穿透**：内网穿透工具将本地回调端口暴露到公网，保证企业微信回调可达。

### 4. 移动端 Web

- **多页面单页应用**：`home_server.py`（FastAPI）提供 `home.html`——聊天、电话（来电窗）、朋友圈、日记、剪贴板、看球复盘、约会计划批阅、日历、冰箱、雅思学习、API 用量面板等模块。
- **iOS Safari 兼容修复**（内嵌于 `home.html`）：
  - `position:fixed` 全屏容器 + `100vh/max-height:100vh`，规避地址栏伸缩导致的视口跳动与软键盘顶起错位；
  - `-webkit-backdrop-filter` 与 `backdrop-filter` 双写毛玻璃，`-webkit-overflow-scrolling:touch` + `overscroll-behavior:contain` 防滚动穿透与橡皮筋回弹；
  - `Intl.DateTimeFormat`（含 `sv-SE` / `en-GB` 区域技巧）本地化时间格式，避免 Safari 对 `toLocaleString` 的兼容差异；
  - 时间显示统一走 `APP_TZ` 常量，与后端 `APP_TIMEZONE` 对齐。
- **跨设备同步**：Web 与企微双入口共用同一 SQLite 聊天历史与状态文件，回复与状态实时一致。

### 5. 部署与运维

- **多进程守护**：Web 服务 / 主动消息循环 / 企微回调各自独立进程，`start_*.bat` 提供幂等启动（端口占用检查、防重复拉起）。
- **内网穿透**：穿透进程随服务启动，保证公网回调与本地服务的连通。
- **开机自启**：启动脚本可注册为开机自启项；各进程日志独立落盘，网络层诊断日志辅助排障。

### 6. 情感引擎（Drivesoid）

- **独立 Node.js 服务**（`backend/drivesoid/`，端口 24601）：维护多维连续情感状态（longing / intimacy / possessiveness / vitality / jealousy / anxiety / contentment 等），支持中性基线 + 下限覆盖；主对话循环周期性拉取 `GET /api/drives/context` 注入系统提示，聊天中情感变化回写。
- **双入口**：REST（`src/server.js`，`npm start`）+ MCP 服务（`src/mcp-server.js`，`npm run mcp`）。
- **配置**：`drives.config.json`（运行时生成）+ 环境变量（`DRIVES_API_KEY` 等），仓库内仅保留脱敏模板 `drives.config.example.json` 与 `.env.example`。
- **配套 Python 引擎**：`backend/companion_awakening/` 提供心跳「念头」引擎（AwakeningService），`runner.py` 通过 adapter 与其联动。
- **许可说明**：Drivesoid 为独立组件，遵循其自带 `LICENSE`（CC-BY-NC-SA-4.0）；本仓库根目录 `LICENSE`（MIT）仅覆盖仓库原创代码。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 语言 | Python 3.11 · Node.js ≥ 18 |
| Web 服务 | FastAPI · Uvicorn · Express（Drivesoid） |
| LLM 接入 | OpenAI SDK（兼容 DeepSeek / 火山方舟，峰谷多模型路由） |
| RAG | LangChain · ChromaDB · sentence-transformers |
| 数据 | SQLite · PostgreSQL (Supabase) · JSON 状态文件 |
| 情感引擎 | Drivesoid（Node 多维情感状态机）· companion-awakening（Python 念头/心跳） |
| 外部集成 | MCP 协议（stdio JSON-RPC）· 企业微信 API · Open-Meteo · 内网穿透 |
| 前端 | HTML / CSS / JS 单页应用 · Vite + TypeScript（桌面悬浮球，Electron） |

## 部署方式

```bash
# 1. 安装依赖（backend 目录）
pip install -r requirements.txt

# 2. 配置（首次运行自动生成模板，按需填写）
#   ~/.reunion/config.json        LLM API Key / base_url / model / persona
#   ~/.reunion/*.txt               persona、知识库、赛程等数据文件
#   wecom/wecom_config.json        企业微信自建应用 corp_id / agent_id / secret / token

# 3. 启动（三个独立进程）
cd backend && python home/home_server.py      # 移动端 Web 服务
python proactive/runner.py                    # 主动消息心跳循环
python ../wecom/run.py                        # 企业微信回调服务

# 4. 内网穿透：将本地回调端口暴露到公网，在企业微信后台配置回调 URL。

# 5. （可选）情感引擎 Drivesoid
cd backend/drivesoid && npm install && npm start   # 127.0.0.1:24601

# 6. 时区：默认 UTC；如部署地为其他时区，设置环境变量
#    APP_TIMEZONE=Europe/Berlin（任意 IANA 时区）后重启服务
```

> 说明：本仓库为脱敏后的代码展示。运行时所需的 API Key、数据库连接串、知识库数据文件、状态文件均以占位符（`YOUR_API_KEY`、`YOUR_DOMAIN`、`YOUR_DB_URL`、`./data` 等）或外部配置文件形式存在，不包含在仓库内。

## 项目结构

```
reunion-portfolio/
├── README.md
├── LICENSE                       # MIT（Reunion Project）
├── index.html                    # 桌面端入口（Vite 单页）
├── integrations/
│   └── mcp/                      # MCP 协议适配层（stdio JSON-RPC）
│       ├── mcp_stdio_client.py   # 独立可复用 MCP 客户端
│       └── README.md
├── backend/
│   ├── config.py                 # 多模型路由 / 峰谷切换 / 时区 / 配置读写
│   ├── api_usage.py              # LLM token 用量统计（按 key / 按天）
│   ├── requirements.txt          # Python 依赖
│   ├── drivesoid/                # 情感引擎（Node.js，REST + MCP 双入口）
│   ├── companion_awakening/      # Python 心跳念头引擎
│   ├── agent/
│   │   └── loop.py               # 主对话循环（RAG 按需注入 / 状态门控 / 情感同步）
│   ├── home/
│   │   ├── home_server.py        # 移动端 Web 服务（FastAPI）
│   │   ├── home.html             # 主界面（聊天 / 电话 / 朋友圈 / 日历 / 约会计划…）
│   │   ├── clip_page.html        # 剪贴板页面
│   │   ├── meal_planner.py       # 做饭计划
│   │   ├── fridge_filler.py      # 冰箱食材管理
│   │   ├── diary_manager.py      # 日记
│   │   ├── moments_manager.py    # 朋友圈
│   │   ├── clipboard_manager.py  # 剪贴板同步
│   │   ├── watch_manager.py      # 看球复盘（含 MCP 赛事适配）
│   │   ├── call_manager.py       # 来电状态机
│   │   ├── date_roller.py        # 日期滚动（时区可配置）
│   │   └── ielts_manager.py      # 雅思学习管理
│   ├── rag/
│   │   ├── embedder.py           # 文本向量化
│   │   ├── store.py              # ChromaDB 向量存取
│   │   ├── chunker.py            # 结构化切块
│   │   └── *_kb.py               # 各知识库索引器（数据存外部文本文件）
│   └── proactive/
│       ├── runner.py             # 心跳循环
│       ├── adapter.py            # 场景念头生成 / 推送适配
│       └── start_proactive.bat   # 启动脚本
└── wecom/
    ├── server.py                 # 企业微信回调服务
    ├── crypto.py                 # 消息签名（SHA1）
    ├── push.py                   # 主动推送
    ├── push_thoughts.py          # 思考链独立 bot
    ├── config.py / run.py / dedup.py
    └── start_wecom*.bat          # 启动 / 守护脚本
```

## 截图

截图见 `docs/screenshots/`（占位目录，后续补充移动端界面、架构示意等截图）。
