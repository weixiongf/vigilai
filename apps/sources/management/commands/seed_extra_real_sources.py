"""管理命令: 把"代码已实现但 data/*.json 里没有"的真实爬虫源补到 InfoSource.

适用场景: real_crawler.py 中已新增了 GitHub / arXiv / CoinGecko / Frankfurter /
OpenAlex / 公共 RSS 新闻聚合的真实采集器, 但 data_source_*.json 里没有对应
独立条目, 导致 scheduling 页面看不到也无法手动触发.

用法:
    python manage.py seed_extra_real_sources
    python manage.py seed_extra_real_sources --dry-run

幂等: 以 spider_name 作为 unique key, 已存在则跳过.
"""
from django.core.management.base import BaseCommand

from apps.sources.models import InfoSource


# 这些 spider_name 必须与 real_crawler.SPIDER_REGISTRY 中的 key 完全一致,
# 这样 dispatch 走精确匹配, 不依赖关键词模糊路由.
EXTRA_SOURCES = [
    {
        'spider_name': 'spider_github',
        'name': 'GitHub Public API（开源仓库趋势）',
        'category': 'Tech - 开源生态',
        'official_url': 'https://github.com',
        'list_url': 'https://api.github.com/search/repositories',
        'source_type': 'api',
        'interface_type': 'REST API',
        'data_format': 'JSON',
        'update_frequency': '每小时',
        'crawl_method': 'GitHub Search API (公开)',
        'rate_limit_hint': '60次/小时(匿名)/5000次/小时(token)',
        'access_tier': 'free',
        'priority': 'high',
        'difficulty': 1,
        'relevance': '高 - 技术趋势/开源竞品',
        'notes': '采集近期 stars 增长最快的仓库, 监测开源动态',
    },
    {
        'spider_name': 'spider_arxiv',
        'name': 'arXiv（预印本论文）',
        'category': 'Tech - 学术前沿',
        'official_url': 'https://arxiv.org',
        'list_url': 'https://export.arxiv.org/api/query',
        'source_type': 'api',
        'interface_type': 'Atom Feed',
        'data_format': 'XML',
        'update_frequency': '每日',
        'crawl_method': 'arXiv Atom API',
        'rate_limit_hint': '≤3次/秒',
        'access_tier': 'free',
        'priority': 'high',
        'difficulty': 1,
        'relevance': '高 - AI/CS/物理 等前沿研究',
        'notes': '关注 cs.AI / cs.LG / cs.CL 等分类的最新预印本',
    },
    {
        'spider_name': 'spider_coingecko',
        'name': 'CoinGecko（加密货币市场）',
        'category': 'Crypto - 加密资产',
        'official_url': 'https://www.coingecko.com',
        'list_url': 'https://api.coingecko.com/api/v3/coins/markets',
        'source_type': 'api',
        'interface_type': 'REST API',
        'data_format': 'JSON',
        'update_frequency': '实时',
        'crawl_method': 'CoinGecko Public API',
        'rate_limit_hint': '10-50次/分钟',
        'access_tier': 'free',
        'priority': 'medium',
        'difficulty': 1,
        'relevance': '中 - 加密市场情绪/资金流',
        'notes': '采集市值前 N 加密资产快照',
    },
    {
        'spider_name': 'spider_frankfurter',
        'name': 'Frankfurter（外汇汇率）',
        'category': 'Economic - 外汇',
        'official_url': 'https://www.frankfurter.app',
        'list_url': 'https://api.frankfurter.app/latest',
        'source_type': 'api',
        'interface_type': 'REST API',
        'data_format': 'JSON',
        'update_frequency': '每日(欧央行)',
        'crawl_method': 'Frankfurter Public API',
        'rate_limit_hint': '无明确限制',
        'access_tier': 'free',
        'priority': 'medium',
        'difficulty': 1,
        'relevance': '中 - 进出口汇率成本',
        'notes': '基于 ECB 参考汇率, 无需 Key',
    },
    {
        'spider_name': 'spider_openalex',
        'name': 'OpenAlex（学术论文图谱）',
        'category': 'Tech - 学术图谱',
        'official_url': 'https://openalex.org',
        'list_url': 'https://api.openalex.org/works',
        'source_type': 'api',
        'interface_type': 'REST API',
        'data_format': 'JSON',
        'update_frequency': '每日',
        'crawl_method': 'OpenAlex Public API',
        'rate_limit_hint': '10次/秒',
        'access_tier': 'free',
        'priority': 'medium',
        'difficulty': 1,
        'relevance': '中 - 学术影响力/技术追踪',
        'notes': '覆盖 2.4 亿篇论文/作者/机构, Microsoft Academic 替代',
    },
    {
        'spider_name': 'spider_rss_news',
        'name': '国际新闻 RSS 聚合（BBC/Guardian/CNN/NPR/Al Jazeera）',
        'category': 'Media - 国际新闻',
        'official_url': 'https://www.bbc.com',
        'list_url': 'https://feeds.bbci.co.uk/news/world/rss.xml',
        'source_type': 'rss',
        'interface_type': 'RSS',
        'data_format': 'XML',
        'update_frequency': '实时',
        'crawl_method': '通用 RSS 解析(并发拉取多家)',
        'rate_limit_hint': '≥10秒/家',
        'access_tier': 'free',
        'priority': 'high',
        'difficulty': 1,
        'relevance': '高 - 全球宏观/地缘事件',
        'notes': '一次采集打包 BBC/Guardian/CNN/NPR/Al Jazeera 五家头条',
    },
]


class Command(BaseCommand):
    help = '补齐已实现真实爬虫但 data/*.json 缺失的 InfoSource 记录'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='只打印不写入')

    def handle(self, *args, **options):
        dry = options['dry_run']
        created = 0
        skipped = 0
        for cfg in EXTRA_SOURCES:
            spider = cfg['spider_name']
            exist = InfoSource.objects.filter(spider_name=spider).first()
            if exist:
                self.stdout.write(self.style.WARNING(
                    f'  [SKIP] {spider} 已存在 (id={exist.id}, name={exist.name})'))
                skipped += 1
                continue
            if dry:
                self.stdout.write(self.style.HTTP_INFO(
                    f'  [DRY] +{spider} -> {cfg["name"]}'))
                continue
            obj = InfoSource.objects.create(
                name=cfg['name'][:200],
                category=cfg['category'][:80],
                official_url=cfg['official_url'][:500],
                list_url=cfg['list_url'][:500],
                source_type=cfg['source_type'],
                interface_type=cfg['interface_type'][:80],
                data_format=cfg['data_format'][:40],
                update_frequency=cfg['update_frequency'][:80],
                crawl_method=cfg['crawl_method'][:200],
                rate_limit_hint=cfg['rate_limit_hint'][:120],
                access_tier=cfg['access_tier'],
                priority=cfg['priority'],
                difficulty=cfg['difficulty'],
                spider_name=cfg['spider_name'],
                relevance=cfg['relevance'][:120],
                notes=cfg['notes'],
                is_active=True,
            )
            created += 1
            self.stdout.write(self.style.SUCCESS(
                f'  [NEW] id={obj.id} {obj.name} -> {obj.spider_name} '
                f'(tier={obj.access_tier})'))
        self.stdout.write(self.style.SUCCESS(
            f'\n=== 完成: 新建 {created} 条, 跳过 {skipped} 条 ==='))
