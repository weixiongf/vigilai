"""信息源 API URL"""
from django.urls import path

from . import views

app_name = 'sources'
urlpatterns = [
    path('', views.source_list, name='list'),
    path('create/', views.source_create, name='create'),
    path('overview/', views.sources_overview, name='overview'),
    path('simulation-mode/', views.simulation_mode, name='simulation_mode'),
    path('tier-switch/', views.tier_switch_view, name='tier_switch'),
    path('jobs/', views.jobs_recent, name='jobs'),
    path('jobs/<int:pk>/', views.job_detail, name='job_detail'),
    path('<int:pk>/', views.source_detail, name='detail'),
    path('<int:pk>/trigger/', views.source_trigger, name='trigger'),
    path('<int:pk>/toggle/', views.source_toggle, name='toggle'),
    path('<int:pk>/delete/', views.source_delete, name='delete'),
]
