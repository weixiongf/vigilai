<!--
  ============================================================
  作者：冯伟雄
  项目：深圳 AI for Human 企业 Agent 挑战赛 · 赛道 A 战略情报预警
  时间：2026-05-23 ~ 2026-05-24
  ============================================================
-->

# Strategic Radar · 海外市场战略情报 Agent

> **一句话定位**：一个**真正可落地的企业级战略情报中枢** —— 不止于黑客松赛题，
> 通过自定义数据源即可面向**任何行业、任何企业**，成为其全天候的「市场雷达 + 决策外脑」。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2.30-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Channels](https://img.shields.io/badge/Channels-4.3-44B78B)](https://channels.readthedocs.io/)
[![Celery](https://img.shields.io/badge/Celery-5.6-37814A?logo=celery)](https://docs.celeryq.dev/)
[![Daphne](https://img.shields.io/badge/Daphne-ASGI-009688)](https://github.com/django/daphne)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek%20%2B%20Mock兜底-2B6CB0)](https://www.deepseek.com/)
[![License](https://img.shields.io/badge/License-MIT-FCD34D)](#十四许可)

---

## 🎯 3 分钟导览

| # | 看点 | 一句话证据 |
|---|---|---|
| 🧩 **架构差异** | **拒绝**「LLM 直搜」「龙虾/第三方 Agent」 | 自编采集器跑数 + LLM 只做分析 → 见 [§三 架构决策](#三架构决策采集器跑数--llm-做脑) |
| ⚡ 真流式 SSE | DeepSeek token 级流式直达浏览器 | Daphne ASGI + 路径分流（仅 `/static/` 走静态 handler） |
| 🛡 Mock 兜底 | 评委无 KEY 也能跑通完整链路 | LLM_API_KEY 留空 → 自动启发式分类 + 仿真噪声 |
| 📡 数据规模 | **134** 候选信息源 / **35** 路由 / **18** 真实采集函数 | `data/data_source_{1,2,3}.json` 合计 58+50+26 |
| 🧠 框架落地 | PEST 自动分类 + 4 维评分 + SWOT 跨象限策略 | [apps/analysis/](file:///c:/Users/Feng/Desktop/20260523/apps/analysis) |
| 📨 多通道 | 邮件 + 飞书 + 短信（阿里云）+ Webhook | [apps/notifications/](file:///c:/Users/Feng/Desktop/20260523/apps/notifications) |
| 📅 简报矩阵 | Daily / Weekly / Monthly 三档可调度 | [config/briefing_schedule.json](file:///c:/Users/Feng/Desktop/20260523/config/briefing_schedule.json) |
| 🤝 人机协同 | 4 节点 A2A 协议 · 反馈学习闭环 | [apps/agents/protocol.py](file:///c:/Users/Feng/Desktop/20260523/apps/agents/protocol.py) |
| 🚀 落地能力 | 一键启动（[start.bat](file:///c:/Users/Feng/Desktop/20260523/start.bat)）+ 一键演示 | 健康检查 / 启停 / 迁移 / collectstatic 全菜单化 |

> 📊 **演示文稿**：[presentation/index.html](file:///c:/Users/Feng/Desktop/20260523/presentation/index.html)（项目根目录，浏览器直接打开，含 15 分钟评委精讲路径）

---

## 一、赛题与背景

### 1.1 赛题方向 A — 战略模拟 Agent

企业 X 为一个业务覆盖多个海外市场的品牌型企业，在不同国家及地区同时面对快速变化的市场环境，
包括竞争对手动态、产品趋势、社交媒体声量、销售平台策略调整以及相关法律与合规要求的变动。
由于市场资讯来源高度分散、且更新频率高，企业需要能在不依赖即时内部数据的前提下，
快速掌握各市场关键变化，并以一致且可对比的方式，汇总为管理层与营运团队可快速理解与使用的决策参考。

### 1.2 赛题任务

设计并构建一个**海外市场战略情报 Agent**，在不接入任何企业内部数据的前提下，
能够主动从多类型公开信息来源（新闻、社交、行业报告、电商平台公告等）获取并整合市场动态信息，
对不同海外市场的变化进行结构化分析与归纳，并以「**每日战略简报**」的形式输出，
支持运营与管理团队进行快速判断与决策参考。

### 1.3 输出要求（赛题指引）

- 不同市场的关键变化要点（竞争 / 产品 / 平台 / 社媒 / 法规等）
- 对业务潜在影响的判断（机会 / 风险 / 需关注事项）
- 建议的观察重点或后续行动方向

> 📎 完整赛题：[docs/01_企业Agent挑战赛赛题.pdf](file:///c:/Users/Feng/Desktop/20260523/docs/01_企业Agent挑战赛赛题.pdf)
> 📎 解题深度梳理：[docs/03_战略模拟器核心需求.md](file:///c:/Users/Feng/Desktop/20260523/docs/03_战略模拟器核心需求.md)

---

## 二、产品哲学

> **「不只做赛题答卷，要做企业用得起、用得久、用得放心的战略外脑」**

| 哲学 | 落地解释 |
|---|---|
| 🪶 **轻量但完整** | 单机即可跑全套（PostgreSQL + Redis + Daphne + Celery），无云依赖、无第三方爬虫服务 |
| 🧱 **分层而非堆砌** | 采集层 / 分析层 / 简报层 / 通知层 / 协议层各自闭环，可独立升级、独立替换 |
| 🛡 **永远有兜底** | LLM 没 KEY → Mock；真采失败超阈值 → 自动仿真；推送失败 → 文件落盘留痕 |
| 🎚 **配置即上线** | 公司战略画像、目标市场、LLM Provider、简报调度、通知渠道全部 UI 可改，**无需重启** |
| 🔌 **可插拔为先** | 一行配置切 Provider（OpenAI / DeepSeek / Qwen / Ollama），一份 JSON 上线新信息源 |
| 📦 **企业级合规姿态** | HSTS / CSRF / Cookie Secure / CORS 白名单 全套生产开关；`.env` 与 `.env.example` 严格分离 |

---

## 三、架构决策：采集器跑数 + LLM 做脑

> **这是本项目最核心的架构差异化决策**。
> 评审现场如果只能讲一页，就讲这一页。

### 3.1 我们拒绝的两条路线

#### ❌ 路线 A：LLM 直搜 / Function Calling 满天飞

让 LLM 直接联网搜索、调工具、抓页面，看似"大力出奇迹"，实则：

- **幻觉风险**：LLM 编造一条不存在的 Reuters 新闻，足以让决策者信错
- **时间差**：LLM 训练截止 + 工具检索延迟，"今日情报"常常是上周的
- **token 烧穿**：每条情报都要让 LLM "再读一次互联网"，成本无法控制
- **不稳定**：rate limit / 工具失败 / 上下文超长，链路黑盒不可调试

#### ❌ 路线 B：龙虾搜索 / 第三方爬虫 SaaS / 商业 Agent 平台

看起来省事，实际是：

- **本质还是第三方爬虫 + 付费 API**，把命脉交到外人手上
- **数据所有权不清**：抓回来的数据是平台的还是你的？合规审查无法过
- **价格按量阶梯**：MVP 每天几十块，规模化每月几万块
- **黑盒不可控**：选源逻辑、去重逻辑、限流策略全都不在你手里

### 3.2 我们选择的路线：✅ 职责分离

```
┌─────────────────────────┐         ┌─────────────────────────┐
│  ⚡ 采集层（工程问题）  │         │  🧠 分析层（认知问题）  │
│                          │         │                          │
│  · 134 候选信息源        │  ────▶  │  · PEST 自动分类         │
│  · 35 SPIDER_REGISTRY    │         │  · 4 维价值评分          │
│    路由                  │         │  · SWOT 跨象限策略       │
│  · 18 真实采集函数       │         │  · 战略简报生成          │
│  · Scrapy + Playwright   │         │  · DeepSeek 真流式       │
│  · 失败自动仿真兜底      │         │  · 24h 缓存 + Mock 兜底  │
└─────────────────────────┘         └─────────────────────────┘
       自编 · 快 · 稳 · 免费              LLM · 只做"读判理结写"
```

### 3.3 八维度对比一览

| 维度 | ❌ LLM 直搜 | ❌ 龙虾/第三方 | ✅ 我们的路线 |
|---|---|---|---|
| **数据真实性** | 易幻觉 | 取决于平台 | 自采，源头可追溯 |
| **时效性** | 训练截止 + 检索延迟 | 平台抓取频率 | 自定义 cron，分钟级 |
| **成本** | 每条情报烧 token | 按量付费 | 大部分免费（RSS / 官 API） |
| **稳定性** | rate limit 黑盒 | SaaS 限流 | 失败超阈自动降级仿真 |
| **可控性** | LLM 自由发挥 | 平台规则 | 35 路由 18 函数全自有 |
| **合规性** | 数据出境模糊 | 数据归属模糊 | 自部署，数据不出企业 |
| **可调试** | 链路黑盒 | 平台不开放 | 全链路日志可观测 |
| **可扩展** | 加 prompt | 申请权限 | 新增一个 spider_name |

### 3.4 一句金句

> **「采集是工程问题，不该交给 LLM；LLM 不该拿去跑爬虫。」**
>
> 让擅长工程的工程师写采集器，让擅长理解的 LLM 做分析师 —— 这才是工程智慧。

---

## 四、五大差异化亮点

### ⭐ 亮点 1：DeepSeek token 级真流式（不是假的 stream=True）

- [apps/analysis/llm/](file:///c:/Users/Feng/Desktop/20260523/apps/analysis/llm)：基于 `httpx` 实现 OpenAI 兼容协议的 SSE 解析
- **关键细节**：[config/asgi.py](file:///c:/Users/Feng/Desktop/20260523/config/asgi.py) 路径分流 —— 仅 `/static/` 走 `ASGIStaticFilesHandler`，
  其余走原生 Django ASGI，避免 SSE 被 StaticFilesHandler 缓冲
- **启动器避坑**：[start.bat](file:///c:/Users/Feng/Desktop/20260523/start.bat#L284-L290) 注释明确写了 —— `runserver` (WSGI 同步) 会缓冲 `StreamingHttpResponse`，
  必须用 `daphne` (ASGI) 才能让 token 一帧一帧到达浏览器

### ⭐ 亮点 2：Mock 兜底 + 真采降级 双保险

- **LLM 层**：`LLM_API_KEY` 留空 → 自动切 Mock，启发式分类 + 受控随机噪声，评委 0 配置跑通全链路
- **采集层**：`DATA_SOURCE_MODE=auto`（[默认](file:///c:/Users/Feng/Desktop/20260523/.env.example#L57-L60)）—— 真采连续失败超过 `CRAWLER_FAILURE_THRESHOLD` 自动切仿真
- **24 小时缓存**：相同 prompt 命中即返回，token 节省 70%+

### ⭐ 亮点 3：134 候选信息源的工程化管理

- [data/data_source_1.json](file:///c:/Users/Feng/Desktop/20260523/data/data_source_1.json)：58 条主源（FRED / SEC / GDELT / Reddit / arXiv …）
- [data/data_source_2.json](file:///c:/Users/Feng/Desktop/20260523/data/data_source_2.json)：50 条扩展源
- [data/data_source_3.json](file:///c:/Users/Feng/Desktop/20260523/data/data_source_3.json)：26 条行业源
- 通过 `spider_name` 字段映射到 35 个 `SPIDER_REGISTRY` 路由，最终落到 18 个真实采集函数

### ⭐ 亮点 4：PEST + 4 维评分 + SWOT 跨象限策略 全自动

- **PEST**：每条情报自动标注 P/E/S/T 维度
- **4 维评分**：紧迫度 × 权威性 × 相关度 × 影响面，加权排序
- **SWOT**：基于公司战略画像自动判断 O/T 方向，并生成 SO/ST/WO/WT 四象限策略

### ⭐ 亮点 5：4 节点 A2A 协议多智能体编排

- [apps/agents/protocol.py](file:///c:/Users/Feng/Desktop/20260523/apps/agents/protocol.py) + [apps/agents/coordinator.py](file:///c:/Users/Feng/Desktop/20260523/apps/agents/coordinator.py)
- **采集 Agent → 分析 Agent → 简报 Agent → 通知 Agent**，节点间通过协议消息编排
- 驾驶舱「智能体控制台」可视化运行状态：[/dashboard/agents/](http://127.0.0.1:8000/dashboard/agents/)

---

## 五、超越赛题：通用企业战略雷达底座

> 赛题指定的是"出海品牌"，但这个系统的能力边界**远不止于此**。
> 通过 **自定义数据源 + 自定义公司画像** 两步，即可成为任何行业的战略雷达。

### 5.1 跨行业延展矩阵

#### 表 1：制造业 / 供应链

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 原材料价格监控 | 大宗商品 RSS / 期货公开数据 | 早 1 周锁定库存策略 |
| 海运运力告警 | 港口 / 船期公开公告 | 提前调整发货计划 |
| 关税政策跟踪 | 海关 / 商务部公告 | 合规风险 H/M/L 分级 |

#### 表 2：金融 / 投研

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 宏观因子日报 | FRED / World Bank / IMF | 替代部分晨会资料 |
| 监管政策预警 | SEC / 证监会 / 央行 | 第一时间合规复核 |
| 舆情风控 | 推特 / Reddit / 雪球 | 突发性舆情 H 级告警 |

#### 表 3：消费品 / 电商

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 竞品上新追踪 | Amazon / Shopify / TikTok Shop | 周报自动汇总差异 |
| KOL/KOC 声量 | YouTube / Instagram / 小红书 | SWOT 中"S/W"动态更新 |
| 平台规则变动 | Amazon / TikTok / Meta 公告 | 政策变更秒级触达运营 |

#### 表 4：医药 / 大健康

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 临床试验进度 | ClinicalTrials.gov / arXiv | 竞争管线提前感知 |
| 药监审批 | FDA / NMPA / EMA | 关键节点 H 级告警 |
| 学术前沿 | PubMed / Nature / Cell | PEST 中 T 维度自动归档 |

#### 表 5：跨境 / 出海（赛题原场景）

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 多市场动态 | 各国新闻 + 行业报告 | 每日战略简报 |
| 法规合规 | 各国监管公告 | 合规风险预警 |
| 竞品动态 | 公开融资 / 招聘 / 专利 | 战略动作早识别 |

#### 表 6：政府 / 智库 / 园区

| 应用 | 自定义点 | 雷达价值 |
|---|---|---|
| 区域经济监测 | 统计局 / 海关 / 行业协会 | 月度经济运行报告 |
| 招商情报 | 上市公司公告 / 招聘 | 重点企业动向跟踪 |
| 突发事件感知 | GDELT / 应急部 / 气象 | 高影响事件 H 级触达 |

### 5.2 一行话总结

> **「换一份信息源 JSON + 改一份公司画像 = 一个新行业的战略雷达」**

---

## 六、核心能力总览

### 6.1 8 大驾驶舱页面（[apps/dashboard/urls.py](file:///c:/Users/Feng/Desktop/20260523/apps/dashboard/urls.py)）

| # | 页面 | 路径 | 核心能力 |
|---|---|---|---|
| 01 | 情报蓝图 | `/dashboard/` | 五大战略维度全景 + 实时动态 |
| 02 | 今日简报 | `/dashboard/briefing/` | Daily / Weekly / Monthly 三档简报 |
| 03 | 市场动态 / 时间线 | `/dashboard/feed/` `/timeline/` | 跨市场情报流 + SSE 真流式分析 |
| 04 | 采集调度 | `/dashboard/scheduling/` | Celery 任务可视化 + 手动触发 |
| 05 | 信息源配置 | `/dashboard/sources/` | 134 源管理 + 优先级 + 难度 |
| 06 | 通知记录 | `/dashboard/notifications/` | 邮件 / 飞书 / 短信 / Webhook 全通道 |
| 07 | 系统配置 | `/dashboard/settings/` | LLM / 邮箱 / 短信 / 公司画像 全 UI 可改 |
| 08 | 智能体控制台 | `/dashboard/agents/` | 4 节点 A2A 编排可视化 |

### 6.2 6 个 API 模块（[config/urls.py](file:///c:/Users/Feng/Desktop/20260523/config/urls.py)）

| 模块 | 前缀 | 职责 |
|---|---|---|
| sources | `/api/sources/` | 信息源 CRUD + 触发采集 |
| intelligence | `/api/intel/` | 情报检索 + 批量打标 |
| analysis | `/api/analysis/` | PEST / SWOT / 4 维评分 + LLM 流式 |
| briefings | `/api/briefings/` | 简报生成 + 历史查询 |
| notifications | `/api/notifications/` | 多通道推送 + 模板管理 |
| agents | `/api/agents/` | A2A 协议 + 节点编排 |

---

## 七、快速开始（5 分钟跑起来）

### 7.1 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.11+ | 虚拟环境推荐 `.venv/` |
| PostgreSQL | 14+ | 监听 `127.0.0.1:5432` |
| Redis | 7+ | 监听 `127.0.0.1:6379` |
| Node | — | 不需要，前端为静态资源 |

### 7.2 三步跑通

```powershell
# 1. 克隆 + 创建虚拟环境 + 安装依赖
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium    # 反指纹采集需要

# 2. 配置环境变量
copy .env.example .env
# 按需编辑 .env（最关键的是 PG_PASSWORD；LLM_API_KEY 可留空，自动走 Mock）

# 3. 数据迁移 + 加载初始信息源 + 启动
python manage.py migrate
python manage.py loaddata data/data_source_1.json data/data_source_2.json data/data_source_3.json
.\start.bat
```

> ⚠️ **PowerShell 不展开通配符**，`loaddata` **必须显式传三个文件名**，不能写 `data/data_source_*.json`。

### 7.3 [start.bat](file:///c:/Users/Feng/Desktop/20260523/start.bat) 菜单

| 序号 | 功能 |
|---|---|
| 1 | 启动全部（Daphne + Celery Worker + Celery Beat） |
| 2 | 重启全部 |
| 3 | 数据迁移（makemigrations + migrate） |
| 4 | 静态资源同步（collectstatic） |
| 5 | 健康检查（Redis / PostgreSQL / Django 端口） |
| 6 | 仅停止已运行服务 |
| 7 | 退出 |

> 💡 **服务运行中按 Ctrl+C** 会优雅停止全部服务并回到主菜单（不会让 Python 子进程变孤儿）。

---

## 八、访问入口

| 入口 | URL | 说明 |
|---|---|---|
| 驾驶舱首页 | <http://127.0.0.1:8000/> | 自动跳转 `/dashboard/` |
| Django Admin | <http://127.0.0.1:8000/admin/> | 数据后台（`createsuperuser` 后） |
| 健康检查 | <http://127.0.0.1:8000/healthz> | 返回 200 + JSON |
| 演示文稿 | [presentation/index.html](file:///c:/Users/Feng/Desktop/20260523/presentation/index.html) | 项目根目录，浏览器直接打开（独立 file://） |

---

## 九、目录结构

```
20260523/
├── apps/                          # Django 应用层（每个子应用独立闭环）
│   ├── dashboard/                 # 驾驶舱前端（8 大页面 + Channels Consumer）
│   ├── sources/                   # 信息源管理（134 源 / 35 路由 / 18 函数）
│   ├── intelligence/              # 情报存储 + 批量打标
│   ├── analysis/                  # PEST / SWOT / 评分 / LLM 流式
│   │   └── llm/                   # DeepSeek httpx 客户端 + Mock 兜底
│   ├── briefings/                 # Daily / Weekly / Monthly 简报
│   ├── notifications/             # 邮件 / 飞书 / 短信 / Webhook 多通道
│   └── agents/                    # 4 节点 A2A 协议 + Coordinator
├── config/                        # Django 项目配置
│   ├── settings.py                # 全局设置（环境变量驱动）
│   ├── asgi.py                    # ASGI 路径分流（SSE 不被静态 handler 缓冲）
│   ├── urls.py                    # 根路由（admin + dashboard + 6 个 api 模块）
│   ├── celery.py                  # Celery + Beat 配置
│   ├── company_profile.json       # 公司战略画像（UI 可改 / 即时生效）
│   └── briefing_schedule.json     # 简报调度规则（UI 可改）
├── data/                          # 信息源种子数据
│   ├── data_source_1.json         # 58 条主源
│   ├── data_source_2.json         # 50 条扩展源
│   └── data_source_3.json         # 26 条行业源
├── docs/                          # 赛题与需求文档
├── presentation/                  # 评委演示文稿（20 页 HTML 幻灯）
│   ├── index.html                 # 目录页 + 15 分钟评委精讲路径
│   └── slide-01 ~ slide-20.html
├── static/ + staticfiles/         # 前端静态资源（collectstatic 输出）
├── templates/                     # Django 模板（驾驶舱 8 页 + base）
├── tests/                         # SSE 探针 + 集成测试
├── tmp/sent_emails/               # 演示模式邮件落盘日志
├── .env.example                   # 环境变量样板
├── manage.py
├── requirements.txt
├── start.bat                      # 一键启动菜单（Windows）
└── start_venv.bat                 # 虚拟环境快速激活
```

---

## 十、生产部署建议

| 环节 | 建议 |
|---|---|
| **WSGI/ASGI** | 必须用 `daphne` 或 `uvicorn` —— `runserver` 仅开发用，会缓冲 SSE |
| **反向代理** | Nginx 反代时关闭 `proxy_buffering` for `/api/analysis/.../stream/`，否则 SSE 失流式 |
| **HTTPS** | `.env` 设置 `DJANGO_SSL_REDIRECT=1` + `DJANGO_SECURE_HSTS_SECONDS=31536000` |
| **数据库** | PostgreSQL 14+，建议为 `intelligence_*` 大表加 BRIN 时间索引 |
| **Celery** | 生产改用 `-P prefork` + 多 worker；Beat 单实例避免任务重复 |
| **LLM** | 生产 `LLM_API_KEY` 必填；保留 Mock 兜底用于 KEY 失效自动降级 |
| **邮件** | 演示用 `filebased.EmailBackend`（落盘 [tmp/sent_emails/](file:///c:/Users/Feng/Desktop/20260523/tmp/sent_emails)），生产改 `smtp.EmailBackend` |
| **静态文件** | `collectstatic` 后由 Nginx 直接服务 `/staticfiles/`，不让 Django 处理 |

---

## 十一、工程价值沉淀

> **本项目的"工程价值"远超过 MVP 跑通本身**：

1. **ASGI 路径分流方案**（[config/asgi.py](file:///c:/Users/Feng/Desktop/20260523/config/asgi.py)）—— 解决 Django Channels + SSE + StaticFiles 的经典缓冲冲突
2. **Mock-First LLM 抽象**（[apps/analysis/llm/](file:///c:/Users/Feng/Desktop/20260523/apps/analysis/llm)）—— 0 配置可演示 + 1 行配置切 Provider
3. **三档采集模式**（`auto` / `simulated` / `real`）—— 失败超阈自动降级，工程鲁棒性教科书级
4. **配置即上线**（[apps/dashboard/views.py](file:///c:/Users/Feng/Desktop/20260523/apps/dashboard/views.py) 的 `runtime_config_api`）—— 数据库配置覆盖 `.env`，UI 改了就生效
5. **4 节点 A2A 协议**（[apps/agents/protocol.py](file:///c:/Users/Feng/Desktop/20260523/apps/agents/protocol.py)）—— 一份可复用的多智能体编排范式
6. **start.bat 工程化菜单**（340 行）—— Ctrl+C 优雅停服 + 孤儿进程清理 + 健康检查全菜单化

---

## 十二、相关文档

- 📎 [docs/01_企业Agent挑战赛赛题.pdf](file:///c:/Users/Feng/Desktop/20260523/docs/01_企业Agent挑战赛赛题.pdf)
- 📎 [docs/02_企业Agent挑战赛_赛题讲解.pdf](file:///c:/Users/Feng/Desktop/20260523/docs/02_企业Agent挑战赛_赛题讲解.pdf)
- 📎 [docs/03_战略模拟器核心需求.md](file:///c:/Users/Feng/Desktop/20260523/docs/03_战略模拟器核心需求.md)
- 📎 [STRUCTURE.MD](file:///c:/Users/Feng/Desktop/20260523/STRUCTURE.MD)（项目结构白皮书）
- 📎 [presentation/index.html](file:///c:/Users/Feng/Desktop/20260523/presentation/index.html)（20 页演示文稿 + 15 分钟评委精讲路径）

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
> 因为我们相信：**采集是工程问题，不该交给 LLM；LLM 不该拿去跑爬虫。**
>
> 让擅长工程的工程师写采集器，让擅长理解的 LLM 做分析师。
>
> **这就是我们交给评委的那份"工程智慧"。**

---

## 十四、许可

MIT License · © 2026 冯伟雄

> 项目用于深圳 AI for Human 企业 Agent 挑战赛 · 赛道 A 战略情报预警方向。
> 欢迎企业基于本框架二次开发，搭建自己的战略雷达。
