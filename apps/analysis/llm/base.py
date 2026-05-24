"""LLM Provider 抽象 — 所有真实/Mock 实现都遵循该接口.

设计原则:
  - 输入是结构化的 dict(标题/正文/上下文), 输出是结构化 dict;
  - 不依赖任何外部 SDK, Mock 模式确保黑客松无 Key 也能跑;
  - 真实 Provider(OpenAI/Claude/通义)只需要实现 _complete() 即可;
  - 所有 Provider 共享 prompt 模板 + 输出解析(在 base 实现);
  - 具备幂等的"返回 dict"形态, 便于结果落库 analysis_chain(JSONField).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


# ======================================================================
# DTO
# ======================================================================
@dataclass
class IntelInput:
    """LLM 分析输入 — 单条情报"""
    title: str
    content: str
    target_market: str = ''
    strategic_dimension: str = ''
    source_name: str = ''
    company_strengths: list = field(default_factory=list)
    company_weaknesses: list = field(default_factory=list)


@dataclass
class IntelAnalysis:
    """LLM 分析输出 — 结构化结果"""
    pest_type: str          # P/E/S/T
    opportunity_or_threat: str  # O/T
    impact_level: str       # H/M/L
    impact_type: str        # opportunity/risk/watch/neutral
    severity: str           # high/medium/low
    sentiment: str          # positive/negative/neutral
    score_relevance: float  # 0-4
    score_urgency: float    # 0-3
    score_authority: float  # 0-2
    score_scope: float      # 0-1
    impact_score: float     # 总分 0-10
    summary: str
    rationale: str
    action_advice: str
    tags: list
    chain: list             # [{step, prompt, response}, ...]

    def to_dict(self) -> dict:
        return self.__dict__


# ======================================================================
# Base Provider
# ======================================================================
class BaseLLMProvider(abc.ABC):
    """LLM Provider 抽象基类."""

    name: str = 'base'

    @abc.abstractmethod
    def _complete(self, prompt: str, **kwargs) -> str:
        """子类实现: 给定 prompt 返回字符串结果."""

    def analyze_intel(self, intel: IntelInput,
                      on_token=None, on_thinking=None) -> IntelAnalysis:
        """对一条情报做完整分析(PEST + 评分 + 行动建议).

        on_token: 可选回调 fn(token: str), 子类支持流式时实时透传 LLM
        正文 delta 片段; 不支持流式或同步路径可忽略此参数.
        on_thinking: 可选回调 fn(token: str), 仅接收思考过程片段.

        子类可以覆盖整段流程; 默认实现是顺序 4 步链路:
        1) PEST + O/T + level
        2) 价值评分 4 维
        3) 摘要 + 判断理由
        4) 行动建议
        """
        chain = []

        # Step 1
        prompt1 = self._build_pest_prompt(intel)
        resp1 = self._complete(prompt1, step='pest')
        pest_result = self._parse_pest(resp1)
        chain.append({'step': 'pest', 'prompt': prompt1, 'response': resp1, 'parsed': pest_result})

        # Step 2
        prompt2 = self._build_score_prompt(intel, pest_result)
        resp2 = self._complete(prompt2, step='score')
        score_result = self._parse_score(resp2)
        chain.append({'step': 'score', 'prompt': prompt2, 'response': resp2, 'parsed': score_result})

        # Step 3
        prompt3 = self._build_summary_prompt(intel, pest_result)
        resp3 = self._complete(prompt3, step='summary')
        summary, rationale, tags = self._parse_summary(resp3)
        chain.append({'step': 'summary', 'prompt': prompt3, 'response': resp3,
                      'parsed': {'summary': summary, 'rationale': rationale, 'tags': tags}})

        # Step 4
        prompt4 = self._build_action_prompt(intel, pest_result, score_result)
        resp4 = self._complete(prompt4, step='action')
        action = self._parse_action(resp4)
        chain.append({'step': 'action', 'prompt': prompt4, 'response': resp4, 'parsed': action})

        # 汇总到 IntelAnalysis
        impact_score = round(
            score_result['relevance']
            + score_result['urgency']
            + score_result['authority']
            + score_result['scope'], 2)

        if pest_result['ot'] == 'O':
            impact_type = 'opportunity'
        elif pest_result['level'] == 'H':
            impact_type = 'risk'
        else:
            impact_type = 'watch'

        severity_map = {'H': 'high', 'M': 'medium', 'L': 'low'}

        return IntelAnalysis(
            pest_type=pest_result['pest'],
            opportunity_or_threat=pest_result['ot'],
            impact_level=pest_result['level'],
            impact_type=impact_type,
            severity=severity_map.get(pest_result['level'], 'medium'),
            sentiment=score_result.get('sentiment', 'neutral'),
            score_relevance=score_result['relevance'],
            score_urgency=score_result['urgency'],
            score_authority=score_result['authority'],
            score_scope=score_result['scope'],
            impact_score=impact_score,
            summary=summary,
            rationale=rationale,
            action_advice=action,
            tags=tags,
            chain=chain,
        )

    # ---- Prompt 模板(子类可覆盖) ----
    def _build_pest_prompt(self, intel: IntelInput) -> str:
        return (
            '你是出海战略情报分析师。请对以下情报做 PEST 分类:\n'
            f'标题: {intel.title}\n正文: {intel.content[:600]}\n'
            f'目标市场: {intel.target_market}\n维度: {intel.strategic_dimension}\n'
            '请返回 JSON-like 结构: pest=P/E/S/T, ot=O/T, level=H/M/L\n'
        )

    def _build_score_prompt(self, intel: IntelInput, pest: dict) -> str:
        return (
            '请对该情报做 4 维价值评分(总分 0-10):\n'
            ' relevance(0-4) urgency(0-3) authority(0-2) scope(0-1)\n'
            f'已知: pest={pest}, 内容={intel.title}\n'
        )

    def _build_summary_prompt(self, intel: IntelInput, pest: dict) -> str:
        return f'请用一句话总结+判断理由+3个标签:\n{intel.title}\n{intel.content[:500]}'

    def _build_action_prompt(self, intel: IntelInput, pest: dict, score: dict) -> str:
        return (
            '请给出 1-3 条具体可执行的战略动作建议:\n'
            f'公司优势: {intel.company_strengths}\n劣势: {intel.company_weaknesses}\n'
            f'情报: {intel.title}'
        )

    # ---- 默认解析(基类提供 mock 友好的解析, 真实 Provider 可覆盖) ----
    def _parse_pest(self, resp: str) -> dict:
        """返回 {pest:'P', ot:'O', level:'H'}; 子类覆盖."""
        raise NotImplementedError

    def _parse_score(self, resp: str) -> dict:
        raise NotImplementedError

    def _parse_summary(self, resp: str):
        raise NotImplementedError

    def _parse_action(self, resp: str) -> str:
        raise NotImplementedError


def get_provider(name: str | None = None) -> BaseLLMProvider:
    """工厂方法 — 根据 settings.LLM_PROVIDER 返回对应实现.

    【强制真实LLM】LLM 不再受全链路真实化总开关 (mode) 拦截—
    无论 mode = real / auto / simulated, 都按 settings.LLM_PROVIDER 走真实
    LLM (DeepSeek/OpenAI), 仅当显式传 name='mock' 或配置 LLM_PROVIDER='mock'
    时才走 Mock. 保证任何场景下点分析/批量分析都能看到真实 LLM
    流式输出.
    """
    from django.conf import settings

    explicit = name is not None
    name = (name or getattr(settings, 'LLM_PROVIDER', 'mock') or 'mock').lower()
    # 运行时配置 (settings 页 LLM TAB) 覆盖 — 仅在未显式指定 name 时生效
    if not explicit:
        try:
            from apps.dashboard.services.runtime_config import llm_effective
            rc_provider = (llm_effective() or {}).get('provider')
            if rc_provider:
                name = str(rc_provider).lower()
        except Exception:
            pass
    if name == 'mock':
        from .mock_provider import MockLLMProvider
        return MockLLMProvider()
    if name in ('deepseek', 'openai', 'openai_compat'):
        # DeepSeek 与 OpenAI Chat Completions 接口兼容, 复用同一个 Provider
        from .deepseek_provider import DeepSeekProvider
        return DeepSeekProvider()
    raise ValueError(f'未实现的 LLM Provider: {name}')
