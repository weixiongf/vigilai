# 海外市场战略情报 Agent — 演示规划 (presentation.md)

> 本文件用于规划项目最终的 **20 页 HTML 演示文稿**。
> 现阶段只做**内容大纲与结构定稿**，所有 HTML 页面将在项目开发完成后再统一生成。
> 项目实际功能/架构/数据若有调整，**先在此处更新对应章节**，最后再统一渲染 HTML。

---

## 一、演示定位

| 维度 | 说明 |
|---|---|
| 目标受众 | 黑客松评委（评分关注：可用性、技术深度、业务洞察） |
| 演示时长 | 8 ~ 10 分钟讲述 + 2 分钟问答 |
| 演示风格 | 商业咨询 + 技术架构混合，**驾驶舱级**视觉，深色背景 + 信息密度 + 数据图 |
| 演示介质 | 静态 HTML（独立文件，可双击打开），跨页统一样式 |
| 视觉关键词 | 战略雷达 / 蓝橙双色 / 暗色商务 / 数据可视化 / 卡片栅格 |

---

## 二、整体故事线 (3 幕)

1. **第一幕 · 痛点与定义 (Slides 1-5)**：海外业务情报杂、慢、漏 → 我们要做什么
2. **第二幕 · 解决方案与价值 (Slides 6-14)**：5维度 + PEST + SWOT + 智能分析 + 高影响告警
3. **第三幕 · 技术与未来 (Slides 15-20)**：架构 / 数据 / 演示 / Roadmap / 致谢

---

## 三、20 页详细规划

### Slide 01 · 封面 (Cover)
- **主标题**：海外市场战略情报 Agent
- **副标题**：从信息洪流到战略决策 — 一个面向中国出海企业的智能情报驾驶舱
- **小字**：黑客松 · 主题 A · 团队代号 / 日期 2026
- **视觉**：背景是地球暗夜图 + 五大区域光点 + 雷达扫描动效（CSS）
- **呈现**：上中下三层布局；底部一行五个 emoji（🇺🇸 🇪🇺 🇯🇵 🇸🇬 🇧🇷）

### Slide 02 · 行业洞察：出海企业的 3 大情报困局
- 困局 1：信息源 60+ 分散（央行/统计局/新闻/社媒/法规/平台）
- 困局 2：情报噪声 95%，真正影响战略的不到 5%
- 困局 3：发现→响应慢，关键政策/竞品动作往往滞后 1-2 周才识别
- **视觉**：左侧三个红色 ⚠ 卡片，右侧"沙漏"造型暗示信息流失

### Slide 03 · 我们要解决的核心问题
- **一句话**："让出海决策者在 60 秒内拿到当日影响公司的关键情报"
- 关键能力：抓得到 / 看得懂 / 排得齐 / 推得准
- **视觉**：核心卡片，4 个能力图标横排，每个有一句话注释

### Slide 04 · 用户画像 / 使用场景
| 角色 | 关心问题 | 触点 |
|---|---|---|
| 出海业务负责人 | 战略机会/重大风险 | 早晨打开飞书看每日简报 |
| 市场分析师 | 各市场细粒度动态 | 驾驶舱 PEST/SWOT 切片 |
| 产品/合规 | 法规变化/平台规则更新 | 高影响告警推送 |

### Slide 05 · 系统五大战略维度
- 🎯 **竞争维度**：竞品动作、定价、新品、并购
- 🛍 **产品维度**：消费趋势、品类机会、消费者评价
- 🌐 **平台维度**：Amazon/TikTok Shop/Shopee 规则变化
- 💬 **社媒维度**：KOL 内容、话题热度、口碑
- ⚖ **法规维度**：关税、合规、出口管制、数据保护
- **视觉**：五边形雷达图，每个维度一个角

### Slide 06 · 解决方案：智能情报驾驶舱
- 三层架构：**采集层 / 分析层 / 决策层**
- **关键卖点**：
  - LLM 自动 PEST 分类 + O/T 标注 + H/M/L 影响等级
  - SWOT 矩阵 + SO/ST/WO/WT **跨象限策略**
  - 价值评分 0-10：相关 4 + 紧迫 3 + 权威 2 + 规模 1
- **视觉**：从左到右三段管道流图

### Slide 07 · 数据采集策略：双引擎
- **引擎 A**：精选免费 API（FRED / BLS / ECB / 世行 / GDELT / Reddit / NewsAPI）
- **引擎 B**：仿真数据生成器（500 条种子，覆盖所有市场×维度×影响类型）
- **理由**：免去爬虫被封风险，确保黑客松演示稳定，**真实管道照样接通**
- 已注册 113 个候选信息源，按优先级、难度、付费分类

### Slide 08 · 价值评分模型
- 公式：`score = 4·相关度 + 3·紧迫度 + 2·权威性 + 1·规模`
- 阈值：≥8 关键 / 5-7 中价值 / 3-4 低价值 / <3 噪声丢弃
- **视觉**：仪表盘 + 横向条形图 + 阈值线

### Slide 09 · PEST 框架落地
- 每条情报自动打标 P/E/S/T 维度 + O/T + H/M/L
- 时间窗口聚合 → PESTSnapshot 生成洞察文本
- **视觉**：4 象限卡片，配实际仿真示例标题（关税/利率/TikTok 监管/生成式 AI）

### Slide 10 · SWOT 矩阵 + 跨象限策略
- 内部 S/W：来自系统配置（公司画像）
- 外部 O/T：来自 PEST + 高分情报聚合
- **核心创新**：自动生成 4 类跨象限策略
  - **SO** 增长：用优势抓机会
  - **ST** 防御：用优势挡威胁
  - **WO** 扭转：抓机会补劣势
  - **WT** 规避：保守收缩
