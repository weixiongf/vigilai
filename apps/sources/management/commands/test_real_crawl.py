"""管理命令: 真实爬虫连通性冒烟测试 — 直接调用 real_crawler 注册的采集器,
不经过 Celery / fallback / tier_switch, 用于验证 "强制真实数据" 链路是否真的能拿到数据.

用法:
    # 列出所有已注册的真实爬虫
    python manage.py test_real_crawl --list

    # 测试单个爬虫 (按 spider_name)
    python manage.py test_real_crawl --spider spider_fred
    python manage.py test_real_crawl --spider spider_ecb
    python manage.py test_real_crawl --spider spider_rss_news

    # 跑所有真实爬虫 (会向公开 API 发起多次请求, 注意 rate limit)
    python manage.py test_real_crawl --all

    # 仅 dry-run, 不写入 RawInfo (默认会写入数据库以触发下游 LLM 分析)
    python manage.py test_real_crawl --all --dry-run
"""
from __future__ import annotations

import time
import traceback

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sources.models import InfoSource
from apps.sources.services import real_crawler as rc


class _FakeSource:
    """伪 InfoSource — 在没有匹配真实记录时仍能调用爬虫.

    爬虫只用 source 当外键写入 RawInfo, 这里给一个 None 安全占位.
    """
    id = 0
    name = '__cli_test__'
    spider_name = ''
    official_url = ''
    list_url = ''


class Command(BaseCommand):
    help = '直接调用真实爬虫验证连通性 (绕过 Celery / fallback / tier_switch)'

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group(required=True)
        g.add_argument('--list', action='store_true',
                       help='列出所有已注册的真实爬虫')
        g.add_argument('--spider', type=str,
                       help='指定要测试的 spider_name (如 spider_fred / spider_ecb)')
        g.add_argument('--all', action='store_true',
                       help='依次测试所有真实爬虫 (注意 rate limit)')
        parser.add_argument('--dry-run', action='store_true',
                            help='仅打印结果, 回滚事务不写库')

    # ------------------------------------------------------------ helpers
    def _list_spiders(self):
        names = rc.supported_spider_names()
        self.stdout.write(self.style.SUCCESS(
            f'已注册真实爬虫 {len(names)} 个:'))
        for n in names:
            fn = rc.SPIDER_REGISTRY.get(n)
            self.stdout.write(f'  - {n}  ->  {fn.__name__ if fn else "?"}')

    def _resolve_source(self, spider_name: str) -> InfoSource | _FakeSource:
        """优先用数据库中匹配 spider_name 的 InfoSource, 否则用 FakeSource 占位."""
        src = InfoSource.objects.filter(spider_name__iexact=spider_name).first()
        if src is not None:
            return src
        # 用名字 contains 兜底 (例如 spider_fred -> 名字含 FRED)
        keyword = spider_name.replace('spider_', '').split('_')[0]
        if keyword:
            src = InfoSource.objects.filter(name__icontains=keyword).first()
            if src is not None:
                return src
        fake = _FakeSource()
        fake.spider_name = spider_name
        return fake

    def _run_one(self, spider_name: str, dry_run: bool) -> dict:
        fn = rc.SPIDER_REGISTRY.get(spider_name)
        if fn is None:
            return {'spider': spider_name, 'ok': False,
                    'error': 'not in SPIDER_REGISTRY'}
        src = self._resolve_source(spider_name)
        t0 = time.time()
        try:
            if dry_run:
                # 用事务+回滚保证不污染数据库
                with transaction.atomic():
                    fetched, created = fn(src)
                    transaction.set_rollback(True)
            else:
                fetched, created = fn(src)
            cost = time.time() - t0
            return {'spider': spider_name, 'ok': True,
                    'fetched': fetched, 'created': created,
                    'cost_s': round(cost, 2),
                    'source_resolved': getattr(src, 'name', '?')}
        except Exception as exc:
            cost = time.time() - t0
            return {'spider': spider_name, 'ok': False,
                    'error': f'{type(exc).__name__}: {exc}',
                    'cost_s': round(cost, 2),
                    'trace': traceback.format_exc(limit=3)}

    def _print_result(self, r: dict):
        if r.get('ok'):
            self.stdout.write(self.style.SUCCESS(
                f'  [OK] {r["spider"]:42} fetched={r["fetched"]:>3} '
                f'created={r["created"]:>3} cost={r["cost_s"]}s '
                f'(source={r.get("source_resolved", "?")})'
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f'  [FAIL] {r["spider"]:42} {r.get("error", "")} '
                f'(cost={r.get("cost_s", "?")}s)'
            ))

    # ------------------------------------------------------------ main
    def handle(self, *args, **opts):
        if opts['list']:
            self._list_spiders()
            return

        dry_run = bool(opts.get('dry_run'))

        if opts['spider']:
            spider = opts['spider'].strip().lower()
            self.stdout.write(self.style.HTTP_INFO(
                f'>>> 测试 {spider} (dry_run={dry_run})'))
            r = self._run_one(spider, dry_run)
            self._print_result(r)
            if not r.get('ok') and r.get('trace'):
                self.stdout.write(r['trace'])
            return

        if opts['all']:
            spiders = rc.supported_spider_names()
            # 同一函数可能挂载多个 alias, 去重
            seen_fn = set()
            unique_spiders = []
            for s in spiders:
                fn = rc.SPIDER_REGISTRY.get(s)
                if fn and fn not in seen_fn:
                    seen_fn.add(fn)
                    unique_spiders.append(s)
            self.stdout.write(self.style.HTTP_INFO(
                f'>>> 顺序测试 {len(unique_spiders)} 个真实爬虫 '
                f'(dry_run={dry_run}, 每两次间隔 1s)'))
            results = []
            for s in unique_spiders:
                r = self._run_one(s, dry_run)
                results.append(r)
                self._print_result(r)
                time.sleep(1)
            ok_n = sum(1 for r in results if r.get('ok'))
            self.stdout.write(self.style.SUCCESS(
                f'\n=== 完成: {ok_n}/{len(results)} 成功 ===') if ok_n
                else self.style.ERROR(
                    f'\n=== 完成: {ok_n}/{len(results)} 成功 ==='))
