"""占位骨架 — 列出所有 "需注册/付费" 数据源对应的 spider 接入路线图.

本文件不参与运行时分发 (real_crawler.py 的 SPIDER_REGISTRY 才是真正的路由表),
仅作为后续接入工作的 To-Do 索引: 每个条目说明:
- 数据源名称
- 接入难度 (注册难度 / 是否付费)
- 官方文档地址
- 接入要点 (Auth 头 / 频率 / 数据格式)

启用流程:
    1. 在 settings 页面将对应 access_tier (register / paid) 的 toggle 打开;
    2. 在 .env 中配置该数据源所需的 API Key;
    3. 在 real_crawler.py 中实现真实 crawl_xxx() 函数并注册到 SPIDER_REGISTRY;
    4. 删除本文件中对应条目.

设计目的: 把 "未实现" 这件事显式化, 避免在异常列表里反复出现 "spider not in registry"
噪音 (噪音从架构层 access_tier 开关 + tasks.py NotImplementedError 静默两道屏障消除).
"""
from __future__ import annotations

# ---- register tier (免费但需注册) -----------------------------------------
REGISTER_TIER_ROADMAP = {
    'spider_newsapi': {
        'name': 'NewsAPI',
        'doc': 'https://newsapi.org/docs',
        'auth': 'X-Api-Key header',
        'free_tier': '100 req/day',
        'note': '注册即领 Key, 适合做新闻聚合 backbone',
    },
    'spider_thenewsapi': {
        'name': 'TheNewsAPI',
        'doc': 'https://www.thenewsapi.com/documentation',
        'auth': 'api_token query',
        'free_tier': '100 req/day',
    },
    'spider_worldnewsapi': {
        'name': 'WorldNewsAPI',
        'doc': 'https://worldnewsapi.com/docs',
        'auth': 'api-key query',
    },
    'spider_gnews_api': {
        'name': 'GNews API',
        'doc': 'https://gnews.io/docs',
        'auth': 'apikey query',
        'free_tier': '100 req/day',
    },
    'spider_newsdataio': {
        'name': 'NewsData.io',
        'doc': 'https://newsdata.io/documentation',
        'auth': 'apikey query',
    },
    'spider_newsapiai': {
        'name': 'NewsAPI.ai (Event Registry)',
        'doc': 'https://eventregistry.org/documentation',
    },
    'spider_youtube_data_api': {
        'name': 'YouTube Data API v3',
        'doc': 'https://developers.google.com/youtube/v3',
        'auth': 'Google API Key',
        'free_tier': '10000 quota/day',
    },
    'spider_reddit_api': {
        'name': 'Reddit API (OAuth2)',
        'doc': 'https://www.reddit.com/dev/api',
        'auth': 'OAuth2 (client_id + secret)',
    },
    'spider_twitterx_api': {
        'name': 'Twitter/X API v2',
        'doc': 'https://developer.x.com/en/docs',
        'auth': 'Bearer token',
        'note': '免费档 100 read/月, 极易耗尽',
    },
    'spider_google_trends': {
        'name': 'Google Trends',
        'doc': 'pytrends 第三方库 (无官方 API)',
        'note': '受限较多, 需控速 + 代理池',
    },
    'spider_us_ofac_sanctions_api': {
        'name': 'US OFAC SDN List',
        'doc': 'https://www.treasury.gov/ofac/downloads',
        'auth': '无 (但 ITA Consolidated Screening List 需 api.gov key)',
    },
    'spider_oec_world_trade_data': {
        'name': 'OEC World Trade Data',
        'doc': 'https://oec.world/en/resources/api',
        'auth': '免费需注册',
    },
    'spider_wto_': {
        'name': 'WTO 关税数据库',
        'doc': 'https://api.wto.org',
        'auth': 'subscription-key (免费需申请)',
    },
    'spider_imf_data_api': None,  # ✅ 已在 real_crawler 实现
    'spider_imf_datamapper_api': None,  # ✅ 已在 real_crawler 实现
    'spider_eurostat_': {
        'name': 'Eurostat',
        'doc': 'https://ec.europa.eu/eurostat/web/main/data/web-services',
        'auth': '免费无 Key (但 SDMX 解析较重)',
        'note': '建议接入 — 后续优先级高',
    },
    'spider_ecb_data_portal_': {
        'name': 'ECB Data Portal (SDW API)',
        'doc': 'https://data.ecb.europa.eu/help/api/overview',
        'auth': '免费无 Key, SDMX-XML 格式',
    },
    'spider_bls_': {
        'name': 'BLS (美国劳工统计局)',
        'doc': 'https://www.bls.gov/developers/api_signature_v2.htm',
        'auth': 'registrationKey',
        'free_tier': '500 query/day with key',
    },
    'spider_bea_': {
        'name': 'BEA (美国经济分析局)',
        'doc': 'https://apps.bea.gov/api/signup',
        'auth': 'UserID',
    },
    # ... 其余 register-tier 条目可继续补充
}


# ---- paid tier (付费 API) --------------------------------------------------
PAID_TIER_ROADMAP = {
    'spider_competitor_price_monitor_apify_': {
        'name': 'Competitor Price Monitor (Apify Actor)',
        'doc': 'https://apify.com/store',
        'auth': 'Apify Token, 按 actor run 计费',
    },
    'spider_google_news_scraper_apify_': {
        'name': 'Google News Scraper (Apify)',
        'doc': 'https://apify.com/store',
        'auth': 'Apify Token',
    },
    'spider_regulationsgov_crawler_apify_': {
        'name': 'Regulations.gov Crawler (Apify)',
        'doc': 'https://apify.com/store',
        'auth': 'Apify Token',
    },
    'spider_statista': {
        'name': 'Statista',
        'doc': 'https://www.statista.com/aboutus/our-research-commitment',
        'auth': '企业订阅, 无公开 API',
    },
    'spider_similarweb': {
        'name': 'SimilarWeb',
        'doc': 'https://developers.similarweb.com',
        'auth': '付费 API Key',
    },
    'spider_semrush_api': {
        'name': 'SEMrush API',
        'doc': 'https://www.semrush.com/api-documentation',
        'auth': '付费 API Key',
    },
    # ... 其余 paid-tier 条目可继续补充
}


def roadmap_for(spider_name: str) -> dict | None:
    """根据 spider_name 返回对应的接入说明 (None 表示已实现或未在路线图中)."""
    s = (spider_name or '').strip().lower()
    if s in REGISTER_TIER_ROADMAP:
        return REGISTER_TIER_ROADMAP[s]
    if s in PAID_TIER_ROADMAP:
        return PAID_TIER_ROADMAP[s]
    return None
