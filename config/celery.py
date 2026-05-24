"""Celery 入口配置 — 定义 Celery app + Beat 周期任务调度."""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('strategic_radar')
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现 apps.<app>/tasks.py
app.autodiscover_tasks()


# Celery Beat 周期任务调度表
app.conf.beat_schedule = {
    # 每 30 分钟触发一次主动采集
    'crawl-active-sources-every-30min': {
        'task': 'apps.sources.tasks.crawl_active_sources',
        'schedule': 30 * 60.0,
    },
    # 每 10 分钟把新增 RawInfo 推入 LLM 分析队列
    'analyze-pending-intel-every-10min': {
        'task': 'apps.intelligence.tasks.analyze_pending_intel',
        'schedule': 10 * 60.0,
    },
    # 每 15 分钟扫描高影响情报并推送告警
    'scan-high-impact-every-15min': {
        'task': 'apps.notifications.tasks.scan_and_alert_high_impact',
        'schedule': 15 * 60.0,
    },
    # 每天 08:00 生成日报
    'generate-daily-briefing': {
        'task': 'apps.briefings.tasks.generate_daily_briefing',
        'schedule': crontab(hour=8, minute=0),
    },
    # 每天 09:00 生成单市场简报 (仅有匹配数据时才发送)
    'generate-market-briefings': {
        'task': 'apps.briefings.tasks.generate_market_briefings',
        'schedule': crontab(hour=9, minute=0),
    },
    # 每周日 14:00 生成周报
    'generate-weekly-briefing': {
        'task': 'apps.briefings.tasks.generate_weekly_briefing',
        'schedule': crontab(hour=14, minute=0, day_of_week=0),
    },
    # 每月最后一天 14:00 生成月报
    'generate-monthly-briefing': {
        'task': 'apps.briefings.tasks.generate_monthly_briefing',
        'schedule': crontab(hour=14, minute=0, day_of_month=28),
    },
    # 每天 00:30 重新计算 PEST + SWOT
    'rebuild-pest-swot-daily': {
        'task': 'apps.analysis.tasks.rebuild_pest_swot',
        'schedule': crontab(hour=0, minute=30),
    },
    # 每 1 分钟拣出 pending/retrying 的 NotificationLog 重发
    'process-pending-notifications-every-1min': {
        'task': 'apps.notifications.tasks.process_pending_notifications',
        'schedule': 60.0,
    },
}

app.conf.timezone = 'Asia/Shanghai'


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
