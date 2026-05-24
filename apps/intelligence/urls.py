"""情报 API URL"""
from django.urls import path

from . import views

app_name = 'intelligence'
urlpatterns = [
    path('', views.intel_list, name='list'),
    path('kpi/', views.intel_kpi, name='kpi'),
    path('timeline/', views.intel_timeline, name='timeline'),
    path('batch-analyze/', views.intel_batch_analyze, name='batch_analyze'),
    path('<int:pk>/', views.intel_detail, name='detail'),
    path('<int:pk>/feedback/', views.intel_feedback, name='feedback'),
    path('<int:pk>/analyze/', views.intel_trigger_analyze, name='trigger_analyze'),
    path('<int:pk>/analyze-stream/', views.intel_analyze_stream, name='analyze_stream'),
]
