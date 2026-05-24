"""统一简报 HTML 渲染服务 — 三处共用一份模板.

调用方:
  - apps.notifications.services.email.send_briefing_email() : 邮件正文
  - apps.briefings.views.briefing_render()                  : 详情页
  - apps.briefings.views.briefing_preview()                 : 通知中心模板预览

模板路径: templates/briefings/_briefing_full.html
所有样式 inline 化, 同时兼容 Web 与邮件客户端.
"""
from __future__ import annotations

import re
from typing import Optional

from django.template.loader import render_to_string


# ---------- 渲染辅助 ----------
def _build_sparkline_svg(values, color='#3b82f6', w=110, h=28, pad=2) -> str:
    """与 static/js/briefing.js::sparkSVG 等价的 Python 端实现.

    返回 inline SVG 字符串, 主流邮件客户端 (Apple Mail / Gmail Web / 移动端)
    均支持; Outlook Desktop 会降级为不显示, 不影响整体阅读.
    """
    if not values:
        return ''
    max_v = max(1, max(values))
    min_v = min(0, min(values))
    rng = (max_v - min_v) or 1
    n = len(values)
    step_x = (w - pad * 2) / max(1, n - 1)
    pts = []
    for i, v in enumerate(values):
        x = pad + i * step_x
        y = h - pad - ((v - min_v) / rng) * (h - pad * 2)
        pts.append((x, y))
    path = ' '.join(
        f'{"M" if i == 0 else "L"}{p[0]:.1f},{p[1]:.1f}'
        for i, p in enumerate(pts))
    area = (path
            + f' L{pts[-1][0]:.1f},{h - pad}'
            + f' L{pts[0][0]:.1f},{h - pad} Z')
    last = pts[-1]
    return (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'preserveAspectRatio="none" '
        f'style="display:block;margin-top:4px;max-width:100%;">'
        f'<path d="{area}" fill="{color}" opacity="0.12"/>'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.4" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="2" fill="{color}"/>'
        f'</svg>'
    )


def _delta_tag(pct, trend, invert_good=False) -> str:
    """与 briefing.js::deltaTag 一致的环比箭头标签."""
    if pct is None:
        return '<span style="color:#9ca3af;">—</span>'
    arrow = '↑' if trend == 'up' else ('↓' if trend == 'down' else '→')
    is_good = (trend == 'down') if invert_good else (trend == 'up')
    if trend == 'flat':
        color = '#9ca3af'
    elif is_good:
        color = '#16a34a'
    else:
        color = '#dc2626'
    sign = '+' if (pct or 0) > 0 else ''
    return (f'<span style="color:{color};font-weight:600;">'
            f'{arrow} {sign}{pct}%</span>')


def _ot_tag(ot: str) -> str:
    if ot == 'O':
        return ('<span style="display:inline-block;width:18px;height:18px;'
                'line-height:18px;text-align:center;font-size:11px;'
                'border-radius:3px;background:#dcfce7;color:#16a34a;'
                'font-weight:700;margin-right:4px;">机</span>')
    if ot == 'T':
        return ('<span style="display:inline-block;width:18px;height:18px;'
                'line-height:18px;text-align:center;font-size:11px;'
                'border-radius:3px;background:#fee2e2;color:#dc2626;'
                'font-weight:700;margin-right:4px;">威</span>')
    return ''


# 与 briefing.js::SECTION_ICON 对齐: emoji + 主色
SECTION_META = {
    'exec':        ('🔖', '#3b82f6'),
    'findings':    ('🔑', '#f59e0b'),
    'competition': ('⚔️', '#f43f5e'),
    'product':     ('🛍️', '#06b6d4'),
    'platform':    ('🏪', '#8b5cf6'),
    'social':      ('💬', '#ec4899'),
    'regulation':  ('⚖️', '#14b8a6'),
    'macro':       ('📈', '#22c55e'),
    'industry':    ('🏢', '#64748b'),
}


