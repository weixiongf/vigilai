"""战略简报 App 模型 — 每日/周期战略简报"""
from django.db import models
from django.contrib.postgres.fields import ArrayField


class Briefing(models.Model):
    """战略简报 — 每日/每周/按需生成的多维度情报报告"""

    PERIOD_CHOICES = [
        ('daily', '日报'),
        ('weekly', '周报'),
        ('monthly', '月报'),
        ('adhoc', '临时'),
    ]

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('published', '已发布'),
        ('archived', '已归档'),
    ]

    title = models.CharField('标题', max_length=300)
    period_type = models.CharField(
        '周期', max_length=20, choices=PERIOD_CHOICES, default='daily')
    period_start = models.DateField('窗口起')
    period_end = models.DateField('窗口止')
    target_market = models.CharField('目标市场', max_length=60, default='global')

    # 概览
    executive_summary = models.TextField('行政摘要')
    key_findings = models.JSONField('关键发现', default=list)
    top_opportunities = models.JSONField('Top 机会', default=list)
    top_risks = models.JSONField('Top 风险', default=list)

    # 维度切片摘要
    competition_summary = models.TextField('竞争维度', blank=True)
    product_summary = models.TextField('产品维度', blank=True)
    platform_summary = models.TextField('平台维度', blank=True)
    social_summary = models.TextField('社媒维度', blank=True)
    regulation_summary = models.TextField('法规维度', blank=True)

    # 关联分析
    pest_snapshot_id = models.IntegerField(
        'PEST 快照ID', null=True, blank=True)
    swot_id = models.IntegerField('SWOT ID', null=True, blank=True)

    # 引用情报
    referenced_info_ids = ArrayField(
        models.IntegerField(), default=list, blank=True,
        verbose_name='引用情报ID')

    recommended_actions = models.JSONField('推荐行动项', default=list)

    status = models.CharField(
        '状态', max_length=20, choices=STATUS_CHOICES, default='draft')

    generated_by = models.CharField('生成方式', max_length=40, default='auto')
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = '战略简报'
        verbose_name_plural = '战略简报'
        ordering = ['-period_end', '-created_at']
        indexes = [
            models.Index(fields=['period_type', '-period_end']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'[{self.get_period_type_display()}] {self.title}'


class BriefingSection(models.Model):
    """简报子章节 — 用于驾驶舱页面分块渲染"""

    briefing = models.ForeignKey(
        Briefing, on_delete=models.CASCADE, related_name='sections')
    order = models.IntegerField('序号', default=0)
    section_key = models.CharField('节键', max_length=40)
    title = models.CharField('小标题', max_length=200)
    content = models.TextField('内容')
    chart_payload = models.JSONField('图表数据', null=True, blank=True)

    class Meta:
        verbose_name = '简报章节'
        verbose_name_plural = '简报章节'
        ordering = ['briefing', 'order']

    def __str__(self):
        return f'{self.briefing.title} - {self.title}'
