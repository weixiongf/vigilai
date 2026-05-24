"""初始化目标市场种子数据 — 全站市场下拉的唯一数据源.

数据来自 apps/intelligence/management/commands/_simulation_corpus.py
的 TARGET_MARKETS 常量, 一次写入数据库, 后续可在 Django admin 维护.
"""
from django.db import migrations


# code -> (name, region, flag_emoji, priority)
SEED_MARKETS = [
    ('US', '美国',         '北美',     '🇺🇸', 10),
    ('EU', '欧盟',         '欧洲',     '🇪🇺', 20),
    ('UK', '英国',         '欧洲',     '🇬🇧', 30),
    ('JP', '日本',         '东亚',     '🇯🇵', 40),
    ('KR', '韩国',         '东亚',     '🇰🇷', 50),
    ('SG', '新加坡',       '东南亚',   '🇸🇬', 60),
    ('ID', '印度尼西亚',   '东南亚',   '🇮🇩', 70),
    ('TH', '泰国',         '东南亚',   '🇹🇭', 80),
    ('VN', '越南',         '东南亚',   '🇻🇳', 90),
    ('MX', '墨西哥',       '拉美',     '🇲🇽', 100),
    ('BR', '巴西',         '拉美',     '🇧🇷', 110),
    ('AE', '阿联酋',       '中东',     '🇦🇪', 120),
    ('SA', '沙特',         '中东',     '🇸🇦', 130),
    ('AU', '澳大利亚',     '大洋洲',   '🇦🇺', 140),
]


def seed_markets(apps, schema_editor):
    TargetMarket = apps.get_model('dashboard', 'TargetMarket')
    for code, name, region, flag, priority in SEED_MARKETS:
        TargetMarket.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'region': region,
                'flag_emoji': flag,
                'priority': priority,
                'is_active': True,
            },
        )


def unseed_markets(apps, schema_editor):
    TargetMarket = apps.get_model('dashboard', 'TargetMarket')
    TargetMarket.objects.filter(
        code__in=[c for c, *_ in SEED_MARKETS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_markets, unseed_markets),
    ]
