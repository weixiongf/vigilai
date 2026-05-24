# -*- coding: utf-8 -*-
"""agents App URL 路由"""
from django.urls import path

from . import views

app_name = 'agents'

urlpatterns = [
    path('logs/', views.log_list, name='log_list'),
    path('logs/<str:trace_id>/', views.trace_detail, name='trace_detail'),
    path('nodes/', views.node_status, name='node_status'),
    path('run/', views.run_pipeline, name='run_pipeline'),
]
