"""管理命令：生成仿真情报种子数据 (默认 500 条)。

用法:
    python manage.py seed_intel
    python manage.py seed_intel --count 500
    python manage.py seed_intel --count 800 --reset
    python manage.py seed_intel --days 30

字段覆盖:
  - 战略维度 / 目标市场 / PEST / O-T / H-M-L / 影响分数 / 价值评分
  - 真实信息源关联 (从已导入的 InfoSource 中按维度匹配)
  - 时间分布在最近 N 天
  - is_simulated=True 区分真实数据
"""
import hashlib
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.intelligence.models import RawInfo
from apps.sources.models import InfoSource

from ._simulation_corpus import (
    TARGET_MARKETS, COMPETITORS, PLATFORMS, KOLS, REGULATORS, TEMPLATES,
)


# 维度到信息源类别(category)关键词的近似映射,
# 用来从 InfoSource 中挑一个看上去合适的来源 FK
DIMENSION_SOURCE_HINTS = {
    'competition': ['竞品', '商业', '科技', '财经', '产业', 'tech', 'business'],
    'product':     ['消费', '产品', '电商', '零售', 'consumer', 'retail'],
    'platform':    ['电商', '平台', 'amazon', 'tiktok', 'shopee'],
    'social':      ['社交', '社媒', 'social', 'reddit', 'tiktok', 'youtube'],
    'regulation':  ['法规', '政策', '海关', 'regulation', 'policy', 'gov', 'fed', 'eu'],
    'macro':       ['economic', '经济', '宏观', 'fred', 'bls', 'ecb', 'imf', '央行'],
    'industry':    ['行业', '研究', 'research', 'industry', 'mckinsey', 'gartner'],
    'other':       [],
}


def _pick_source_by_dimension(dimension: str, cache: dict):
    """根据维度从 InfoSource 中随机挑一个最贴近的来源."""
    if dimension in cache:
        pool = cache[dimension]
    else:
        hints = DIMENSION_SOURCE_HINTS.get(dimension, [])
        qs = InfoSource.objects.filter(is_active=True)
        pool = []
        for src in qs:
            blob = (src.name + ' ' + src.category).lower()
            if any(h.lower() in blob for h in hints):
                pool.append(src)
        if not pool:
            pool = list(qs[:30])
        cache[dimension] = pool
    return random.choice(pool) if pool else None


def _fill_template(tpl: str, market_name: str) -> str:
    """填充占位符 {market}/{competitor}/{platform}/{kol}/{regulator}/{value}/{pct}."""
    return (
        tpl
        .replace('{market}', market_name)
        .replace('{competitor}', random.choice(COMPETITORS))
        .replace('{platform}', random.choice(PLATFORMS))
        .replace('{kol}', random.choice(KOLS))
        .replace('{regulator}', random.choice(REGULATORS))
        .replace('{value}', str(random.choice([3, 5, 7, 10, 12, 15, 20, 30, 50, 80, 100])))
        .replace('{pct}', str(random.choice([3, 5, 7, 8, 10, 12, 15, 18, 22, 25, 30])))
    )


def _build_record(template: dict, market: dict, idx: int, max_days: int):
    """根据模板+市场+序号构造一条 RawInfo 待写记录."""
    title = _fill_template(template['title_tpl'], market['name'])
    content = _fill_template(template['content_tpl'], market['name'])

    # 价值评分四要素 (与项目 README 一致: 0-4 / 0-3 / 0-2 / 0-1)
    seed = template['score_seed']
    s_relevance = round(min(4.0, max(0.0, seed * 0.45 + random.uniform(-0.4, 0.4))), 2)
    s_urgency   = round(min(3.0, max(0.0, seed * 0.32 + random.uniform(-0.4, 0.4))), 2)
    s_authority = round(min(2.0, max(0.0, seed * 0.22 + random.uniform(-0.3, 0.3))), 2)
    s_scope     = round(min(1.0, max(0.0, seed * 0.10 + random.uniform(-0.2, 0.2))), 2)
    impact_score = round(s_relevance + s_urgency + s_authority + s_scope, 2)

    # impact_type 由 ot+severity 推导
    if template['ot'] == 'O':
        impact_type = 'opportunity'
    elif template['level'] == 'H':
        impact_type = 'risk'
    elif template['level'] == 'M':
        impact_type = 'watch'
    else:
        impact_type = 'watch'

    severity_map = {'H': 'high', 'M': 'medium', 'L': 'low'}
    severity = severity_map[template['level']]

    # 时间分布: 越近的日期权重越大 (指数衰减)
    days_ago = int(random.expovariate(1 / 5))  # 均值≈5 天
    days_ago = min(days_ago, max_days)
    published_at = timezone.now() - timedelta(
        days=days_ago,
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )

    # 唯一 URL (避免 unique 冲突): hash 标题+市场+序号
    digest = hashlib.md5(f'{title}|{market["code"]}|{idx}'.encode('utf-8')).hexdigest()[:16]
    url = f'https://sim.strategic-radar.local/intel/{digest}'

    # 摘要 = 内容前 80 字
    summary = content[:80] + ('...' if len(content) > 80 else '')

    # 标签 = 模板标签 + 市场代码
    tags = list(template['tags']) + [market['code'], market['region']]

    # 受影响实体 (随机 1-2 个)
    entities = []
    if template['dimension'] == 'competition':
        entities.append(random.choice(COMPETITORS))
    if template['dimension'] == 'platform':
        entities.append(random.choice(PLATFORMS))
    if template['dimension'] == 'social':
        entities.append(random.choice(KOLS))
    if template['dimension'] == 'regulation':
        entities.append(random.choice(REGULATORS))
    if not entities:
        entities = [market['name']]

    return {
        'title': title[:500],
        'content': content,
        'summary': summary,
        'url': url,
        'reference_quote': content.split('。')[0][:200],
        'language': 'zh',
        'raw_json': {'simulated': True, 'template_dimension': template['dimension']},
        'published_at': published_at,
        'strategic_dimension': template['dimension'],
        'target_market': market['name'],
        'country': market['name'],
        'impact_type': impact_type,
        'severity': severity,
        'impact_score': impact_score,
        'sentiment': template['sentiment'],
        'pest_type': template['pest'],
        'opportunity_or_threat': template['ot'],
        'impact_level': template['level'],
        'impact_rationale': '基于模板维度+市场+严重度自动评估',
        'score_relevance': s_relevance,
        'score_urgency': s_urgency,
        'score_authority': s_authority,
        'score_scope': s_scope,
        'affected_entities': entities,
        'tags': tags,
        'is_simulated': True,
        'is_processed': False,  # 留给 LLM 分析阶段后续处理
        'action_advice': '',
        'analysis_chain': None,
    }


