"""驾驶舱 App 模型 — 系统设置、公告、用户偏好"""
from django.db import models


class SystemSetting(models.Model):
    """系统级配置 — 公司画像、目标市场、阈值等"""

    key = models.CharField('键', max_length=100, unique=True)
    value = models.JSONField('值')
    description = models.CharField('说明', max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '系统设置'
        verbose_name_plural = '系统设置'
        ordering = ['key']

    def __str__(self):
        return self.key


class Announcement(models.Model):
    """系统公告 / 操作日志卡片"""

    LEVEL_CHOICES = [
        ('info', '信息'),
        ('warning', '警告'),
        ('critical', '关键'),
        ('success', '成功'),
    ]

    title = models.CharField('标题', max_length=200)
    body = models.TextField('正文', blank=True)
    level = models.CharField(
        '级别', max_length=20, choices=LEVEL_CHOICES, default='info')
    icon = models.CharField('图标', max_length=20, blank=True)
    is_pinned = models.BooleanField('置顶', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '公告'
        verbose_name_plural = '公告'
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f'[{self.get_level_display()}] {self.title}'


class TargetMarket(models.Model):
    """目标市场画像 — 用于驾驶舱地图、SWOT 渲染"""

    code = models.CharField('代码', max_length=20, unique=True)
    name = models.CharField('名称', max_length=80)
    region = models.CharField('区域', max_length=40, blank=True)
    description = models.TextField('画像', blank=True)
    is_active = models.BooleanField('启用', default=True)
    priority = models.IntegerField('优先级', default=10)
    flag_emoji = models.CharField('国旗', max_length=10, blank=True)

    class Meta:
        verbose_name = '目标市场'
        verbose_name_plural = '目标市场'
        ordering = ['priority', 'code']

    def __str__(self):
        return f'{self.flag_emoji} {self.name}'
