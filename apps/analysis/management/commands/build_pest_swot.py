"""管理命令: 生成 PEST 快照 + SWOT 矩阵."""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.analysis.services.pest import aggregate_pest
from apps.analysis.services.swot import build_swot
from apps.intelligence.models import RawInfo


class Command(BaseCommand):
    help = '生成最近 N 天的 PEST 快照与 SWOT 分析(覆盖 global + Top 市场)'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7)
        parser.add_argument('--markets', nargs='*',
                            help='指定市场名称(空则自动取 Top6 + global)')

    def handle(self, *args, **options):
        end = date.today()
        start = end - timedelta(days=options['days'] - 1)

        markets = options['markets']
        if not markets:
            top = (RawInfo.objects.filter(is_processed=True)
                   .values('target_market')
                   .annotate(c=Count('id'))
                   .order_by('-c')[:6])
            markets = ['global'] + [r['target_market'] for r in top
                                    if r['target_market']]

        for m in markets:
            self.stdout.write(self.style.HTTP_INFO(
                f'>>> {m}: {start} ~ {end}'))
            snap = aggregate_pest(start, end, m)
            swot = build_swot(snap)
            self.stdout.write(
                f'  PEST id={snap.id} '
                f'P/E/S/T={len(snap.political_items)}/'
                f'{len(snap.economic_items)}/'
                f'{len(snap.social_items)}/'
                f'{len(snap.technological_items)}; '
                f'SWOT id={swot.id} 置信度={swot.confidence_score}')

        self.stdout.write(self.style.SUCCESS(
            f'\n=== 完成: 共 {len(markets)} 个市场的 PEST+SWOT ==='))
