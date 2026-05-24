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

## 二、核心能力总览

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

## 三、快速开始

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

## 四、访问入口

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

## 五、目录结构

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

## 六、生产部署

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

---

## 七、技术栈

- **Web 框架**：Django 4.2.30 · DRF 3.17 · django-cors-headers
- **ASGI / 实时**：Daphne 4.2 · Channels 4.3 · channels_redis（Redis pub/sub）
- **异步任务**：Celery 5.6 · Redis 7
- **数据库**：PostgreSQL 14（psycopg2-binary）
- **采集**：Scrapy 2.16 · scrapy-playwright · Playwright 1.60 · scrapling · camoufox（反指纹）
- **解析**：beautifulsoup4 · lxml · parsel · feedparser
- **LLM**：DeepSeek（OpenAI 兼容协议）· httpx 流式
- **流式**：Server-Sent Events token 级真流式 + WebSocket 状态推送

---

## 八、相关文档

- 演示文稿（20 页 HTML）：[presentation/index.html](presentation/index.html)
- 全栈深度审计报告：[check_report.md](check_report.md)
- 项目结构说明：[STRUCTURE.MD](STRUCTURE.MD)
- 赛题原始文档：[docs/01_企业Agent挑战赛赛题.pdf](docs/01_企业Agent挑战赛赛题.pdf)
- 战略模拟器核心需求：[docs/03_战略模拟器核心需求.md](docs/03_战略模拟器核心需求.md)

---

## 九、许可

本项目为深圳 AI for Human 企业 Agent 挑战赛参赛作品，仅用于教学与赛题演示，不含任何企业内部数据。所有采集均面向公开信息源，遵循各源的 robots / Rate Limit / ToS 约定。
