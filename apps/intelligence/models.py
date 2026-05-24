"""情报 App 模型 — 原始信息、用户反馈"""
from django.db import models
from django.contrib.postgres.fields import ArrayField

from apps.sources.models import InfoSource


class RawInfo(models.Model):
    """原始情报信息 — 所有采集 / 仿真信息的统一主表"""

    DIMENSION_CHOICES = [
        ('competition', '竞争'),
        ('product', '产品'),
        ('platform', '平台'),
        ('social', '社媒'),
        ('regulation', '法规'),
        ('macro', '宏观经济'),
        ('industry', '行业报告'),
        ('other', '其他'),
    ]

    PEST_CHOICES = [
        ('P', '政治法律 P'),
        ('E', '经济 E'),
        ('S', '社会文化 S'),
        ('T', '技术 T'),
    ]

    IMPACT_CHOICES = [
        ('opportunity', '机会'),
        ('risk', '风险'),
        ('watch', '需关注'),
        ('neutral', '中性'),
    ]

    SEVERITY_CHOICES = [
        ('high', '高'),
        ('medium', '中'),
        ('low', '低'),
    ]

    SENTIMENT_CHOICES = [
        ('positive', '正面'),
        ('negative', '负面'),
        ('neutral', '中性'),
    ]

    LANGUAGE_CHOICES = [
        ('zh', '中文'),
        ('en', '英文'),
        ('multi', '多语言'),
    ]

    source = models.ForeignKey(
        InfoSource, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='infos')

    title = models.CharField('标题', max_length=500)
    content = models.TextField('内容')
    summary = models.TextField('摘要', blank=True)
    url = models.URLField('原文链接', max_length=600, unique=True)
    reference_quote = models.TextField('原文关键引述', blank=True)

    language = models.CharField(
        '语言', max_length=10, choices=LANGUAGE_CHOICES, default='zh')
    raw_json = models.JSONField('原始JSON', null=True, blank=True)

    published_at = models.DateTimeField('发布时间')
    fetched_at = models.DateTimeField('采集时间', auto_now_add=True)

    # 战略分析字段
    strategic_dimension = models.CharField(
        '战略维度', max_length=20, choices=DIMENSION_CHOICES, blank=True)
    target_market = models.CharField('目标市场', max_length=60, blank=True)
    country = models.CharField('国家', max_length=60, blank=True)

    impact_type = models.CharField(
        '影响类型', max_length=20, choices=IMPACT_CHOICES, blank=True)
    severity = models.CharField(
        '严重等级', max_length=10, choices=SEVERITY_CHOICES, blank=True)
    impact_score = models.FloatField('影响分数(0-10)', null=True, blank=True)
    sentiment = models.CharField(
        '情感倾向', max_length=20, choices=SENTIMENT_CHOICES, blank=True)

    # PEST 字段
    pest_type = models.CharField(
        'PEST分类', max_length=2, choices=PEST_CHOICES, blank=True)
    opportunity_or_threat = models.CharField(
        '机会/威胁', max_length=1,
        choices=[('O', '机会'), ('T', '威胁')], blank=True)
    impact_level = models.CharField(
        '影响程度', max_length=1,
        choices=[('H', '高'), ('M', '中'), ('L', '低')], blank=True)
    impact_rationale = models.TextField('LLM判断理由', blank=True)

    # 价值评分明细
    score_relevance = models.FloatField('业务相关度(0-4)', null=True, blank=True)
    score_urgency = models.FloatField('时效紧迫度(0-3)', null=True, blank=True)
    score_authority = models.FloatField('信息权威性(0-2)', null=True, blank=True)
    score_scope = models.FloatField('影响规模(0-1)', null=True, blank=True)

    affected_entities = ArrayField(
        models.CharField(max_length=80), default=list,
        blank=True, verbose_name='涉及实体')
    tags = ArrayField(
        models.CharField(max_length=60), default=list,
        blank=True, verbose_name='标签')

    is_simulated = models.BooleanField('是否仿真数据', default=False)
    is_processed = models.BooleanField('是否已LLM分析', default=False)

    action_advice = models.TextField('行动建议', blank=True)
    analysis_chain = models.JSONField('LLM分析链', null=True, blank=True)

    class Meta:
        verbose_name = '原始情报'
        verbose_name_plural = '原始情报'
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['-published_at']),
            models.Index(fields=['strategic_dimension', '-published_at']),
            models.Index(fields=['target_market', '-published_at']),
            models.Index(fields=['impact_type', '-impact_score']),
            models.Index(fields=['pest_type']),
            models.Index(fields=['is_processed']),
        ]

    def __str__(self):
        return f'[{self.target_market or "未分类"}] {self.title[:50]}'

    @property
    def value_grade(self) -> str:
        score = self.impact_score or 0
        if score >= 8:
            return 'critical'
        if score >= 5:
            return 'medium'
        if score >= 3:
            return 'low'
        return 'noise'


class UserFeedback(models.Model):
    """人机协同反馈 — 管理者对情报判断的修正与确认"""

    ACTION_CHOICES = [
        ('confirmed', '确认'),
        ('corrected', '修正'),
        ('ignored', '忽略'),
    ]

    raw_info = models.ForeignKey(
        RawInfo, on_delete=models.CASCADE, related_name='feedbacks')
    action = models.CharField('动作', max_length=20, choices=ACTION_CHOICES)
    correction_note = models.TextField('修正说明', blank=True)
    created_by = models.CharField('提交人', max_length=80, default='anonymous')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '反馈'
        verbose_name_plural = '反馈'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_action_display()} - {self.raw_info.title[:30]}'
