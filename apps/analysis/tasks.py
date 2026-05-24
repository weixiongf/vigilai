"""分析 App Celery 任务 — 重建 PEST + SWOT."""
import logging
from datetime import date, timedelta

from celery import shared_task
from django.db.models import Count

from apps.analysis.services.pest import aggregate_pest
from apps.analysis.services.swot import build_swot
from apps.intelligence.models import RawInfo


logger = logging.getLogger(__name__)


@shared_task(name='apps.analysis.tasks.rebuild_pest_swot')
def rebuild_pest_swot(days: int = 7, top_markets: int = 6) -> dict:
    """重新生成最近 N 天的 PEST + SWOT 快照."""
    end = date.today()
    start = end - timedelta(days=days - 1)

    top = (RawInfo.objects.filter(is_processed=True)
           .values('target_market')
           .annotate(c=Count('id'))
           .order_by('-c')[:top_markets])
    markets = ['global'] + [r['target_market'] for r in top if r['target_market']]

    results = []
    for m in markets:
        snap = aggregate_pest(start, end, m)
        swot = build_swot(snap)
        results.append({'market': m, 'pest_id': snap.id, 'swot_id': swot.id})

    return {'period': f'{start}~{end}', 'markets': len(markets), 'items': results}


@shared_task(name='apps.analysis.tasks.rebuild_for_market')
def rebuild_for_market(target_market: str, days: int = 7) -> dict:
    """重建指定市场的 PEST + SWOT."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    snap = aggregate_pest(start, end, target_market)
    swot = build_swot(snap)
    return {'market': target_market, 'pest_id': snap.id, 'swot_id': swot.id,
            'confidence': swot.confidence_score}
