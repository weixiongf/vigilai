# -*- coding: utf-8 -*-
"""Agents App 配置 — 多智能体协作中心."""
from django.apps import AppConfig


class AgentsConfig(AppConfig):
    """多智能体协作 App."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.agents'
    verbose_name = '多智能体协作'
