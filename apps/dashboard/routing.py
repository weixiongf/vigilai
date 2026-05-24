"""Channels WebSocket 路由 — 驾驶舱 + 通知 + 单情报订阅."""
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/dashboard/$', consumers.DashboardConsumer.as_asgi()),
    re_path(r'^ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'^ws/intel/(?P<info_id>\d+)/$', consumers.IntelDetailConsumer.as_asgi()),
]
