"""信息源 App 模型 — 信息源注册表与采集任务"""
from django.db import models


class InfoSource(models.Model):
    """信息源注册表 — 描述一个外部信息媒介及其采集策略"""

    SOURCE_TYPE_CHOICES = [
        ('api', '免费API'),
        ('web', '网页爬取'),
        ('rss', 'RSS/Atom'),
        ('social', '社交媒体'),
        ('mixed', '混合'),
    ]

    PRIORITY_CHOICES = [
        ('critical', '🔴 最高'),
        ('high', '🟠 高'),
        ('medium', '🟡 中'),
        ('low', '🟢 低'),
    ]

    DIFFICULTY_CHOICES = [
        (1, '⭐ 极易'),
        (2, '⭐⭐ 容易'),
        (3, '⭐⭐⭐ 中等'),
        (4, '⭐⭐⭐⭐ 困难'),
        (5, '⭐⭐⭐⭐⭐ 极难'),
    ]

    ACCESS_TIER_CHOICES = [
        ('free',     '免费 (无需注册)'),
        ('register', '需注册/登录 (免费)'),
        ('paid',     '付费 API'),
    ]

    name = models.CharField('名称', max_length=200, unique=True)
    category = models.CharField('类别', max_length=80, blank=True)
    official_url = models.URLField('官方网址', max_length=500)
    list_url = models.URLField('信息列表/接口地址', max_length=500, blank=True)

    source_type = models.CharField(
        '类型', max_length=20, choices=SOURCE_TYPE_CHOICES, default='web')
    interface_type = models.CharField('接口类型', max_length=80, blank=True)
    data_format = models.CharField('数据格式', max_length=40, blank=True)

    update_frequency = models.CharField('更新频率', max_length=80, blank=True)
    crawl_method = models.CharField('推荐采集方式', max_length=200, blank=True)
    rate_limit_hint = models.CharField('访问频率建议', max_length=120, blank=True)
    crawl_interval = models.IntegerField('爬取间隔(秒)', default=3600)

    needs_register = models.BooleanField('是否需注册', default=False)
    needs_login = models.BooleanField('是否需登录', default=False)
    is_paid = models.BooleanField('是否付费', default=False)
    needs_custom_spider = models.BooleanField('是否需自编爬虫', default=True)

    difficulty = models.IntegerField(
        '难度', choices=DIFFICULTY_CHOICES, default=2)
    priority = models.CharField(
        '优先级', max_length=20, choices=PRIORITY_CHOICES, default='medium')
    relevance = models.CharField('战略相关度', max_length=120, blank=True)
    notes = models.TextField('备注', blank=True)

    spider_name = models.CharField('对应Spider', max_length=120, blank=True)
    access_tier = models.CharField(
        '访问层级', max_length=20, choices=ACCESS_TIER_CHOICES,
        default='free', db_index=True)

    is_active = models.BooleanField('启用', default=True)
    last_crawled_at = models.DateTimeField('最近抓取时间', null=True, blank=True)
    last_status = models.CharField('最近状态', max_length=20, blank=True)
    last_message = models.TextField('最近消息', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '信息源'
        verbose_name_plural = '信息源'
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['source_type', 'is_active']),
            models.Index(fields=['priority']),
        ]

    def __str__(self):
        return f'[{self.get_priority_display()}] {self.name}'


class CrawlJob(models.Model):
    """爬虫任务执行记录"""

    STATUS_CHOICES = [
        ('pending', '排队中'),
        ('running', '执行中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    ]

    source = models.ForeignKey(
        InfoSource, on_delete=models.CASCADE, related_name='jobs')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    items_fetched = models.IntegerField(default=0)
    items_new = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending')
    error_log = models.TextField(blank=True)
    triggered_by = models.CharField(max_length=40, default='scheduler')

    class Meta:
        verbose_name = '采集任务'
        verbose_name_plural = '采集任务'
        ordering = ['-started_at']
        indexes = [models.Index(fields=['source', '-started_at'])]

    def __str__(self):
        return f'{self.source.name} @ {self.started_at:%Y-%m-%d %H:%M}'
