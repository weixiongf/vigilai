"""分析 App REST API — PEST 快照 / SWOT 矩阵 / 手动重建."""
from __future__ import annotations

from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.analysis.models import PESTSnapshot, SWOTAnalysis


# ---- 序列化辅助 ----
def _serialize_pest(snap: PESTSnapshot, full: bool = False) -> dict:
    data = {
        'id': snap.id,
        'target_market': snap.target_market,
        'period_start': snap.period_start.isoformat() if snap.period_start else None,
        'period_end': snap.period_end.isoformat() if snap.period_end else None,
        'overall_summary': snap.overall_summary,
        'political_summary': snap.political_summary,
        'economic_summary': snap.economic_summary,
        'social_summary': snap.social_summary,
        'technological_summary': snap.technological_summary,
        'created_at': snap.created_at.isoformat() if snap.created_at else None,
    }
    if full:
        data.update({
            'political_items': snap.political_items or [],
            'economic_items': snap.economic_items or [],
            'social_items': snap.social_items or [],
            'technological_items': snap.technological_items or [],
        })
    return data


def _serialize_swot(swot: SWOTAnalysis) -> dict:
    return {
        'id': swot.id,
        'target_market': swot.target_market,
        'period_start': swot.period_start.isoformat() if swot.period_start else None,
        'period_end': swot.period_end.isoformat() if swot.period_end else None,
        'strengths': swot.strengths or [],
        'weaknesses': swot.weaknesses or [],
        'opportunities': swot.opportunities or [],
        'threats': swot.threats or [],
        'so_strategies': swot.so_strategies,
        'st_strategies': swot.st_strategies,
        'wo_strategies': swot.wo_strategies,
        'wt_strategies': swot.wt_strategies,
        'overall_recommendation': swot.overall_recommendation,
        'confidence_score': swot.confidence_score,
        'pest_snapshot_id': swot.pest_snapshot_id,
        'created_at': swot.created_at.isoformat() if swot.created_at else None,
    }


# ---- PEST 快照 ----
@require_GET
def pest_list(request):
    """PEST 快照列表 — ?market=US&days=7&page=1&size=10"""
    qs = PESTSnapshot.objects.all()
    market = request.GET.get('market')
    if market:
        qs = qs.filter(target_market=market)
    qs = qs.order_by('-period_end', '-created_at')

    try:
        page = max(1, int(request.GET.get('page', '1')))
        size = min(50, max(1, int(request.GET.get('size', '10'))))
    except ValueError:
        page, size = 1, 10

    total = qs.count()
    start = (page - 1) * size
    items = [_serialize_pest(s) for s in qs[start:start + size]]
    return JsonResponse({'total': total, 'page': page, 'size': size, 'items': items})


@require_GET
def pest_detail(request, pk: int):
    """PEST 快照详情 — 含四维 items."""
    try:
        snap = PESTSnapshot.objects.get(id=pk)
    except PESTSnapshot.DoesNotExist:
        raise Http404()
    return JsonResponse(_serialize_pest(snap, full=True))


# ---- SWOT 矩阵 ----
@require_GET
def swot_list(request):
    """SWOT 列表 — ?market=US&page=1&size=10"""
    qs = SWOTAnalysis.objects.all()
    market = request.GET.get('market')
    if market:
        qs = qs.filter(target_market=market)
    qs = qs.order_by('-period_end', '-created_at')

    try:
        page = max(1, int(request.GET.get('page', '1')))
        size = min(50, max(1, int(request.GET.get('size', '10'))))
    except ValueError:
        page, size = 1, 10

    total = qs.count()
    start = (page - 1) * size
    items = [_serialize_swot(s) for s in qs[start:start + size]]
    return JsonResponse({'total': total, 'page': page, 'size': size, 'items': items})


@require_GET
def swot_detail(request, pk: int):
    """SWOT 详情."""
    try:
        swot = SWOTAnalysis.objects.get(id=pk)
    except SWOTAnalysis.DoesNotExist:
        raise Http404()
    return JsonResponse(_serialize_swot(swot))


# ---- 手动触发重建 ----
@csrf_exempt
@require_POST
def rebuild(request):
    """手动触发 PEST + SWOT 重建 — {days: 7, top_markets: 6}."""
    import json
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        payload = {}
    days = int(payload.get('days', 7))
    top_markets = int(payload.get('top_markets', 6))
    try:
        from apps.analysis.tasks import rebuild_pest_swot
        task = rebuild_pest_swot.delay(days=days, top_markets=top_markets)
        return JsonResponse({'ok': True, 'task_id': task.id,
                             'days': days, 'top_markets': top_markets})
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=500)
