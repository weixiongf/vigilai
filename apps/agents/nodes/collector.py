# -*- coding: utf-8 -*-
"""采集 Agent — 包装 apps.sources.tasks.crawl_one_source / crawl_active_sources."""
from __future__ import annotations

from ..protocol import (
    AgentNode, AgentMessage, AgentResult,
    NODE_COLLECTOR, NODE_CLASSIFIER, STATUS_DONE, STATUS_FAILED,
)


class CollectorAgent(AgentNode):
    """采集智能体 — 接收 collect.request, 触发采集并向下游 ClassifierAgent 发送 intel.collected."""

    name = 'collector'
    node_type = NODE_COLLECTOR

    def handle(self, message: AgentMessage) -> AgentResult:
        from apps.sources.models import InfoSource
        from apps.sources.tasks import crawl_one_source

        payload = message.payload or {}
        source_ids = payload.get('source_ids') or []
        limit = int(payload.get('limit', 5))

        # 没有指定 source_ids 时, 自动选择活跃源(按优先级)
        if not source_ids:
            qs = (InfoSource.objects.filter(is_active=True)
                  .order_by('priority', 'name')[:limit])
            source_ids = list(qs.values_list('id', flat=True))

        triggered = []
        next_msgs = []
        for sid in source_ids:
            try:
                # 同步执行(便于演示链路); 生产环境改为 .delay() 走 Celery
                result = crawl_one_source(sid)
                triggered.append({'source_id': sid, 'result': result})
                created = result.get('created', 0) if isinstance(result, dict) else 0
                if created:
                    next_msgs.append(self.emit(
                        msg_type='intel.collected',
                        payload={'source_id': sid, 'created': created},
                        receiver=NODE_CLASSIFIER,
                        trace_id=message.trace_id,
                    ))
            except Exception as exc:  # noqa: BLE001
                triggered.append({'source_id': sid, 'error': str(exc)})

        return AgentResult(
            status=STATUS_DONE if triggered else STATUS_FAILED,
            output={'triggered': triggered, 'count': len(triggered)},
            next_messages=next_msgs,
        )
