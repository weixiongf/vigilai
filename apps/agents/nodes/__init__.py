# -*- coding: utf-8 -*-
"""智能体节点实现 — 包装现有 service 函数为 AgentNode."""
from .collector import CollectorAgent
from .classifier import ClassifierAgent
from .briefer import BrieferAgent
from .dispatcher import DispatcherAgent

__all__ = ['CollectorAgent', 'ClassifierAgent', 'BrieferAgent', 'DispatcherAgent']
