# -*- coding: utf-8 -*-
"""A2A 消息协议 + AgentNode 抽象 — 多智能体协作的最小通信单元.

设计参考: Google A2A / Anthropic MCP 的语义.
- AgentMessage: 节点之间统一的消息体, 含 trace_id 串联整条链路;
- AgentNode: 抽象基类, 子类实现 handle(); 包装为 Celery Task 后即可分布式执行;
- AgentResult: 节点处理结果, 用于回写 AgentMessage 的 status/payload.
"""
from __future__ import annotations

import abc
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


# 节点类型枚举(对应赛题"市场雷达"五大职能)
NODE_COLLECTOR = 'collector'      # 采集 Agent
NODE_CLASSIFIER = 'classifier'    # 分类归因 Agent
NODE_BRIEFER = 'briefer'          # 简报撰写 Agent
NODE_DISPATCHER = 'dispatcher'    # 分发(人机协同)
NODE_COORDINATOR = 'coordinator'  # 总控

STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_DONE = 'done'
STATUS_FAILED = 'failed'


@dataclass
class AgentMessage:
    """A2A 协议消息 — 节点之间传递的统一封装."""

    msg_type: str                       # 业务事件类型 (intel.collected / intel.classified / briefing.requested ...)
    payload: dict = field(default_factory=dict)
    sender: str = ''                    # 发送方节点名
    receiver: str = ''                  # 接收方节点名
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'AgentMessage':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AgentResult:
    """节点处理结果."""

    status: str = STATUS_DONE           # done / failed
    output: dict = field(default_factory=dict)
    next_messages: list = field(default_factory=list)   # 触发下游节点的 AgentMessage 列表
    error: str = ''

    def to_dict(self) -> dict:
        return {
            'status': self.status,
            'output': self.output,
            'next_messages': [m.to_dict() if isinstance(m, AgentMessage) else m
                              for m in self.next_messages],
            'error': self.error,
        }


class AgentNode(abc.ABC):
    """智能体节点抽象基类 — 一个 Agent = 一个职能 + 一个 handle() 函数."""

    name: str = 'agent'                 # 节点名称(用于日志/路由)
    node_type: str = ''                 # 见上方枚举

    @abc.abstractmethod
    def handle(self, message: AgentMessage) -> AgentResult:
        """处理一条入站消息, 返回处理结果与可能的下游消息."""

    # ---- 工具方法 ----
    def emit(self, msg_type: str, payload: dict, receiver: str = '',
             trace_id: str = '', metadata: dict | None = None) -> AgentMessage:
        """生成一条下游消息 — 复用当前 trace_id 串联整条链路."""
        return AgentMessage(
            msg_type=msg_type,
            payload=payload,
            sender=self.name,
            receiver=receiver,
            trace_id=trace_id or uuid.uuid4().hex[:16],
            metadata=metadata or {},
        )

    def __repr__(self) -> str:
        return f'<AgentNode {self.name}({self.node_type})>'
