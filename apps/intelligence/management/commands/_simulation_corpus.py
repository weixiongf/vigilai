"""仿真数据语料库 — 真实感强的情报模板，按战略维度组织。

每个模板含：
  - title_tpl / content_tpl：标题/正文模板（{market}/{entity}/{value} 占位）
  - dimension：战略维度
  - pest：PEST 分类
  - ot：O(机会) / T(威胁)
  - level：H/M/L 影响等级
  - tags：固定标签
  - sentiment：情感
  - severity：严重度
  - score_seed：基础分（0-10），实际会加扰动

模板遵循：每个维度 ≥ 8 个模板，覆盖正负样本，可拼装出 500+ 唯一情报。
"""

# 目标市场池
TARGET_MARKETS = [
    {'code': 'US', 'name': '美国', 'flag': '🇺🇸', 'region': '北美'},
    {'code': 'EU', 'name': '欧盟', 'flag': '🇪🇺', 'region': '欧洲'},
    {'code': 'UK', 'name': '英国', 'flag': '🇬🇧', 'region': '欧洲'},
    {'code': 'JP', 'name': '日本', 'flag': '🇯🇵', 'region': '东亚'},
    {'code': 'KR', 'name': '韩国', 'flag': '🇰🇷', 'region': '东亚'},
    {'code': 'SG', 'name': '新加坡', 'flag': '🇸🇬', 'region': '东南亚'},
    {'code': 'ID', 'name': '印度尼西亚', 'flag': '🇮🇩', 'region': '东南亚'},
    {'code': 'TH', 'name': '泰国', 'flag': '🇹🇭', 'region': '东南亚'},
    {'code': 'VN', 'name': '越南', 'flag': '🇻🇳', 'region': '东南亚'},
    {'code': 'MX', 'name': '墨西哥', 'flag': '🇲🇽', 'region': '拉美'},
    {'code': 'BR', 'name': '巴西', 'flag': '🇧🇷', 'region': '拉美'},
    {'code': 'AE', 'name': '阿联酋', 'flag': '🇦🇪', 'region': '中东'},
    {'code': 'SA', 'name': '沙特', 'flag': '🇸🇦', 'region': '中东'},
    {'code': 'AU', 'name': '澳大利亚', 'flag': '🇦🇺', 'region': '大洋洲'},
]

# 竞品池（用于竞争维度模板填充）
COMPETITORS = [
    'Anker', 'SHEIN', 'TEMU', 'TikTok Shop', 'Lazada', 'Shopee',
    'Amazon', 'eBay', '小米国际', 'OPPO海外', 'Xiaomi Global',
    'BYD', 'Tesla', 'Samsung', 'LG', 'Sony', 'Nike', 'Adidas',
    '名创优品', 'Pop Mart', '乐高', 'Mattel',
]

# 平台池
PLATFORMS = [
    'Amazon', 'TikTok Shop', 'Shopee', 'Lazada', 'Mercado Libre',
    'Coupang', 'Rakuten', 'Allegro', 'Noon', 'Trendyol', 'Etsy',
]

# KOL/媒体池
KOLS = [
    'MrBeast', 'PewDiePie', 'Charli D\'Amelio', 'Khaby Lame',
    'Markiplier', 'Logan Paul', 'KSI', '木下ゆうか',
]

# 法规机构池
REGULATORS = [
    '欧盟委员会', '美国 FTC', '美国 SEC', '美国海关 CBP',
    '英国 CMA', '日本经产省 METI', '韩国 KCC', '新加坡 MAS',
    '印尼 KOMINFO', 'CFIUS', 'FDA', 'CPSC',
]

