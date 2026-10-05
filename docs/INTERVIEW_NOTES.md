# 面试笔记（Interview Notes）

面试官可能问的 10 个技术问题 + 回答要点。全部基于本仓库真实代码，可随手打开对应文件佐证。

## 1. 为什么用双库（SQLite + PostgreSQL）？

- **SQLite 承担热数据**：聊天历史（`chat_history.db`）、角色状态（`home_state.json` 等 JSON 文件）都是高频读写、单机一致的数据，用 SQLite 零运维、低延迟，进程内读写。
- **PostgreSQL (Supabase) 承担云侧**：知识库、跨设备同步、备份与审计。连接串来自运行时配置，代码内零真实值。
- **分层逻辑**：本地状态必须"活着随时可读"（Web 与企微双入口共用同一 SQLite，回复与状态实时一致）；云侧数据允许一点延迟换可靠与容量。一句话：**热数据本地化、冷数据云端化**。

## 2. 主动触发怎么防骚扰？

- **心跳循环先评估再行动**：`proactive/runner.py` 常驻 tick，`AwakeningConfig(think_threshold=0.15, speak_threshold=0.0)` —— 用 think 阈值控制"要不要想"，控制频率，避免每 60 秒烧一次 token。
- **可用性门控**：主对话循环按状态拦截——睡觉 / 比赛 / 会议场景直接走自动回复，训练间隙允许短消息；连续未回触发安抚兜底而不是追加推送。
- **旁路节流**：看球发起有 30 分钟节流（`_last_watch_attempt`）；日记只在目标时区 22:00 后且当天未写时才触发。
- **原则**：主动性做过头就是骚扰，"克制"是产品判断也是工程约束。

## 3. 多模型路由怎么保证一致性？

- **统一出口**：所有 LLM 调用走 `config.py` 的 `llm_model() / llm_base_url() / llm_api_key() / llm_key_id()`，`effective_config()` 按峰谷 + 来源返回当前生效配置，调用方不感知切换。
- **同族模型**：DeepSeek 官方与火山方舟均为 DeepSeek 系模型，指令风格一致；切换只换 endpoint/model，**系统提示词与对话状态不变**，所以行为连续。
- **能力开关统一**：深度思考（thinking）开关经 `llm_extra_body()` 三 API 统一启停，不会出现"这个 API 开了思考、那个没开"的差异。
- **配额回退可预期**：`api_usage.py` 按 key_id 本地累计 token，`_api2_remaining` 算剩余额度，兜底链 api3 → api2 → api1 是确定性的。

## 4. 情感引擎为什么独立进程？

- **可观测**：情感是连续状态（longing / intimacy / vitality / jealousy / anxiety / contentment 等多维值），独立进程 + `drives_health.py` 生成健康报告，能看趋势、能报警。
- **可测试**：`scripts/simulate.js` 可离线模拟对话序列验证情感漂移，不依赖真实 LLM。
- **跨语言复用**：REST + MCP 双入口，Python 主循环用 HTTP 拉取，其他 MCP 客户端也能消费——情感状态机与"谁在聊天"解耦。
- **故障隔离**：主对话循环拉取失败时静默返回空串（`get_drives_context` 失败不阻塞聊天），情感引擎挂了不影响主回复。
- **架构意义**：把"情感"从 prompt 里的一次性文本，变成可持久化、可观测、可测试的状态机。

## 5. iOS Safari 兼容踩了哪些坑？

- **地址栏伸缩导致视口跳动**：用 `position:fixed` 全屏容器 + `100vh/max-height:100vh` 兜底，避免软键盘顶起时布局错位。
- **毛玻璃不生效**：Safari 只认 `-webkit-backdrop-filter`，需要与标准属性双写。
- **滚动穿透 / 橡皮筋回弹**：`-webkit-overflow-scrolling:touch` + `overscroll-behavior:contain` 一起处理。
- **时间格式化差异**：Safari 对 `toLocaleString` 兼容不稳，改用 `Intl.DateTimeFormat`（还用了 `sv-SE` / `en-GB` 区域技巧拿固定格式）。
- **时区不一致**：前端时间显示与后端共用 `APP_TIMEZONE`（前端 `APP_TZ` 常量），支持任意 IANA 时区、默认 UTC，杜绝"前后端各说各的时间"。

## 6. RAG 按需检索怎么控制成本？

- **关键词触发**：每个知识库配独立 `frozenset` 关键词表，**日常聊天完全不检索**；只有用户消息命中关键词才注入对应知识片段——省 token、不干扰闲聊。
- **向量库懒加载**：文件变更按 mtime 自动重建（`store.py`），不是每次启动全量索引。
- **缓存与上限**：天气 30 分钟缓存、思考链 120 字上限、逐请求 token 用量日志（`api_usage.py`）——成本可计量、可追溯。
- **失败静默**：所有旁路能力（日记 / 朋友圈 / 赛程 / 知识库）失败不影响主回复。

## 7. 角色状态机怎么防"穿帮"？

- **三层日期**：`home_state.json` 维护 today / yesterday / day_before，`date_roller.py` 按目标时区（`APP_TIMEZONE`）自动滚动，过期状态自动失效——跨天不穿帮。
- **聊天信号回写**：聊天中模型提到"回家了"等信号，会回写状态覆盖，保持"状态一致"。
- **状态即事实**：天气、赛程、情感引擎都读取同一份状态/时区，不会出现"状态说在家、天气却说在客场"的矛盾。

## 8. 企业微信回调怎么保证安全与可靠？

- **签名校验**：`wecom/crypto.py` 用 SHA1 校验回调消息签名，token + 密钥都在运行时配置，防伪造回调。
- **推送稳定性**：access_token 带锁缓存、过期自动刷新（`push.py`），避免并发刷新与限流。
- **消息去重**：`dedup.py` 对重复回调去重，防止重放导致重复回复。
- **多进程守护**：回调服务独立进程，`start_wecom*.bat` 幂等启动（端口占用检查、防重复拉起），日志独立落盘。

## 9. MCP 适配层为什么用 npx 子进程 + stdio？

- **零本地依赖污染**：`_mcp_call` 用 `npx -y football-api-mcp` 临时拉起第三方 MCP server，不污染项目依赖。
- **协议简单可控**：stdio + JSON-RPC 2.0，`initialize(protocolVersion 2024-11-05) → notifications/initialized → tools/call`，逐行 JSON 收发。
- **超时与静默**：初始化 10s / 调用 20s 超时，失败静默返回，不影响主对话。
- **密钥隔离**：API Key 经环境变量（`FIVEDOLLARFOOTBALL_API_KEY`）注入子进程，代码内零真实值。
- **服务端示例**：Drivesoid 的 `src/mcp-server.js` 提供 `drives_sleep` / `drives_event` / `drives_context` 三个工具，证明这套适配层双向可通。

## 10. 多进程部署与运维怎么搭？

- **三个独立进程**：移动端 Web（`home_server.py`）、主动触发心跳（`runner.py`）、企微回调（`wecom/run.py`），互不阻塞、各自守护；可选情感引擎（Drivesoid）。
- **幂等启动**：`start_*.bat` 做端口占用检查，防止重复拉起。
- **内网穿透**：穿透进程随服务启动，保证公网回调可达。
- **开机自启**：启动脚本可注册自启项；各进程日志独立落盘，网络层诊断日志辅助排障。
- **配置外置**：API Key / 连接串 / 企微凭据全部在运行时配置文件（`~/.reunion/config.json`、`wecom_config.json`），仓库内只有占位符。
