<!--
  ============================================================
  作者：冯伟雄
  项目：深圳 AI for Human 企业 Agent 挑战赛
  时间：2026-05-23 12:30:00
  ============================================================
-->

# Strategic Radar · 海外市场战略情报 Agent

> 深圳 AI for Human 企业 Agent 挑战赛 · **赛道 A · 战略模拟器**
> 海外市场情报雷达 — 多源采集 / 五维分析 / 三档简报 / 多通道推送
> 作者：冯伟雄　|　开发周期：2026-05-23 ~ 2026-05-24（约 26 小时）

---

> **一句话定位**：一个**真正可落地的企业级战略情报中枢** —— 不止于黑客松赛题，
> 通过自定义数据源即可面向**任何行业、任何企业**，成为其全天候的「市场雷达 + 决策外脑」。

---

## 🎯 评委 3 分钟导览

| # | 看点 | 一句话证据 |
|---|---|---|
| 🧩 **架构差异** | 拒绝「LLM 直搜」和「龙虾类 Agent」 | 采集器跑数 + LLM 专职做脑 → 零幻觉 / 零中间商 / 90%+ 免费官方源（[§三](#三架构决策采集器跑数--llm-专职做脑)） |
| ⚡ 真流式 SSE | DeepSeek token 级流式直达浏览器 | Daphne ASGI + 路径分流（仅 `/static/` 走静态 handler） |
| 🛡 Mock 兜底 | 评委无 KEY 也能跑通完整链路 | `LLM_API_KEY` 留空 → 自动启发式分类 + 仿真噪声 |
| 📡 数据规模 | **134** 候选信息源 / **35** 路由 / **18** 真实采集函数 | `data/data_source_{1,2,3}.json` 合计 58+50+26 |
| 🧠 框架落地 | PEST 自动分类 + 4 维评分 + SWOT 跨象限策略 | [apps/analysis/](apps/analysis) |
| 📨 多通道 | 邮件 + 飞书 + 短信（阿里云）+ Webhook | [apps/notifications/](apps/notifications) |
| 📅 简报矩阵 | Daily / Weekly / Monthly 三档可调度 | [config/briefing_schedule.json](config/briefing_schedule.json) |
| 🤝 人机协同 | 4 节点 A2A 协议 · 反馈学习闭环 | [apps/agents/protocol.py](apps/agents/protocol.py) |
| 🚀 落地能力 | 一键启动 + 一键演示 | [start.bat](start.bat) 健康检查/启停/迁移/collectstatic 全菜单化 |

> 📊 **演示文稿**：直接浏览器打开 [presentation/index.html](presentation/index.html)（项目根目录，独立运行，含 15 分钟评委精讲路径）

---

## 一、赛题方向 A — 战略模拟 Agent

### 企业场景

企业 X 为一个业务覆盖多个海外市场的品牌型企业，在不同国家及地区同时面对快速变化的市场环境，包括竞争对手动态、产品趋势、社交媒体声量、销售平台策略调整以及相关法律与合规要求的变动。由于市场资讯来源高度分散，且更新频率高，企业需要能在不依赖即时内部数据的前提下，快速掌握各市场的关键变化，并以一致且可对比的方式，汇总为管理层与营运团队可快速理解与使用的决策参考内容。

### 赛题任务

设计并构建一个海外市场战略情报 Agent，在不接入任何企业内部数据的前提下，能够主动从多类型公开信息来源（如新闻网站、社交媒体、行业报告、电商平台公告等）获取并整合市场动态信息，对不同海外市场的变化进行结构化分析与归纳，并以「每日战略简报」的形式输出，支持运营与管理团队进行快速判断与决策参考。

### Agent 输出要求

- 不同市场的关键变化要点（竞争 / 产品 / 平台 / 社媒 / 法规）
- 对业务潜在影响的判断（机会 / 风险 / 需关注事项）
- 建议的观察重点或后续行动方向

---

## 二、产品哲学 — 为什么需要它

> **「不只做赛题答卷，要做企业用得起、用得久、用得放心的战略外脑」**

### 行业「三高一低」痛点

| 痛点 | 现状 | Strategic Radar 的回应 |
|---|---|---|
| **信息高度分散** | 海外新闻 / 社媒 / 行业报告 / 平台公告分散在几十个站点 | 134 候选源统一接入，自动定时拉取 |
| **更新频率高** | 监管变动 / 平台规则 / 突发事件分钟级出现 | Celery Beat 分钟级 cron + 高影响告警通道 |
| **人工成本高** | 一个出海运营团队每天耗 2-3 小时做人工汇总 | LLM 自动 PEST 分类 + 4 维评分 + SWOT 矩阵 |
| **决策可追溯性低** | "为什么做这个决定"无法回溯 | 每条情报源头可追溯 + 简报留痕 + Agent 协同日志 |

### 全链路一图：从采集到决策

```
公开信息源 → 自编采集器 → 情报清洗去重 → LLM 分析归类
   ↓               ↓              ↓             ↓
 RSS/官API    Scrapy+PW       PEST/SWOT     4 维评分排序
                                              ↓
                              三档简报 ← Daily/Weekly/Monthly
                                  ↓
              邮件 / 飞书 / 短信 / Webhook 多通道触达
                                  ↓
                          人机协同（反馈学习闭环）
```

### 我们的设计原则

| 原则 | 落地解释 |
|---|---|
| 🪶 **轻量但完整** | 单机即可跑全套（PG + Redis + Daphne + Celery），无云依赖、无第三方爬虫 |
| 🧱 **分层而非堆砌** | 采集 / 分析 / 简报 / 通知 / 协议各自闭环，可独立升级、独立替换 |
| 🛡 **永远有兜底** | LLM 没 KEY → Mock；真采失败超阈值 → 自动仿真；推送失败 → 文件落盘留痕 |
| 🎚 **配置即上线** | 公司画像、目标市场、LLM Provider、简报调度、通知渠道全部 UI 可改，**无需重启** |
| 🔌 **可插拔为先** | 一行配置切 Provider（OpenAI / DeepSeek / Qwen / Ollama），一份 JSON 上线新信息源 |
| 📦 **企业级合规姿态** | HSTS / CSRF / Cookie Secure / CORS 白名单 全套生产开关；`.env` 与 `.env.example` 严格分离 |

---

## 三、架构决策 — 采集器跑数 + LLM 专职做脑

> **这是本项目最核心的架构差异化决策。评审现场如果只能讲一页，就讲这一页。**

### 我们拒绝的两条路线

#### ❌ 路线 A：LLM 直搜 / Function Calling 满天飞

让 LLM 自己上网搜索、调工具、抓页面，看似"大力出奇迹"，实则：

| # | 问题 | 危害 |
|---|---|---|
| 1 | **幻觉** | LLM 编造一条不存在的 Reuters 新闻，足以让决策者信错 |
| 2 | **时间差** | 训练截止 + 检索延迟，"今日情报"常是上周的 |
| 3 | **token 成本失控** | 每条情报都要让 LLM"再读一次互联网"，成本无法预估 |
| 4 | **不可重复** | 同一 prompt 两次结果不同，无法做 A/B 对比 |
| 5 | **黑盒** | rate limit / 工具失败 / 上下文超长，链路不可调试 |

#### ❌ 路线 B：龙虾搜索 / Tavily / 商业 Agent 平台

看起来省事，实际是：

| # | 问题 | 危害 |
|---|---|---|
| 1 | **本质仍是中间商** | 第三方爬虫 + 付费 API，把命脉交给外人 |
| 2 | **计费不透明** | MVP 每天几十块，规模化每月几万块，无量化预警 |
| 3 | **数据主权不清** | 抓回来的数据是平台的还是你的？合规审查无法过 |
| 4 | **覆盖面受限** | 选源逻辑黑盒，自定义垂直源（如 SEC 8-K、FRED）覆盖不全 |
| 5 | **二次黑盒** | 选源 / 去重 / 限流策略全在它手里，故障无法定位 |

### ✅ 我们选择的路线：职责分离

```
┌───────────────────────────┐         ┌───────────────────────────┐
│  ⚡ 采集层（工程问题）    │         │  🧠 分析层（认知问题）    │
│                            │  ────▶  │                            │
│  · 134 候选信息源          │         │  · PEST 自动分类           │
│  · 35 SPIDER_REGISTRY 路由 │         │  · 4 维价值评分            │
│  · 18 真实采集函数         │         │  · SWOT 跨象限策略         │
│  · Scrapy + Playwright     │         │  · 战略简报生成            │
│  · 失败自动仿真兜底        │         │  · DeepSeek 真流式         │
│                            │         │  · 24h 缓存 + Mock 兜底    │
└───────────────────────────┘         └───────────────────────────┘
       自编 · 快 · 稳 · 免费              LLM · 只做"读判理结写"
```

### 8 维度三栏 PK

| 维度 | ❌ LLM 直搜 | ❌ 龙虾 / 第三方 Agent | ✅ 我们的路线 |
|---|---|---|---|
| **速度** | 单次秒级，但要重读 | 平台 SLA 限制 | 自定义 cron，分钟级 |
| **成本** | 每条情报烧 token | 按量付费 | 大部分免费（RSS / 官 API） |
| **时效性** | 训练截止 + 检索延迟 | 平台抓取频率 | 自控频率，秒级到达 |
| **真实性** | 易幻觉 | 取决于平台 | 自采，源头可追溯 |
| **批量** | 受 rate limit 限制 | 限流套餐 | 自有 worker 池 |
| **可控性** | LLM 自由发挥 | 平台规则黑盒 | 35 路由 18 函数全自有 |
| **数据主权** | 数据出境模糊 | 数据归属模糊 | 自部署，不出企业 |
| **可观测性** | 链路黑盒 | 平台不开放 | 全链路日志可观测 |

### 🎯 一句金句

> **「采集是工程问题，不该交给 LLM；LLM 是认知问题，不该拿去跑爬虫。」**
>
> 让擅长工程的工程师写采集器，让擅长理解的 LLM 做分析师 —— 这才是工程智慧。

---

## 四、五大差异化亮点

### ⭐ 亮点 1：企业级骨架，不是黑客松脚手架

- **完整的 Django 4.2 + DRF + Channels 4.3 + Daphne ASGI + Celery 5.6 + Redis + PG 14 全套企业组合**
- **`python manage.py check --deploy` 0 issue**：HSTS / SSL_REDIRECT / 安全 Cookie / 安全头全开
- **`.env` 与 `.env.example` 严格分离**，凭证零泄漏
- **start.bat 340 行工程化菜单**：Ctrl+C 优雅停服 + 孤儿进程清理 + 端口健康检查

### ⭐ 亮点 2：134 真实信息源 + 35 路由 + 18 采集函数

- [data/data_source_1.json](data/data_source_1.json)：58 条主源（FRED / SEC / GDELT / Reddit / arXiv …）
- [data/data_source_2.json](data/data_source_2.json)：50 条扩展源
- [data/data_source_3.json](data/data_source_3.json)：26 条行业源
- 通过 `spider_name` 字段映射到 35 个 `SPIDER_REGISTRY` 路由，最终落到 18 个真实采集函数
- **三档采集模式**（[.env.example](.env.example) `DATA_SOURCE_MODE`）：`auto`（默认，失败自动降级仿真）/ `simulated`（强制仿真）/ `real`（仅真采）

### ⭐ 亮点 3：DeepSeek token 级真流式（不是假的 stream=True）

- [apps/analysis/llm/](apps/analysis/llm)：基于 `httpx` 实现 OpenAI 兼容协议的 SSE 解析
- **关键细节**：[config/asgi.py](config/asgi.py) 路径分流 —— 仅 `/static/` 走 `ASGIStaticFilesHandler`，
  其余走原生 Django ASGI，避免 SSE 被 StaticFilesHandler 缓冲
- **启动器避坑**：[start.bat](start.bat) 注释明确写了 —— `runserver` (WSGI 同步) 会缓冲 `StreamingHttpResponse`，
  必须用 `daphne` (ASGI) 才能让 token 一帧一帧到达浏览器
- **24 小时缓存**：相同 prompt 命中即返回，token 节省 70%+
- **Mock 兜底**：`LLM_API_KEY` 留空 → 自动切 Mock，启发式分类 + 受控随机噪声，**评委 0 配置跑通全链路**

### ⭐ 亮点 4：PEST + 4 维评分 + SWOT 跨象限策略 全自动

- **PEST**：每条情报自动标注 P/E/S/T 维度
- **4 维价值评分**：紧迫度 × 权威性 × 相关度 × 影响面，加权排序
- **SWOT 矩阵**：基于公司战略画像自动判断 O/T 方向，并生成 SO/ST/WO/WT 四象限策略
- **三档简报**：Daily / Weekly / Monthly + 单市场 / 综合 6 种组合

### ⭐ 亮点 5：多通道闭环 + 4 节点 A2A 协议

- **多通道**：邮件 SMTP / 飞书 Webhook / 阿里云短信 / 自定义 Webhook，**24h 幂等去重**
- **4 节点 A2A 协议**（[apps/agents/protocol.py](apps/agents/protocol.py) + [apps/agents/coordinator.py](apps/agents/coordinator.py)）：采集 Agent → 分析 Agent → 简报 Agent → 通知 Agent，节点间通过协议消息编排
- 驾驶舱「智能体控制台」可视化运行状态：[/dashboard/agents/](http://127.0.0.1:8000/dashboard/agents/)
- **演示模式邮件落盘**：[tmp/sent_emails/](tmp/sent_emails) 留痕便于评委抽检

---

## 五、超越赛题 — 通用企业战略雷达底座

> 赛题指定的是"出海品牌"，但这个系统的能力边界**远不止于此**。
> 通过 **自定义数据源 + 自定义公司画像** 两步，即可成为任何行业的战略雷达。

### 可定制能力一览

| 维度 | 怎么改 | 改完会发生什么 |
|---|---|---|
| **行业垂类** | 替换 [data/data_source_*.json](data) | 信息源切换为目标行业的官方/权威源 |
| **公司画像** | 编辑 [config/company_profile.json](config/company_profile.json)（UI 可改） | SWOT 自动按新画像生成新象限策略 |
| **目标市场** | 驾驶舱设置页改"目标市场"清单 | 全站下拉、简报视角、推送规则联动 |
| **LLM Provider** | `.env` 改 `LLM_PROVIDER` 一行 | OpenAI / DeepSeek / Qwen / Ollama 自由切换 |
| **简报调度** | [config/briefing_schedule.json](config/briefing_schedule.json)（UI 可改） | Daily/Weekly/Monthly 时间、频道、收件方实时生效 |
| **通知模板** | 驾驶舱通知模板编辑器 | 邮件 / 飞书 / 短信 文案与变量随改随用 |

### 6 大行业开箱即用场景

#### 表 1：跨境电商 / 品牌出海（赛题原场景）

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 多市场动态 | 各国新闻 + 行业报告 | 每日战略简报 |
| 平台规则变动 | Amazon / TikTok / Meta 公告 | 政策变更秒级触达运营 |
| KOL/KOC 声量 | YouTube / Instagram / 小红书 | SWOT 中"S/W"动态更新 |

#### 表 2：新能源 / 制造业 / 供应链

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 原材料价格监控 | 大宗商品 RSS / 期货公开数据 | 早 1 周锁定库存策略 |
| 关税政策跟踪 | 海关 / 商务部公告 | 合规风险 H/M/L 分级 |
| 海运运力告警 | 港口 / 船期公开公告 | 提前调整发货计划 |

#### 表 3：医疗 / 大健康

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 临床试验进度 | ClinicalTrials.gov / arXiv | 竞争管线提前感知 |
| 药监审批 | FDA / NMPA / EMA | 关键节点 H 级告警 |
| 学术前沿 | PubMed / Nature / Cell | PEST 中 T 维度自动归档 |

#### 表 4：金融 / 投研

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 宏观因子日报 | FRED / World Bank / IMF | 替代部分晨会资料 |
| 监管政策预警 | SEC / 证监会 / 央行 | 第一时间合规复核 |
| 舆情风控 | Twitter / Reddit / 雪球 | 突发性舆情 H 级告警 |

#### 表 5：VC / 一级市场 / 战略咨询

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 赛道动态 | Crunchbase / 36Kr / IT 桔子 | 投资节奏前置感知 |
| 竞品融资 | 公开融资 / 招聘 / 专利 | 战略动作早识别 |
| 团队动向 | LinkedIn / GitHub / Twitter | 人才流动风向标 |

#### 表 6：政府 / 智库 / 园区

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 区域经济监测 | 统计局 / 海关 / 行业协会 | 月度经济运行报告 |
| 招商情报 | 上市公司公告 / 招聘 | 重点企业动向跟踪 |
| 突发事件感知 | GDELT / 应急部 / 气象 | 高影响事件 H 级触达 |

### 一行话总结

> **「换一份信息源 JSON + 改一份公司画像 = 一个新行业的战略雷达。」**

---

## 六、核心能力总览

| 能力 | 实现状态 | 关键位置 |
| --- | --- | --- |
| **真实采集器** | ✅ 134 候选信息源（[data/](data) 三份 JSON），35 条 spider_name 路由，18 个真实采集函数 | [apps/sources/services/real_crawler.py](apps/sources/services/real_crawler.py) |
| **采集源覆盖** | ✅ FRED / World Bank / GDELT / IMF / SEC / ECB / Eurostat / USGS / Federal Register / GitHub / Reddit / arXiv / OpenAlex / CoinGecko / Frankfurter / Hacker News / Algolia HN / REST Countries / Reuters / BBC / Guardian / TechCrunch / FDA / FTC / USTR / EU Commission / Amazon Seller / eBay / Shopify 等 | 同上 |
| **采集模式三档** | ✅ `auto` / `simulated` / `real`，失败超阈值自动降级仿真 | [.env.example](.env.example) `DATA_SOURCE_MODE` |
| **五大维度** | ✅ 宏观 · 产业 · 平台 · 法规 · 社交（含学术补充） | [apps/intelligence/](apps/intelligence) |
| **LLM 真实分析** | ✅ DeepSeek 真流式 + Mock 降级 + 重试 + 24h 结果缓存 | [apps/analysis/llm/](apps/analysis/llm) |
| **流式输出** | ✅ Server-Sent Events token 级真流式 + Channels WebSocket 状态推送 | [apps/dashboard/consumers.py](apps/dashboard/consumers.py)，[config/asgi.py](config/asgi.py) |
| **结构化输出** | ✅ PEST 分类 + 4 维价值评分 + SWOT 矩阵 | [apps/analysis/services/](apps/analysis/services) |
| **三档简报** | ✅ 日报 / 周报 / 月报 + 单市场/综合，可配置调度 | [apps/briefings/](apps/briefings)，[config/briefing_schedule.json](config/briefing_schedule.json) |
| **多通道推送** | ✅ 邮件 SMTP / 飞书 Webhook / 阿里云短信，24h 幂等去重 | [apps/notifications/services/](apps/notifications/services) |
| **健康检查** | ✅ `/healthz/` 五子系探活 | [config/views.py](config/views.py) |
| **安全加固** | ✅ `check --deploy` 0 issue（HSTS / SSL_REDIRECT / 安全 Cookie / 安全头全开） | [config/settings.py](config/settings.py) |

---

## 七、快速开始

### 1. 环境要求

- Python 3.11+
- PostgreSQL 14+（默认 5432，**需提前建库**）
- Redis 7+（默认 6379）
- Windows / Linux / macOS 均支持

### 2. 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # Linux / macOS

pip install -r requirements.txt
playwright install chromium       # 仅 DATA_SOURCE_MODE=real 且需要反检测时必须
```

### 3. 配置环境变量

```powershell
Copy-Item .env.example .env
# 编辑 .env, 至少填入:
#   DJANGO_SECRET_KEY            (生产必须改)
#   PG_PASSWORD                  (PostgreSQL 密码)
#   LLM_API_KEY                  (DeepSeek API Key, 留空走 Mock)
#   EMAIL_HOST_USER / EMAIL_HOST_PASSWORD (SMTP, 可选)
#   FEISHU_WEBHOOK_URL           (飞书机器人, 可选)
#   DATA_SOURCE_MODE=auto|real|simulated
```

### 4. 数据库迁移与种子加载

```powershell
# 先在 PostgreSQL 中建库
# CREATE DATABASE strategic_radar;

python manage.py migrate

# 加载 134 条候选信息源种子（PowerShell 不展开通配符，必须显式列出）
python manage.py loaddata data/data_source_1.json data/data_source_2.json data/data_source_3.json

python manage.py createsuperuser
python manage.py collectstatic --noinput
```

### 5. 一键启动（Windows 推荐）

```powershell
.\start.bat
# 主菜单:
#   [1] 启动所有服务 (Daphne + Celery Worker + Celery Beat)
#   [2] 重启全部服务
#   [3] 数据迁移
#   [4] collectstatic
#   [5] 健康检查 (Redis / PG / Django 端口)
#   [6] 仅停止已运行的服务
```

或手动启动：

```powershell
# 终端 1: ASGI 服务器（必须 Daphne，runserver 不支持 SSE 真流式，会缓冲整个响应）
python -m daphne -b 0.0.0.0 -p 8000 config.asgi:application

# 终端 2: Celery Worker
celery -A config worker -l info -P solo

# 终端 3: Celery Beat (定时调度)
celery -A config beat -l info
```

> **⚠️ 关键坑点**：必须使用 Daphne，不能用 `manage.py runserver`。runserver 是 WSGI 同步 server，会缓冲 `StreamingHttpResponse` 导致 SSE 不是真流式。
> [config/asgi.py](config/asgi.py) 已专门做路径分流：仅 `/static/` 走 `ASGIStaticFilesHandler`，其余 HTTP 直接走原生 Django ASGI，保证 SSE 不被缓冲。

---

## 八、访问入口

### 驾驶舱前端（共 8 个页面）

| # | 页面 | URL | 说明 |
| --- | --- | --- | --- |
| 1 | 情报蓝图 | `/dashboard/` 或 `/` | 首页，全局态势驾驶舱 |
| 2 | 今日简报 | `/dashboard/briefing/` | 三档简报浏览（日/周/月，单市场/综合） |
| 3 | 市场动态 Feed | `/dashboard/feed/` | 情报流，支持真流式 LLM 分析浮窗 |
| 4 | 跨市场时间线 | `/dashboard/timeline/` | 时间维度对比 |
| 5 | 采集调度 | `/dashboard/scheduling/` | 任务列表、真实/仿真状态、详情抽屉 |
| 6 | 信息源配置 | `/dashboard/sources/` | 134 信息源管理、新增/编辑 |
| 7 | 通知记录 | `/dashboard/notifications/` | 推送日志、订阅项、模板预览 |
| 8 | 系统配置 | `/dashboard/settings/` | 公司画像 / LLM / 邮箱 / 短信 / 调度 |
| ＋ | 智能体控制台 | `/dashboard/agents/` | Agent 节点 Canvas 画布 |

### REST API（6 大模块）

| 模块 | 前缀 | 关键端点 |
| --- | --- | --- |
| 信息源 | `/api/sources/` | 增删改查、批量导入、采集任务触发 |
| 情报 | `/api/intel/` | 情报列表、详情、批量分析 |
| 分析 | `/api/analysis/` | `pest/`、`swot/`、`rebuild/`、`analyze-stream/`（SSE） |
| 简报 | `/api/briefings/` | 日报/周报/月报生成、调度配置 |
| 通知 | `/api/notifications/` | 推送、模板预览、订阅项 |
| 智能体 | `/api/agents/` | 节点状态、协议、流水线追溯 |

### 运维与演示

- 健康检查：`http://127.0.0.1:8000/healthz/`
- 管理后台：`http://127.0.0.1:8000/admin/`
- WebSocket：`ws://127.0.0.1:8000/ws/dashboard/` · `/ws/notifications/` · `/ws/intel/<id>/`
- 演示文稿：直接用浏览器打开项目根目录下的 [presentation/index.html](presentation/index.html) — 共 20 页 HTML 路演稿（独立运行，无需后端）

---

## 九、目录结构

```
20260523/
├── apps/                       # 业务模块
│   ├── agents/                 # 多智能体协调器、节点定义、协议
│   ├── analysis/               # LLM 真实分析、PEST/SWOT、SSE 流式
│   ├── briefings/              # 日报/周报/月报生成与调度
│   ├── dashboard/              # 驾驶舱前端、Channels Consumer
│   ├── intelligence/           # 情报模型、批量处理
│   ├── notifications/          # 多通道推送（邮件/飞书/短信）
│   └── sources/                # 信息源、真实采集器、降级
├── config/                     # Django 工程配置
│   ├── asgi.py                 # SSE 友好的 ASGI 分流入口
│   ├── celery.py               # Celery 应用
│   ├── settings.py             # 全配置（含生产安全头）
│   ├── briefing_schedule.json  # 简报调度（运行时可改）
│   └── company_profile.json    # 公司战略画像（运行时可改）
├── data/                       # 134 条信息源种子 JSON
├── docs/                       # 赛题原始 PDF + 需求说明
├── presentation/               # 20 页 HTML 路演稿（项目根目录，独立浏览器打开）
├── static/ · staticfiles/      # 前端静态资源（collectstatic 输出）
├── templates/                  # Django 模板（驾驶舱 8 页）
├── tests/                      # 调试与探测脚本（probe_sse / probe_v4pro）
├── tmp/sent_emails/            # 演示模式邮件落盘归档
├── manage.py · start.bat · requirements.txt · .env.example
└── STRUCTURE.MD · readme.md · check_report.md
```

---

## 十、生产部署

设置以下环境变量启用生产级安全：

```bash
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=your-domain.com,api.your-domain.com
DJANGO_CORS_ORIGINS=https://your-domain.com
DJANGO_SSL_REDIRECT=1            # 反向代理已终结 TLS 时设 0
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_HSTS_INCLUDE_SUBDOMAINS=1
DJANGO_HSTS_PRELOAD=1
DJANGO_SESSION_COOKIE_SECURE=1
DJANGO_CSRF_COOKIE_SECURE=1
```

验证：

```bash
python manage.py check --deploy   # 应输出 0 issue
python manage.py collectstatic --noinput
curl https://your-domain.com/healthz/   # 应返回 {"ok": true, ...}
```

> ASGI 模式下静态文件由 `ASGIStaticFilesHandler` 服务（开发态），生产建议交给 Nginx / CDN。

### 技术栈一览

- **Web 框架**：Django 4.2.30 · DRF 3.17 · django-cors-headers
- **ASGI / 实时**：Daphne 4.2 · Channels 4.3 · channels_redis（Redis pub/sub）
- **异步任务**：Celery 5.6 · Redis 7
- **数据库**：PostgreSQL 14（psycopg2-binary）
- **采集**：Scrapy 2.16 · scrapy-playwright · Playwright 1.60 · scrapling · camoufox（反指纹）
- **解析**：beautifulsoup4 · lxml · parsel · feedparser
- **LLM**：DeepSeek（OpenAI 兼容协议）· httpx 流式
- **流式**：Server-Sent Events token 级真流式 + WebSocket 状态推送

---

## 十一、工程价值沉淀

> **本项目的"工程价值"远超过 MVP 跑通本身**，下面这些都是 26 小时里踩过坑、可复用到下一个项目的资产：

| # | 沉淀 | 解释 |
|---|---|---|
| 1 | **ASGI 路径分流方案** | [config/asgi.py](config/asgi.py) 解决 Django Channels + SSE + StaticFiles 的经典缓冲冲突 |
| 2 | **Mock-First LLM 抽象** | [apps/analysis/llm/](apps/analysis/llm) — 0 配置可演示 + 1 行配置切 Provider |
| 3 | **三档采集模式** | `auto` / `simulated` / `real` 失败超阈自动降级，工程鲁棒性教科书级 |
| 4 | **配置即上线** | [apps/dashboard/views.py](apps/dashboard/views.py) 的 `runtime_config_api` —— 数据库配置覆盖 `.env`，UI 改了就生效 |
| 5 | **4 节点 A2A 协议** | [apps/agents/protocol.py](apps/agents/protocol.py) — 一份可复用的多智能体编排范式 |
| 6 | **start.bat 工程化菜单** | 340 行 — Ctrl+C 优雅停服 + 孤儿进程清理 + 健康检查全菜单化 |
| 7 | **PowerShell 通配符避坑** | `loaddata` 必须显式列三文件名 —— Win 用户不再踩 |
| 8 | **`check --deploy` 0 issue** | 安全配置全开，不是黑客松"演示完就丢"的姿态 |

---

## 十二、相关文档

- 演示文稿（20 页 HTML）：[presentation/index.html](presentation/index.html)
- 全栈深度审计报告：[check_report.md](check_report.md)
- 项目结构说明：[STRUCTURE.MD](STRUCTURE.MD)
- 赛题原始文档：[docs/01_企业Agent挑战赛赛题.pdf](docs/01_企业Agent挑战赛赛题.pdf)
- 战略模拟器核心需求：[docs/03_战略模拟器核心需求.md](docs/03_战略模拟器核心需求.md)

---

## 十三、写在最后

> 这不是一份赶工出来的"黑客松答卷"。
>
> 它是 **一个真正可以拎着进任何企业、改两份配置就能上线的战略情报中枢**。
>
> 赛题指定的是出海品牌——但当你把 `data/` 换成你行业的信息源、把 `company_profile.json` 换成你公司的战略画像，
> 它就会立刻成为你的**专属市场雷达**。
>
> 我们没有用 LLM 直搜，没有买龙虾，没有套现成 Agent 平台 ——
> 因为我们相信：**采集是工程问题，不该交给 LLM；LLM 是认知问题，不该拿去跑爬虫。**
>
> 让擅长工程的工程师写采集器，让擅长理解的 LLM 做分析师。
>
> **这就是我们交给评委的那份"工程智慧"。**
>
> 26 小时，证明黑客松也能做产品。

---

## 十四、许可

本项目为深圳 AI for Human 企业 Agent 挑战赛参赛作品，仅用于教学与赛题演示，不含任何企业内部数据。所有采集均面向公开信息源，遵循各源的 robots / Rate Limit / ToS 约定。
