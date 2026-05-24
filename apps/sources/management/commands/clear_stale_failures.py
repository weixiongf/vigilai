"""\u4e00\u6b21\u6027\u4fee\u590d\u811a\u672c \u2014 \u6e05\u7406\u5386\u53f2\u810f\u5931\u8d25\u8ba1\u6570 / \u9519\u8bef\u6587\u6848.

\u80cc\u666f:
\u65e9\u671f\u7248\u672c\u4e2d, \u672a\u6ce8\u518c spider \u7684\u4fe1\u606f\u6e90 \u5728 except Exception \u5206\u652f\u91cc\u5403\u4e0b
"\u771f\u5b9e\u5931\u8d25(spider not in real_crawler registry)" + record_failure(),
\u5bfc\u81f4 cache \u91cc\u9057\u7559\u4e86\u5927\u91cf\u8ba1\u6570 + \u8be5\u8bbe\u7f6e\u4e86 last_status='failed' / last_message='spider...'.

\u672c\u547d\u4ee4\u4f1a:
1) \u904d\u5386\u6240\u6709 InfoSource;
2) \u8c03\u7528 fb.reset_failure(src) \u6e05\u638d cache \u8ba1\u6570;
3) \u82e5 last_message \u5305\u542b "not in real_crawler registry" \u6216 \u4ec5\u542b\u4ec5\u8d39\u5931\u8d25\u540e\u7eed\u5df2\u4eff\u771f\u8865\u4e0a, \u91cd\u7f6e\u4e3a\u51c0\u6001;
4) \u4e0d\u4f1a\u52a8\u4f5c access_tier / spider_name \u7b49\u8be6\u7ec6\u914d\u7f6e.

\u4f7f\u7528: ``python manage.py clear_stale_failures``
\u53ef\u52a0 ``--dry-run`` \u53ea\u9884\u89c8\u4e0d\u5199.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.sources.models import InfoSource
from apps.sources.services import fallback as fb


_STALE_PATTERNS = (
    'not in real_crawler registry',
    '\u672a\u6ce8\u518c\u771f\u5b9e\u91c7\u96c6\u5668',
    '\u771f\u5b9e\u5931\u8d25(spider ',
)


class Command(BaseCommand):
    help = '\u6e05\u7406\u4fe1\u606f\u6e90\u5386\u53f2\u810f\u5931\u8d25\u8ba1\u6570 / \u9519\u8bef\u6587\u6848 (\u4e00\u6b21\u6027\u4fee\u590d\u811a\u672c)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='\u53ea\u9884\u89c8\u4e0d\u5b9e\u9645\u4fee\u6539')

    def handle(self, *args, **opts):
        dry = opts.get('dry_run', False)
        total = InfoSource.objects.count()
        cleared_cache = 0
        cleared_msg = 0

        for src in InfoSource.objects.all().iterator():
            cnt = fb.failure_count(src)
            if cnt > 0:
                if not dry:
                    fb.reset_failure(src)
                cleared_cache += 1

            msg = (src.last_message or '').strip()
            if any(p in msg for p in _STALE_PATTERNS):
                if not dry:
                    src.last_status = 'pending'
                    src.last_message = ''
                    src.save(update_fields=['last_status', 'last_message', 'updated_at'])
                cleared_msg += 1

        prefix = '[dry-run] ' if dry else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}\u5b8c\u6210: \u4fe1\u606f\u6e90\u603b\u6570={total}, '
            f'\u6e05\u7406 cache \u5931\u8d25\u8ba1\u6570={cleared_cache}, '
            f'\u91cd\u7f6e last_message \u810f\u6587\u6848={cleared_msg}'))