class Command(BaseCommand):
    help = '生成仿真情报种子数据 (默认 500 条)'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=500, help='生成条数')
        parser.add_argument('--days', type=int, default=30, help='时间窗口(天)')
        parser.add_argument('--reset', action='store_true', help='清空已有仿真数据')
        parser.add_argument('--seed', type=int, default=None, help='随机种子(可复现)')

    def handle(self, *args, **options):
        if options['seed'] is not None:
            random.seed(options['seed'])

        count = options['count']
        max_days = options['days']

        if options['reset']:
            n = RawInfo.objects.filter(is_simulated=True).count()
            RawInfo.objects.filter(is_simulated=True).delete()
            self.stdout.write(self.style.WARNING(f'已清空 {n} 条仿真数据'))

        if not InfoSource.objects.exists():
            self.stderr.write(self.style.ERROR(
                '未发现任何 InfoSource, 请先运行: python manage.py import_sources'))
            return

        source_cache: dict = {}
        records = []
        seen_urls = set(RawInfo.objects.values_list('url', flat=True))

        attempts = 0
        max_attempts = count * 4  # 防止极端碰撞

        while len(records) < count and attempts < max_attempts:
            attempts += 1
            template = random.choice(TEMPLATES)
            market = random.choice(TARGET_MARKETS)
            payload = _build_record(template, market, attempts, max_days)

            if payload['url'] in seen_urls:
                continue
            seen_urls.add(payload['url'])

            payload['source'] = _pick_source_by_dimension(
                template['dimension'], source_cache)

            records.append(payload)

        # 批量写入: 切批 transaction
        BATCH = 100
        with transaction.atomic():
            for i in range(0, len(records), BATCH):
                chunk = records[i:i + BATCH]
                RawInfo.objects.bulk_create(
                    [RawInfo(**r) for r in chunk], ignore_conflicts=True)

        # 简要分布统计
        total = RawInfo.objects.filter(is_simulated=True).count()
        self.stdout.write(self.style.SUCCESS(
            f'\n=== 完成: 本次生成 {len(records)} 条, 数据库仿真情报合计 {total} 条 ==='))

        # 打印分布
        self.stdout.write('\n按维度分布:')
        for d in ['competition', 'product', 'platform', 'social',
                  'regulation', 'macro', 'industry']:
            n = RawInfo.objects.filter(is_simulated=True, strategic_dimension=d).count()
            self.stdout.write(f'  {d:12s} {n:5d}')

        self.stdout.write('\n按价值等级分布:')
        for label, lo, hi in [('critical', 8, 99), ('medium', 5, 8),
                               ('low', 3, 5), ('noise', 0, 3)]:
            n = RawInfo.objects.filter(
                is_simulated=True, impact_score__gte=lo, impact_score__lt=hi).count()
            self.stdout.write(f'  {label:10s} {n:5d}')

        self.stdout.write('\n按 PEST 分布:')
        for p in ['P', 'E', 'S', 'T']:
            n = RawInfo.objects.filter(is_simulated=True, pest_type=p).count()
            self.stdout.write(f'  {p}  {n:5d}')

        self.stdout.write('\n按目标市场 Top10:')
        from django.db.models import Count
        top_markets = (RawInfo.objects.filter(is_simulated=True)
                       .values('target_market')
                       .annotate(c=Count('id'))
                       .order_by('-c')[:10])
        for row in top_markets:
            self.stdout.write(f'  {row["target_market"]:12s} {row["c"]:5d}')
