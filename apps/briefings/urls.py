"""战略简报 API URL"""
from django.urls import path

from . import views

app_name = 'briefings'
urlpatterns = [
    path('', views.briefing_list, name='list'),
    path('trigger/', views.briefing_trigger, name='trigger'),
    path('pest-swot/', views.pest_swot_latest, name='pest_swot'),
    path('preview/', views.briefing_preview, name='preview'),
    path('<int:pk>/', views.briefing_detail, name='detail'),
    path('<int:pk>/metrics/', views.briefing_metrics, name='metrics'),
    path('<int:pk>/render/', views.briefing_render, name='render'),
    path('<int:pk>/dispatch/', views.briefing_dispatch, name='dispatch'),
]
