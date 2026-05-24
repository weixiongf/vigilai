"""管理命令: 生成战略简报(自动级联 PEST + SWOT).

策略:
  - 日报: 仅生成 1 份 global 综合简报;
  - 周报: 生成 1 份 global 周报, 内含各市场分区子章节.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.briefings.services.generator import generate_briefing
from apps.intelligence.models import RawInfo


class Command(BaseCommand):
    help = '生成战略简报: 日报=1份global, 周报=1份global+市场分区'

    def add_arguments(self, parser):
        parser.add_argument('--period', default='daily',
                            choices=['daily', 'weekly', 'monthly'],
                            help='周期类型')
        parser.add_argument('--days-back', type=int, default=0,
                            help='以 today-N 作为 period_end (用于历史回测)')

    def handle(self, *args, **options):
        period = options['period']
        end = date.today() - timedelta(days=options['days_back'])
        if period == 'daily':
            start = end
        elif period == 'weekly':
            start = end - timedelta(days=6)
        else:
            start = end - timedelta(days=29)

        # 周报额外参数: 各市场分区
        market_breakdown = None
        if period == 'weekly':
            top = (RawInfo.objects.filter(is_processed=True)
                   .values('target_market')
                   .annotate(c=Count('id'))
                   .order_by('-c')[:5])
            market_breakdown = [r['target_market'] for r in top
                                if r['target_market']]
            self.stdout.write(self.style.HTTP_INFO(
                f'  周报市场分区: {market_breakdown}'))

        self.stdout.write(self.style.HTTP_INFO(
            f'>>> 生成 global {period} 简报...'))
        b = generate_briefing(period_type=period,
                              period_start=start, period_end=end,
                              target_market='global',
                              auto_pest_swot=True,
                              market_breakdown=market_breakdown)
        self.stdout.write(
            f'  Briefing id={b.id} title="{b.title}" '
            f'机会={len(b.top_opportunities)} 风险={len(b.top_risks)} '
            f'行动={len(b.recommended_actions)} '
            f'章节={b.sections.count()}')

        self.stdout.write(self.style.SUCCESS(
            f'\n=== 完成: 已生成 1 份{period}简报 ==='))
