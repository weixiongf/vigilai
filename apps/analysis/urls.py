"""分析 API URL"""
from django.urls import path

from . import views

app_name = 'analysis'
urlpatterns = [
    path('pest/', views.pest_list, name='pest_list'),
    path('pest/<int:pk>/', views.pest_detail, name='pest_detail'),
    path('swot/', views.swot_list, name='swot_list'),
    path('swot/<int:pk>/', views.swot_detail, name='swot_detail'),
    path('rebuild/', views.rebuild, name='rebuild'),
]
