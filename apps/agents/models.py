# -*- coding: utf-8 -*-
"""Agents 持久化模型 — A2A 消息追溯日志."""
from django.db import models


class AgentMessageLog(models.Model):
    """A2A 消息流水 — 用于追溯/审计/可视化."""

    STATUS_CHOICES = [
        ('pending', '排队中'),
        ('running', '执行中'),
        ('done', '已完成'),
        ('failed', '失败'),
    ]

    trace_id = models.CharField('链路ID', max_length=32, db_index=True)
    msg_id = models.CharField('消息ID', max_length=32, unique=True)
    msg_type = models.CharField('事件类型', max_length=80)
    sender = models.CharField('发送方节点', max_length=60, blank=True)
    receiver = models.CharField('接收方节点', max_length=60, blank=True)

    payload = models.JSONField('载荷', null=True, blank=True)
    metadata = models.JSONField('元数据', null=True, blank=True)

    status = models.CharField('状态', max_length=20,
                              choices=STATUS_CHOICES, default='pending')
    output = models.JSONField('输出', null=True, blank=True)
    error = models.TextField('错误', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'A2A 消息流水'
        verbose_name_plural = 'A2A 消息流水'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['trace_id', 'created_at']),
            models.Index(fields=['msg_type', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'[{self.trace_id[:8]}] {self.sender}→{self.receiver} {self.msg_type}'
