"""项目顶层包"""
from .celery import app as celery_app

__all__ = ('celery_app',)
