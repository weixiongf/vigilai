"""战略简报 App Celery 任务 — 实时/单市场/每日/每周/每月生成简报.

策略:
  - 实时发送: 开启后自动关闭所有定时开关(单市场/日/周/月), 采集到新数据即刻推送;
  - 各定时任务只需检查自身 enabled 字段, 互斥逻辑由配置保存时保证;
  - 单市场简报: 每天 09:00, 按市场分别生成, 仅有匹配级别的数据时才发送;
  - 日报: 每天早上 08:00, 生成 1 份 global 综合简报(汇总所有市场);
  - 周报: 每周日下午 14:00, 生成 1 份 global 周报, 内含各市场分区子章节;
  - 月报: 每月最后一天下午 14:00, 生成 1 份 global 月报, 全月汇总.
"""
import logging
import calendar
from datetime import date, timedelta

from celery import shared_task
from django.db.models import Count

from apps.briefings.services.generator import generate_briefing
from apps.intelligence.models import RawInfo


logger = logging.getLogger(__name__)


def _resolve_markets(top_n: int = 5) -> list:
    """返回情报量 Top N 的市场列表(不含 global)."""
    top = (RawInfo.objects.filter(is_processed=True)
           .values('target_market')
           .annotate(c=Count('id'))
           .order_by('-c')[:top_n])
    return [r['target_market'] for r in top if r['target_market']]


@shared_task(name='apps.briefings.tasks.generate_daily_briefing')
def generate_daily_briefing() -> dict:
    """每天 08:00 生成 1 份 global 日报(汇总所有市场情报).

    读取 briefing_schedule.json 判断是否启用; 若禁用或实时模式已开启则跳过.
    """
    from apps.dashboard.services.briefing_schedule import load_schedule
    sched = load_schedule()
    if not sched['daily']['enabled']:
        logger.info('[briefing] 日报已禁用(或实时模式覆盖), 跳过')
        return {'period': 'daily', 'skipped': True}
    end = date.today()
    b = generate_briefing(period_type='daily',
                          period_start=end, period_end=end,
                          target_market='global', auto_pest_swot=True)
    _push_notify({
        'type': 'briefing.published',
        'period_type': 'daily',
        'briefing_id': b.id,
        'title': b.title,
        'market': 'global',
    })
    from apps.notifications.tasks import dispatch_briefing
    dispatch_briefing.delay(b.id)
    return {'period': 'daily', 'count': 1, 'briefing_ids': [b.id]}


@shared_task(name='apps.briefings.tasks.generate_weekly_briefing')
def generate_weekly_briefing() -> dict:
    """每周日 14:00 生成 1 份 global 周报(含各市场分区子章节).

    读取 briefing_schedule.json 判断是否启用; 若禁用或实时模式已开启则跳过.
    """
    from apps.dashboard.services.briefing_schedule import load_schedule
    sched = load_schedule()
    if not sched['weekly']['enabled']:
        logger.info('[briefing] 周报已禁用(或实时模式覆盖), 跳过')
        return {'period': 'weekly', 'skipped': True}
    end = date.today()
    start = end - timedelta(days=6)
    markets = _resolve_markets()
    b = generate_briefing(period_type='weekly',
                          period_start=start, period_end=end,
                          target_market='global', auto_pest_swot=True,
                          market_breakdown=markets)
    _push_notify({
        'type': 'briefing.published',
        'period_type': 'weekly',
        'briefing_id': b.id,
        'title': b.title,
        'market': 'global',
    })
    from apps.notifications.tasks import dispatch_briefing
    dispatch_briefing.delay(b.id)
    return {'period': 'weekly', 'count': 1, 'briefing_ids': [b.id]}


@shared_task(name='apps.briefings.tasks.generate_briefing_for_market')
def generate_briefing_for_market(target_market: str = 'global',
                                 period_type: str = 'daily') -> dict:
    """按需生成单市场简报.

    策略纠偏: 周报强制 global 并填充市场分区子章节,
    避免手动触发产生单市场周报冗余.
    """
    end = date.today()
    if period_type == 'daily':
        start = end
    elif period_type == 'weekly':
        start = end - timedelta(days=6)
    else:
        start = end - timedelta(days=29)

    # 周报: 强制 global + 市场分区
    market_breakdown = None
    if period_type == 'weekly':
        target_market = 'global'
        market_breakdown = _resolve_markets()

    b = generate_briefing(period_type=period_type,
                          period_start=start, period_end=end,
                          target_market=target_market,
                          auto_pest_swot=True,
                          market_breakdown=market_breakdown)

    # 推送 WebSocket 通知 + 自动分发(飞书+邮件)
    _push_notify({
        'type': 'briefing.published',
        'period_type': period_type,
        'briefing_id': b.id,
        'title': b.title,
        'market': target_market,
    })
    from apps.notifications.tasks import dispatch_briefing
    dispatch_briefing.delay(b.id)

    return {'briefing_id': b.id, 'title': b.title, 'market': target_market}


