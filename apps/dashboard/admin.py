"""驾驶舱 admin 注册."""
from django.contrib import admin

from .models import TargetMarket


@admin.register(TargetMarket)
class TargetMarketAdmin(admin.ModelAdmin):
    """目标市场 — 全站市场下拉的唯一数据源, 修改后前端实时生效."""

    list_display = ('priority', 'code', 'name', 'region',
                    'flag_emoji', 'is_active')
    list_display_links = ('code', 'name')
    list_editable = ('priority', 'is_active')
    list_filter = ('is_active', 'region')
    search_fields = ('code', 'name', 'region')
    ordering = ('priority', 'code')
