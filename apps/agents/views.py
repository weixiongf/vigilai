# -*- coding: utf-8 -*-
"""agents App REST API — AgentMessageLog 查询 + Pipeline 触发."""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.agents.models import AgentMessageLog


def _serialize_log(log: AgentMessageLog) -> dict:
    return {
        'id': log.id,
        'trace_id': log.trace_id,
        'msg_id': log.msg_id,
        'msg_type': log.msg_type,
        'sender': log.sender,
        'receiver': log.receiver,
        'status': log.status,
        'payload': log.payload,
        'output': log.output,
        'error': log.error,
        'created_at': log.created_at.isoformat() if log.created_at else None,
        'finished_at': log.finished_at.isoformat() if log.finished_at else None,
    }


@require_GET
def log_list(request):
    """AgentMessageLog 列表 — ?trace_id=xxx&status=done&page=1&size=20"""
    qs = AgentMessageLog.objects.all()
    trace_id = request.GET.get('trace_id')
    if trace_id:
        qs = qs.filter(trace_id=trace_id)
    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)
    qs = qs.order_by('-created_at')

    try:
        page = max(1, int(request.GET.get('page', '1')))
        size = min(100, max(1, int(request.GET.get('size', '50'))))
    except ValueError:
        page, size = 1, 50

    total = qs.count()
    start = (page - 1) * size
    items = [_serialize_log(l) for l in qs[start:start + size]]
    return JsonResponse({'total': total, 'page': page, 'size': size, 'items': items})


@require_GET
def trace_detail(request, trace_id: str):
    """单条 trace_id 的完整链路 — 按时间排序."""
    qs = AgentMessageLog.objects.filter(trace_id=trace_id).order_by('created_at')
    if not qs.exists():
        return JsonResponse({'error': 'trace_not_found'}, status=404)
    return JsonResponse({'trace_id': trace_id, 'steps': [_serialize_log(l) for l in qs]})


@require_GET
def node_status(request):
    """各节点最近执行状态 — 按 receiver 分组统计."""
    from django.db.models import Count, Max
    stats = (AgentMessageLog.objects.values('receiver')
             .annotate(total=Count('id'),
                       last_at=Max('created_at'))
             .order_by('receiver'))
    nodes = []
    for s in stats:
        last = (AgentMessageLog.objects.filter(receiver=s['receiver'])
                .order_by('-created_at').first())
        nodes.append({
            'node': s['receiver'],
            'total': s['total'],
            'last_status': last.status if last else None,
            'last_at': last.created_at.isoformat() if last and last.created_at else None,
        })
    return JsonResponse({'nodes': nodes})


@csrf_exempt
@require_POST
def run_pipeline(request):
    """触发多智能体 A2A 完整链路 — {market, period, limit}."""
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        payload = {}

    market = payload.get('market', 'global')
    period = payload.get('period', 'daily')
    limit = int(payload.get('limit', 3))

    try:
        from apps.agents.coordinator import build_default_coordinator
        from apps.agents.protocol import AgentMessage, NODE_COLLECTOR

        coord = build_default_coordinator()
        entry = AgentMessage(
            msg_type='collect.request',
            receiver=NODE_COLLECTOR,
            sender='dashboard',
            payload={
                'limit': limit,
                'briefing_hint': {'period_type': period, 'target_market': market},
            },
        )
        results = coord.dispatch(entry)

        # WebSocket 推送 pipeline 完成
        _push_pipeline_done(entry.trace_id, results)

        return JsonResponse({
            'ok': True,
            'trace_id': entry.trace_id,
            'steps': len(results),
            'market': market,
            'period': period,
            'limit': limit,
        })
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=500)


def _push_pipeline_done(trace_id: str, results: list):
    """通知驾驶舱: Agent 链路执行完毕."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            'notifications.broadcast',
            {
                'type': 'notify',
                'payload': {
                    'type': 'agent.pipeline_done',
                    'trace_id': trace_id,
                    'steps': len(results),
                    'statuses': [r.status for r in results],
                },
            },
        )
    except Exception as exc:
        logger.warning('push pipeline done failed: %s', exc)
