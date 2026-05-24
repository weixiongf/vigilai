"""战略简报 REST API."""
from __future__ import annotations

from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

import json

from apps.briefings.models import Briefing, BriefingSection


def _aggregate_dispatch_status(briefing_ids):
    """按 briefing 聚合通知日志状态: sent / failed / pending."""
    from apps.notifications.models import NotificationLog
    from collections import defaultdict

    counts = defaultdict(lambda: {'sent': 0, 'failed': 0, 'pending': 0,
                                  'retrying': 0})
    rows = (NotificationLog.objects
            .filter(ref_model='Briefing', ref_id__in=list(briefing_ids))
            .exclude(channel='websocket')
            .values_list('ref_id', 'status'))
    for ref_id, status in rows:
        counts[ref_id][status] = counts[ref_id].get(status, 0) + 1

    result = {}
    for bid in briefing_ids:
        c = counts.get(bid)
        if not c:
            result[bid] = 'pending'
        elif c.get('failed', 0) and not c.get('sent', 0):
            result[bid] = 'failed'
        elif c.get('sent', 0):
            result[bid] = 'sent'
        else:
            result[bid] = 'pending'
    return result


def _serialize_briefing(b: Briefing, sections: bool = False,
                        dispatch_status: str = 'pending') -> dict:
    data = {
        'id': b.id,
        'title': b.title,
        'period_type': b.period_type,
        'period_type_label': b.get_period_type_display(),
        'period_start': b.period_start.isoformat() if b.period_start else None,
        'period_end': b.period_end.isoformat() if b.period_end else None,
        'target_market': b.target_market,
        'status': b.status,
        'dispatch_status': dispatch_status,
        'executive_summary': b.executive_summary,
        'key_findings': b.key_findings or [],
        'top_opportunities': b.top_opportunities or [],
        'top_risks': b.top_risks or [],
        'recommended_actions': b.recommended_actions or [],
        'referenced_info_ids': b.referenced_info_ids or [],
        'created_at': b.created_at.isoformat() if b.created_at else None,
    }
    if sections:
        data['sections'] = [
            {
                'id': s.id,
                'order': s.order,
                'section_key': s.section_key,
                'title': s.title,
                'content': s.content,
                'chart_payload': s.chart_payload,
            }
            for s in b.sections.all().order_by('order')
        ]
    return data


@require_GET
def briefing_list(request):
    qs = Briefing.objects.all()

    period = request.GET.get('period')
    if period:
        qs = qs.filter(period_type=period)
    market = request.GET.get('market')
    if market:
        qs = qs.filter(target_market=market)

    # 排序: 同一期(period_end)内 global 综合简报置顶, 其余按创建时间倒序
    from django.db.models import Case, When, IntegerField
    qs = qs.annotate(
        is_global=Case(
            When(target_market='global', then=0),
            default=1,
            output_field=IntegerField(),
        )
    ).order_by('-period_end', 'is_global', '-created_at')

    qs = list(qs[:50])
    status_map = _aggregate_dispatch_status([b.id for b in qs])
    return JsonResponse({
        'items': [_serialize_briefing(b, dispatch_status=status_map.get(b.id, 'pending'))
                  for b in qs],
        'total': len(qs),
    })


@require_GET
def briefing_detail(request, pk: int):
    try:
        b = Briefing.objects.prefetch_related('sections').get(id=pk)
    except Briefing.DoesNotExist:
        raise Http404()
    status_map = _aggregate_dispatch_status([b.id])
    return JsonResponse(_serialize_briefing(
        b, sections=True, dispatch_status=status_map.get(b.id, 'pending')))


@csrf_exempt
@require_POST
def briefing_trigger(request):
    """手动触发简报生成: { period_type, target_market }.

    策略纠偏: 周报仅生成 1 份 global 综合简报(含市场分区),
    任何单市场 + weekly 的请求都会被重定向到 global.
    """
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid_json'}, status=400)

    period_type = payload.get('period_type', 'daily')
    market = payload.get('target_market', 'US')

    # 周报强制 global, 避免产生单市场周报冗余
    if period_type == 'weekly' and market != 'global':
        market = 'global'

    try:
        from apps.briefings.tasks import generate_briefing_for_market
        generate_briefing_for_market.delay(market, period_type)
        return JsonResponse({'ok': True, 'queued': True,
                             'period_type': period_type, 'market': market})
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=500)