- **视觉**：2x2 矩阵 + 4 条策略文本卡

### Slide 11 · 战略简报：Daily / Weekly
- 自动生成行政摘要 / Top3 机会 / Top3 风险
- 每日早 09:00 推送到飞书 + 邮件
- 支持市场切片 / 维度切片 / 周期切换
- **视觉**：手机端 + PC 端 mockup 双联

### Slide 12 · 高影响告警链路
- 触发条件：`impact_score ≥ 8` 或 `severity = high`
- 通道：飞书 Webhook + 邮件 + WebSocket 驾驶舱红点
- **去抖动**：同主题 30 分钟合并、相似情报聚合
- **视觉**：从情报 → 评分 → 通道分发的时序图

### Slide 13 · 人机协同：反馈学习
- 管理者一键 **确认 / 修正 / 忽略**
- 修正样本进入训练池 → 优化分类 prompt
- 忽略样本积累形成"黑名单关键词"反馈给 LLM

### Slide 14 · 演示截图：驾驶舱主页
- 顶部 KPI 条：今日新增 / 高影响 / 待处理
- 左侧导航：驾驶舱 / 简报 / 动态 / 调度 / 设置
- 主区：地图热度 + 维度雷达 + 高分情报 Top10 + 今日简报
- **视觉**：实测大图（截图占位）

### Slide 15 · 技术架构总览
- 三层：**接入层（Daphne/ASGI）→ 业务层（Django+DRF）→ 数据层（PG+Redis）**
- 异步：**Celery（任务）+ Channels（WebSocket 推送）**
- 集成：**Scrapy / Playwright / curl_cffi / LLM Mock**
- **视觉**：经典分层架构图

### Slide 16 · 数据库设计要点
- `InfoSource` (113) → `CrawlJob` → `RawInfo` (target 500+) → `UserFeedback`
- `PESTSnapshot` ↔ `SWOTAnalysis` ↔ `Briefing`
- `NotificationLog` / `NotificationTemplate`
- **视觉**：ER 图（精简版）

### Slide 17 · LLM 抽象与 Mock 模式
- `analyzers/llm_provider.py` 统一接口（`classify_pest`, `score_value`, `summarize`）
- 黑客松默认 Mock 实现（确定性返回 + 随机噪声），可一键切真实 API（OpenAI/Claude/通义）
- **代码片段**：展示 `LLMProvider.complete(prompt)` 的简化签名
- 优势：评委环境无 API Key 也能跑

### Slide 18 · 关键指标 / 演示数据
| 指标 | 数值 |
|---|---|
| 信息源注册 | 113 |
| 仿真情报种子 | 500 |
| 战略主题 | 20+ |
| PEST 快照 | 7 (近 7 天) |
| SWOT 分析 | 5 个目标市场 |
| 高影响告警 | 30+ |
| Daily 简报样本 | 7 |

### Slide 19 · 路线图 (Roadmap)
- **现在**：黑客松 MVP — 仿真+少量真实 API
- **下一步**：接通 GDELT/Reddit/NewsAPI 真实数据流
- **再下一步**：多租户 + 团队订阅 + 自定义关键词
- **未来**：Agent 自动调研 / 行业大模型微调 / 多模态情报（视频/直播）

### Slide 20 · 致谢 & 团队 & 联系方式
- 团队成员卡片
- "Strategic Radar — See Earlier, Decide Smarter"
- GitHub / 联系方式 / 二维码

---

## 四、统一视觉规范 (供 HTML 实现时参考)

```css
:root {
  --bg-deep: #0B1120;
  --bg-card: #131A2D;
  --primary: #2563EB;        /* 蓝 */
  --accent:  #F59E0B;        /* 暖橙强调 */
  --success: #10B981;
  --danger:  #EF4444;
  --text-1:  #E5E7EB;
  --text-2:  #94A3B8;
  --border:  rgba(255,255,255,0.08);
}
```
- 字体：'Inter', 'PingFang SC', system-ui, sans-serif
- 圆角：12px / 卡片间距：24px / 栅格：12 列
- 单页尺寸：**1280x800**，居中固定
- 顶部页码 + 章节名称（如 `第一幕 · 02/20`）
- 底部底色条 + 项目 LOGO

---

## 五、HTML 文件命名规范

```
presentation/
  index.html              # 入口，列出全部20页 + 自动跳转
  slide-01-cover.html
  slide-02-pain-points.html
  slide-03-mission.html
  slide-04-personas.html
  slide-05-five-dimensions.html
  slide-06-solution.html
  slide-07-data-strategy.html
  slide-08-value-score.html
  slide-09-pest-framework.html
  slide-10-swot-matrix.html
  slide-11-briefings.html
  slide-12-alert-pipeline.html
  slide-13-human-loop.html
  slide-14-screenshot-dashboard.html
  slide-15-architecture.html
  slide-16-database.html
  slide-17-llm-mock.html
  slide-18-metrics.html
  slide-19-roadmap.html
  slide-20-team.html
  assets/
    css/common.css         # 共用样式
    js/common.js           # 翻页 (← →) + 进度条
    img/...
```

---

## 六、变更记录

| 版本 | 日期 | 修改人 | 变更摘要 |
|---|---|---|---|
| v0.1 | 2026-05-23 | Agent | 初稿大纲 20 页 + 视觉规范 |

> ⚠️ 后续若架构 / 模块 / 关键指标发生显著变化，请回到 **第三章对应 Slide 章节** 与 **第六章变更记录** 同步更新；切勿在此期间生成 HTML，避免反复返工。
