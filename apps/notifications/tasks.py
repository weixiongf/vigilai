"""通知 App Celery 任务 — 高影响告警 / 简报分发 / 重试队列."""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.intelligence.models import RawInfo
from apps.notifications.models import (
    NotificationLog, NotificationRecipient,
)


logger = logging.getLogger(__name__)


HIGH_IMPACT_THRESHOLD = 8.0


@shared_task(name='apps.notifications.tasks.scan_and_alert_high_impact')
def scan_and_alert_high_impact(window_minutes: int = 30) -> dict:
    """扫描最近窗口内尚未告警过的高影响情报, 触发告警."""
    since = timezone.now() - timedelta(minutes=window_minutes)
    qs = RawInfo.objects.filter(
        is_processed=True,
        impact_score__gte=HIGH_IMPACT_THRESHOLD,
        fetched_at__gte=since,
    )

    triggered = []
    for info in qs:
        # 去抖: 同情报 24h 内只发一次
        recent_log = NotificationLog.objects.filter(
            event_type='high_impact_alert',
            ref_model='RawInfo',
            ref_id=info.id,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).exists()
        if recent_log:
            continue
        send_high_impact_alert.delay(info.id)
        triggered.append(info.id)

    return {'scanned': qs.count(), 'triggered': len(triggered)}


@shared_task(name='apps.notifications.tasks.send_high_impact_alert',
             bind=True, max_retries=3, default_retry_delay=60)
