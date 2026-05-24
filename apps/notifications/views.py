"""通知 REST API — 收件人 CRUD / 通知日志 / 测试发送."""
from __future__ import annotations

import json

from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.notifications.models import (
    NotificationLog, NotificationRecipient, NotificationTemplate,
)


def _serialize_recipient(r: NotificationRecipient) -> dict:
    return {
        'id': r.id,
        'name': r.name,
        'role': r.role,
        'email': r.email,
        'feishu_webhook': r.feishu_webhook,
        'subscribe_high_impact': r.subscribe_high_impact,
        'subscribe_opportunity': r.subscribe_opportunity,
        'subscribe_daily': r.subscribe_daily,
        'subscribe_weekly': r.subscribe_weekly,
        'subscribe_monthly': r.subscribe_monthly,
        'is_active': r.is_active,
    }


@require_GET
def recipient_list(request):
    qs = NotificationRecipient.objects.all().order_by('-is_active', 'id')
    return JsonResponse({
        'items': [_serialize_recipient(r) for r in qs],
        'total': qs.count(),
    })


@csrf_exempt
@require_POST
def recipient_create(request):
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid_json'}, status=400)
    if not payload.get('name'):
        return JsonResponse({'error': 'name_required'}, status=400)
    r = NotificationRecipient.objects.create(
        name=payload.get('name', ''),
        role=payload.get('role', ''),
        email=payload.get('email', '') or '',
        feishu_webhook=payload.get('feishu_webhook', '') or '',
        subscribe_high_impact=bool(payload.get('subscribe_high_impact', True)),
        subscribe_opportunity=bool(payload.get('subscribe_opportunity', True)),
        subscribe_daily=bool(payload.get('subscribe_daily', True)),
        subscribe_weekly=bool(payload.get('subscribe_weekly', True)),
        subscribe_monthly=bool(payload.get('subscribe_monthly', True)),
        is_active=bool(payload.get('is_active', True)),
    )
    return JsonResponse(_serialize_recipient(r), status=201)


@csrf_exempt
@require_http_methods(['PUT', 'PATCH', 'DELETE'])
def recipient_update_or_delete(request, pk: int):
    try:
        r = NotificationRecipient.objects.get(id=pk)
    except NotificationRecipient.DoesNotExist:
        raise Http404()

    if request.method == 'DELETE':
        r.delete()
        return JsonResponse({'ok': True, 'deleted': pk})

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid_json'}, status=400)

    for f in ['name', 'role', 'email', 'feishu_webhook']:
        if f in payload:
            setattr(r, f, payload[f] or '')
    for f in ['subscribe_high_impact', 'subscribe_opportunity', 'subscribe_daily',
              'subscribe_weekly', 'subscribe_monthly', 'is_active']:
        if f in payload:
            setattr(r, f, bool(payload[f]))
    r.save()
    return JsonResponse(_serialize_recipient(r))


@require_GET
def log_list(request):
    qs = NotificationLog.objects.all().order_by('-id')
    channel = request.GET.get('channel')
    if channel:
        qs = qs.filter(channel=channel)
    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)
    qs = qs[:100]
    return JsonResponse({
        'items': [
            {
                'id': l.id,
                'channel': l.channel,
                'event_type': l.event_type,
                'recipient': l.recipient,
                'subject': l.subject,
                'body': l.body,
                'ref_model': l.ref_model,
                'ref_id': l.ref_id,
                'status': l.status,
                'response_payload': l.response_payload,
                'retry_count': l.retry_count,
                'created_at': l.created_at.isoformat(),
                'sent_at': l.sent_at.isoformat() if l.sent_at else None,
                'error_message': l.error_message,
            }
            for l in qs
        ],
    })


@csrf_exempt
@require_POST
def log_resend(request, pk: int):
    try:
        from apps.notifications.tasks import send_one_log
        send_one_log.delay(pk)
        return JsonResponse({'ok': True, 'queued': pk})
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=500)


@csrf_exempt
@require_POST
def test_send(request):
    """测试发送 — 给指定 Recipient 发送一条测试消息."""
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid_json'}, status=400)
    rid = payload.get('recipient_id')
    if not rid:
        return JsonResponse({'error': 'recipient_id_required'}, status=400)
    try:
        r = NotificationRecipient.objects.get(id=rid)
    except NotificationRecipient.DoesNotExist:
        raise Http404()

    results = {}
    if r.feishu_webhook:
        from apps.notifications.services.feishu import FeishuWebhookClient
        from django.conf import settings
        c = FeishuWebhookClient(
            webhook_url=r.feishu_webhook,
            secret=getattr(settings, 'FEISHU_WEBHOOK_SECRET', '') or '')
        results['feishu'] = c.send_text(
            f'[测试] 海外市场战略情报 Agent — {r.name} 通道连通测试')

    if r.email:
        from apps.notifications.services.email import send_html_email
        results['email'] = send_html_email(
            subject='[测试] 海外市场战略情报 Agent',
            html=f'<p>这是一封测试邮件, 收件人: <b>{r.name}</b></p>',
            to=[r.email],
        )
    return JsonResponse({'ok': True, 'results': results})