@csrf_exempt
@require_POST
def briefing_dispatch(request, pk: int):
    """手动分发简报到飞书+邮件."""
    try:
        from apps.notifications.tasks import dispatch_briefing
        dispatch_briefing.delay(pk)
        return JsonResponse({'ok': True, 'queued': pk})
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=500)


@require_GET
def briefing_metrics(request, pk: int):
    """简报决策参照: KPI对比 / 7日趋势 / 变化雷达 / 重要性分层.

    输出结构:
      kpi:       今日指标 + 环比(日报比昨日/周报比上周) + 指数同比7日均值
      sparkline: 过去 7 天的 total/high_impact/opp/threat 迷你曲线
      delta:    今日新增高影响 / 持续话题 / 已消退话题
      priority: 紧急/本周关注/长期跟踪三档

    实际计算逻辑由 services/metrics.py::compute_briefing_metrics 提供,
    保证邮件 / 详情页 / 通知预览三处使用相同数据.
    """
    try:
        b = Briefing.objects.get(id=pk)
    except Briefing.DoesNotExist:
        raise Http404()
    from apps.briefings.services.metrics import compute_briefing_metrics
    return JsonResponse(compute_briefing_metrics(b))


@require_GET
def briefing_render(request, pk: int):
    """返回简报渲染后的 HTML 片段, 供详情页 / 邮件 / 通知预览三处共用.

    Query:
      mode: email | web | preview (默认 web — 内嵌片段)
    """
    try:
        b = Briefing.objects.prefetch_related('sections').get(id=pk)
    except Briefing.DoesNotExist:
        raise Http404()
    mode = request.GET.get('mode', 'web')
    from apps.briefings.services.templates import render_briefing_html
    html = render_briefing_html(b, mode=mode)
    return JsonResponse({'html': html, 'mode': mode, 'briefing_id': b.id})


@require_GET
def briefing_preview(request):
    """通知中心模板预览 — 渲染最新一条已发布简报."""
    mode = request.GET.get('mode', 'email')
    from apps.briefings.services.templates import render_latest_briefing_preview
    html = render_latest_briefing_preview(mode=mode)
    return JsonResponse({'html': html, 'mode': mode})


@require_GET
def pest_swot_latest(request):
    """获取最新的 PEST + SWOT 快照."""
    from apps.analysis.models import PESTSnapshot, SWOTAnalysis

    market = request.GET.get('market', 'US')
    pest = PESTSnapshot.objects.filter(target_market=market) \
        .order_by('-period_end').first()
    if not pest:
        return JsonResponse({'pest': None, 'swot': None,
                             'note': f'no_data_for_{market}'})

    swot = SWOTAnalysis.objects.filter(pest_snapshot=pest).first()

    return JsonResponse({
        'market': market,
        'pest': {
            'period_start': pest.period_start.isoformat(),
            'period_end': pest.period_end.isoformat(),
            'political': pest.political_items,
            'economic': pest.economic_items,
            'social': pest.social_items,
            'technological': pest.technological_items,
            'political_summary': pest.political_summary,
            'economic_summary': pest.economic_summary,
            'social_summary': pest.social_summary,
            'technological_summary': pest.technological_summary,
            'overall_summary': pest.overall_summary,
        },
        'swot': {
            'strengths': swot.strengths,
            'weaknesses': swot.weaknesses,
            'opportunities': swot.opportunities,
            'threats': swot.threats,
            'so_strategies': swot.so_strategies,
            'st_strategies': swot.st_strategies,
            'wo_strategies': swot.wo_strategies,
            'wt_strategies': swot.wt_strategies,
            'overall_recommendation': swot.overall_recommendation,
            'confidence_score': swot.confidence_score,
        } if swot else None,
    })
