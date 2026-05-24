"""SWOT 生成服务 — 基于 PESTSnapshot + 公司画像生成 SWOTAnalysis(含 SO/ST/WO/WT 跨象限策略)."""
from __future__ import annotations

from datetime import date

from django.conf import settings

from apps.analysis.models import PESTSnapshot, SWOTAnalysis


def _extract_external(snapshot: PESTSnapshot, max_each: int = 5) -> tuple[list, list]:
    """从 PESTSnapshot 抽取 O / T 两组 (Top 影响分)."""
    opportunities = []
    threats = []
    for items in (snapshot.political_items, snapshot.economic_items,
                  snapshot.social_items, snapshot.technological_items):
        for it in items:
            payload = {
                'id': it.get('id'),
                'title': it.get('title', ''),
                'score': it.get('score', 0),
                'level': it.get('level', ''),
            }
            if it.get('ot') == 'O':
                opportunities.append(payload)
            elif it.get('ot') == 'T':
                threats.append(payload)
    opportunities.sort(key=lambda x: x['score'], reverse=True)
    threats.sort(key=lambda x: x['score'], reverse=True)
    return opportunities[:max_each], threats[:max_each]


def _label_of(x) -> str:
    """统一抽取一个可读 label — 兼容字符串/带 title/带 item 的字典."""
    if isinstance(x, dict):
        return str(x.get('title') or x.get('item') or x.get('label') or x)
    return str(x)


def _format_strategy(prefix: str, items_a: list, items_b: list,
                     joiner: str = ' × ') -> str:
    """生成跨象限策略文本 — 把 a×b 的关键词组合成 1-3 条建议."""
    if not items_a or not items_b:
        return f'[{prefix}] 暂无足够输入项, 待下一周期重新评估。'
    lines = []
    for i, a in enumerate(items_a[:2], start=1):
        for j, b in enumerate(items_b[:2], start=1):
            a_title = _label_of(a)[:40]
            b_title = _label_of(b)[:40]
            lines.append(
                f'{prefix}-{i}{j}: {a_title} {joiner} {b_title}'
            )
            if len(lines) >= 3:
                break
        if len(lines) >= 3:
            break
    return '\n'.join(lines)


def build_swot(snapshot: PESTSnapshot,
               strengths: list | None = None,
               weaknesses: list | None = None) -> SWOTAnalysis:
    """生成 SWOT — 内部 S/W 来自 settings 公司画像, 外部 O/T 来自 PESTSnapshot."""
    strengths = strengths or getattr(settings, 'COMPANY_STRENGTHS', [])
    weaknesses = weaknesses or getattr(settings, 'COMPANY_WEAKNESSES', [])

    # 兼容字符串/字典两种写法
    s_list = [{'item': s} if isinstance(s, str) else s for s in strengths]
    w_list = [{'item': w} if isinstance(w, str) else w for w in weaknesses]

    opportunities, threats = _extract_external(snapshot)

    so = _format_strategy('SO 增长', s_list, opportunities, joiner='× 抓取')
    st = _format_strategy('ST 防御', s_list, threats, joiner='× 抵御')
    wo = _format_strategy('WO 扭转', w_list, opportunities, joiner='× 借势')
    wt = _format_strategy('WT 规避', w_list, threats, joiner='× 规避')

    overall = (
        f'{snapshot.target_market} 市场 {snapshot.period_start}~{snapshot.period_end} 战略建议:\n'
        f'· 优先抓取 Top 机会: {opportunities[0]["title"][:40] if opportunities else "无"};\n'
        f'· 重点防御 Top 威胁: {threats[0]["title"][:40] if threats else "无"};\n'
        f'· 整体姿态: {"进攻" if len(opportunities) >= len(threats) else "防御"}。'
    )

    confidence = round(min(1.0, 0.5 + 0.05 * (len(opportunities) + len(threats))), 2)

    swot, _ = SWOTAnalysis.objects.update_or_create(
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        target_market=snapshot.target_market,
        defaults={
            'strengths': s_list,
            'weaknesses': w_list,
            'opportunities': opportunities,
            'threats': threats,
            'so_strategies': so,
            'st_strategies': st,
            'wo_strategies': wo,
            'wt_strategies': wt,
            'pest_snapshot': snapshot,
            'overall_recommendation': overall,
            'confidence_score': confidence,
        },
    )
    return swot
