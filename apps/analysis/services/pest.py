"""PEST 聚合服务 — 在指定时间窗口内, 按 PEST 维度汇总 RawInfo, 生成 PESTSnapshot."""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Avg, Count

from apps.analysis.models import PESTSnapshot
from apps.intelligence.models import RawInfo


def aggregate_pest(period_start: date, period_end: date,
                   target_market: str = 'global') -> PESTSnapshot:
    """构建 PESTSnapshot — 一个目标市场+时间窗口=一个快照."""
    qs = RawInfo.objects.filter(
        published_at__date__gte=period_start,
        published_at__date__lte=period_end,
        is_processed=True,
    )
    if target_market != 'global':
        qs = qs.filter(target_market=target_market)

    bucket = {'P': [], 'E': [], 'S': [], 'T': []}
    for info in qs.only('id', 'pest_type', 'title', 'impact_score',
                        'opportunity_or_threat', 'impact_level').iterator():
        if info.pest_type in bucket:
            bucket[info.pest_type].append({
                'id': info.id,
                'title': info.title,
                'score': info.impact_score or 0,
                'ot': info.opportunity_or_threat,
                'level': info.impact_level,
            })

    # 排序:按分数降序, 截断 Top20
    for k in bucket:
        bucket[k].sort(key=lambda x: x['score'], reverse=True)
        bucket[k] = bucket[k][:20]

    # 维度洞察文本
    summaries = {}
    for code, label in [('P', '政治法律'), ('E', '经济'),
                        ('S', '社会文化'), ('T', '技术')]:
        items = bucket[code]
        if not items:
            summaries[code] = f'{label}维度本期未捕获显著情报。'
            continue
        opp = sum(1 for x in items if x['ot'] == 'O')
        thr = len(items) - opp
        avg_score = round(sum(x['score'] for x in items) / len(items), 2)
        top_titles = [x['title'][:40] for x in items[:3]]
        summaries[code] = (
            f'{label}维度本期捕获 {len(items)} 条情报(机会 {opp} / 威胁 {thr}), '
            f'平均影响分 {avg_score}/10。代表事件: '
            + ' | '.join(top_titles) + '。'
        )

    # 整体结论
    total = sum(len(v) for v in bucket.values())
    overall = (
        f'{target_market} 市场 {period_start} ~ {period_end} 共聚合 {total} 条经分析情报, '
        f'PEST 分布: P {len(bucket["P"])} / E {len(bucket["E"])} / '
        f'S {len(bucket["S"])} / T {len(bucket["T"])}。'
    )

    snapshot, _ = PESTSnapshot.objects.update_or_create(
        period_start=period_start, period_end=period_end,
        target_market=target_market,
        defaults={
            'political_items': bucket['P'],
            'economic_items': bucket['E'],
            'social_items': bucket['S'],
            'technological_items': bucket['T'],
            'political_summary': summaries['P'],
            'economic_summary': summaries['E'],
            'social_summary': summaries['S'],
            'technological_summary': summaries['T'],
            'overall_summary': overall,
        },
    )
    return snapshot


def aggregate_recent(days: int = 7, markets: list | None = None) -> list[PESTSnapshot]:
    """近 N 天 PEST 快照(每个市场各一张, 含 global)."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    if markets is None:
        markets = ['global']
        # 从数据中取出 Top 市场
        top = (RawInfo.objects.filter(is_processed=True)
               .values('target_market')
               .annotate(c=Count('id'))
               .order_by('-c')[:6])
        markets += [r['target_market'] for r in top if r['target_market']]

    return [aggregate_pest(start, end, m) for m in markets]
