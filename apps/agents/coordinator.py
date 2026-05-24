# -*- coding: utf-8 -*-
"""Agent 编排器 — 注册节点 + 路由消息 + 持久化日志.

用法:
    coordinator = AgentCoordinator()
    coordinator.register(CollectorAgent())
    coordinator.register(ClassifierAgent())
    coordinator.dispatch(AgentMessage(msg_type='collect.request',
                                      receiver='collector',
                                      payload={'limit': 3}))
"""
from __future__ import annotations

import logging
from typing import Iterable

from django.utils import timezone

from .protocol import (
    AgentMessage, AgentNode, AgentResult,
    STATUS_RUNNING, STATUS_DONE, STATUS_FAILED,
)

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """A2A 编排器 — 把 AgentMessage 路由给对应 AgentNode 并记录追溯."""

    def __init__(self):
        self._nodes: dict[str, AgentNode] = {}

    # ---- 节点注册 ----
    def register(self, agent: AgentNode) -> None:
        self._nodes[agent.name] = agent
        logger.info('agent registered: %s', agent)

    def register_all(self, agents: Iterable[AgentNode]) -> None:
        for a in agents:
            self.register(a)

    def get(self, name: str) -> AgentNode | None:
        return self._nodes.get(name)

    def list_nodes(self) -> list:
        return [{'name': n.name, 'type': n.node_type}
                for n in self._nodes.values()]

    # ---- 消息分发 ----
    def dispatch(self, message: AgentMessage, depth: int = 0,
                 max_depth: int = 8) -> list[AgentResult]:
        """分发消息 — 同步链式执行直到无下游消息或达到 max_depth.

        Args:
            message: 入口 AgentMessage.
            depth:   当前递归深度.
            max_depth: 防止意外死循环, 默认 8 层.
        """
        results: list[AgentResult] = []
        if depth >= max_depth:
            logger.warning('dispatch depth limit reached: %s', max_depth)
            return results

        log = self._persist_pending(message)
        target = self._nodes.get(message.receiver)
        if target is None:
            err = f'no_agent_named:{message.receiver}'
            self._persist_done(log, AgentResult(status=STATUS_FAILED, error=err))
            logger.warning(err)
            return results

        # 执行
        self._mark_running(log)
        try:
            result = target.handle(message)
        except Exception as exc:  # noqa: BLE001
            logger.exception('agent %s handle failed', target.name)
            result = AgentResult(status=STATUS_FAILED, error=str(exc))

        self._persist_done(log, result)
        results.append(result)

        # 触发下游
        for nxt in result.next_messages or []:
            if isinstance(nxt, dict):
                nxt = AgentMessage.from_dict(nxt)
            results.extend(self.dispatch(nxt, depth=depth + 1, max_depth=max_depth))

        return results

    # ---- 持久化 ----
    def _persist_pending(self, message: AgentMessage):
        from .models import AgentMessageLog
        log, _ = AgentMessageLog.objects.update_or_create(
            msg_id=message.msg_id,
            defaults={
                'trace_id': message.trace_id,
                'msg_type': message.msg_type,
                'sender': message.sender,
                'receiver': message.receiver,
                'payload': message.payload,
                'metadata': message.metadata,
                'status': 'pending',
            },
        )
        return log

    def _mark_running(self, log) -> None:
        log.status = STATUS_RUNNING
        log.save(update_fields=['status'])

    def _persist_done(self, log, result: AgentResult) -> None:
        log.status = result.status
        log.output = result.output
        log.error = result.error or ''
        log.finished_at = timezone.now()
        log.save(update_fields=['status', 'output', 'error', 'finished_at'])


# ---- 默认编排器: 注册 4 个标准节点 ----
def build_default_coordinator() -> AgentCoordinator:
    """构造默认编排器 — 已注册 collector / classifier / briefer / dispatcher."""
    from .nodes import (
        CollectorAgent, ClassifierAgent, BrieferAgent, DispatcherAgent,
    )
    coord = AgentCoordinator()
    coord.register_all([
        CollectorAgent(), ClassifierAgent(),
        BrieferAgent(), DispatcherAgent(),
    ])
    return coord
