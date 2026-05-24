"""情报 App Celery 任务 — LLM 分析 + 新情报推送 + 实时通知."""
import logging

from celery import shared_task

from apps.intelligence.models import RawInfo


logger = logging.getLogger(__name__)


@shared_task(name='apps.intelligence.tasks.analyze_pending_intel', bind=True)
def analyze_pending_intel(self, limit: int = 50) -> dict:
    """对未分析情报批量调用 LLM Provider."""
    from apps.analysis.services.analyzer import analyze_one

    qs = RawInfo.objects.filter(is_processed=False)
    ids = list(qs.values_list('id', flat=True)[:limit])
    if not ids:
        return {'analyzed': 0}

    # 读取实时发送配置
    from apps.dashboard.services.briefing_schedule import load_schedule
    sched = load_schedule()
    realtime_enabled = sched.get('realtime', {}).get('enabled', False)

    success = 0
    for info in RawInfo.objects.filter(id__in=ids):
        try:
            analyze_one(info, save=True)
            success += 1
            # 每条分析后通过 WebSocket 推一条信号
            _push_intel_event({
                'type': 'intel.analyzed',
                'id': info.id,
                'title': info.title[:80],
                'impact_score': info.impact_score,
                'pest': info.pest_type,
                'ot': info.opportunity_or_threat,
                'level': info.impact_level,
                'market': info.target_market,
            })
            # 高影响立即触发告警
            if (info.impact_score or 0) >= 8:
                from apps.notifications.tasks import send_high_impact_alert
                send_high_impact_alert.delay(info.id)
            # 实时发送: 采到新数据即刻推送通知给所有订阅者
            if realtime_enabled:
                from apps.notifications.tasks import dispatch_realtime_intel
                dispatch_realtime_intel.delay(info.id)
        except Exception as exc:
            logger.exception('analyze fail id=%s: %s', info.id, exc)

    return {'analyzed': success, 'requested': len(ids)}


@shared_task(name='apps.intelligence.tasks.analyze_one_intel')
def analyze_one_intel(info_id: int) -> dict:
    """单条分析(供其它任务调用)."""
    from apps.analysis.services.analyzer import analyze_one
    try:
        info = RawInfo.objects.get(id=info_id)
    except RawInfo.DoesNotExist:
        return {'error': 'not_found'}
    analyze_one(info, save=True)
    return {'id': info.id, 'impact_score': info.impact_score}


def _push_intel_event(payload: dict):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            'dashboard.broadcast',
            {'type': 'dashboard.event', 'payload': payload},
        )
    except Exception as exc:
        logger.warning('push intel event failed: %s', exc)