def _section_meta(key: str):
    if key in SECTION_META:
        return SECTION_META[key]
    if key.startswith('market_'):
        return ('🌍', '#3b82f6')
    return ('📄', '#64748b')


# 数字高亮: 与 briefing.js::hilite 等价 (但只针对纯数字+常见单位, 避免乱标)
_HILITE_RE = re.compile(
    r'(\d+(?:\.\d+)?(?:\s*%|\s*条|\s*份|\s*次|\s*天|\s*小时|\s*分钟|'
    r'\s*倍|\s*分|\s*个|\s*项|\s*市场|\s*话题|\s*人|/\d+)?)'
)


def _hilite(text: str) -> str:
    """对数字+单位加红色高亮 (HTML 已转义后调用)."""
    if not text:
        return ''
    return _HILITE_RE.sub(
        r'<span style="color:#dc2626;font-weight:700;">\1</span>', text)


# ---------- 上下文构建 ----------
def build_briefing_context(briefing, metrics: Optional[dict] = None) -> dict:
    """根据 Briefing 与可选 metrics 构建模板上下文."""
    period_label_map = {
        'daily': '战略日报', 'weekly': '战略周报',
        'monthly': '战略月报', 'adhoc': '临时简报',
    }
    period_label = period_label_map.get(briefing.period_type, '战略简报')

    raw_summary = briefing.executive_summary or ''
    parts = [s.strip() for s in re.split(r'[。；;\n]+', raw_summary) if s.strip()]
    summary_parts = parts if len(parts) > 1 else []

    # ---- 子章节: 附加 icon/color ----
    sections = []
    try:
        for s in briefing.sections.all().order_by('order'):
            icon, color = _section_meta(s.section_key)
            sections.append({
                'order': s.order,
                'section_key': s.section_key,
                'title': s.title,
                'content': s.content or '',
                'icon': icon,
                'color': color,
            })
    except Exception:
        pass

    ctx = {
        'briefing': briefing,
        'title': briefing.title or '',
        'market': briefing.target_market or '',
        'period_label': period_label,
        'period_type_label': briefing.get_period_type_display(),
        'period_range': f'{briefing.period_start} ~ {briefing.period_end}',
        'period_start': briefing.period_start,
        'period_end': briefing.period_end,
        'refs': len(briefing.referenced_info_ids or []),
        'executive_summary': raw_summary,
        'summary_parts': summary_parts,
        'key_findings': briefing.key_findings or [],
        'top_opportunities': (briefing.top_opportunities or [])[:5],
        'top_risks': (briefing.top_risks or [])[:5],
        'recommended_actions': (briefing.recommended_actions or [])[:6],
        'sections': sections,
        # metrics 默认为空, 模板内通过 if 判断是否渲染仪表板
        'has_metrics': False,
        'kpi_cards': [],
        'delta': None,
        'priority': None,
    }

    if metrics:
        kpi = metrics.get('kpi') or {}
        sp = metrics.get('sparkline') or {}
        prev_label = kpi.get('prev_label', '')
        # 4 张 KPI 卡片
        total_k = kpi.get('total') or {}
        high_k = kpi.get('high_impact') or {}
        ratio_k = kpi.get('opp_thr_ratio') or {}
        avg_k = kpi.get('avg_score') or {}
        avg_v = avg_k.get('value', 0)
        try:
            avg_str = f'{float(avg_v):.1f}'
        except Exception:
            avg_str = str(avg_v or '0.0')

        kpi_cards = [
            {
                'label': '📋 情报总量',
                'value': total_k.get('value', 0),
                'unit': '',
                'value_color': '#111827',
                'delta_html': _delta_tag(total_k.get('delta_pct'),
                                         total_k.get('trend')),
                'baseline_html': (f'7日均 {total_k.get("baseline_7d", 0)} '
                                  + _delta_tag(total_k.get('vs_baseline_pct'),
                                               'up' if (total_k.get('vs_baseline_pct') or 0) >= 0 else 'down')),
                'sparkline': _build_sparkline_svg(sp.get('total') or [], '#3b82f6'),
                'prev_label': prev_label,
            },
            {
                'label': '🔥 高影响数',
                'value': high_k.get('value', 0),
                'unit': '',
                'value_color': '#dc2626',
                'delta_html': _delta_tag(high_k.get('delta_pct'),
                                         high_k.get('trend'),
                                         invert_good=True),
                'baseline_html': f'7日均 {high_k.get("baseline_7d", 0)}',
                'sparkline': _build_sparkline_svg(sp.get('high') or [], '#dc2626'),
                'prev_label': prev_label,
            },
            {
                'label': '⚖️ 机会/威胁',
                'value': f'{ratio_k.get("opp", 0)} : {ratio_k.get("thr", 0)}',
                'unit': '',
                'value_color': '#111827',
                'delta_html': (f'<span style="font-weight:600;color:'
                               f'{"#dc2626" if (ratio_k.get("thr", 0) > ratio_k.get("opp", 0)) else "#16a34a"};">'
                               f'{ratio_k.get("verdict", "")}</span>'),
                'baseline_html': (f'{prev_label} '
                                  f'{ratio_k.get("prev_opp", 0)}:'
                                  f'{ratio_k.get("prev_thr", 0)}'),
                'sparkline': _build_sparkline_svg(sp.get('thr') or [], '#dc2626'),
                'prev_label': prev_label,
            },
            {
                'label': '⚡ 平均影响分',
                'value': avg_str,
                'unit': '/10',
                'value_color': '#f59e0b',
                'delta_html': (f'<span style="color:'
                               f'{"#16a34a" if (avg_k.get("delta", 0) or 0) >= 0 else "#dc2626"};'
                               f'font-weight:600;">'
                               f'{"↑ +" if (avg_k.get("delta", 0) or 0) >= 0 else "↓ "}'
                               f'{avg_k.get("delta", 0)}</span>'),
                'baseline_html': f'7日基线 {avg_k.get("baseline_7d", 0)}',
                'sparkline': _build_sparkline_svg(sp.get('high') or [], '#f59e0b'),
                'prev_label': prev_label,
            },
        ]
        ctx['has_metrics'] = True
        ctx['kpi_cards'] = kpi_cards
        ctx['delta'] = metrics.get('delta')
        ctx['priority'] = metrics.get('priority')

    return ctx


