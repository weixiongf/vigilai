"""数据源访问层级开关 — settings 页"数据源分档启用"持久化服务.

按 InfoSource.access_tier (free / register / paid) 三档独立控制是否调度采集.

设计原则:
- 默认仅 free 档启用, register / paid 默认关闭, 避免误触发未实现采集器.
- 状态 7 天有效期, 过期后回落到默认值 (与 fallback.py 的 _MODE_TTL 一致).
- 任务调度与单源采集双重过滤: crawl_active_sources 不调度禁用档,
  crawl_one_source 入口再次校验, 确保手动 trigger 也受控.
"""
from __future__ import annotations

import logging
from typing import Dict

from django.core.cache import cache

logger = logging.getLogger(__name__)

# 三档默认值 — 仅 free 默认启用
TIER_DEFAULTS: Dict[str, bool] = {
    'free': True,
    'register': False,
    'paid': False,
}

VALID_TIERS = tuple(TIER_DEFAULTS.keys())

_KEY_TPL = 'sr:tier_enabled:{tier}'
_TTL = 7 * 24 * 3600


def get_tier_enabled(tier: str) -> bool:
    """读取该档启用状态 — 优先 cache, 回落默认值."""
    if tier not in TIER_DEFAULTS:
        return False
    cached = cache.get(_KEY_TPL.format(tier=tier))
    if cached is None:
        return TIER_DEFAULTS[tier]
    return bool(cached)


def set_tier_enabled(tier: str, enabled: bool) -> None:
    """切换该档启用状态, 持久化到 cache."""
    if tier not in TIER_DEFAULTS:
        raise ValueError(f'invalid tier: {tier}, expect one of {VALID_TIERS}')
    cache.set(_KEY_TPL.format(tier=tier), bool(enabled), _TTL)
    logger.info('[tier_switch] %s -> %s', tier, enabled)


def is_source_allowed(source) -> bool:
    """判定该信息源是否被允许调度采集."""
    return get_tier_enabled(getattr(source, 'access_tier', 'free') or 'free')


def snapshot() -> Dict[str, bool]:
    """三档状态快照, 供任务过滤 + UI 渲染."""
    return {tier: get_tier_enabled(tier) for tier in VALID_TIERS}


def enabled_tiers() -> list:
    """返回当前启用的档列表 — 供 ORM filter(access_tier__in=...) 使用."""
    return [tier for tier, enabled in snapshot().items() if enabled]
