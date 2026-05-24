"""简报决策指标计算服务.

输出结构: KPI 对比 / 7 日 sparkline / 变化雷达 / 重要性分层.
被 views.briefing_metrics 与 services.templates.render_briefing_html 共用,
确保接口数据与邮件 / 详情页渲染数据完全一致.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Optional

from django.db.models import Avg


def _window_qs(start_d, end_d, target_market: str):
    """指定窗口内、匹配简报市场范围的情报 queryset."""
    from apps.intelligence.models import RawInfo
    qs = RawInfo.objects.filter(
        published_at__date__gte=start_d,
        published_at__date__lte=end_d,
        is_processed=True,
    )
    if target_market != 'global':
        qs = qs.filter(target_market=target_market)
    return qs


def _stats(qs):
    total = qs.count()
    high = qs.filter(impact_score__gte=8).count()
    opp = qs.filter(opportunity_or_threat='O').count()
    thr = qs.filter(opportunity_or_threat='T').count()
    avg = round(qs.aggregate(a=Avg('impact_score'))['a'] or 0, 2)
    return {'total': total, 'high': high, 'opp': opp, 'thr': thr, 'avg': avg}


def _pct_delta(cur_v, prev_v):
    if not prev_v:
        return None if cur_v == 0 else 100.0
    return round((cur_v - prev_v) / prev_v * 100.0, 1)


def _trend_of(cur_v, prev_v):
    if cur_v > prev_v:
        return 'up'
    if cur_v < prev_v:
        return 'down'
    return 'flat'


def compute_briefing_metrics(briefing) -> dict:
    """根据简报对象计算决策参照数据.

    返回 {kpi, sparkline, delta, priority, briefing_id, period_type}.
    """
    is_weekly = briefing.period_type == 'weekly'
    end = briefing.period_end
    target_market = briefing.target_market or 'global'

    def w(start_d, end_d):
        return _window_qs(start_d, end_d, target_market)

    # ---- 1) 当期 vs 上期 ----
    if is_weekly:
        cur = _stats(w(briefing.period_start, briefing.period_end))
        prev_end = briefing.period_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=6)
        prev = _stats(w(prev_start, prev_end))
        prev_label = '上周'
    else:
        cur = _stats(w(end, end))
        prev_d = end - timedelta(days=1)
        prev = _stats(w(prev_d, prev_d))
        prev_label = '昨日'

    # ---- 2) 7 日 sparkline ----
    sparkline = {'total': [], 'high': [], 'opp': [], 'thr': [], 'dates': []}
    base_avg_total = base_avg_high = base_avg_score = 0
    for i in range(6, -1, -1):
        d = end - timedelta(days=i)
        s = _stats(w(d, d))
        sparkline['total'].append(s['total'])
        sparkline['high'].append(s['high'])
        sparkline['opp'].append(s['opp'])
        sparkline['thr'].append(s['thr'])
        sparkline['dates'].append(d.isoformat())
        base_avg_total += s['total']
        base_avg_high += s['high']
        base_avg_score += s['avg']
    base_avg_total = round(base_avg_total / 7.0, 2)
    base_avg_high = round(base_avg_high / 7.0, 2)
    base_avg_score = round(base_avg_score / 7.0, 2)

    kpi = {
        'period_label': '周报' if is_weekly else '日报',
        'prev_label': prev_label,
        'total': {
            'value': cur['total'],
            'prev': prev['total'],
            'delta_pct': _pct_delta(cur['total'], prev['total']),
            'trend': _trend_of(cur['total'], prev['total']),
            'baseline_7d': base_avg_total,
            'vs_baseline_pct': _pct_delta(cur['total'], base_avg_total),
        },
        'high_impact': {
            'value': cur['high'],
            'prev': prev['high'],
            'delta_pct': _pct_delta(cur['high'], prev['high']),
            'trend': _trend_of(cur['high'], prev['high']),
            'baseline_7d': base_avg_high,
            'vs_baseline_pct': _pct_delta(cur['high'], base_avg_high),
        },
        'opp_thr_ratio': {
            'opp': cur['opp'],
            'thr': cur['thr'],
            'prev_opp': prev['opp'],
            'prev_thr': prev['thr'],
            'verdict': ('机会主导' if cur['opp'] > cur['thr']
                        else ('威胁主导' if cur['thr'] > cur['opp']
                              else '机会/威胁持平')),
        },
        'avg_score': {
            'value': cur['avg'],
            'prev': prev['avg'],
            'delta': round(cur['avg'] - prev['avg'], 2),
            'trend': _trend_of(cur['avg'], prev['avg']),
            'baseline_7d': base_avg_score,
            'vs_baseline': round(cur['avg'] - base_avg_score, 2),
        },
    }

    # ---- 3) 变化雷达 ----
    today_qs = w(end, end)
    prev_d = end - timedelta(days=1)
    yest_qs = w(prev_d, prev_d)
    week_qs = w(end - timedelta(days=6), end - timedelta(days=1))

    today_high = list(today_qs.filter(impact_score__gte=7)
                      .order_by('-impact_score')[:20]
                      .values('id', 'title', 'impact_score',
                              'target_market', 'opportunity_or_threat',
                              'tags', 'strategic_dimension'))
    yest_titles = set(yest_qs.values_list('title', flat=True))
    new_high_impact = [
        {
            'id': r['id'],
            'title': (r['title'] or '')[:80],
            'score': round(r['impact_score'] or 0, 1),
            'market': r['target_market'],
            'ot': r['opportunity_or_threat'],
        }
        for r in today_high if r['title'] not in yest_titles
    ][:5]

    tag_day_set = {}
    for i in range(6, -1, -1):
        d = end - timedelta(days=i)
        for r in w(d, d).values_list('tags', flat=True):
            for t in (r or []):
                tag_day_set.setdefault(t, set()).add(d.isoformat())
    rising_topics = sorted(
        [{'tag': t, 'days': len(ds)} for t, ds in tag_day_set.items()
         if len(ds) >= 3],
        key=lambda x: -x['days'])[:6]

    today_tags = set()
    for r in today_qs.values_list('tags', flat=True):
        for t in (r or []):
            today_tags.add(t)
    week_tag_count = Counter()
    for r in week_qs.values_list('tags', flat=True):
        for t in (r or []):
            week_tag_count[t] += 1
    faded_topics = [
        {'tag': t, 'prev_count': c}
        for t, c in week_tag_count.most_common()
        if t not in today_tags and c >= 2
    ][:5]

    delta_radar = {
        'new_high_impact': new_high_impact,
        'rising_topics': rising_topics,
        'faded_topics': faded_topics,
    }

    # ---- 4) 重要性分层 ----
    cur_qs = w(briefing.period_start, briefing.period_end)
    cur_titles_yest = yest_titles

    def serialize_intel(it):
        return {
            'id': it.id,
            'title': (it.title or '')[:90],
            'score': round(it.impact_score or 0, 1),
            'market': it.target_market,
            'dimension': it.strategic_dimension,
            'ot': it.opportunity_or_threat,
            'level': it.impact_level,
            'is_new': it.title not in cur_titles_yest,
        }

    urgent_qs = cur_qs.filter(
        impact_score__gte=8, opportunity_or_threat='T'
    ).order_by('-impact_score')[:10]
    urgent = []
    for it in urgent_qs:
        d_ = serialize_intel(it)
        if d_['is_new'] or d_['level'] == 'H':
            urgent.append(d_)
        if len(urgent) >= 5:
            break

    weekly_qs = cur_qs.filter(impact_score__gte=7).exclude(
        id__in=[u['id'] for u in urgent]
    ).order_by('-impact_score')[:5]
    weekly_focus = [serialize_intel(it) for it in weekly_qs]

    longterm_qs = cur_qs.filter(
        impact_score__lt=7, impact_score__gte=5
    ).order_by('-impact_score')[:5]
    longterm = [serialize_intel(it) for it in longterm_qs]

    priority = {
        'urgent': urgent,
        'weekly': weekly_focus,
        'longterm': longterm,
    }

    return {
        'briefing_id': briefing.id,
        'period_type': briefing.period_type,
        'kpi': kpi,
        'sparkline': sparkline,
        'delta': delta_radar,
        'priority': priority,
    }
