"""简报调度配置 — 文件型读写 helper.

把实时推送 + 日报/周报/月报的开启状态和发送规则持久化到 ``config/briefing_schedule.json``,
每次读取直接 read 文件 (无缓存), 写入即生效, 不依赖数据库.

文件结构示例::

    {
      "realtime": {"enabled": false},
      "market_briefing": {"enabled": true, "level": "all", "hour": 9},
      "daily": {"enabled": true, "hour": 8},
      "weekly": {"enabled": true, "day_of_week": 0, "hour": 14},
      "monthly": {"enabled": true, "day_of_month": -1, "hour": 14},
      "updated_at": "2026-05-23T18:30:00+08:00"
    }

其中:
  - realtime.enabled: 开启后采集器采到新数据即刻 Celery 推送通知, 覆盖所有定时规则
  - market_briefing.level: "all" | "threat" | "opportunity", 仅推送匹配类型的单市场简报
  - day_of_week: 0=周日, 1=周一 ... 6=周六
  - day_of_month: -1 表示每月最后一天; 正数为具体日期(1~28)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

SCHEDULE_PATH: Path = Path(settings.BASE_DIR) / 'config' / 'briefing_schedule.json'

# 默认调度规则
DEFAULTS = {
    'realtime': {'enabled': False},
    'market_briefing': {'enabled': True, 'level': 'all', 'hour': 9},
    'daily': {'enabled': True, 'hour': 8},
    'weekly': {'enabled': True, 'day_of_week': 0, 'hour': 14},
    'monthly': {'enabled': True, 'day_of_month': -1, 'hour': 14},
    'updated_at': None,
}


def load_schedule() -> dict:
    """读取最新调度配置 — 直接读盘, 无缓存; 文件缺失则回落默认值."""
    if not SCHEDULE_PATH.exists():
        return _deep_copy_defaults()
    try:
        data = json.loads(SCHEDULE_PATH.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.warning('[briefing_schedule] read failed, fallback defaults: %s', exc)
        return _deep_copy_defaults()
    # 确保结构完整 (兼容旧文件缺少某些字段)
    result = _deep_copy_defaults()
    for key in ('realtime', 'market_briefing', 'daily', 'weekly', 'monthly'):
        if key in data and isinstance(data[key], dict):
            result[key].update(data[key])
    result['updated_at'] = data.get('updated_at')
    return result


def save_schedule(realtime: dict = None, market_briefing: dict = None,
                  daily: dict = None,
                  weekly: dict = None, monthly: dict = None) -> dict:
    """写入调度配置, 立即生效."""
    current = load_schedule()
    if realtime and isinstance(realtime, dict):
        current['realtime'].update(_sanitize_realtime(realtime))
    if market_briefing and isinstance(market_briefing, dict):
        current['market_briefing'].update(_sanitize_market_briefing(market_briefing))
    if daily and isinstance(daily, dict):
        current['daily'].update(_sanitize_daily(daily))
    if weekly and isinstance(weekly, dict):
        current['weekly'].update(_sanitize_weekly(weekly))
    if monthly and isinstance(monthly, dict):
        current['monthly'].update(_sanitize_monthly(monthly))
    # 互斥规则: 实时开启 → 其他全部关闭
    if current['realtime']['enabled']:
        for key in ('market_briefing', 'daily', 'weekly', 'monthly'):
            current[key]['enabled'] = False

    current['updated_at'] = timezone.now().isoformat(timespec='seconds')

    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info(
        '[briefing_schedule] saved realtime=%s market=%s daily=%s weekly=%s monthly=%s',
        current['realtime']['enabled'],
        current['market_briefing']['enabled'],
        current['daily']['enabled'], current['weekly']['enabled'],
        current['monthly']['enabled'],
    )
    return current


def _deep_copy_defaults() -> dict:
    import copy
    return copy.deepcopy(DEFAULTS)


def _sanitize_realtime(d: dict) -> dict:
    r = {}
    if 'enabled' in d:
        r['enabled'] = bool(d['enabled'])
    return r


VALID_LEVELS = {'all', 'threat', 'opportunity'}


def _sanitize_market_briefing(d: dict) -> dict:
    r = {}
    if 'enabled' in d:
        r['enabled'] = bool(d['enabled'])
    if 'level' in d:
        lv = str(d['level']).strip().lower()
        if lv in VALID_LEVELS:
            r['level'] = lv
    if 'hour' in d:
        r['hour'] = max(0, min(23, int(d['hour'])))
    return r


def _sanitize_daily(d: dict) -> dict:
    r = {}
    if 'enabled' in d:
        r['enabled'] = bool(d['enabled'])
    if 'hour' in d:
        r['hour'] = max(0, min(23, int(d['hour'])))
    return r


def _sanitize_weekly(d: dict) -> dict:
    r = {}
    if 'enabled' in d:
        r['enabled'] = bool(d['enabled'])
    if 'day_of_week' in d:
        r['day_of_week'] = max(0, min(6, int(d['day_of_week'])))
    if 'hour' in d:
        r['hour'] = max(0, min(23, int(d['hour'])))
    return r


def _sanitize_monthly(d: dict) -> dict:
    r = {}
    if 'enabled' in d:
        r['enabled'] = bool(d['enabled'])
    if 'day_of_month' in d:
        dom = int(d['day_of_month'])
        # -1 = 最后一天, 1~28 = 具体日期
        if dom == -1 or (1 <= dom <= 28):
            r['day_of_month'] = dom
    if 'hour' in d:
        r['hour'] = max(0, min(23, int(d['hour'])))
    return r
