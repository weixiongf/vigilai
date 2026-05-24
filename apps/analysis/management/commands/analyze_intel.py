"""管理命令: 对未分析的 RawInfo 调用 LLM Provider 进行 PEST/评分/行动建议."""
from django.core.management.base import BaseCommand

from apps.analysis.services.analyzer import analyze_batch
from apps.intelligence.models import RawInfo


class Command(BaseCommand):
    help = '对未分析的情报批量执行 LLM 分析(默认 Mock Provider)'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0,
                            help='本次最多处理多少条(0=全部)')
        parser.add_argument('--reset', action='store_true',
                            help='将所有 is_processed=True 重置后再分析')
        parser.add_argument('--only-simulated', action='store_true',
                            help='仅处理仿真数据')

    def handle(self, *args, **options):
        if options['reset']:
            n = RawInfo.objects.update(is_processed=False)
            self.stdout.write(self.style.WARNING(f'已重置 {n} 条情报的处理状态'))

        qs = RawInfo.objects.filter(is_processed=False)
        if options['only_simulated']:
            qs = qs.filter(is_simulated=True)

        pending = qs.count()
        if pending == 0:
            self.stdout.write(self.style.SUCCESS('无待分析情报。'))
            return

        self.stdout.write(self.style.HTTP_INFO(
            f'>>> 待分析: {pending} 条 (limit={options["limit"] or "ALL"})'))

        success = analyze_batch(queryset=qs, limit=options['limit'])

        # 打印分析后分布
        total_proc = RawInfo.objects.filter(is_processed=True).count()
        crit = RawInfo.objects.filter(impact_score__gte=8).count()
        opp = RawInfo.objects.filter(opportunity_or_threat='O').count()
        thr = RawInfo.objects.filter(opportunity_or_threat='T').count()
        self.stdout.write(self.style.SUCCESS(
            f'\n=== 完成: 本次分析 {success} 条, '
            f'累计已分析 {total_proc} 条 (高影响 {crit}, 机会 {opp}, 威胁 {thr}) ==='))
