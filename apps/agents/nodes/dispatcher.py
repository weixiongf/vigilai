# -*- coding: utf-8 -*-
"""分发 Agent — 包装 apps.notifications.tasks.dispatch_briefing / send_high_impact_alert."""
from __future__ import annotations

from ..protocol import (
    AgentNode, AgentMessage, AgentResult,
    NODE_DISPATCHER, STATUS_DONE,
)


class DispatcherAgent(AgentNode):
    """分发智能体 — 飞书+邮件+WebSocket 发送, 写 NotificationLog."""

    name = 'dispatcher'
    node_type = NODE_DISPATCHER

    def handle(self, message: AgentMessage) -> AgentResult:
        payload = message.payload or {}
        msg_type = message.msg_type

        if msg_type == 'briefing.published':
            from apps.notifications.tasks import dispatch_briefing
            briefing_id = payload.get('briefing_id')
            if briefing_id:
                # 同步执行便于演示; 生产环境改为 .delay()
                result = dispatch_briefing(briefing_id)
                return AgentResult(status=STATUS_DONE,
                                   output={'dispatch': result})

        elif msg_type == 'alert.high_impact':
            from apps.notifications.tasks import send_high_impact_alert
            for info_id in payload.get('high_impact_ids', []):
                try:
                    send_high_impact_alert(info_id)
                except Exception:  # noqa: BLE001
                    continue
            return AgentResult(
                status=STATUS_DONE,
                output={'alerted': len(payload.get('high_impact_ids', []))},
            )

        return AgentResult(status=STATUS_DONE,
                           output={'note': f'no_handler_for:{msg_type}'})
