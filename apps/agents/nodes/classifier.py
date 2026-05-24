# -*- coding: utf-8 -*-
"""分类归因 Agent — 包装 apps.analysis.services.analyzer.analyze_one."""
from __future__ import annotations

from ..protocol import (
    AgentNode, AgentMessage, AgentResult,
    NODE_CLASSIFIER, NODE_BRIEFER, STATUS_DONE,
)


class ClassifierAgent(AgentNode):
    """分类归因智能体 — PEST 分类 + 4 维评分 + 行动建议; 完成后请求 BrieferAgent 重建简报."""

    name = 'classifier'
    node_type = NODE_CLASSIFIER

    def handle(self, message: AgentMessage) -> AgentResult:
        from apps.analysis.services.analyzer import analyze_one
        from apps.intelligence.models import RawInfo

        payload = message.payload or {}
        limit = int(payload.get('limit', 50))
        source_id = payload.get('source_id')

        qs = RawInfo.objects.filter(is_processed=False)
        if source_id:
            qs = qs.filter(source_id=source_id)

        ids = list(qs.values_list('id', flat=True)[:limit])
        analyzed = 0
        high_impact_ids = []
        for info in RawInfo.objects.filter(id__in=ids):
            try:
                analyze_one(info, save=True)
                analyzed += 1
                if (info.impact_score or 0) >= 8:
                    high_impact_ids.append(info.id)
            except Exception:  # noqa: BLE001
                continue

        next_msgs = []
        # 有新分析结果 → 触发简报刷新
        if analyzed:
            next_msgs.append(self.emit(
                msg_type='briefing.requested',
                payload={'reason': 'new_intel_analyzed',
                         'count': analyzed,
                         'high_impact_ids': high_impact_ids},
                receiver=NODE_BRIEFER,
                trace_id=message.trace_id,
            ))

        return AgentResult(
            status=STATUS_DONE,
            output={'analyzed': analyzed, 'high_impact': len(high_impact_ids)},
            next_messages=next_msgs,
        )
