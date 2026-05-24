"""降级 & 仿真切换服务 — 全链路真实化总开关.

提供三种全局模式 (DATA_SOURCE_MODE):
- ``auto``      : 优先真实采集; 真实失败 >= CRAWLER_FAILURE_THRESHOLD 自动转仿真.
- ``simulated`` : 强制仿真 (任何环境都能稳定演示, 简报永不为空).
- ``real``      : 强制真实, 失败不兜底 (用于压测真实链路).

【全链路真实化语义】
is_real_mode() == True (mode == 'real') → 采集 + LLM分析 + 邮件 + 飞书 全部走真实通道;
is_real_mode() == False (auto / simulated) → 采集仿真, LLM 强制 Mock,
  邮件落到 tmp/sent_emails 文件后端, 飞书 webhook 跳过实际 HTTP 只记日志.

关键 API:
- get_mode() / set_mode(mode) : 全局开关读写, 持久化到 cache.
- is_real_mode() : 是否处于 "强制真实" 总开关状态 (供 LLM/邮件/飞书读取).
- record_failure(source) / reset_failure(source) / failure_count(source)
- should_use_simulation(source) : 综合 mode + 失败计数判定本次任务走仿真.
- run_simulation(source, count) : 直接调用模板生成 N 条仿真 RawInfo.
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

VALID_MODES = ('auto', 'simulated', 'real')

_MODE_CACHE_KEY = 'sr:data_source_mode'
_FAIL_KEY_TPL = 'sr:source_fail:{source_id}'
_FAIL_TTL = 24 * 3600  # 失败计数 24h 过期
_MODE_TTL = 7 * 24 * 3600


def get_mode() -> str:
    """读取当前全局数据源模式 — 优先 cache, 回落 settings."""
    cached = cache.get(_MODE_CACHE_KEY)
    if cached in VALID_MODES:
        return cached
    fallback = getattr(settings, 'DATA_SOURCE_MODE', 'auto')
    if fallback not in VALID_MODES:
        fallback = 'auto'
    return fallback


def set_mode(mode: str) -> str:
    """切换全局数据源模式, 同步写入 cache."""
    if mode not in VALID_MODES:
        raise ValueError(f'invalid mode: {mode}, expect one of {VALID_MODES}')
    cache.set(_MODE_CACHE_KEY, mode, _MODE_TTL)
    logger.info('[fallback] data source mode -> %s', mode)
    return mode


def is_real_mode() -> bool:
    """全链路真实化总开关 — 仅在 mode == 'real' 时走真实通道.

    被 LLM 分析 (apps.analysis.llm.base.get_provider) /
    邮件发送 (apps.notifications.services.email) /
    飞书推送 (apps.notifications.services.feishu) 读取,
    以避免仿真演示场景下意外调用真实 API / 发出真实邮件.
    """
    return get_mode() == 'real'


def failure_count(source) -> int:
    """读取该信息源最近的连续失败计数 (cache 持久 24h)."""
    return int(cache.get(_FAIL_KEY_TPL.format(source_id=source.id)) or 0)


def record_failure(source, error: str = '') -> int:
    """累加该信息源失败计数, 同步写入 InfoSource.last_status / last_message."""
    key = _FAIL_KEY_TPL.format(source_id=source.id)
    new_val = (cache.get(key) or 0) + 1
    cache.set(key, new_val, _FAIL_TTL)
    try:
        source.last_status = 'failed'
        source.last_message = (error or '采集失败')[:240]
        source.save(update_fields=['last_status', 'last_message', 'updated_at'])
    except Exception:
        pass
    logger.warning('[fallback] source=%s consecutive_failures=%d', source.name, new_val)
    return new_val


def reset_failure(source) -> None:
    """重置该信息源连续失败计数."""
    cache.delete(_FAIL_KEY_TPL.format(source_id=source.id))


def should_use_simulation(source) -> bool:
    """综合全局模式 + 失败计数, 判定本次采集是否走仿真."""
    mode = get_mode()
    if mode == 'simulated':
        return True
    if mode == 'real':
        return False
    threshold = getattr(settings, 'CRAWLER_FAILURE_THRESHOLD', 3)
    return failure_count(source) >= threshold


def run_simulation(source, count: Optional[int] = None) -> int:
    """生成仿真 RawInfo (不走真实网络). 返回新建条数.

    复用 seed_intel 模板, 始终能稳定产出, 是黑客松"永不空场"的兜底.
    """
    from apps.intelligence.management.commands.seed_intel import _build_record
    from apps.intelligence.management.commands._simulation_corpus import (
        TARGET_MARKETS, TEMPLATES,
    )
    from apps.intelligence.models import RawInfo

    if count is None:
        count = max(getattr(settings, 'MIN_SIMULATED_ITEMS', 1),
                    random.randint(1, 3))

    created = 0
    for _ in range(count):
        template = random.choice(TEMPLATES)
        market = random.choice(TARGET_MARKETS)
        payload = _build_record(
            template, market,
            int(timezone.now().timestamp()) + random.randint(0, 99999),
            max_days=1)
        payload['source'] = source
        payload['is_simulated'] = True
        try:
            RawInfo.objects.create(**payload)
            created += 1
        except Exception:
            # title 唯一冲突等 — 忽略
            pass
    return created


def snapshot() -> dict:
    """运维仪表板使用的状态快照 — 当前模式 + 失败汇总."""
    from apps.sources.models import InfoSource

    sources = InfoSource.objects.filter(is_active=True).only(
        'id', 'name', 'category', 'source_type', 'priority',
        'last_status', 'last_message', 'last_crawled_at',
    )
    items = []
    for s in sources:
        cnt = failure_count(s)
        if cnt > 0:
            items.append({
                'source_id': s.id,
                'name': s.name,
                'category': s.category,
                'source_type': s.get_source_type_display(),
                'priority': s.get_priority_display(),
                'consecutive_failures': cnt,
                'last_error': s.last_message or '',
                'last_status': s.last_status or '',
                'last_crawled_at': s.last_crawled_at.isoformat() if s.last_crawled_at else None,
            })
    items.sort(key=lambda x: -x['consecutive_failures'])
    return {
        'mode': get_mode(),
        'threshold': getattr(settings, 'CRAWLER_FAILURE_THRESHOLD', 3),
        'fallback_on_failure': getattr(settings, 'FALLBACK_ON_FAILURE', True),
        'failing_sources': items[:20],
        'failing_count': len(items),
    }
