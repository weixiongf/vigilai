"""战略简报生成器 — 把分析结果聚合成 Briefing(行政摘要 + 维度切片 + 行动项)."""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Avg, Count
from django.utils import timezone

from apps.analysis.models import PESTSnapshot, SWOTAnalysis
from apps.analysis.services.pest import aggregate_pest
from apps.analysis.services.swot import build_swot
from apps.briefings.models import Briefing, BriefingSection
from apps.intelligence.models import RawInfo


DIMENSION_LABELS = {
    'competition': '竞争',
    'product': '产品',
    'platform': '平台',
    'social': '社媒',
    'regulation': '法规',
    'macro': '宏观',
    'industry': '行业',
}


def _summarize_dimension(qs, label: str) -> str:
    if not qs.exists():
        return f'{label}维度本期无显著情报。'
    total = qs.count()
    opp = qs.filter(opportunity_or_threat='O').count()
    thr = qs.filter(opportunity_or_threat='T').count()
    avg = qs.aggregate(a=Avg('impact_score'))['a'] or 0
    top = list(qs.order_by('-impact_score')[:3].values_list('title', flat=True))
    return (
        f'{label}维度共 {total} 条 (机会 {opp} / 威胁 {thr}), '
        f'平均影响 {round(avg, 2)}/10。\n  · '
        + '\n  · '.join(t[:60] for t in top)
    )


def _top_items(qs, ot: str, n: int = 3) -> list:
    items = qs.filter(opportunity_or_threat=ot).order_by('-impact_score')[:n]
    return [{
        'id': it.id,
        'title': it.title,
        'score': it.impact_score,
        'market': it.target_market,
        'dimension': it.strategic_dimension,
        'level': it.impact_level,
        'advice': (it.action_advice or '')[:200],
    } for it in items]


