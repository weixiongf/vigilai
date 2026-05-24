"""管理命令: 自举默认通知收件人 (邮件 + 飞书 Webhook).

读取 .env / settings 中的 DEFAULT_RECIPIENT_EMAIL / FEISHU_WEBHOOK_URL,
确保 NotificationRecipient 表里至少有一条订阅了高影响告警/日报/周报的活跃记录.

用法:
    python manage.py bootstrap_recipients                  # 按 .env 默认值创建
    python manage.py bootstrap_recipients --email a@b.com  # 显式指定邮箱
    python manage.py bootstrap_recipients --list           # 仅列出现有收件人
"""
from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.notifications.models import NotificationRecipient


class Command(BaseCommand):
    help = '自举默认通知收件人 (默认: v5cg@qq.com + 飞书 webhook)'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, default='',
                            help='指定收件邮箱 (覆盖 .env 默认值)')
        parser.add_argument('--name', type=str, default='',
                            help='收件人姓名')
        parser.add_argument('--feishu', type=str, default='',
                            help='飞书 webhook URL (覆盖 .env 默认值)')
        parser.add_argument('--list', action='store_true',
                            help='仅列出当前所有收件人')

    def handle(self, *args, **opts):
        if opts['list']:
            self._print_all()
            return

        email = (opts['email']
                 or os.environ.get('DEFAULT_RECIPIENT_EMAIL', '')
                 or 'v5cg@qq.com').strip()
        name = (opts['name']
                or os.environ.get('DEFAULT_RECIPIENT_NAME', '')
                or '战略情报负责人').strip()
        feishu = (opts['feishu']
                  or getattr(settings, 'FEISHU_WEBHOOK_URL', '')
                  or '').strip()

        if not email and not feishu:
            self.stdout.write(self.style.ERROR(
                '邮箱与飞书 webhook 都为空, 没有可用通道; 请用 --email 或在 .env '
                '中设置 DEFAULT_RECIPIENT_EMAIL / FEISHU_WEBHOOK_URL'))
            return

        recipient, created = NotificationRecipient.objects.update_or_create(
            email=email,
            defaults={
                'name': name,
                'role': '默认收件人',
                'feishu_webhook': feishu,
                'subscribe_high_impact': True,
                'subscribe_daily': True,
                'subscribe_weekly': True,
                'is_active': True,
            },
        )
        verb = '已创建' if created else '已更新'
        self.stdout.write(self.style.SUCCESS(
            f'[bootstrap] {verb}收件人 #{recipient.id}: '
            f'{recipient.name} <{recipient.email}>'))
        if feishu:
            self.stdout.write(f'  飞书 webhook: {feishu[:80]}...')
        self.stdout.write('  订阅: 高影响告警 / 日报 / 周报 (全开)')

        self._print_all()

    def _print_all(self):
        qs = NotificationRecipient.objects.all().order_by('id')
        if not qs:
            self.stdout.write('当前 NotificationRecipient 表为空')
            return
        self.stdout.write(self.style.HTTP_INFO(
            f'\n=== 当前共有 {qs.count()} 条收件人 ==='))
        for r in qs:
            flags = []
            if r.subscribe_high_impact:
                flags.append('告警')
            if r.subscribe_daily:
                flags.append('日报')
            if r.subscribe_weekly:
                flags.append('周报')
            channels = []
            if r.email:
                channels.append(f'email={r.email}')
            if r.feishu_webhook:
                channels.append('feishu=✓')
            status = '✓' if r.is_active else '✗'
            self.stdout.write(
                f'  [{status}] #{r.id} {r.name} ({r.role or "—"}) '
                f'订阅={"/".join(flags) or "无"} {" ".join(channels)}')
