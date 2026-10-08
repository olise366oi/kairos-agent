# SECURITY REDACTION REPORT

作品集仓库 `本作品集仓库` 脱敏报告（含第一轮脱敏与第二轮时区/标识符修正）。撰写日期：2026-10-05。

## 1. 已删除文件清单（路径 + 原因）

以下文件/目录在原项目中存在，**未复制入仓**。路径为原项目相对路径。

### 密钥与连接凭据

| 路径 | 原因 |
| --- | --- |
| `backend/.env`、`backend/home/.env` | 数据库连接串、API Key |
| `sidecar/Drivesoid/.env` | 情感引擎 API Key |
| `~/.kairos/config.json`、`~/.kairos/volc_ak_sk.txt` | 运行期 LLM 配置与云账户签名密钥（运行期数据目录，未触碰） |

### 个人身份 / 剧情 / 对话数据

| 路径 | 原因 |
| --- | --- |
| `backend/persona/`（含 `persona*.md`、`persona_distilled*`） | 角色人设 |
| `~/.kairos/persona.md`、`memory_core.txt`、`profile.txt`、`trivia.txt`、`nutrition_kb.txt`、`psych_kb.txt` | 角色记忆与知识库数据（运行期数据目录） |
| `~/.kairos/home_state.json`、`moments.json`、`diary.json`、`clipboard.json`、`watch_state.json`、`call_state.json`、`chat_history.db`、`schedule.txt`、`match_results.json` 等 | 对话历史 / 状态 / 朋友圈 / 日记 / 赛程（运行期数据目录） |
| `backend/data/`、`backend/logs/`、`backend/home/*.log`、根目录 `*.log` | 运行日志（含对话与诊断信息） |
| `backend/_all_chat.txt`、`_recent_chat*.txt`、`_fights_*.txt`、`_tracks_*.txt` 等 | 对话导出与私人关系时间线 |
| `backend/home/assets/`、`backend/home/_shots/`、`reunion_icon_src.png` | 个人照片 / 截图 / 图标素材 |
| `sidecar/Drivesoid/drives.config.json`、`drives-personas-context.md` | 真实角色配置与个人语境 |
| `backend/chat/`、`backend/api/`、`backend/prompts/` | 对话工具 / 接口 / 提示词工程目录 |

### 一次性调试脚本与临时产物

根目录 `add_*.py`、`fix_*.py`、`check_*.py`、`test_*.py`、`analyze_*.py`、`update_*.py`、`diff_check.py`、`find_all_intercepts.py`、伴侣相关的一次性检查脚本 等；`backend/_*.py` 大量 `_fix/_probe/_peek/_set/_test/_check/_backup/_diag/_scan` 等一次性脚本；`backend/home/_*.py` 同类脚本；`_check_syntax.py`、`_final_check.py`、`_supabase_connect_test.py`、`_supabase_schemas.py` 等 —— 含真实路径、临时逻辑、调试输出，非成品代码。

### 未纳入展示范围的功能模块

| 路径 | 原因 |
| --- | --- |
| `src/`、`electron/`、根目录 `package.json` / `vite.config.ts` / `tsconfig.json` / `index.html` | 桌面端（React + Electron 悬浮球）未在本次展示范围，如需可后续脱敏纳入 |
| `sidecar/VisionBridge`、`sidecar/VoiceASR` | 视觉 / 语音 sidecar，未要求纳入 |
| `tools/ielts-ai-dataset-raw`、`tools/tungo` | 数据集 / 实验目录 |
| `docs/superpowers/`、`scripts/` | 内部文档与工具脚本 |
| `backend/main.py`、`proactive.py`、`weekly_check.py`、`health.py`、`archive.py`、`availability.py`、`call_promise_manager.py`、`channel_monitor*.py`、`web_tunnel_monitor.py`、`volc_balance.py`、`start_channel_monitor.bat` 等 | 运维 / 监控 / 守护模块（`channel_monitor.py` 含原机绝对路径），按需可后续纳入 |
| `backend/home/status_rule.py`、`next_match.py`、`match_fetcher.py`、`match_news.py`、`calendar_builder.py`、`date_plans_manager.py`、`sync_fridge_names.py`、`start_home.bat` 等 | 未被复制清单点名但有耦合的辅助模块；代码中的引用保留，运行需完整环境 |

### 依赖与构建产物

`node_modules/`、`package-lock.json`、`backend/drivesoid/node_modules/`、`backend/drivesoid/package-lock.json`、原项目 `.git/`、Drivesoid 自带 `.git/`、`__pycache__/`、`*.pyc`、`backup/`。

## 2. 已替换敏感字段类型（类别 + 替换为）

