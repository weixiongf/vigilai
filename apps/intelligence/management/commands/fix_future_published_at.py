"""一次性修复脚本 — 清洗 RawInfo 中离谱的 published_at 时间.

背景:
IMF DataMapper / World Bank 等宏观数据源会返回包含未来预测的年份 (如 2031),
早期采集器直接把 latest_year 拼装为 published_at, 导致 feed 列表出现
"2031/12/31 08:00:00" 这种离谱发布时间.

合理区间 (相对今天 today):
    [today - 90 天, today]  — 默认窗口
本命令默认把所有 published_at > now() 或 published_at < now()-90d 的记录,
重映射到 [now()-90d, now()] 之间, 优先用 fetched_at, 否则按 url hash
均匀打散到合理区间内 (保持稳定性, 同一条 RawInfo 多次执行结果一致).

使用:
    python manage.py fix_future_published_at            # 实际写入
    python manage.py fix_future_published_at --dry-run  # 仅预览
    python manage.py fix_future_published_at --window 90  # 自定义窗口天数
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.intelligence.models import RawInfo


class Command(BaseCommand):
    help = '清洗 RawInfo 中超未来 / 过早的 published_at, 夹紧到合理区间'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='仅预览不写入')
        parser.add_argument('--window', type=int, default=90,
                            help='合理区间窗口天数, 默认 90')

    def handle(self, *args, **opts):
        dry = opts.get('dry_run', False)
        window_days = max(1, int(opts.get('window') or 90))

        now = timezone.now()
        upper = now
        lower = now - timedelta(days=window_days)
        span_seconds = max(1, int((upper - lower).total_seconds()))

        # 找出所有越界条目: published_at > now() 或 < now()-window
        bad_qs = RawInfo.objects.filter(
            Q(published_at__gt=upper) | Q(published_at__lt=lower)
        ).only('id', 'url', 'published_at', 'fetched_at')

        total_bad = bad_qs.count()
        if total_bad == 0:
            self.stdout.write(self.style.SUCCESS(
                f'无需修复: 所有 RawInfo.published_at 已在 '
                f'[{lower:%Y-%m-%d %H:%M}, {upper:%Y-%m-%d %H:%M}] 区间内'))
            return

        future_cnt = bad_qs.filter(published_at__gt=upper).count()
        too_old_cnt = total_bad - future_cnt

        self.stdout.write(self.style.WARNING(
            f'发现 {total_bad} 条越界记录: '
            f'未来时间={future_cnt}, 过早时间={too_old_cnt}'))
        self.stdout.write(
            f'合理区间: [{lower:%Y-%m-%d %H:%M}, {upper:%Y-%m-%d %H:%M}]')

        fixed = 0
        for raw in bad_qs.iterator():
            new_dt = self._remap(raw, lower, upper, span_seconds)
            if not dry:
                RawInfo.objects.filter(pk=raw.pk).update(published_at=new_dt)
            fixed += 1
            if fixed <= 5:
                self.stdout.write(
                    f'  · id={raw.id} {raw.published_at:%Y-%m-%d} → '
                    f'{new_dt:%Y-%m-%d %H:%M:%S}')

        prefix = '[dry-run] ' if dry else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}完成: 修复 {fixed} 条 RawInfo.published_at'))

    @staticmethod
    def _remap(raw: RawInfo, lower, upper, span_seconds: int):
        """选择新的 published_at:

        1) 若 fetched_at 已落在 [lower, upper] 区间内 → 直接用 fetched_at
           (这是最准确的"系统首次见到该情报"的时间)
        2) 否则用 url hash 把记录稳定地均匀打散到合理区间内,
           保证多次执行结果一致, 不会让数据"漂移".
        """
        f = raw.fetched_at
        if f is not None and lower <= f <= upper:
            return f
        key = (raw.url or str(raw.pk)).encode('utf-8', errors='ignore')
        h = int(hashlib.md5(key).hexdigest()[:8], 16)
        offset = h % span_seconds
        from datetime import timedelta as _td
        return lower + _td(seconds=offset)