# ===== 情报模板：每条按维度+PEST+O/T+level 锚定 =====
TEMPLATES = [
    # ---------- 竞争维度 (Competition) ----------
    {
        'dimension': 'competition', 'pest': 'E', 'ot': 'T', 'level': 'H',
        'title_tpl': '{competitor} 在{market}市场推出新一代旗舰产品 抢占高端份额',
        'content_tpl': '据 {market} 市场观察, {competitor} 于近期发布新一代旗舰产品, 售价较前代下调约 {pct}%, 主打 AI 与续航升级, 一周内冲上 {platform} 同品类销量榜前三, 对中国出海品牌形成明显的高端市场挤压。',
        'tags': ['竞品动作', '新品发布', '价格战'],
        'sentiment': 'negative', 'severity': 'high', 'score_seed': 8.4,
    },
    {
        'dimension': 'competition', 'pest': 'E', 'ot': 'T', 'level': 'M',
        'title_tpl': '{competitor} 在{market}启动激进促销 折扣最高达 {pct}%',
        'content_tpl': '{competitor} 在{market}市场启动为期两周的大促, 全品类折扣最高达 {pct}%, 预计将拉低{market}同品类整体均价约 5-8%, 中国卖家短期内利润空间承压。',
        'tags': ['促销', '价格战', '市场份额'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 6.5,
    },
    {
        'dimension': 'competition', 'pest': 'E', 'ot': 'O', 'level': 'M',
        'title_tpl': '{competitor} 在{market}撤出部分品类 释放约 {pct}% 市场空间',
        'content_tpl': '{competitor} 公告将在{market}市场停止运营若干非核心品类, 约 {pct}% 的需求将出现真空, 中国出海品牌如能在 30-60 天内补位, 有望承接其遗留客群与渠道资源。',
        'tags': ['竞品退出', '空白市场', '品类机会'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 7.2,
    },
    {
        'dimension': 'competition', 'pest': 'E', 'ot': 'T', 'level': 'H',
        'title_tpl': '{competitor} 完成对{market}本地头部经销商的并购',
        'content_tpl': '{competitor} 宣布以约 {value} 亿美元完成对{market}头部本地经销商的全资收购, 短期内将垂直整合 700+ 家线下门店与本地仓配, 渠道护城河进一步扩大。',
        'tags': ['并购', '渠道整合', '本地化'],
        'sentiment': 'negative', 'severity': 'high', 'score_seed': 8.7,
    },
    {
        'dimension': 'competition', 'pest': 'T', 'ot': 'O', 'level': 'M',
        'title_tpl': '{competitor} 因供应链问题在{market}缺货 客户加速寻替代',
        'content_tpl': '{competitor} 在{market}市场出现连续 3 周的关键 SKU 缺货, 本地买家社区出现明显的替代品搜索需求, 中国卖家在该窗口期可针对性投放广告并加快补货。',
        'tags': ['供应链', '缺货', '替代机会'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 6.8,
    },
    {
        'dimension': 'competition', 'pest': 'E', 'ot': 'T', 'level': 'M',
        'title_tpl': '{competitor} 在{market}获新一轮 {value} 亿美元融资 加注本地化',
        'content_tpl': '{competitor} 完成新一轮 {value} 亿美元融资, 资方计划用于扩大{market}本地仓储、本地客服与本地短视频投放, 中国出海品牌的长期份额防御压力上升。',
        'tags': ['融资', '本地化', '长期威胁'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 7.0,
    },
    {
        'dimension': 'competition', 'pest': 'E', 'ot': 'T', 'level': 'L',
        'title_tpl': '{competitor} 在{market}新增 {value} 个 SKU 价格带下沉',
        'content_tpl': '{competitor} 在{market}新上 {value} 个入门级 SKU, 对应价格带覆盖到 9.9 - 19.9 美元, 中国白牌厂商在该价格带的领先优势开始被稀释。',
        'tags': ['SKU扩张', '价格下沉'],
        'sentiment': 'negative', 'severity': 'low', 'score_seed': 4.5,
    },
    {
        'dimension': 'competition', 'pest': 'S', 'ot': 'O', 'level': 'M',
        'title_tpl': '{competitor} 在{market}社交媒体出现负面口碑 NPS 跌至历史低点',
        'content_tpl': '{competitor} 在{market} TikTok / Reddit 上的客诉视频在过去 7 天累计播放超 {value} 万次, NPS 评分较上月下跌约 {pct} 点, 中国品牌可借势放大"质量+服务"差异化叙事。',
        'tags': ['口碑', '社媒舆情', 'NPS'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 6.2,
    },

    # ---------- 产品维度 (Product) ----------
    {
        'dimension': 'product', 'pest': 'S', 'ot': 'O', 'level': 'H',
        'title_tpl': '{market}消费者对"可持续/环保"标签的支付意愿同比增长 {pct}%',
        'content_tpl': '{market}权威消费洞察机构最新调查显示, 18-34 岁消费者对带有"可持续/可回收/低碳"标签产品的额外支付意愿同比上涨 {pct}%, 出海品牌在包装与材质故事化叙事上的窗口扩大。',
        'tags': ['可持续消费', '溢价', 'Z世代'],
        'sentiment': 'positive', 'severity': 'high', 'score_seed': 8.1,
    },
    {
        'dimension': 'product', 'pest': 'S', 'ot': 'O', 'level': 'M',
        'title_tpl': '{market} {value} 类目搜索量周环比上涨 {pct}%',
        'content_tpl': '据 {platform} 后台数据, {market}市场对 {value} 相关品类的搜索量周环比上涨 {pct}%, 主要驱动因素为本地节庆与达人内容; 建议运营加单与广告倾斜。',
        'tags': ['搜索趋势', '品类机会'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 6.6,
    },
    {
        'dimension': 'product', 'pest': 'T', 'ot': 'O', 'level': 'M',
        'title_tpl': '{market}消费者评测：AI 功能成新一代{value}产品决策核心',
        'content_tpl': '{market}本地科技媒体在评测 30 款新品后总结: 是否搭载 AI 助理 / 端侧大模型已成为消费者购买决策中权重最高的三项之一; 建议产品线在下一代规划中前置 AI 卖点。',
        'tags': ['AI产品', '消费者偏好'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 6.9,
    },
    {
        'dimension': 'product', 'pest': 'S', 'ot': 'T', 'level': 'M',
        'title_tpl': '{market}用户差评聚焦"品控不一致" 中国白牌口碑承压',
        'content_tpl': '过去 30 天 {market} {platform} 平台对中国白牌品牌的 1-2 星差评中, "品控不一致 / 装机即坏 / 售后联系不上"占比达 {pct}%, 进一步推高退货率与广告 ACoS。',
        'tags': ['品控', '差评', '退货'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 6.5,
    },
    {
        'dimension': 'product', 'pest': 'S', 'ot': 'O', 'level': 'L',
        'title_tpl': '{market}年轻女性消费者对"国潮/东方美学"接受度抬升',
        'content_tpl': '{market}头部时尚博主连续推荐数款带有"东方美学"元素的中国出海品牌, 评论区正面声量占比达 {pct}%, 国潮品类有阶段性出圈机会。',
        'tags': ['国潮', '美学', '出圈'],
        'sentiment': 'positive', 'severity': 'low', 'score_seed': 5.0,
    },
    {
        'dimension': 'product', 'pest': 'E', 'ot': 'T', 'level': 'M',
        'title_tpl': '{market}核心原材料价格上涨 {pct}% 中端定价压力增大',
        'content_tpl': '{market}本地大宗商品指数显示关键原材料价格周环比上涨 {pct}%, 短期内中端价格带的中国出海品牌毛利将被进一步压缩, 需评估是否调价或换料。',
        'tags': ['原材料', '成本', '毛利'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 6.7,
    },
    {
        'dimension': 'product', 'pest': 'T', 'ot': 'O', 'level': 'L',
        'title_tpl': '{market}智能家居细分品类出现新爆款形态',
        'content_tpl': '{market}过去 14 天智能家居品类出现一款形态新颖的产品(含 Matter 协议+本地语音), 上线 10 天进入类目 Best Seller Top10, 显示出新品类爆款窗口。',
        'tags': ['智能家居', 'Matter', '爆款'],
        'sentiment': 'positive', 'severity': 'low', 'score_seed': 4.8,
    },

    # ---------- 平台维度 (Platform) ----------
    {
        'dimension': 'platform', 'pest': 'P', 'ot': 'T', 'level': 'H',
        'title_tpl': '{platform} 在{market}收紧低价跨境包裹政策 月内生效',
        'content_tpl': '{platform} 官方公告: 自下月起将对来自跨境的低价小包裹实施新合规清单, 不符合者将下架并冻结资金, 中国卖家备货策略需立即评估调整。',
        'tags': ['平台规则', '合规', '跨境包裹'],
        'sentiment': 'negative', 'severity': 'high', 'score_seed': 8.6,
    },
    {
        'dimension': 'platform', 'pest': 'P', 'ot': 'T', 'level': 'H',
        'title_tpl': '{platform} 调整佣金结构 部分品类费率上调 {pct}%',
        'content_tpl': '{platform} 在{market}发布新版佣金/物流费率, 服饰、电子配件等品类将上调 {pct}%, 卖家需重新核算定价模型, 部分薄利单品建议下架。',
        'tags': ['佣金', '费率', '盈利'],
        'sentiment': 'negative', 'severity': 'high', 'score_seed': 8.3,
    },
    {
        'dimension': 'platform', 'pest': 'P', 'ot': 'O', 'level': 'M',
        'title_tpl': '{platform} 在{market}推出"中国卖家专属流量扶持"计划',
        'content_tpl': '{platform} 官方对外发布"中国跨境卖家专属流量包"计划, 入选商家可获得为期 3 个月的展位资源、广告补贴与本地客服支持; 申报截止下月 15 日。',
        'tags': ['流量扶持', '官方计划', '红利'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 7.4,
    },
    {
        'dimension': 'platform', 'pest': 'T', 'ot': 'O', 'level': 'M',
        'title_tpl': '{platform} 上线 AI 选品助手 中国卖家可用 API 接入',
        'content_tpl': '{platform} 上线基于 LLM 的 AI 选品助手, 提供 GMV 预测、爆款关联、库存周转建议等接口, 中国卖家可通过 API 接入自己的运营系统。',
        'tags': ['AI', '选品', 'API'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 6.8,
    },
    {
        'dimension': 'platform', 'pest': 'P', 'ot': 'T', 'level': 'M',
        'title_tpl': '{platform} 加强"虚假评论/刷单"打击 处罚强度提升',
        'content_tpl': '{platform} 在{market}更新反操纵评论政策, 新增 7 类违规情形, 重犯将永久封店并冻结资金; 中国卖家应当立即排查所有第三方评测合作。',
        'tags': ['虚假评论', '封店', '合规'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 7.2,
    },
    {
        'dimension': 'platform', 'pest': 'P', 'ot': 'T', 'level': 'M',
        'title_tpl': '{platform} 对{market}本地化包装/标签提出强制要求',
        'content_tpl': '{platform} 要求所有进入{market}市场的商品在 90 天内完成本地语言包装、标签、说明书与回收标识合规改造, 否则将限制流量曝光。',
        'tags': ['本地化', '包装标签', '强制改造'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 6.9,
    },
    {
        'dimension': 'platform', 'pest': 'T', 'ot': 'O', 'level': 'L',
        'title_tpl': '{platform} 在{market}新增直播带货功能 内测中',
        'content_tpl': '{platform} 在{market}灰度上线短视频+直播带货闭环, 部分中国头部卖家已收到内测邀请, 早期入场者有望吃到首批流量红利。',
        'tags': ['直播带货', '红利期'],
        'sentiment': 'positive', 'severity': 'low', 'score_seed': 5.6,
    },

    # ---------- 社媒维度 (Social) ----------
    {
        'dimension': 'social', 'pest': 'S', 'ot': 'O', 'level': 'H',
        'title_tpl': '{kol} 在{market} TikTok 上推荐{value}相关品类 单视频破 {value} 万播放',
        'content_tpl': '{kol} 单条短视频带火 {market} 市场 {value} 类目搜索, 24 小时内相关搜索词上涨 {pct}%, 中国出海品牌可乘势加投官方旗舰店广告。',
        'tags': ['KOL', 'TikTok', '种草'],
        'sentiment': 'positive', 'severity': 'high', 'score_seed': 8.0,
    },
    {
        'dimension': 'social', 'pest': 'S', 'ot': 'T', 'level': 'M',
        'title_tpl': '{market} Reddit 出现针对中国跨境品牌的话题集中负面讨论',
        'content_tpl': '{market} Reddit r/BuyItForLife 等社区出现针对中国跨境品牌"短命产品"的集中讨论帖, 累计 upvote 超 {value}, 品牌方需要主动公关澄清。',
        'tags': ['Reddit', '负面舆情', '公关'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 6.6,
    },
    {
        'dimension': 'social', 'pest': 'S', 'ot': 'O', 'level': 'M',
        'title_tpl': '{market} TikTok #MadeInChina 标签播放量周环比上涨 {pct}%',
        'content_tpl': '{market} TikTok #MadeInChina 与相关变体标签累计播放量周环比上涨 {pct}%, 内容情感正负比约为 7:3, 中国品牌应当加大本地达人合作。',
        'tags': ['标签热度', '达人合作'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 6.4,
    },
    {
        'dimension': 'social', 'pest': 'S', 'ot': 'T', 'level': 'M',
        'title_tpl': '{market}主流媒体围绕"中国电商低价"展开专题报道',
        'content_tpl': '{market} 主流媒体 {value} 等连续 3 天发表针对中国跨境低价电商的深度报道, 触达高端消费者; 中国品牌应该在官网与本地账号同步发布回应内容。',
        'tags': ['主流媒体', '舆论压力'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 6.8,
    },
    {
        'dimension': 'social', 'pest': 'S', 'ot': 'O', 'level': 'L',
        'title_tpl': '{market} YouTube 评测频道发布{competitor}与中国品牌对比测评',
        'content_tpl': '{market} 数码评测频道发布 {competitor} 与某中国品牌对比测评, 中国品牌在性价比与软件流畅度上占优, 视频已获 {value} 万播放, 评论区氛围正面。',
        'tags': ['评测', 'YouTube', '正面'],
        'sentiment': 'positive', 'severity': 'low', 'score_seed': 5.2,
    },
    {
        'dimension': 'social', 'pest': 'S', 'ot': 'T', 'level': 'L',
        'title_tpl': '{market}本地用户在 X 平台抱怨{platform}中国卖家发货慢',
        'content_tpl': '{market} X 平台过去 7 天出现多条投诉贴, 集中反映 {platform} 上中国卖家发货时效拉长至 14-21 天; 出海品牌需要重新评估海外仓策略。',
        'tags': ['物流', '时效', '海外仓'],
        'sentiment': 'negative', 'severity': 'low', 'score_seed': 4.7,
    },

    # ---------- 法规维度 (Regulation) ----------
    {
        'dimension': 'regulation', 'pest': 'P', 'ot': 'T', 'level': 'H',
        'title_tpl': '{regulator} 公布新一轮对华出口管制清单 {market}受影响',
        'content_tpl': '{regulator} 正式公布新版出口管制清单, 涉及 {value} 类高科技/敏感商品, 对面向 {market} 的中国出海企业供应链构成显著合规压力。',
        'tags': ['出口管制', '合规', '高敏感'],
        'sentiment': 'negative', 'severity': 'high', 'score_seed': 8.8,
    },
    {
        'dimension': 'regulation', 'pest': 'P', 'ot': 'T', 'level': 'H',
        'title_tpl': '{market} 上调对中国进口商品关税 平均增加 {pct}%',
        'content_tpl': '{market} 政府宣布对从中国进口的部分品类商品上调关税平均 {pct}%, 自 30 日后生效, 出海品牌需要立刻重新核算到岸成本与定价模型。',
        'tags': ['关税', '到岸成本', '定价'],
        'sentiment': 'negative', 'severity': 'high', 'score_seed': 8.9,
    },
    {
        'dimension': 'regulation', 'pest': 'P', 'ot': 'T', 'level': 'H',
        'title_tpl': '{regulator} 立法严管短视频电商 {platform}首当其冲',
        'content_tpl': '{regulator} 启动新立法程序, 拟对短视频电商在数据本地化、青少年保护、税务申报等方面提出强制要求, 中国出海卖家在 {platform} 的运营节奏将受牵连。',
        'tags': ['立法', '短视频电商', '数据本地化'],
        'sentiment': 'negative', 'severity': 'high', 'score_seed': 8.4,
    },
    {
        'dimension': 'regulation', 'pest': 'P', 'ot': 'O', 'level': 'M',
        'title_tpl': '{market}与中国签署新一轮自贸/物流便利化协议',
        'content_tpl': '{market} 与中国签署新一轮自贸/物流便利化双边协议, {value} 类商品获关税优惠或通关便利, 中国出海企业应抓紧申请相关 HS 编码资质。',
        'tags': ['自贸协定', '关税优惠', '通关'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 7.1,
    },
    {
        'dimension': 'regulation', 'pest': 'P', 'ot': 'T', 'level': 'M',
        'title_tpl': '{market}强化数据保护法 跨境数据传输需通过新认证',
        'content_tpl': '{market} 数据保护监管机构发布实施细则, 跨境业务相关用户数据传输必须通过新认证, 6 个月过渡期, 中国出海企业需启动数据合规专项。',
        'tags': ['GDPR类', '数据合规', '认证'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 7.0,
    },
    {
        'dimension': 'regulation', 'pest': 'P', 'ot': 'T', 'level': 'M',
        'title_tpl': '{regulator} 发布对儿童产品的新一轮安全召回',
        'content_tpl': '{regulator} 在{market}发布最新一轮儿童相关产品安全召回, 涉及 {value} 个 SKU (含若干中国品牌), 召回成本高、品牌伤害大, 应自查产品认证。',
        'tags': ['召回', '儿童安全', '认证'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 7.3,
    },
    {
        'dimension': 'regulation', 'pest': 'P', 'ot': 'O', 'level': 'L',
        'title_tpl': '{market}简化外资电商主体登记流程 周期缩短至 {value} 天',
        'content_tpl': '{market}商业登记机构简化外资电商主体申请流程, 周期从 60 天缩短至 {value} 天, 中国出海企业本地实体设立成本下降, 利于品牌出海长期化。',
        'tags': ['本地化主体', '简化流程'],
        'sentiment': 'positive', 'severity': 'low', 'score_seed': 5.4,
    },

    # ---------- 宏观经济 (Macro) ----------
    {
        'dimension': 'macro', 'pest': 'E', 'ot': 'T', 'level': 'H',
        'title_tpl': '{market}央行加息 {pct} 个基点 消费信贷收缩',
        'content_tpl': '{market}央行宣布加息 {pct} 个基点, 短期内消费信贷与大额耐用品支出预期收缩, 出海品牌中端及以上价格带销售将承压。',
        'tags': ['加息', '消费收缩', '宏观'],
        'sentiment': 'negative', 'severity': 'high', 'score_seed': 8.0,
    },
    {
        'dimension': 'macro', 'pest': 'E', 'ot': 'T', 'level': 'M',
        'title_tpl': '{market}本币兑人民币贬值 {pct}% 中国卖家结算受影响',
        'content_tpl': '过去 30 天 {market} 本币兑人民币贬值 {pct}%, 出海卖家美元/本币结算环节出现汇兑损失, 建议启用对冲工具或调整收款节奏。',
        'tags': ['汇率', '汇兑损失', '对冲'],
        'sentiment': 'negative', 'severity': 'medium', 'score_seed': 6.8,
    },
    {
        'dimension': 'macro', 'pest': 'E', 'ot': 'O', 'level': 'M',
        'title_tpl': '{market} CPI 回落至 {pct}% 消费意愿回暖',
        'content_tpl': '{market}最新 CPI 同比回落至 {pct}%, 居民可支配收入增速企稳, 中端家居/电子配件等可选消费品有阶段性恢复机会。',
        'tags': ['CPI', '消费回暖'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 6.4,
    },
    {
        'dimension': 'macro', 'pest': 'E', 'ot': 'T', 'level': 'L',
        'title_tpl': '{market}失业率小幅上行至 {pct}% 消费保守化趋势',
        'content_tpl': '{market}失业率小幅上行至 {pct}%, 消费者对非必需品支出更为保守, 高客单价品类应考虑分期付款方案与小套装组合。',
        'tags': ['失业', '消费保守'],
        'sentiment': 'negative', 'severity': 'low', 'score_seed': 5.0,
    },

    # ---------- 行业报告 (Industry) ----------
    {
        'dimension': 'industry', 'pest': 'T', 'ot': 'O', 'level': 'M',
        'title_tpl': '{market}行业报告：跨境电商 {value} 类目 5 年复合增长率达 {pct}%',
        'content_tpl': '{market}本地权威咨询机构发布行业白皮书, 测算未来 5 年跨境电商 {value} 类目复合增长率达 {pct}%, 报告将"中国白牌升级品牌"列为最大增量驱动。',
        'tags': ['行业报告', '复合增长'],
        'sentiment': 'positive', 'severity': 'medium', 'score_seed': 7.0,
    },
    {
        'dimension': 'industry', 'pest': 'T', 'ot': 'O', 'level': 'L',
        'title_tpl': '{market}咨询机构发布"中国出海品牌力 TOP50"榜单',
        'content_tpl': '{market}本地咨询机构发布"中国出海品牌力 TOP50", {competitor} 等中国品牌跻身前列, 整体品牌力得分较去年提升 {pct}%; 表明出海品牌在认知度上稳步追赶。',
        'tags': ['品牌力', '榜单'],
        'sentiment': 'positive', 'severity': 'low', 'score_seed': 5.5,
    },
]