| 类别 | 替换为 |
| --- | --- |
| 人名（用户侧，含昵称） | `user` |
| 人名（AI 角色侧，含中文名 / 罗马音 / 音译 / 英文名） | `companion` |
| JSON 键 / 变量名 / 标识符中的角色名 | 中性标识（`companion` / `rin_*`→`companion_*` 类） |
| 城市（多个城市名） | `city` |
| 家乡（一个地名） | `home` |
| 时区文字（“xx时间 / xx时区”） | `city时间 / city时区` |
| IANA 时区字面量 `Europe/Paris`（17 处） | `TIMEZONE`（env `APP_TIMEZONE`，默认 `UTC`）；前端 JS 用 `APP_TZ` |
| 自建隧道域名 / 云数据库域名 | `YOUR_DOMAIN` |
| PostgreSQL 连接串 | `YOUR_DB_URL` |
| API Key（足球数据 / 云数据库账号密码 / 兜底 `sk-*`） | `YOUR_API_KEY` |
| 云服务实例标识（docstring 中的资源后缀） | 编号（2 号 / 3 号） |
| 本地绝对路径（用户目录 / 项目目录 / 数据目录） | `./data` / `YOUR_PATH` / `~/.kairos` |
| 剧情数据（纪念日、医疗诊断词、亲密规则、恋爱时间线等） | 占位符 / 删除 / 中性表述 |
| 素材文件名中的角色名缩写 | 中性文件名 |

## 3. 仍未处理但已知的项目

- **两处写死 UTC+2 小时偏移**（主对话循环的“明天计划”时间锚点、Web 端电话接通时间标签）：已中性化为变量名，但 +2 常量保留；建议后续改为按 `APP_TIMEZONE` + DST 计算。
- **未入库模块的导入引用**：`status_rule`、`next_match`、`match_fetcher`、`match_news`、`chat.history` 等模块不在复制清单内，代码中的 `import` 保留（展示用途，运行需完整环境）。
- **公开信息保留**：球队 / 联赛名（已抽象化）、公开品牌（iMessage / FaceTime）、公开 API 域名（DeepSeek / 火山方舟 / Open-Meteo / 企业微信）。
- **桌面端未纳入**：`src/`、`electron/`（React + Electron），如需展示可单独脱敏。
- **许可边界**：Drivesoid 为独立组件，保留其原始 `LICENSE`（CC-BY-NC-SA-4.0）与示例配置模板；根目录 `LICENSE`（MIT）仅覆盖本仓库原创代码。

## 4. 敏感词扫描命令与结果概述

扫描方式：对 `本作品集仓库` 全库执行正则匹配（区分大小写按词表），词表覆盖：人名（含中文 / 音译 / 罗马音 / 英文名）、城市与家乡名、自建隧道域名、云数据库域名与连接串关键字、足球数据 API Key 前缀、账户密码片段、纪念日日期、Windows 用户目录名、原项目绝对路径、医疗诊断词、剧情关键词等。扫描范围为仓库内**代码与数据文件**；本报告文件作为脱敏记录文档，包含被替换项字面量（如 `Europe/Paris`）属预期，不计入残留。

实际执行结果（撰写时运行所得）：

| 校验项 | 结果 |
| --- | --- |
| 敏感词全库扫描（约 60 项词表，含新增 Drivesoid / companion-awakening / api_usage） | **0 命中** |
| `Europe/Paris` / `paris` / `Paris` 残留扫描 | **0 处** |
| Python 语法校验（`py_compile`，46 个 `.py`，含新增文件） | **全部通过，0 失败** |
| Git 工作区检查 | 干净；无 `.env` / `*.db` / `*.log` / `__pycache__` / `node_modules` 混入 |

说明：以上数值为本次报告撰写时对仓库实际执行所得，非预设值；后续若新增文件需重跑同口径扫描。

## 5. 迭代脱敏记录

脱敏不是一次性操作。首轮脱敏后，在后续全仓审查与工程化改造中又发现并修复了以下漏网项：

| 漏网项 | 位置 | 修复方式 |
| --- | --- | --- |
| 拼音残留 `ringing_from_rin / ringing_from_asu` | `call_manager.py` + 前端 JS | 改为 `ringing_from_companion / ringing_from_user` |
| 真名 `Olise` / `Olise_Tu` | `home.html` 朋友圈显示名 + MOMENT 文案 | 改为 `user` |
| 球员名映射表 `NAME_MAP`（含姆巴佩 / 哈兰德等） | `home.html` 行程卡片渲染 JS | 随行程卡片删除一并清除 |
| 剧情账号 `@companion_ltoshi` / `@Olise_Tu` | `home.html` MOMENT 文案 | 删除账号提及，剧情文案中性化 |
| 脱敏占位死路径 `YOUR_PATH` | 约 50 处 `sys.path.insert` + 5 处活代码路径 | 死代码删除（run.py 已注入真实路径），活代码改为 `Path(__file__)` 动态路径 |
| 反斜杠路径 `Path(r"./data\...")` | 19 处 + 后续审查再发现 5 处 | 统一改为正斜杠（跨平台兼容） |
| 隧道名 `foreverlove.tunnel` | `call_manager.py` / `watch_manager.py` | 改为环境变量 + 占位默认值 `https://your-tunnel.example.com` |
| 硬编码 `HOME_TOKEN = "kairos_home_2026"` | `home_server.py` | 改为 `os.environ.get("HOME_TOKEN")` + 启动检查 + `hmac.compare_digest` |
| 法语球队 / 城市关键词 | `loop.py` `SCHEDULE_KEYWORDS` | 具体队名整行删除，保留通用足球词 |
| 半脱敏重复词 `companion（companion）` | `loop.py` retry_system prompt | 重写为中性角色兜底 prompt |

这些修复已全部合入仓库，最终 `grep` 确认 0 残留。说明脱敏是迭代收敛过程：首轮批量替换后，仍需结合运行时审查、代码走读与真实使用场景二次清理。