def generate_briefing(period_type: str = 'daily',
                      period_start: date | None = None,
                      period_end: date | None = None,
                      target_market: str = 'global',
                      auto_pest_swot: bool = True,
                      market_breakdown: list | None = None) -> Briefing:
    """生成一份 Briefing(并自动级联生成 PEST + SWOT).

    参数:
      market_breakdown: 可选市场列表, 仅周报有效 — 会在子章节中为每个市场
                        生成独立的摘要小节, 实现"一份周报看全局".
    """
    today = date.today()
    if not period_end:
        period_end = today
    if not period_start:
        if period_type == 'daily':
            period_start = period_end
        elif period_type == 'weekly':
            period_start = period_end - timedelta(days=6)
        elif period_type == 'monthly':
            period_start = period_end - timedelta(days=29)
        else:
            period_start = period_end - timedelta(days=6)

    # 1) 触发 PEST + SWOT
    snapshot = None
    swot = None
    if auto_pest_swot:
        snapshot = aggregate_pest(period_start, period_end, target_market)
        swot = build_swot(snapshot)

    # 2) 选取窗口内已分析情报
    qs = RawInfo.objects.filter(
        published_at__date__gte=period_start,
        published_at__date__lte=period_end,
        is_processed=True,
    )
    if target_market != 'global':
        qs = qs.filter(target_market=target_market)

    total = qs.count()

    # 3) 维度切片摘要
    dim_summaries = {}
    for code, label in DIMENSION_LABELS.items():
        dim_summaries[code] = _summarize_dimension(
            qs.filter(strategic_dimension=code), label)

    # 4) Top opportunities / risks
    top_opps = _top_items(qs, 'O', n=5)
    top_risks = _top_items(qs, 'T', n=5)

    # 5) 关键发现
    high_impact = qs.filter(impact_score__gte=8).count()
    market_dist = list(qs.values('target_market').annotate(c=Count('id')).order_by('-c')[:5])
    key_findings = [
        f'本期共聚合分析情报 {total} 条, 其中高影响(≥8) {high_impact} 条。',
        f'机会/威胁比: {len(top_opps)} : {len(top_risks)} (Top5 各)。',
        f'热度市场 Top5: ' + ', '.join(
            f'{r["target_market"]}({r["c"]})' for r in market_dist) or '无',
    ]
    if swot:
        key_findings.append(f'SWOT 置信度: {swot.confidence_score}')

    # 6) 推荐行动项
    actions = []
    for opp in top_opps[:2]:
        actions.append({
            'type': 'pursue',
            'title': f'抓取机会: {opp["title"][:40]}',
            'market': opp['market'],
            'priority': 'high',
            'detail': opp['advice'],
        })
    for risk in top_risks[:2]:
        actions.append({
            'type': 'mitigate',
            'title': f'防御风险: {risk["title"][:40]}',
            'market': risk['market'],
            'priority': 'high',
            'detail': risk['advice'],
        })

    # 7) Executive summary
    period_label = {'daily': '日报', 'weekly': '周报', 'monthly': '月报'}.get(period_type, '简报')
    exec_summary = (
        f'【{target_market} {period_label}】{period_start}~{period_end}: '
        f'共分析情报 {total} 条, 高影响 {high_impact} 条; '
        f'识别 Top {len(top_opps)} 战略机会与 Top {len(top_risks)} 主要风险; '
        f'建议本周期重点行动 {len(actions)} 项。'
    )

    title = f'{target_market} 战略{period_label} · {period_end.isoformat()}'

    briefing, _ = Briefing.objects.update_or_create(
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        target_market=target_market,
        defaults={
            'title': title,
            'executive_summary': exec_summary,
            'key_findings': key_findings,
            'top_opportunities': top_opps,
            'top_risks': top_risks,
            'competition_summary': dim_summaries.get('competition', ''),
            'product_summary': dim_summaries.get('product', ''),
            'platform_summary': dim_summaries.get('platform', ''),
            'social_summary': dim_summaries.get('social', ''),
            'regulation_summary': dim_summaries.get('regulation', ''),
            'pest_snapshot_id': snapshot.id if snapshot else None,
            'swot_id': swot.id if swot else None,
            'referenced_info_ids': [
                *[o['id'] for o in top_opps],
                *[r['id'] for r in top_risks],
            ],
            'recommended_actions': actions,
            'status': 'published',
            'generated_by': 'auto',
            'published_at': timezone.now(),
        },
    )

    # 8) 重建 sections
    briefing.sections.all().delete()
    sections_payload = [
        ('exec', '行政摘要', exec_summary),
        ('findings', '关键发现', '\n'.join(f'· {f}' for f in key_findings)),
        ('competition', '竞争维度', dim_summaries['competition']),
        ('product', '产品维度', dim_summaries['product']),
        ('platform', '平台维度', dim_summaries['platform']),
        ('social', '社媒维度', dim_summaries['social']),
        ('regulation', '法规维度', dim_summaries['regulation']),
        ('macro', '宏观维度', dim_summaries['macro']),
        ('industry', '行业维度', dim_summaries['industry']),
    ]

    # 周报: 追加各市场分区子章节
    if market_breakdown and period_type == 'weekly':
        for mkt in market_breakdown:
            mkt_qs = qs.filter(target_market=mkt)
            if not mkt_qs.exists():
                continue
            mkt_total = mkt_qs.count()
            mkt_opp = mkt_qs.filter(opportunity_or_threat='O').count()
            mkt_thr = mkt_qs.filter(opportunity_or_threat='T').count()
            mkt_avg = mkt_qs.aggregate(a=Avg('impact_score'))['a'] or 0
            mkt_top = list(mkt_qs.order_by('-impact_score')[:3]
                          .values_list('title', flat=True))
            body = (
                f'{mkt} 市场本周共 {mkt_total} 条情报 '
                f'(机会 {mkt_opp} / 威胁 {mkt_thr}), '
                f'平均影响 {round(mkt_avg, 2)}/10。\n'
                f'重点情报:\n  · '
                + '\n  · '.join(t[:60] for t in mkt_top)
            )
            sections_payload.append(
                (f'market_{mkt.lower()}', f'🌍 {mkt} 市场情况', body)
            )

    for i, (key, t, body) in enumerate(sections_payload):
        BriefingSection.objects.create(
            briefing=briefing,
            order=i,
            section_key=key,
            title=t,
            content=body,
        )

    return briefing
