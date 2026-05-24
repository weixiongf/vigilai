"""公司战略画像配置 — 文件型读写 helper.

把"公司战略画像 / SWOT 固定基线"持久化到 ``config/company_profile.json``,
每次读取直接 read 文件 (无缓存), 写入即生效, 不依赖数据库, 不需要重启服务.

文件结构示例::

    {
      "strengths": ["品牌全球认知度高", ...],
      "weaknesses": ["北美渠道议价能力较弱", ...],
      "updated_at": "2026-05-23T18:30:00+08:00"
    }
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PROFILE_PATH: Path = Path(settings.BASE_DIR) / 'config' / 'company_profile.json'


def _defaults() -> dict:
    """settings.py 中的默认基线 — 文件不存在/损坏时使用."""
    return {
        'strengths': list(getattr(settings, 'COMPANY_STRENGTHS', []) or []),
        'weaknesses': list(getattr(settings, 'COMPANY_WEAKNESSES', []) or []),
        'updated_at': None,
    }


def _normalize_lines(value) -> List[str]:
    """把 list / 多行字符串归一化成已去空的行列表."""
    if value is None:
        return []
    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, (list, tuple)):
        items = [str(x) for x in value]
    else:
        return []
    return [s.strip() for s in items if s and s.strip()]


def load_profile() -> dict:
    """读取最新画像 — 直接读盘, 无缓存; 文件缺失则回落默认值."""
    if not PROFILE_PATH.exists():
        return _defaults()
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.warning('[company_profile] read failed, fallback defaults: %s', exc)
        return _defaults()
    return {
        'strengths': _normalize_lines(data.get('strengths')),
        'weaknesses': _normalize_lines(data.get('weaknesses')),
        'updated_at': data.get('updated_at'),
    }


def save_profile(strengths, weaknesses) -> dict:
    """写入画像配置, 立即生效."""
    payload = {
        'strengths': _normalize_lines(strengths),
        'weaknesses': _normalize_lines(weaknesses),
        'updated_at': timezone.now().isoformat(timespec='seconds'),
    }
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info(
        '[company_profile] saved strengths=%d weaknesses=%d',
        len(payload['strengths']), len(payload['weaknesses']),
    )
    return payload
