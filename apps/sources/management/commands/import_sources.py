"""管理命令：将 data/*.json 信息源元数据导入 InfoSource 表。

用法:
    python manage.py import_sources
    python manage.py import_sources --files data/data_source_1.json
    python manage.py import_sources --truncate
"""
import glob
import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sources.models import InfoSource


PRIORITY_MAP = {
    '🔴 最高': 'critical',
    '🔴最高': 'critical',
    '最高': 'critical',
    '🟠 高': 'high',
    '🟠高': 'high',
    '高': 'high',
    '🟡 中': 'medium',
    '🟡中': 'medium',
    '中': 'medium',
    '🟢 低': 'low',
    '🟢低': 'low',
    '低': 'low',
}

YES_TOKENS = {'是', 'yes', 'y', 'true', '1', '需注册', '需要', '需登录'}


def parse_difficulty(value: str) -> int:
    """ ⭐ 数量 -> 整数 1-5"""
    if not value:
        return 2
    stars = str(value).count('⭐')
    if stars == 0:
        # 兜底从数字解析
        m = re.search(r'(\d+)', str(value))
        return int(m.group(1)) if m else 2
    return min(max(stars, 1), 5)


def parse_priority(value: str) -> str:
    if not value:
        return 'medium'
    s = str(value).strip()
    if s in PRIORITY_MAP:
        return PRIORITY_MAP[s]
    for k, v in PRIORITY_MAP.items():
        if k in s:
            return v
    return 'medium'


def parse_bool(value: str) -> bool:
    if value is None:
        return False
    s = str(value).strip().lower()
    if not s:
        return False
    if any(tok in s for tok in YES_TOKENS):
        if '否' in s or 'no' in s or 'n/a' in s:
            return '是' in s
        return True
    if '免费' in s and '付费' not in s:
        return False
    return False


def parse_paid(value: str) -> bool:
    if not value:
        return False
    s = str(value).strip()
    if '付费' in s or 'paid' in s.lower():
        return True
    return False


def detect_source_type(item: dict) -> str:
    """根据 接口信息源类型 / 数据获取方式 / 数据格式 推断源类型"""
    interface = (item.get('接口信息源类型') or '').lower()
    method = (item.get('数据获取方式') or '').lower()
    fmt = (item.get('数据格式') or '').lower()
    cat = (item.get('信息源类别') or '').lower()

    if 'api' in interface or 'api' in method or 'rest' in method or 'sdmx' in method:
        return 'api'
    if 'rss' in interface or 'rss' in method or 'rss' in fmt or 'atom' in fmt:
        return 'rss'
    if any(k in cat for k in ['social', '社交', 'twitter', 'tiktok', 'youtube', 'reddit']):
        return 'social'
    if 'web' in method or '爬' in method or 'html' in fmt:
        return 'web'
    return 'mixed'


def derive_spider_name(name: str) -> str:
    """根据信息源名称生成 spider 标识"""
    s = re.sub(r'[\s（）()\[\]【】\u00a0]+', '_', name)
    s = re.sub(r'[^A-Za-z0-9_\u4e00-\u9fff]+', '', s)
    return f'spider_{s.lower()}'[:120]


def derive_access_tier(payload: dict) -> str:
    """根据 is_paid / needs_register / needs_login 判定访问层级.

    优先级: paid > register > free.
    """
    if payload.get('is_paid'):
        return 'paid'
    if payload.get('needs_register') or payload.get('needs_login'):
        return 'register'
    return 'free'


class Command(BaseCommand):
    help = '将 data/*.json 信息源元数据批量导入 InfoSource 表'

    def add_arguments(self, parser):
        parser.add_argument(
            '--files', nargs='*',
            help='指定 JSON 文件(空则扫描 data/data_source_*.json)')
        parser.add_argument(
            '--truncate', action='store_true',
            help='导入前清空 InfoSource 表(慎用)')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='只打印不写入')

    def handle(self, *args, **options):
        files = options['files']
        if not files:
            base = Path(settings.BASE_DIR) / 'data'
            files = sorted(glob.glob(str(base / 'data_source_*.json')))

        if not files:
            self.stderr.write(self.style.ERROR('未找到任何 JSON 文件'))
            return

        if options['truncate'] and not options['dry_run']:
            count = InfoSource.objects.count()
            InfoSource.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'已清空 {count} 条 InfoSource'))

        total_in = 0
        total_created = 0
        total_updated = 0

        for file_path in files:
            self.stdout.write(self.style.HTTP_INFO(f'\n>>> 处理 {file_path}'))
            with open(file_path, 'r', encoding='utf-8') as f:
                items = json.load(f)
            self.stdout.write(f'  读取 {len(items)} 条')

            for item in items:
                total_in += 1
                name = (item.get('信息媒介名称') or '').strip()
                if not name:
                    continue

                official_url = (item.get('官方网址') or '').strip() or 'https://example.com'
                # URL 缺协议补全
                if not official_url.startswith(('http://', 'https://')):
                    official_url = 'https://' + official_url

                list_url = (item.get('信息列表地址/接口地址') or '').strip()
                if list_url and not list_url.startswith(('http://', 'https://')):
                    list_url = 'https://' + list_url

                # 字段映射
                payload = {
                    'category': (item.get('信息源类别') or '')[:80],
                    'official_url': official_url[:500],
                    'list_url': list_url[:500],
                    'source_type': detect_source_type(item),
                    'interface_type': (item.get('接口信息源类型') or '')[:80],
                    'data_format': (item.get('数据格式') or '')[:40],
                    'update_frequency': (item.get('更新频率') or '')[:80],
                    'crawl_method': (item.get('推荐爬取方式') or '')[:200],
                    'rate_limit_hint': (item.get('访问频率建议') or '')[:120],
                    'needs_register': '是' in (item.get('是否需要注册') or ''),
                    'needs_login': '是' in (item.get('是否需要登录') or ''),
                    'is_paid': parse_paid(item.get('是否付费')),
                    'needs_custom_spider': '是' in (item.get('是否需要自编爬虫') or ''),
                    'difficulty': parse_difficulty(item.get('爬取难度星级')),
                    'priority': parse_priority(item.get('优先级建议')),
                    'relevance': (item.get('项目战略情报相关度') or '')[:120],
                    'notes': (item.get('备注说明') or ''),
                    'spider_name': derive_spider_name(name),
                    'is_active': True,
                }
                payload['access_tier'] = derive_access_tier(payload)

                if options['dry_run']:
                    self.stdout.write(f'  [DRY] {name} -> {payload["priority"]}/{payload["source_type"]}')
                    continue

                with transaction.atomic():
                    obj, created = InfoSource.objects.update_or_create(
                        name=name[:200], defaults=payload)
                    if created:
                        total_created += 1
                    else:
                        total_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n=== 完成: 输入={total_in}  新建={total_created}  更新={total_updated} ==='))
