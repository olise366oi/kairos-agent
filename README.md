# Kairos Agent

> 一个具备主动意识、长期记忆与情感引擎的 AI 陪伴 Agent，通过多渠道成本控制实现可持续运行。

**核心差异化：**

- 🧠 **主动式 Agent**：心跳循环驱动，在合适时机主动发起对话，而非被动等待。
- 💰 **多渠道成本控制**：同一模型多路 API 调度 + 配额回退，主动触发场景下仍能控制调用成本。
- ❤️ **独立情感引擎**：跨端同步的情感状态，让陪伴更连贯。
- 📱 **三端一致**：移动端 Web、桌面悬浮球、企业微信推送无缝协同。

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![Node.js](https://img.shields.io/badge/Node.js-18+-339933?logo=nodedotjs&logoColor=white)](https://nodejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Uvicorn-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![MCP](https://img.shields.io/badge/MCP-stdio%20JSON--RPC-6E56CF)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/License-MIT-yellow)](./LICENSE)

---

## 一句话说清楚

市面上大多数"AI 伴侣"是**被动应答**：你不发消息，它永远沉默。
Kairos 做的是**主动式**：它维护一套连续的情感状态和角色状态机，在训练间隙、比赛日、睡前等真实场景里**自己决定要不要开口**，并且记得三个月前你提过的事。

三个工程上真正难的点：
- **主动性**：什么时候该说话、什么时候该闭嘴——这是可用性问题，不是模型问题
- **成本**：主动触发意味着请求量是被动聊天的数倍，必须有成本控制
- **一致性**：跨 Web / 企业微信 / 桌面三端，状态不能穿帮

---

## ⚠️ 关于本仓库（重要）

这是一个**脱敏展示版**，用于展示系统架构与工程能力，**不是可直接部署的生产版本**。

- `backend/home/` 下引用的部分业务模块（赛事抓取、状态规则、聊天历史等）因涉及第三方数据源与个人数据，**已在公开版中移除**；移动端 Web 主链路无法在本仓库内单独启动。
- `wecom/`（企业微信接入）与 `backend/drivesoid/`（情感引擎）**相对独立，可独立运行**，见下方"快速开始"。
- 如需完整运行移动端 Web，需自行补齐被移除的模块，接口约定见 `docs/`。
- **所有"实测数据"（消息量、调用次数、状态快照数、沉默率等）均来自开发期本地运行记录**，相关数据库与日志文件未随仓库公开，无法在公开版中直接复算。保留这些数字是为了说明机制确实在运行，而非为了展示规模。

---

## 快速开始

### 1. 情感引擎（Drivesoid，独立可跑）

需要 Node.js ≥ 18。

```bash
cd backend/drivesoid
cp .env.example .env   # 按需填入配置
npm install
npm start              # REST 服务，默认端口 :24601
# 或
npm run mcp            # 以 MCP Server 形式启动
```

### 2. 企业微信接入（独立可跑）

```bash
cd wecom
pip install -r ../backend/requirements.txt
# 凭据写入 ~/.kairos/wecom_config.json
#   corp_id / agent_id / secret / token / encoding_aes_key
python run.py          # 监听 0.0.0.0:8765
```

### 3. 移动端 Web 与主动触发（需补齐模块后运行）

```bash
cd backend
pip install -r requirements.txt
# LLM 三路 API 配置写入 ~/.kairos/config.json（api_key / base_url / model）
export APP_TIMEZONE=Asia/Shanghai   # 可选，默认 UTC
# 必须设置 HOME_TOKEN，否则后端启动会直接报错
# Windows (cmd):        set HOME_TOKEN=<你的随机密钥>
# Windows (PowerShell): $env:HOME_TOKEN="<你的随机密钥>"
# macOS/Linux:          export HOME_TOKEN=<你的随机密钥>

python run.py   # 移动端 Web（端口 5971，首次打开会弹设置窗口）
python proactive/runner.py   # 主动触发心跳
```

浏览器打开 http://localhost:5971/home?t=your-secret-token → 首次打开会弹出设置窗口，填称呼 + API Key + 人设即可开始。

注意：看球、约会计划、聊天历史（`chat.history`）等业务模块在公开版中已移除——服务可正常启动（缺失模块自动降级），但对应功能需按 `docs/` 补齐后才可用。

---

## 项目规模

- **Python 7,677 行 / 46 文件**，**JavaScript 2,163 行 / 9 文件**（不含依赖与生成物）
- 核心后端模块 **45 个**，FastAPI 路由 **52 条**（26 GET / 26 POST，home_server.py 单文件口径；含 wecom 回调服务则为 58 条）
- RAG 知识库 **7 类**，MCP 工具 **3 个**（情感引擎服务端）
- 三端入口（移动 Web / 企微 / 桌面），情感引擎独立进程（REST + MCP 双协议）
- 开发周期：2026年9月13日 – 9月24日，独立开发。

---

## 系统能力

| 能力 | 说明 |
| --- | --- |
| 🧠 长周期记忆 | ChromaDB 向量检索 + 多知识库按需注入，7 类知识域 |
| 💓 连续情感状态 | 独立 Node.js 情感引擎，多维情感向量，聊天 ↔ 状态双向闭环 |
| ⏰ 主动触发 | 心跳循环 + 场景上下文拼装，Agent 自主决定推送 / 记录 / 沉默 |
| 🔀 多渠道成本控制 | 双路 API 池（DeepSeek 官方 + 火山方舟，同一模型），配额耗尽自动回退 |
| 📱 三端一致 | 移动端 Web / 企业微信 / 桌面悬浮球共用同一状态层 |
| 🔌 外部集成 | MCP 协议接入赛事数据，Open-Meteo 天气，企业微信推送 |

---

## 架构

```mermaid
flowchart TD
    U["用户<br/>移动端 Web / 企业微信 / 桌面悬浮球"]
    subgraph L1["交互层"]
        HS["home_server<br/>FastAPI 单页应用"]
        WC["wecom<br/>回调服务"]
    end
    subgraph L2["Agent 层"]
        LP["loop.py<br/>主对话循环"]
        PR["proactive/runner.py<br/>心跳循环"]
    end
    subgraph L3["能力层"]
        RAG["RAG 按需检索<br/>ChromaDB"]
        DE["情感引擎<br/>Drivesoid"]
        SM["状态机<br/>SQLite / JSON"]
        RT["多渠道成本控制<br/>双路 API 池"]
    end
    subgraph L4["数据层"]
        DB["SQLite + PostgreSQL"]
        KB["知识库文本"]
        EXT["企业微信 / 赛事 / 天气 API<br/>MCP 接入"]
    end
    U --> HS
    U --> WC
    HS --> LP
    WC --> LP
    LP --> RAG
    LP --> DE
    LP --> SM
    LP --> RT
    PR --> DE
    PR --> SM
    PR --> RT
    RAG --> KB
    SM --> DB
    DE --> SM
    LP --> EXT
    PR --> EXT
```

- **数据层**：SQLite + PostgreSQL (Supabase)——热数据本地化（聊天历史、状态 JSON 单机零运维），云侧做知识库与备份。
- **AI 层**：RAG 按需检索（关键词命中才注入）/ 情感引擎（独立进程多维状态）/ Agent 主动触发（心跳循环）/ 多渠道成本控制（双路 API 池 + 配额回退）。
- **集成层**：MCP 协议（stdio JSON-RPC）/ 企业微信推送 / 内网穿透。
- **交互层**：移动端 Web（FastAPI 单页）/ 多页面 / 桌面悬浮球（Electron）。

---

## 四个技术亮点

### 1. 主动式 Agent：从"应答"到"发起"

大多数 LLM 应用是 request-response。Kairos 加了一个**心跳循环**（`proactive/runner.py`），周期性评估"此刻是否适合主动说一句话"：

- 拼装场景上下文（训练间隙 / 比赛日 / 返程 / 睡前）
- 调用 LLM 生成候选"念头"，再决定推送企微、写日记、发朋友圈，或者什么都不做
- 与**角色状态机**联动：`home_state.json` 记录当天的在家 / 外出 / 比赛状态，过期自动滚动，聊天中信号可回写覆盖

**工程难点在于"克制"**：主动性做过头就是骚扰。系统实现了可用性门控——睡觉 / 比赛 / 会议场景直接拦截，训练间隙允许短回复，连续未回触发安抚兜底而非追加推送。

**实测数据**（来自开发期本地运行记录，数据文件未随仓库公开）：66 次念头评估中，仅 23 次通过发送门槛（`speak_threshold`），**43 次主动沉默，沉默率 65%**。系统真正做的是"决定不打扰"，而不是"找机会说话"。

### 2. 多渠道成本控制：主动触发的请求量下，把成本压到最低

主动触发意味着请求量是被动模式的数倍。系统没有切换模型，而是**在同一个 DeepSeek 模型上，通过多渠道调度来压低单次调用成本**（`backend/config.py`）：

- **双路 API 池**：DeepSeek 官方 API + 火山方舟 API（同样跑 DeepSeek 模型），后者有每日免费额度
- **按用量自动回退**：本地累计 token 计量（`api_usage.py`），主池配额耗尽自动降级到备用池
- **RAG 按需检索**：关键词命中才注入知识片段，日常闲聊完全不检索
- **30 分钟天气缓存** + **思考链长度上限**：减少不必要的 token 消耗

**实测数据**（`backend/logs/usage.log`，2026-09-18 → 09-27，9 天 704 次调用）：**91.8% 的调用使用了火山方舟的免费额度，闲时段 token 占 93.6%**。需要说明的是，这个分布同时受使用时段影响（峰段主要在开发调试，聊天请求集中在闲时），并非纯粹由路由策略造成。但双路池的存在确实让主动触发产生的增量请求没有带来额外 API 支出。

### 3. 连续情感引擎（独立 Node.js 服务）

不是让 LLM"扮演"情绪，而是让情绪成为一个**独立进程里的可查询状态**（`backend/drivesoid/`，端口 24601）：

- 维护 **16 维连续值**（longing / intimacy / vitality / jealousy / anxiety / contentment / elation / possessiveness 等），每维带独立的时间常数、峰值时刻与振幅参数
- 主对话循环周期性拉取情感上下文注入系统提示，聊天中的情感变化回写
- 双入口设计：REST API + MCP 服务，既可被 Python 调用，也可被其他 MCP 客户端消费

**架构意义**：把"情感"从 prompt 里的一次性文本，变成可持久化、可观测、可测试的状态机。配套 Python 心跳引擎（`companion_awakening/`）负责生成"念头"。

**实测数据**：**累积 6,541 条状态快照**，每条含完整 16 维取值，可供回溯、可视化与调参。两套情感状态（Node 引擎 16 维 / Python 念头引擎 8 字段）通过映射同步。

### 4. 移动端工程化与三端一致

`home_server.py`（FastAPI）提供移动端 Web，包含聊天、来电、朋友圈、日记、日历、冰箱、看球复盘、约会计划等模块。真正的坑在 **iOS Safari**：

- `position:fixed` + `100vh` 规避地址栏伸缩导致的视口跳动与软键盘顶起错位
- `-webkit-backdrop-filter` 双写兼容毛玻璃
- `-webkit-overflow-scrolling:touch` + `overscroll-behavior:contain` 防滚动穿透
- `Intl.DateTimeFormat` 绕过 Safari 对 `toLocaleString` 的兼容差异
- 前后端共用 `APP_TIMEZONE`，支持任意 IANA 时区，默认 UTC

三端共用同一 SQLite 聊天历史与状态文件，回复与状态实时一致。

**实测规模**：移动端 Web 聊天库累积 463 条消息，其中 70 条带思考链；企微去重消息 ID 248 条。三端状态实时一致，无跨端穿帮。

---

## 限制与反思

项目在 12 天内独立完成，做了刻意取舍。以下问题尚未解决，或只做到"能跑"而非"可靠"：

- **主动触发的误报率没有系统评估**。目前只能从 66 次念头评估中 23 次开口、43 次沉默推断出"克制"倾向，但"该说时说了"与"不该说时说了"的区分缺乏标注数据。可用性门控依赖硬编码规则（睡觉 / 比赛 / 会议），规则覆盖不到的场景可能误伤或误放。
- **情感引擎的初始值依赖已有聊天记录校准**。16 维状态的起点是基于历史对话手工调配的，新用户没有聊天记录时，冷启动缺乏个性化基线。
- **双路 API 池的切换对用户不可见，但延迟有代价**。主备池切换发生在请求侧，用户无感知，但两个 API 端点之间的响应延迟差异没有做过量化对比。
- **三端一致只在在线场景验证过**。三端共用 SQLite 状态层要求同时可访问同一存储；离线或弱网下多端同时写入状态时的冲突合并未做处理。
- **评估数据来自单人 12 天使用**。66 次念头、704 次调用、6,541 条快照均为开发期自测，样本量不足以支撑普适结论，只能说明"机制在跑"，不能说明"效果好"。
- **公开版无法端到端运行**。`home_server.py` 依赖被移除的业务模块，读者只能验证情感引擎与企业微信两个独立组件，主链路需自行补齐。
- **API Key 明文存储**：当前配置（`~/.kairos/config.json`）为简化实现，生产环境请改用环境变量或密钥管理服务。

---

## 第三方组件与许可

- 本仓库原创代码以 **MIT** 许可开源（见根目录 `LICENSE`，Copyright (c) 2026 Kairos Project）。
- `backend/drivesoid/` 为**独立开源组件**（情感引擎），遵循其自带 **CC-BY-NC-SA-4.0** 许可（见 `backend/drivesoid/LICENSE`）。
- 商用场景建议将情感引擎替换为自研实现——架构已解耦（REST + MCP 双入口），替换不影响主链路。
