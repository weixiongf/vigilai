"""通知 API URL"""
from django.urls import path

from . import views

app_name = 'notifications'
urlpatterns = [
    path('recipients/', views.recipient_list, name='recipient_list'),
    path('recipients/create/', views.recipient_create, name='recipient_create'),
    path('recipients/<int:pk>/', views.recipient_update_or_delete,
         name='recipient_update_or_delete'),
    path('logs/', views.log_list, name='log_list'),
    path('logs/<int:pk>/resend/', views.log_resend, name='log_resend'),
    path('test/', views.test_send, name='test_send'),
]
