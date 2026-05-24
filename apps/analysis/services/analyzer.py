"""LLM 情报分析器 — 把 RawInfo 喂给 LLM Provider, 把结果回写到 RawInfo."""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction

from apps.analysis.llm.base import IntelInput, get_provider
from apps.intelligence.models import RawInfo


logger = logging.getLogger(__name__)


def _build_input(info: RawInfo) -> IntelInput:
    # 优先读取 config/company_profile.json (settings 页可编辑, 即时生效);
    # 文件缺失时 helper 内部会回落到 settings.COMPANY_STRENGTHS/WEAKNESSES.
    try:
        from apps.dashboard.services.company_profile import load_profile
        profile = load_profile()
        strengths = profile.get('strengths') or []
        weaknesses = profile.get('weaknesses') or []
    except Exception:
        strengths = list(getattr(settings, 'COMPANY_STRENGTHS', []) or [])
        weaknesses = list(getattr(settings, 'COMPANY_WEAKNESSES', []) or [])
    return IntelInput(
        title=info.title,
        content=info.content,
        target_market=info.target_market,
        strategic_dimension=info.strategic_dimension,
        source_name=info.source.name if info.source_id else '',
        company_strengths=strengths,
        company_weaknesses=weaknesses,
    )


def analyze_one(info: RawInfo, save: bool = True, on_token=None,
                on_thinking=None) -> RawInfo:
    """对单条 RawInfo 进行 LLM 分析并(可选)写回.

    on_token: 可选回调 fn(token: str). 传入后启用流式调用 (需 Provider 支持),
    LLM 每返回一段正文 delta 就会同步调用 on_token, 供上层 SSE 透传到前端.
    on_thinking: 可选回调 fn(token: str), 仅接收思考过程片段.
    """
    provider = get_provider()
    result = provider.analyze_intel(_build_input(info), on_token=on_token,
                                    on_thinking=on_thinking)

    info.pest_type = result.pest_type
    info.opportunity_or_threat = result.opportunity_or_threat
    info.impact_level = result.impact_level
    info.impact_type = result.impact_type
    info.severity = result.severity
    info.sentiment = result.sentiment
    info.score_relevance = result.score_relevance
    info.score_urgency = result.score_urgency
    info.score_authority = result.score_authority
    info.score_scope = result.score_scope
    info.impact_score = result.impact_score
    if not info.summary:
        info.summary = result.summary
    info.impact_rationale = result.rationale
    info.action_advice = result.action_advice
    if not info.tags:
        info.tags = result.tags
    info.analysis_chain = result.chain
    info.is_processed = True

    if save:
        info.save(update_fields=[
            'pest_type', 'opportunity_or_threat', 'impact_level',
            'impact_type', 'severity', 'sentiment',
            'score_relevance', 'score_urgency', 'score_authority', 'score_scope',
            'impact_score', 'summary', 'impact_rationale', 'action_advice',
            'tags', 'analysis_chain', 'is_processed',
        ])
    return info


def analyze_batch(queryset=None, limit: int = 0) -> int:
    """批量分析未处理情报, 返回成功数."""
    qs = queryset if queryset is not None else RawInfo.objects.filter(is_processed=False)

    # 切片后的 QuerySet 不能再 .iterator(), 改为先取 id 再二次查询
    if limit:
        ids = list(qs.values_list('id', flat=True)[:limit])
        iterable = RawInfo.objects.filter(id__in=ids).iterator(chunk_size=100)
    else:
        iterable = qs.iterator(chunk_size=100)

    success = 0
    fail = 0
    for info in iterable:
        try:
            with transaction.atomic():
                analyze_one(info, save=True)
            success += 1
        except Exception as exc:
            fail += 1
            logger.exception('analyze fail id=%s: %s', info.id, exc)
    return success
