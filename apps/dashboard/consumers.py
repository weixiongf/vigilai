"""Channels WebSocket 消费者 — 驾驶舱 / 通知 / 单情报订阅."""
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async


logger = logging.getLogger(__name__)


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    """驾驶舱实时数据通道 — 推送新情报、KPI 变化、Celery 任务状态."""

    GROUP_NAME = 'dashboard.broadcast'

    async def connect(self):
        await self.channel_layer.group_add(self.GROUP_NAME, self.channel_name)
        await self.accept()
        kpi = await self._fetch_kpi()
        await self.send_json({
            'type': 'system.hello',
            'message': 'Dashboard channel connected.',
            'kpi': kpi,
        })

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.GROUP_NAME, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get('type')
        if msg_type == 'ping':
            await self.send_json({'type': 'pong'})
        elif msg_type == 'kpi.refresh':
            kpi = await self._fetch_kpi()
            await self.send_json({'type': 'kpi.snapshot', 'kpi': kpi})
        elif msg_type == 'crawl.trigger':
            source_id = content.get('source_id')
            if source_id:
                from apps.sources.tasks import crawl_one_source
                crawl_one_source.delay(source_id)
                await self.send_json({'type': 'crawl.queued', 'source_id': source_id})

    async def dashboard_event(self, event):
        """由后端 group_send 触发 — 把 payload 透传到客户端."""
        await self.send_json(event['payload'])

    @database_sync_to_async
    def _fetch_kpi(self) -> dict:
        from apps.intelligence.models import RawInfo
        from apps.briefings.models import Briefing
        from apps.sources.models import InfoSource
        return {
            'total_intel': RawInfo.objects.count(),
            'analyzed': RawInfo.objects.filter(is_processed=True).count(),
            'high_impact': RawInfo.objects.filter(impact_score__gte=8).count(),
            'briefings': Briefing.objects.count(),
            'active_sources': InfoSource.objects.filter(is_active=True).count(),
        }


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """通知推送通道 — 高影响告警、简报发布."""

    GROUP_NAME = 'notifications.broadcast'

    async def connect(self):
        await self.channel_layer.group_add(self.GROUP_NAME, self.channel_name)
        await self.accept()
        await self.send_json({'type': 'system.hello',
                              'channel': 'notifications'})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.GROUP_NAME, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    async def notify(self, event):
        await self.send_json(event['payload'])


class IntelDetailConsumer(AsyncJsonWebsocketConsumer):
    """单条情报订阅 — 进入详情页时打开, 实时跟随分析进度."""

    async def connect(self):
        self.info_id = self.scope['url_route']['kwargs'].get('info_id')
        self.group_name = f'intel.detail.{self.info_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        snapshot = await self._fetch_intel(self.info_id)
        await self.send_json({'type': 'intel.snapshot', 'intel': snapshot})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def intel_update(self, event):
        await self.send_json(event['payload'])

    @database_sync_to_async
    def _fetch_intel(self, info_id) -> dict:
        from apps.intelligence.models import RawInfo
        try:
            info = RawInfo.objects.get(id=info_id)
        except RawInfo.DoesNotExist:
            return {'error': 'not_found'}
        return {
            'id': info.id,
            'title': info.title,
            'summary': info.summary,
            'pest': info.pest_type,
            'ot': info.opportunity_or_threat,
            'level': info.impact_level,
            'impact_score': info.impact_score,
            'action_advice': info.action_advice,
            'is_processed': info.is_processed,
            'analysis_chain': info.analysis_chain,
        }
