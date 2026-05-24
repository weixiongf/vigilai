# -*- coding: utf-8 -*-
"""管理命令: 演示多智能体 A2A 完整链路.

用法:
    python manage.py run_agent_pipeline                       # 跑一次完整链路
    python manage.py run_agent_pipeline --market US           # 指定市场
    python manage.py run_agent_pipeline --period weekly       # 指定周期
    python manage.py run_agent_pipeline --limit 3             # 只采集 3 个源
"""
from django.core.management.base import BaseCommand

from apps.agents.coordinator import build_default_coordinator
from apps.agents.protocol import AgentMessage, NODE_COLLECTOR


class Command(BaseCommand):
    help = '触发多智能体 A2A 协作链路: 采集→分类归因→简报撰写→分发'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=3,
                            help='采集源数量上限')
        parser.add_argument('--market', type=str, default='global',
                            help='目标市场')
        parser.add_argument('--period', type=str, default='daily',
                            choices=['daily', 'weekly', 'monthly'])

    def handle(self, *args, **options):
        coord = build_default_coordinator()

        self.stdout.write(self.style.HTTP_INFO(
            f'>>> 已注册 Agent 节点: {[n["name"] for n in coord.list_nodes()]}'))

        # 入口消息: 让 collector 触发采集
        entry = AgentMessage(
            msg_type='collect.request',
            receiver=NODE_COLLECTOR,
            sender='cli',
            payload={
                'limit': options['limit'],
                # 把简报参数顺带带上, 便于下游 BrieferAgent 拿到
                'briefing_hint': {
                    'period_type': options['period'],
                    'target_market': options['market'],
                },
            },
        )

        results = coord.dispatch(entry)

        # 打印链路结果
        self.stdout.write(self.style.SUCCESS(
            f'\n=== 链路完成: 共执行 {len(results)} 个节点 ==='))
        for i, r in enumerate(results, start=1):
            status_color = (self.style.SUCCESS if r.status == 'done'
                            else self.style.ERROR)
            self.stdout.write(status_color(
                f'  [{i}] status={r.status} '
                f'output={r.output} '
                f'next={len(r.next_messages)} '
                + (f'error={r.error}' if r.error else '')))

        self.stdout.write(self.style.HTTP_INFO(
            f'\n>>> 追溯日志: trace_id={entry.trace_id} '
            f'(查询: AgentMessageLog.objects.filter(trace_id="{entry.trace_id}"))'))
