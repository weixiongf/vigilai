"""通知分发服务 — 飞书 / 邮件 真实分发, 写 NotificationLog 状态."""
from __future__ import annotations

import json
import logging
from typing import Any

from django.utils import timezone

from apps.notifications.models import (
    NotificationLog, NotificationRecipient,
)


logger = logging.getLogger(__name__)


# ---------- 工具 ----------
def _save_payload(obj: Any) -> Any:
    """保证 response_payload 可 JSON 序列化."""
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return {'raw': str(obj)}


def _mark_sent(log: NotificationLog, payload: Any) -> None:
    log.status = 'sent'
    log.sent_at = timezone.now()
    log.response_payload = _save_payload(payload)
    log.error_message = ''
    log.save(update_fields=['status', 'sent_at', 'response_payload', 'error_message'])


def _mark_failed(log: NotificationLog, error: str, payload: Any = None) -> None:
    log.status = 'failed'
    log.error_message = (error or 'unknown')[:1000]
    if payload is not None:
        log.response_payload = _save_payload(payload)
    log.retry_count = (log.retry_count or 0) + 1
    log.save(update_fields=[
        'status', 'error_message', 'response_payload', 'retry_count'])


# ---------- 高影响告警 ----------
def dispatch_high_impact(info, subject: str, body: str) -> int:
    """高影响告警分发 — 给所有订阅高影响的 Recipient 发送."""
    recipients = NotificationRecipient.objects.filter(
        is_active=True, subscribe_high_impact=True)

    sent_count = 0
    has_target = False

    for r in recipients:
        if r.feishu_webhook:
            has_target = True
            log = NotificationLog.objects.create(
                channel='feishu', event_type='high_impact_alert',
                recipient=r.feishu_webhook[:80] + ('...' if len(r.feishu_webhook) > 80 else ''),
                subject=subject, body=body,
                ref_model='RawInfo', ref_id=info.id,
                status='pending')
            _send_feishu_alert(log, info, subject, body, r.feishu_webhook)
            if log.status == 'sent':
                sent_count += 1
        if r.email:
            has_target = True
            log = NotificationLog.objects.create(
                channel='email', event_type='high_impact_alert',
                recipient=r.email,
                subject=subject, body=body,
                ref_model='RawInfo', ref_id=info.id,
                status='pending')
            _send_email_alert(log, info, subject, body, r.email)
            if log.status == 'sent':
                sent_count += 1

    # 即使没有外部 Recipient, 也写一条 websocket log 便于驾驶舱观察
    if not has_target:
        NotificationLog.objects.create(
            channel='websocket', event_type='high_impact_alert',
            recipient='dashboard.broadcast',
            subject=subject, body=body,
            ref_model='RawInfo', ref_id=info.id,
            status='sent', sent_at=timezone.now(),
            response_payload={'note': 'no_external_recipient_fallback_websocket'})
        sent_count = 1

    return sent_count


def _send_feishu_alert(log, info, subject, body, webhook_url) -> None:
    from apps.notifications.services.feishu import FeishuWebhookClient
    from django.conf import settings
    try:
        client = FeishuWebhookClient(
            webhook_url=webhook_url,
            secret=getattr(settings, 'FEISHU_WEBHOOK_SECRET', '') or '',
        )
        result = client.send_high_impact_alert(info, subject, body)
        if result.get('ok'):
            _mark_sent(log, result.get('response') or result)
        else:
            _mark_failed(log, result.get('error', 'feishu_failed'), result)
    except Exception as exc:
        logger.exception('feishu alert failed')
        _mark_failed(log, str(exc))


def _send_email_alert(log, info, subject, body, email) -> None:
    from apps.notifications.services.email import send_high_impact_alert_email
    try:
        result = send_high_impact_alert_email(info, subject, body, [email])
        if result.get('ok'):
            _mark_sent(log, result)
        else:
            _mark_failed(log, result.get('error', 'email_failed'), result)
    except Exception as exc:
        logger.exception('email alert failed')
        _mark_failed(log, str(exc))


