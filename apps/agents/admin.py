# -*- coding: utf-8 -*-
"""Agents Admin 注册."""
from django.contrib import admin

from .models import AgentMessageLog


@admin.register(AgentMessageLog)
class AgentMessageLogAdmin(admin.ModelAdmin):
    """A2A 消息流水管理后台."""

    list_display = ('id', 'trace_id', 'msg_type', 'sender', 'receiver',
                    'status', 'created_at')
    list_filter = ('status', 'msg_type', 'sender', 'receiver')
    search_fields = ('trace_id', 'msg_id', 'msg_type')
    readonly_fields = ('trace_id', 'msg_id', 'created_at', 'finished_at')
