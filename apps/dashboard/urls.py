"""驾驶舱前端路由"""
from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    # 01 情报蓝图
    path('', views.cockpit, name='cockpit'),
    # 02 今日简报
    path('briefing/', views.briefing_page, name='briefing'),
    # 03 市场动态 (含跨市场时间线)
    path('feed/', views.feed_page, name='feed'),
    path('timeline/', views.timeline_page, name='timeline'),
    # 04 采集调度
    path('scheduling/', views.scheduling_page, name='scheduling'),
    # 05 信息源配置
    path('sources/', views.sources_page, name='sources'),
    path('sources/new/', views.source_create_page, name='source_create'),
    # 06 通知记录
    path('notifications/', views.notifications_page, name='notifications'),
    # 07 系统配置
    path('settings/', views.settings_page, name='settings'),
    # 08 智能体控制台
    path('agents/', views.agents_page, name='agents'),
    # 配置型 API — 公司战略画像 (文件存储、即时生效)
    path('api/company-profile/', views.company_profile_api,
         name='company_profile_api'),
    # 配置型 API — 运行时 LLM / 邮箱 / 短信 (数据库存储、覆盖 .env)
    path('api/runtime-config/<str:kind>/', views.runtime_config_api,
         name='runtime_config_api'),
    # 目标市场 — 全站唯一数据源, 前端下拉动态填充
    path('api/markets/', views.markets_api, name='markets_api'),
    # 配置型 API — 简报调度 (日报/周报/月报 开关与发送规则)
    path('api/briefing-schedule/', views.briefing_schedule_api,
         name='briefing_schedule_api'),
]