# ---------- 战略简报 ----------
def dispatch_briefing_to_recipient(briefing, recipient) -> bool:
    """简报真实分发: 同步发送 + 写 log."""
    body_text = (briefing.executive_summary or '')[:2000]

    if recipient.feishu_webhook:
        log = NotificationLog.objects.create(
            channel='feishu',
            event_type=f'{briefing.period_type}_briefing',
            recipient=recipient.feishu_webhook[:80] +
                      ('...' if len(recipient.feishu_webhook) > 80 else ''),
            subject=briefing.title, body=body_text,
            ref_model='Briefing', ref_id=briefing.id,
            status='pending')
        _send_feishu_briefing(log, briefing, recipient.feishu_webhook)

    if recipient.email:
        log = NotificationLog.objects.create(
            channel='email',
            event_type=f'{briefing.period_type}_briefing',
            recipient=recipient.email,
            subject=briefing.title, body=body_text,
            ref_model='Briefing', ref_id=briefing.id,
            status='pending')
        _send_email_briefing(log, briefing, recipient.email)

    return True


def _send_feishu_briefing(log, briefing, webhook_url) -> None:
    from apps.notifications.services.feishu import FeishuWebhookClient
    from django.conf import settings
    try:
        client = FeishuWebhookClient(
            webhook_url=webhook_url,
            secret=getattr(settings, 'FEISHU_WEBHOOK_SECRET', '') or '',
        )
        result = client.send_briefing(briefing)
        if result.get('ok'):
            _mark_sent(log, result.get('response') or result)
        else:
            _mark_failed(log, result.get('error', 'feishu_failed'), result)
    except Exception as exc:
        logger.exception('feishu briefing failed')
        _mark_failed(log, str(exc))


def _send_email_briefing(log, briefing, email) -> None:
    from apps.notifications.services.email import send_briefing_email
    try:
        result = send_briefing_email(briefing, [email])
        if result.get('ok'):
            _mark_sent(log, result)
        else:
            _mark_failed(log, result.get('error', 'email_failed'), result)
    except Exception as exc:
        logger.exception('email briefing failed')
        _mark_failed(log, str(exc))


# ---------- 重试 (供 Celery 调用) ----------
def retry_pending_logs(limit: int = 50) -> dict:
    """从 NotificationLog 拣出 pending/retrying 状态的记录, 重新发送一次."""
    from apps.intelligence.models import RawInfo
    from apps.briefings.models import Briefing

    qs = NotificationLog.objects.filter(
        status__in=['pending', 'retrying']).order_by('id')[:limit]

    success = 0
    failed = 0
    for log in qs:
        log.status = 'retrying'
        log.save(update_fields=['status'])
        try:
            if log.ref_model == 'RawInfo':
                info = RawInfo.objects.filter(id=log.ref_id).first()
                if not info:
                    _mark_failed(log, 'ref_not_found')
                    failed += 1
                    continue
                if log.channel == 'feishu':
                    _send_feishu_alert(log, info, log.subject, log.body,
                                       _resolve_webhook(log.recipient))
                elif log.channel == 'email':
                    _send_email_alert(log, info, log.subject, log.body,
                                      log.recipient)
            elif log.ref_model == 'Briefing':
                briefing = Briefing.objects.filter(id=log.ref_id).first()
                if not briefing:
                    _mark_failed(log, 'ref_not_found')
                    failed += 1
                    continue
                if log.channel == 'feishu':
                    _send_feishu_briefing(log, briefing,
                                          _resolve_webhook(log.recipient))
                elif log.channel == 'email':
                    _send_email_briefing(log, briefing, log.recipient)
            else:
                _mark_failed(log, f'unknown_ref_model:{log.ref_model}')
                failed += 1
                continue

            if log.status == 'sent':
                success += 1
            else:
                failed += 1
        except Exception as exc:
            logger.exception('retry_pending_logs error')
            _mark_failed(log, str(exc))
            failed += 1

    return {'attempted': len(qs), 'success': success, 'failed': failed}


def _resolve_webhook(recipient_field: str) -> str:
    """log.recipient 存的是截断后的 webhook 显示串, 这里反查 NotificationRecipient 拿原值."""
    if not recipient_field:
        return ''
    short = recipient_field.replace('...', '')
    rec = NotificationRecipient.objects.filter(
        feishu_webhook__startswith=short[:60]).first()
    return rec.feishu_webhook if rec and rec.feishu_webhook else ''