# ---------- 对外接口 ----------
def render_briefing_html(briefing, metrics: Optional[dict] = None,
                          mode: str = 'email',
                          include_metrics: bool = True) -> str:
    """渲染简报为 HTML 字符串. 三处共用此函数.

    参数:
      briefing: Briefing ORM 对象
      metrics:  可选 — 已计算好的 metrics 字典. 不传则按 include_metrics 决定是否计算
      mode:     'email' (默认, 整页 HTML) | 'web' (片段, 嵌入详情页) | 'preview' (与 email 相同)
      include_metrics: metrics 为 None 时是否触发计算 (默认 True)

    返回: 完整 HTML 字符串
    """
    if metrics is None and include_metrics:
        try:
            from apps.briefings.services.metrics import compute_briefing_metrics
            metrics = compute_briefing_metrics(briefing)
        except Exception:
            metrics = None

    ctx = build_briefing_context(briefing, metrics)
    ctx['render_mode'] = mode
    ctx['standalone'] = mode in ('email', 'preview')  # 是否输出完整 <html> 包裹
    return render_to_string('briefings/_briefing_full.html', ctx)


def render_latest_briefing_preview(mode: str = 'email') -> str:
    """渲染最新一条 published 简报作为通知中心模板预览."""
    from apps.briefings.models import Briefing
    b = (Briefing.objects.filter(status='published')
         .order_by('-period_end', '-created_at')
         .first())
    if not b:
        return ('<div style="padding:40px;text-align:center;color:#9ca3af;'
                'font-family:-apple-system,sans-serif;">'
                '暂无已发布简报, 触发一次"立即生成"即可看到预览</div>')
    return render_briefing_html(b, mode=mode)
