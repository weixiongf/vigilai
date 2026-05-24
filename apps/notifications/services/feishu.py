"""飞书 Webhook 客户端 — 文本卡片 / 富文本卡片 消息发送."""
from __future__ import annotations

import hashlib
import hmac
import base64
import json
import logging
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


logger = logging.getLogger(__name__)


def _gen_sign(secret: str, timestamp: int) -> str:
    """飞书 v2 加签算法: base64(HmacSHA256(timestamp + '\\n' + secret))."""
    string_to_sign = f'{timestamp}\n{secret}'
    digest = hmac.new(string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode('utf-8')


class FeishuWebhookClient:
    """飞书自定义机器人 Webhook 客户端 — 不依赖 requests, 用标准库即可."""

    def __init__(self, webhook_url: str, secret: str = '', timeout: int = 6):
        self.webhook_url = webhook_url
        self.secret = secret
        self.timeout = timeout

    # ---------- 公开接口 ----------
    def send_text(self, content: str) -> dict:
        return self._post({'msg_type': 'text', 'content': {'text': content}})

    def send_card(self, card: dict) -> dict:
        return self._post({'msg_type': 'interactive', 'card': card})

    def send_high_impact_alert(self, info, subject: str, body: str) -> dict:
        """构造高影响告警卡片(适配 RawInfo 模型)."""
        score = info.impact_score or 0
        score_color = 'red' if score >= 8 else ('orange' if score >= 5 else 'grey')
        ot_label = '🔻 威胁' if info.opportunity_or_threat == 'T' else '🟢 机会'
        level_label = {'H': '🔴 高', 'M': '🟡 中', 'L': '🟢 低'}.get(
            info.impact_level, '—')

        card = {
            'config': {'wide_screen_mode': True},
            'header': {
                'title': {'tag': 'plain_text', 'content': subject[:50]},
                'template': score_color,
            },
            'elements': [
                {
                    'tag': 'div',
                    'fields': [
                        {'is_short': True, 'text': {
                            'tag': 'lark_md',
                            'content': f'**目标市场**\n{info.target_market or "—"}'}},
                        {'is_short': True, 'text': {
                            'tag': 'lark_md',
                            'content': f'**战略维度**\n{info.strategic_dimension or "—"}'}},
                        {'is_short': True, 'text': {
                            'tag': 'lark_md',
                            'content': f'**PEST**\n{info.pest_type or "—"}'}},
                        {'is_short': True, 'text': {
                            'tag': 'lark_md',
                            'content': f'**机会/威胁**\n{ot_label}'}},
                        {'is_short': True, 'text': {
                            'tag': 'lark_md',
                            'content': f'**影响等级**\n{level_label}'}},
                        {'is_short': True, 'text': {
                            'tag': 'lark_md',
                            'content': f'**影响分数**\n**{score:.1f} / 10**'}},
                    ],
                },
                {'tag': 'hr'},
                {
                    'tag': 'div',
                    'text': {'tag': 'lark_md',
                             'content': f'**摘要**\n{(info.summary or info.title)[:300]}'},
                },
                {
                    'tag': 'div',
                    'text': {'tag': 'lark_md',
                             'content': f'**🎯 行动建议**\n{(info.action_advice or "—")[:400]}'},
                },
                {
                    'tag': 'note',
                    'elements': [{
                        'tag': 'plain_text',
                        'content': f'信息源: {info.source.name if info.source_id else "Mock"} '
                                   f'· 发布: {info.published_at:%Y-%m-%d %H:%M}'
                    }],
                },
            ],
        }
        return self.send_card(card)

    def send_briefing(self, briefing) -> dict:
        """战略简报卡片."""
        period_label = {'daily': '战略日报', 'weekly': '战略周报',
                        'monthly': '战略月报', 'adhoc': '临时简报'}.get(
            briefing.period_type, '简报')

        # Top opportunities & risks 简短列表
        opp_text = '\n'.join(
            f'• {o.get("title","")[:50]} ({o.get("score",0):.1f}/10)'
            for o in briefing.top_opportunities[:3]
        ) or '暂无'
        risk_text = '\n'.join(
            f'• {r.get("title","")[:50]} ({r.get("score",0):.1f}/10)'
            for r in briefing.top_risks[:3]
        ) or '暂无'
        action_text = '\n'.join(
            f'{i+1}. [{a.get("type","")}] {a.get("title","")[:50]}'
            for i, a in enumerate(briefing.recommended_actions[:4])
        ) or '暂无'

        card = {
            'config': {'wide_screen_mode': True},
            'header': {
                'title': {'tag': 'plain_text',
                          'content': f'📈 {briefing.target_market} {period_label}'},
                'template': 'blue',
            },
            'elements': [
                {'tag': 'div',
                 'text': {'tag': 'lark_md',
                          'content': f'**📌 行政摘要**\n{briefing.executive_summary[:500]}'}},
                {'tag': 'hr'},
                {'tag': 'div',
                 'text': {'tag': 'lark_md',
                          'content': f'**🟢 Top 机会**\n{opp_text}'}},
                {'tag': 'div',
                 'text': {'tag': 'lark_md',
                          'content': f'**🔴 Top 风险**\n{risk_text}'}},
                {'tag': 'hr'},
                {'tag': 'div',
                 'text': {'tag': 'lark_md',
                          'content': f'**🎯 推荐行动**\n{action_text}'}},
                {'tag': 'note',
                 'elements': [{'tag': 'plain_text',
                               'content': f'周期 {briefing.period_start} ~ {briefing.period_end} · '
                                          f'共引用 {len(briefing.referenced_info_ids)} 条情报'}]},
            ],
        }
        return self.send_card(card)

    # ---------- 内部 ----------
    def _post(self, payload: dict[str, Any]) -> dict:
        if not self.webhook_url:
            return {'ok': False, 'error': 'webhook_url_empty', 'payload': payload}

        # 【全链路真实化总开关】mode != 'real' 时跳过实际 HTTP 调用
        try:
            from apps.sources.services import fallback as fb
            if not fb.is_real_mode():
                logger.info('[feishu] simulated mode, skip real webhook POST '
                            '(msg_type=%s)', payload.get('msg_type'))
                return {'ok': True, 'simulated': True,
                        'response': {'code': 0, 'msg': 'simulated, not sent'}}
        except Exception:
            # cache / DB 不可用时不阻断, 继续走真实发送逻辑
            pass

        if self.secret:
            ts = int(time.time())
            payload['timestamp'] = str(ts)
            payload['sign'] = _gen_sign(self.secret, ts)

        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib_request.Request(
            self.webhook_url, data=body, method='POST',
            headers={'Content-Type': 'application/json; charset=utf-8'})
        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {'raw': raw}
                ok = (parsed.get('code', 0) == 0) or parsed.get('StatusCode') == 0
                return {'ok': ok, 'response': parsed}
        except urllib_error.URLError as exc:
            logger.warning('feishu webhook urlerror: %s', exc)
            return {'ok': False, 'error': str(exc)}
        except Exception as exc:
            logger.exception('feishu webhook error: %s', exc)
            return {'ok': False, 'error': str(exc)}


def get_default_client() -> FeishuWebhookClient:
    """从 settings 读取默认 Webhook 配置."""
    from django.conf import settings
    return FeishuWebhookClient(
        webhook_url=getattr(settings, 'FEISHU_WEBHOOK_URL', '') or '',
        secret=getattr(settings, 'FEISHU_WEBHOOK_SECRET', '') or '',
    )
