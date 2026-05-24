# -*- coding: utf-8 -*-
"""简报撰写 Agent — 包装 apps.briefings.services.generator.generate_briefing."""
from __future__ import annotations

from datetime import date, timedelta

from ..protocol import (
    AgentNode, AgentMessage, AgentResult,
    NODE_BRIEFER, NODE_DISPATCHER, STATUS_DONE,
)


class BrieferAgent(AgentNode):
    """简报撰写智能体 — 生成 Briefing(自动级联 PEST/SWOT), 完成后通知 DispatcherAgent."""

    name = 'briefer'
    node_type = NODE_BRIEFER

    def handle(self, message: AgentMessage) -> AgentResult:
        from apps.briefings.services.generator import generate_briefing

        payload = message.payload or {}
        period_type = payload.get('period_type', 'daily')
        target_market = payload.get('target_market', 'global')
        days = int(payload.get('days', 1 if period_type == 'daily' else 7))

        end = date.today()
        start = end - timedelta(days=max(0, days - 1))

        briefing = generate_briefing(
            period_type=period_type,
            period_start=start, period_end=end,
            target_market=target_market,
            auto_pest_swot=True,
        )

        # 触发分发
        next_msg = self.emit(
            msg_type='briefing.published',
            payload={'briefing_id': briefing.id,
                     'title': briefing.title,
                     'period_type': period_type,
                     'target_market': target_market},
            receiver=NODE_DISPATCHER,
            trace_id=message.trace_id,
        )

        return AgentResult(
            status=STATUS_DONE,
            output={'briefing_id': briefing.id,
                    'title': briefing.title,
                    'referenced': len(briefing.referenced_info_ids or [])},
            next_messages=[next_msg],
        )
