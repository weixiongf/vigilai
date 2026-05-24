"""管理命令: 切换 / 查看数据源仿真模式.

用法:
    python manage.py simulation_mode --status
    python manage.py simulation_mode --on        # = simulated
    python manage.py simulation_mode --off       # = real
    python manage.py simulation_mode --auto      # = auto
    python manage.py simulation_mode --reset <source_id>   # 清零失败计数
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.sources.models import InfoSource
from apps.sources.services import fallback as fb


class Command(BaseCommand):
    help = '查看 / 切换数据源仿真模式 (auto / simulated / real)'

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group()
        g.add_argument('--status', action='store_true', help='查看当前状态')
        g.add_argument('--on', action='store_true', help='强制仿真模式')
        g.add_argument('--off', action='store_true', help='强制真实模式')
        g.add_argument('--auto', action='store_true', help='自动模式 (失败超阈值降级)')
        g.add_argument('--reset', type=int, metavar='SOURCE_ID',
                       help='清零指定信息源连续失败计数')

    def handle(self, *args, **opts):
        if opts['reset'] is not None:
            try:
                src = InfoSource.objects.get(id=opts['reset'])
            except InfoSource.DoesNotExist:
                raise CommandError(f'source #{opts["reset"]} not found')
            fb.reset_failure(src)
            self.stdout.write(self.style.SUCCESS(
                f'[reset] {src.name} 失败计数已清零'))
            return

        if opts['on']:
            fb.set_mode('simulated')
        elif opts['off']:
            fb.set_mode('real')
        elif opts['auto']:
            fb.set_mode('auto')

        snap = fb.snapshot()
        self.stdout.write(self.style.SUCCESS(
            f'[mode] {snap["mode"]}  threshold={snap["threshold"]}  '
            f'fallback_on_failure={snap["fallback_on_failure"]}'))
        if snap['failing_sources']:
            self.stdout.write('当前失败计数 > 0 的信息源:')
            for it in snap['failing_sources']:
                self.stdout.write(
                    f'  - #{it["source_id"]} {it["name"]} '
                    f'(连续失败 {it["consecutive_failures"]} 次)')
        else:
            self.stdout.write('  (所有活跃信息源失败计数为 0)')
