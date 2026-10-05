# Kairos · 主动式 AI 陪伴系统

> 不是"你问它答"的聊天机器人，而是一个**会自己找你的常驻 Agent**。
> 长周期记忆 + 连续情感状态 + 主动触发 + 多模型成本路由，独立完成架构设计与落地。

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

## 项目规模

- **Python 7,677 行 / 46 文件**，**JavaScript 2,163 行 / 9 文件**（不含依赖与生成物）
- 核心后端模块 **45 个**，FastAPI 路由 **52 条**（21 GET / 31 POST）
- RAG 知识库 **7 类**，MCP 工具 **3 个**（情感引擎服务端）
- 三端入口（移动 Web / 企微 / 桌面），情感引擎独立进程（REST + MCP 双协议）

---

## 系统能力

| 能力 | 说明 |
| --- | --- |
| 🧠 长周期记忆 | ChromaDB 向量检索 + 多知识库按需注入，7 类知识域 |
| 💓 连续情感状态 | 独立 Node.js 情感引擎，多维情感向量，聊天 ↔ 状态双向闭环 |
| ⏰ 主动触发 | 心跳循环 + 场景上下文拼装，Agent 自主决定推送 / 记录 / 沉默 |
| 🔀 多模型路由 | DeepSeek + 火山方舟三 API，按峰谷定价与调用来源动态切换 |
| 📱 三端一致 | 移动端 Web / 企业微信 / 桌面悬浮球共用同一状态层 |
| 🔌 外部集成 | MCP 协议接入赛事数据，Open-Meteo 天气，企业微信推送 |

---

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

- **数据层**：SQLite + PostgreSQL (Supabase)——热数据本地化（聊天历史、状态 JSON 单机零运维），云侧做知识库与备份。
- **AI 层**：RAG 按需检索（关键词命中才注入）/ 情感引擎（独立进程多维状态）/ Agent 主动触发（心跳循环）/ 多模型路由（峰谷 + 来源 + 配额三层切换）。
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

### 2. 多模型成本路由：让请求量翻倍而成本不失控

主动触发意味着请求量是被动模式的数倍。系统实现了三层路由（`backend/config.py`）：

- **按定价时段**：DeepSeek 官方峰谷定价，高峰期自动切到火山方舟的闲时资源
- **按调用来源**：网页端与企微端走不同配额池
- **按用量自动回退**：本地累计 token 计量（`api_usage.py`），配额耗尽自动降级到兜底 API

配合 **RAG 按需检索**（关键词命中才注入知识片段，日常闲聊完全不检索）+ 30 分钟天气缓存 + 思考链长度上限，在保证体验的前提下控制单次请求成本。

### 3. 连续情感引擎（独立 Node.js 服务）

不是让 LLM"扮演"情绪，而是让情绪成为一个**独立进程里的可查询状态**（`backend/drivesoid/`，端口 24601）：

- 维护 longing / intimacy / vitality / jealousy / anxiety / contentment 等**多维连续值**
- 主对话循环周期性拉取情感上下文注入系统提示，聊天中的情感变化回写
- 双入口设计：REST API + MCP 服务，既可被 Python 调用，也可被其他 MCP 客户端消费

**架构意义**：把"情感"从 prompt 里的一次性文本，变成可持久化、可观测、可测试的状态机。配套 Python 心跳引擎（`companion_awakening/`）负责生成"念头"。

### 4. 移动端工程化与三端一致

`home_server.py`（FastAPI）提供移动端 Web，包含聊天、来电、朋友圈、日记、日历、冰箱、看球复盘、约会计划等模块。真正的坑在 **iOS Safari**：

- `position:fixed` + `100vh` 规避地址栏伸缩导致的视口跳动与软键盘顶起错位
- `-webkit-backdrop-filter` 双写兼容毛玻璃
- `-webkit-overflow-scrolling:touch` + `overscroll-behavior:contain` 防滚动穿透
- `Intl.DateTimeFormat` 绕过 Safari 对 `toLocaleString` 的兼容差异
- 前后端共用 `APP_TIMEZONE`，支持任意 IANA 时区，默认 UTC

三端共用同一 SQLite 聊天历史与状态文件，回复与状态实时一致。

---

## 我的角色

**独立完成架构设计、产品定义与工程落地**。核心编码通过 AI 辅助编程完成，我负责：

- **架构决策**：为什么把情感引擎拆成独立进程（可观测 / 可测试 / 跨语言复用）
- **成本设计**：多模型路由与按需 RAG 的组合策略
- **产品判断**：主动触发的"克制"边界——什么时候不该说话
- **工程收尾**：iOS 兼容、多进程守护、开机自启、内网穿透、企业微信回调
- **排障与迭代**：独立定位跨进程 / 跨端 / 网络层问题

> 我能独立排查错误、优化性能，也理解每一行代码的作用。

---

## 快速开始

```bash
# 1. Python 依赖
cd backend && pip install -r requirements.txt

# 2. 配置（首次运行生成模板）
#    ~/.kairos/config.json    LLM API Key / base_url / model
#    wecom/wecom_config.json   企业微信自建应用凭据

# 3. 启动三个进程
python home/home_server.py    # 移动端 Web
python proactive/runner.py    # 主动触发心跳
python ../wecom/run.py        # 企业微信回调

# 4. 可选：情感引擎
cd backend/drivesoid && npm install && npm start   # :24601

# 5. 时区（任意 IANA，默认 UTC）
export APP_TIMEZONE=Asia/Shanghai
```

---

## 第三方组件与许可

- 本仓库原创代码以 **MIT** 许可开源（见根目录 `LICENSE`，Copyright (c) 2026 Kairos Project）。
- `backend/drivesoid/` 为**独立开源组件**（情感引擎），遵循其自带 **CC-BY-NC-SA-4.0** 许可（见 `backend/drivesoid/LICENSE`）。
- 商用场景建议将情感引擎替换为自研实现——架构已解耦（REST + MCP 双入口），替换不影响主链路。
