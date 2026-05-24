"""目标市场数据访问层 — 全站市场列表唯一数据源.

读取顺序:
  1. 数据库 TargetMarket(is_active=True) , 按 priority/code 排序
  2. 数据库为空时回退到 apps.intelligence.management.commands
     ._simulation_corpus.TARGET_MARKETS, 避免冷启动时下拉为空.

调用方:
  - 后端 API: apps.dashboard.views.markets_api
  - 数据迁移 / 初始化命令
"""
from typing import Dict, List


def _fallback_from_corpus() -> List[Dict]:
    """从仿真语料库读取保底市场列表."""
    try:
        from apps.intelligence.management.commands._simulation_corpus import (
            TARGET_MARKETS,
        )
    except Exception:
        return []
    return [
        {
            'code': m['code'],
            'name': m['name'],
            'region': m.get('region', ''),
            'flag_emoji': m.get('flag', ''),
        }
        for m in TARGET_MARKETS
    ]


def list_active_markets() -> List[Dict]:
    """返回启用市场列表 — [{code, name, region, flag_emoji}, ...].

    数据库为空时回退到仿真常量, 保证前端下拉始终有可选项.
    """
    from apps.dashboard.models import TargetMarket

    qs = TargetMarket.objects.filter(is_active=True).order_by('priority', 'code')
    items = [
        {
            'code': m.code,
            'name': m.name,
            'region': m.region,
            'flag_emoji': m.flag_emoji,
        }
        for m in qs
    ]
    return items or _fallback_from_corpus()