@shared_task(name='apps.briefings.tasks.generate_monthly_briefing')
def generate_monthly_briefing() -> dict:
    """每月最后一天 14:00 生成 1 份 global 月报(全月汇总).

    读取 briefing_schedule.json 判断是否启用; 若禁用或实时模式已开启则跳过.
    仅在当天确实是本月最后一天时才执行.
    """
    from apps.dashboard.services.briefing_schedule import load_schedule
    sched = load_schedule()
    if not sched['monthly']['enabled']:
        logger.info('[briefing] 月报已禁用(或实时模式覆盖), 跳过')
        return {'period': 'monthly', 'skipped': True}

    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    if today.day != last_day:
        logger.info('[briefing] 今天非月末(%d号), 跳过月报', today.day)
        return {'period': 'monthly', 'skipped': True, 'reason': 'not_last_day'}

    start = today.replace(day=1)
    end = today
    markets = _resolve_markets()
    b = generate_briefing(period_type='monthly',
                          period_start=start, period_end=end,
                          target_market='global', auto_pest_swot=True,
                          market_breakdown=markets)
    _push_notify({
        'type': 'briefing.published',
        'period_type': 'monthly',
        'briefing_id': b.id,
        'title': b.title,
        'market': 'global',
    })
    from apps.notifications.tasks import dispatch_briefing
    dispatch_briefing.delay(b.id)
    return {'period': 'monthly', 'count': 1, 'briefing_ids': [b.id]}


def _push_notify(payload: dict):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            'notifications.broadcast',
            {'type': 'notify', 'payload': payload},
        )
    except Exception as exc:
        logger.warning('push notify failed: %s', exc)


# ==================== 单市场简报 ====================

def _filter_ot(level: str):
    """根据级别过滤 opportunity_or_threat 字段."""
    if level == 'threat':
        return {'opportunity_or_threat': 'threat'}
    elif level == 'opportunity':
        return {'opportunity_or_threat': 'opportunity'}
    return {}  # 'all' 不过滤


@shared_task(name='apps.briefings.tasks.generate_market_briefings')
def generate_market_briefings() -> dict:
    """每天 09:00 按市场分别生成单市场简报.

    规则:
      - 读取 briefing_schedule.json 中 market_briefing 配置;
      - 若实时模式已开启则跳过 (已由 realtime 覆盖);
      - 若 market_briefing.enabled=false 则跳过;
      - 根据 level (全部/威胁/机会) 过滤当日情报;
      - 每个有数据的市场单独生成一份简报并分发.
    """
    from apps.dashboard.services.briefing_schedule import load_schedule
    sched = load_schedule()

    mb = sched.get('market_briefing', {})
    if not mb.get('enabled', False):
        logger.info('[briefing] 单市场简报已禁用(或实时模式覆盖), 跳过')
        return {'period': 'market', 'skipped': True}

    level = mb.get('level', 'all')
    today = date.today()
    ot_filter = _filter_ot(level)

    # 查找当日有匹配数据的市场
    qs = RawInfo.objects.filter(
        is_processed=True,
        fetched_at__date=today,
        **ot_filter,
    ).values('target_market').annotate(c=Count('id')).filter(c__gt=0)

    markets = [r['target_market'] for r in qs
               if r['target_market'] and r['target_market'] != 'global']

    if not markets:
        logger.info('[briefing] 当日无匹配市场数据(level=%s), 跳过单市场简报', level)
        return {'period': 'market', 'skipped': True, 'reason': 'no_data'}

    briefing_ids = []
    for market in markets:
        try:
            b = generate_briefing(
                period_type='daily',
                period_start=today, period_end=today,
                target_market=market, auto_pest_swot=False)
            briefing_ids.append(b.id)
            _push_notify({
                'type': 'briefing.published',
                'period_type': 'market_daily',
                'briefing_id': b.id,
                'title': b.title,
                'market': market,
            })
            from apps.notifications.tasks import dispatch_briefing
            dispatch_briefing.delay(b.id)
        except Exception as exc:
            logger.exception('[briefing] 单市场简报生成失败 market=%s: %s', market, exc)

    logger.info('[briefing] 单市场简报已生成 %d 份 (level=%s)', len(briefing_ids), level)
    return {'period': 'market', 'count': len(briefing_ids),
            'markets': markets, 'briefing_ids': briefing_ids}
