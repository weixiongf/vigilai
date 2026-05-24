"""项目根 URL 配置"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from config.views import healthz

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('healthz/', healthz, name='healthz'),
    path('healthz', healthz),  # 允许不带尾斜杠
    path('dashboard/', include('apps.dashboard.urls')),
    path('api/sources/', include('apps.sources.urls')),
    path('api/intel/', include('apps.intelligence.urls')),
    path('api/analysis/', include('apps.analysis.urls')),
    path('api/briefings/', include('apps.briefings.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/agents/', include('apps.agents.urls')),
]
