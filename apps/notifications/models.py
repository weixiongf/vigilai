"""通知 App 模型 — 通知模板、通知记录"""
from django.db import models


class NotificationTemplate(models.Model):
    """通知模板 — 飞书 / 邮件 / WebSocket 通用模板"""

    CHANNEL_CHOICES = [
        ('feishu', '飞书 Webhook'),
        ('email', '邮件'),
        ('websocket', '驾驶舱推送'),
        ('sms', '短信'),
    ]

    EVENT_CHOICES = [
        ('high_impact_alert', '高影响情报告警'),
        ('daily_briefing', '每日战略简报'),
        ('weekly_briefing', '每周战略简报'),
        ('crawl_failure', '采集失败告警'),
        ('system', '系统事件'),
    ]

    name = models.CharField('名称', max_length=100, unique=True)
    channel = models.CharField('通道', max_length=20, choices=CHANNEL_CHOICES)
    event_type = models.CharField('事件类型', max_length=40, choices=EVENT_CHOICES)
    subject_tpl = models.CharField('标题模板', max_length=300, blank=True)
    body_tpl = models.TextField('正文模板')
    is_active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '通知模板'
        verbose_name_plural = '通知模板'
        ordering = ['channel', 'event_type']

    def __str__(self):
        return f'[{self.get_channel_display()}] {self.name}'


class NotificationLog(models.Model):
    """通知发送记录"""

    STATUS_CHOICES = [
        ('pending', '待发送'),
        ('sent', '已发送'),
        ('failed', '失败'),
        ('retrying', '重试中'),
    ]

    channel = models.CharField('通道', max_length=20)
    event_type = models.CharField('事件类型', max_length=40)
    recipient = models.CharField('收件人/接收方', max_length=300)
    subject = models.CharField('主题', max_length=300, blank=True)
    body = models.TextField('内容')

    # 引用业务对象（情报/简报）
    ref_model = models.CharField('关联模型', max_length=80, blank=True)
    ref_id = models.IntegerField('关联ID', null=True, blank=True)

    status = models.CharField(
        '状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    response_payload = models.JSONField('返回信息', null=True, blank=True)
    error_message = models.TextField('错误', blank=True)
    retry_count = models.IntegerField('重试次数', default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField('发送时间', null=True, blank=True)

    class Meta:
        verbose_name = '通知记录'
        verbose_name_plural = '通知记录'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['channel', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'[{self.channel}] {self.subject or self.event_type}'


class NotificationRecipient(models.Model):
    """通知收件人配置"""

    name = models.CharField('姓名', max_length=80)
    feishu_webhook = models.CharField('飞书 Webhook', max_length=500, blank=True)
    email = models.EmailField('邮箱', blank=True)
    role = models.CharField('角色', max_length=80, blank=True)
    subscribe_high_impact = models.BooleanField('订阅高影响告警', default=True)
    subscribe_opportunity = models.BooleanField('订阅机会推送', default=True)
    subscribe_daily = models.BooleanField('订阅日报', default=True)
    subscribe_weekly = models.BooleanField('订阅周报', default=True)
    subscribe_monthly = models.BooleanField('订阅月报', default=True)
    is_active = models.BooleanField('启用', default=True)

    class Meta:
        verbose_name = '通知收件人'
        verbose_name_plural = '通知收件人'

    def __str__(self):
        return f'{self.name} ({self.role})'