def send_high_impact_alert(self, info_id: int) -> dict:
    """单条高影响情报告警 — 飞书 + 邮件 + WebSocket."""
    try:
        info = RawInfo.objects.get(id=info_id)
    except RawInfo.DoesNotExist:
        return {'error': 'not_found', 'id': info_id}

    subject = f'[高影响告警] {info.title[:60]}'
    body = (
        f'市场: {info.target_market} | 维度: {info.strategic_dimension} | '
        f'PEST: {info.pest_type} | OT: {info.opportunity_or_threat}\n'
        f'影响分: {info.impact_score}/10 等级: {info.impact_level}\n'
        f'摘要: {info.summary or info.title}\n'
        f'建议: {info.action_advice}\n'
    )

    # 飞书 + 邮件 (real dispatcher)
    sent = 0
    try:
        from apps.notifications.services.dispatcher import dispatch_high_impact
        sent = dispatch_high_impact(info, subject, body)
    except Exception as exc:
        logger.warning('dispatch_high_impact failed: %s', exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            pass

    # WebSocket 推送 (即使外部通道失败也要推驾驶舱)
    _push_notify({
        'type': 'alert.high_impact',
        'id': info.id,
        'title': info.title,
        'market': info.target_market,
        'impact_score': info.impact_score,
        'level': info.impact_level,
        'pest': info.pest_type,
        'ot': info.opportunity_or_threat,
        'sent_count': sent,
    })

    return {'id': info.id, 'channels_sent': sent}


@shared_task(name='apps.notifications.tasks.dispatch_briefing',
             bind=True, max_retries=3, default_retry_delay=120)
def dispatch_briefing(self, briefing_id: int) -> dict:
    """简报分发 — 给所有订阅了该周期的 NotificationRecipient 发送."""
    from apps.briefings.models import Briefing
    try:
        b = Briefing.objects.get(id=briefing_id)
    except Briefing.DoesNotExist:
        return {'error': 'briefing_not_found', 'id': briefing_id}

    field_map = {'daily': 'subscribe_daily', 'weekly': 'subscribe_weekly', 'monthly': 'subscribe_monthly'}
    field = field_map.get(b.period_type, 'subscribe_daily')
    recipients = NotificationRecipient.objects.filter(
        is_active=True, **{field: True})

    sent = 0
    failed = 0
    try:
        from apps.notifications.services.dispatcher import dispatch_briefing_to_recipient
        for r in recipients:
            try:
                dispatch_briefing_to_recipient(b, r)
                sent += 1
            except Exception as exc:
                logger.warning('briefing to %s failed: %s', r.name, exc)
                failed += 1
    except Exception as exc:
        logger.warning('dispatch_briefing failed: %s', exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            pass

    # 推驾驶舱: 简报已分发
    _push_notify({
        'type': 'briefing.dispatched',
        'id': b.id,
        'title': b.title,
        'period_type': b.period_type,
        'recipients': sent,
        'failed': failed,
    })

    return {'briefing_id': b.id, 'recipients': sent, 'failed': failed}


@shared_task(name='apps.notifications.tasks.send_one_log',
             bind=True, max_retries=3, default_retry_delay=30)
def send_one_log(self, log_id: int) -> dict:
    """重发单条 NotificationLog (按 channel 分发)."""
    try:
        log = NotificationLog.objects.get(id=log_id)
    except NotificationLog.DoesNotExist:
        return {'error': 'log_not_found', 'id': log_id}

    if log.status == 'sent':
        return {'log_id': log.id, 'note': 'already_sent'}

    # 复用 dispatcher 内部分发逻辑
    from apps.briefings.models import Briefing
    from apps.notifications.services.dispatcher import (
        _send_feishu_alert, _send_email_alert,
        _send_feishu_briefing, _send_email_briefing,
        _resolve_webhook, _mark_failed,
    )

    log.status = 'retrying'
    log.save(update_fields=['status'])

    try:
        if log.ref_model == 'RawInfo':
            info = RawInfo.objects.filter(id=log.ref_id).first()
            if not info:
                _mark_failed(log, 'ref_not_found')
                return {'log_id': log.id, 'status': 'failed'}
            if log.channel == 'feishu':
                _send_feishu_alert(log, info, log.subject, log.body,
                                   _resolve_webhook(log.recipient))
            elif log.channel == 'email':
                _send_email_alert(log, info, log.subject, log.body,
                                  log.recipient)
        elif log.ref_model == 'Briefing':
            b = Briefing.objects.filter(id=log.ref_id).first()
            if not b:
                _mark_failed(log, 'ref_not_found')
                return {'log_id': log.id, 'status': 'failed'}
            if log.channel == 'feishu':
                _send_feishu_briefing(log, b, _resolve_webhook(log.recipient))
            elif log.channel == 'email':
                _send_email_briefing(log, b, log.recipient)
        else:
            _mark_failed(log, f'unknown_ref_model:{log.ref_model}')
    except Exception as exc:
        logger.exception('send_one_log failed')
        _mark_failed(log, str(exc))
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            pass

    return {'log_id': log.id, 'status': log.status}


@shared_task(name='apps.notifications.tasks.process_pending_notifications')
def process_pending_notifications(limit: int = 50) -> dict:
    """Beat 周期任务: 捡出 pending/retrying 的 NotificationLog 重发."""
    from apps.notifications.services.dispatcher import retry_pending_logs
    return retry_pending_logs(limit=limit)


@shared_task(name='apps.notifications.tasks.dispatch_realtime_intel',
             bind=True, max_retries=2, default_retry_delay=30)
def dispatch_realtime_intel(self, info_id: int) -> dict:
    """实时发送: 采集器采到新数据后立即推送通知给所有活跃订阅者.

    每条新情报分析完成后由 analyze_pending_intel 触发此任务,
    仅在 briefing_schedule.json 中 realtime.enabled=true 时生效.
    """
    try:
        info = RawInfo.objects.get(id=info_id)
    except RawInfo.DoesNotExist:
        return {'error': 'not_found', 'id': info_id}

    # 双重检查: 运行时再确认实时发送仍然开启
    from apps.dashboard.services.briefing_schedule import load_schedule
    sched = load_schedule()
    if not sched.get('realtime', {}).get('enabled', False):
        return {'skipped': True, 'reason': 'realtime_disabled'}

    subject = f'[情报实时推送] {info.title[:60]}'
    body = (
        f'市场: {info.target_market} | 维度: {info.strategic_dimension} | '
        f'PEST: {info.pest_type} | OT: {info.opportunity_or_threat}\n'
        f'影响分: {info.impact_score}/10 等级: {info.impact_level}\n'
        f'摘要: {info.summary or info.title}\n'
    )

    # 给所有活跃订阅者发送
    recipients = NotificationRecipient.objects.filter(
        is_active=True, subscribe_daily=True)  # 复用日报订阅者作为实时推送目标

    sent = 0
    try:
        from apps.notifications.services.dispatcher import dispatch_high_impact
        sent = dispatch_high_impact(info, subject, body)
    except Exception as exc:
        logger.warning('dispatch_realtime_intel failed: %s', exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            pass

    # WebSocket 推送
    _push_notify({
        'type': 'intel.realtime_push',
        'id': info.id,
        'title': info.title,
        'market': info.target_market,
        'impact_score': info.impact_score,
        'sent_count': sent,
    })

    return {'id': info.id, 'channels_sent': sent}


# ---------- WebSocket helper ----------
def _push_notify(payload: dict):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            'notifications.broadcast',
            {'type': 'notify', 'payload': payload},
        )
    except Exception as exc:
        logger.warning('push notify failed: %s', exc)
