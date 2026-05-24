"""分析 App 模型 — PEST 汇总、SWOT 矩阵、跨象限策略"""
from django.db import models
from django.contrib.postgres.fields import ArrayField


class PESTSnapshot(models.Model):
    """某个时间窗口内 PEST 四维度情报聚合快照"""

    period_start = models.DateField('窗口起始')
    period_end = models.DateField('窗口结束')
    target_market = models.CharField('目标市场', max_length=60, default='global')

    political_items = models.JSONField('政治法律(P)条目', default=list)
    economic_items = models.JSONField('经济(E)条目', default=list)
    social_items = models.JSONField('社会文化(S)条目', default=list)
    technological_items = models.JSONField('技术(T)条目', default=list)

    political_summary = models.TextField('P 维度洞察', blank=True)
    economic_summary = models.TextField('E 维度洞察', blank=True)
    social_summary = models.TextField('S 维度洞察', blank=True)
    technological_summary = models.TextField('T 维度洞察', blank=True)

    overall_summary = models.TextField('整体宏观环境结论', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'PEST 快照'
        verbose_name_plural = 'PEST 快照'
        ordering = ['-period_end']
        unique_together = [('period_start', 'period_end', 'target_market')]

    def __str__(self):
        return f'PEST {self.target_market} {self.period_start}~{self.period_end}'


class SWOTAnalysis(models.Model):
    """SWOT 分析 — 含 SO/ST/WO/WT 跨象限策略"""

    period_start = models.DateField('窗口起始')
    period_end = models.DateField('窗口结束')
    target_market = models.CharField('目标市场', max_length=60, default='global')

    strengths = models.JSONField('优势 S', default=list)
    weaknesses = models.JSONField('劣势 W', default=list)
    opportunities = models.JSONField('机会 O', default=list)
    threats = models.JSONField('威胁 T', default=list)

    so_strategies = models.TextField('SO 增长策略 (优势×机会)', blank=True)
    st_strategies = models.TextField('ST 防御策略 (优势×威胁)', blank=True)
    wo_strategies = models.TextField('WO 扭转策略 (劣势×机会)', blank=True)
    wt_strategies = models.TextField('WT 规避策略 (劣势×威胁)', blank=True)

    pest_snapshot = models.ForeignKey(
        PESTSnapshot, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='swots')

    overall_recommendation = models.TextField('整体战略建议', blank=True)
    confidence_score = models.FloatField('置信度(0-1)', default=0.7)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'SWOT 分析'
        verbose_name_plural = 'SWOT 分析'
        ordering = ['-period_end']

    def __str__(self):
        return f'SWOT {self.target_market} {self.period_start}~{self.period_end}'


class StrategicTheme(models.Model):
    """战略主题 — 跨多条情报凝结的共性议题"""

    SEVERITY_CHOICES = [('high', '高'), ('medium', '中'), ('low', '低')]
    TREND_CHOICES = [('rising', '上升'), ('steady', '平稳'), ('declining', '减弱')]

    title = models.CharField('主题', max_length=200)
    description = models.TextField('说明')
    target_market = models.CharField('目标市场', max_length=60, blank=True)
    dimension = models.CharField('维度', max_length=20, blank=True)

    related_info_ids = ArrayField(
        models.IntegerField(), default=list, blank=True,
        verbose_name='关联情报ID')

    severity = models.CharField(
        '严重度', max_length=10, choices=SEVERITY_CHOICES, default='medium')
    trend = models.CharField(
        '趋势', max_length=20, choices=TREND_CHOICES, default='steady')

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '战略主题'
        verbose_name_plural = '战略主题'
        ordering = ['-last_updated_at']

    def __str__(self):
        return self.title
