"""项目级视图 — 仅放轻量级公共端点 (健康检查等)."""
from __future__ import annotations

import logging
import socket
from typing import Any

from django.conf import settings
from django.http import JsonResponse


logger = logging.getLogger(__name__)


def _check_db() -> dict:
    """探活 Postgres — 执行 SELECT 1."""
    try:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
        return {'ok': True}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc)[:200]}


def _check_redis() -> dict:
    """探活 Redis — set/get 一次."""
    try:
        from django.core.cache import cache
        cache.set('healthz:ping', '1', timeout=5)
        ok = cache.get('healthz:ping') == '1'
        return {'ok': bool(ok)}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc)[:200]}


def _check_smtp() -> dict:
    """探活 SMTP — 仅做 TCP 连通性检查, 不真正登录,
    避免频繁调用触发 SMTP 服务器的 IP 风控."""
    try:
        host = getattr(settings, 'EMAIL_HOST', '') or ''
        port = int(getattr(settings, 'EMAIL_PORT', 0) or 0)
        backend = getattr(settings, 'EMAIL_BACKEND', '') or ''
        if 'filebased' in backend or 'console' in backend or 'locmem' in backend:
            return {'ok': True, 'note': f'backend={backend.split(".")[-1]}'}
        if not host or not port:
            return {'ok': False, 'error': 'host/port not configured'}
        with socket.create_connection((host, port), timeout=3):
            return {'ok': True, 'host': host, 'port': port}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc)[:200]}


def _check_llm() -> dict:
    """LLM 配置完整性检查 — 不真正调用 (避免计费)."""
    try:
        provider = (getattr(settings, 'LLM_PROVIDER', '') or '').lower()
        if provider == 'mock' or not provider:
            return {'ok': True, 'provider': 'mock'}
        api_key = getattr(settings, 'LLM_API_KEY', '') or ''
        base_url = getattr(settings, 'LLM_BASE_URL', '') or ''
        if not api_key:
            return {'ok': False, 'provider': provider,
                    'error': 'LLM_API_KEY 未配置'}
        return {'ok': True, 'provider': provider,
                'model': getattr(settings, 'LLM_MODEL', ''),
                'base_url': base_url}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc)[:200]}


def _check_feishu() -> dict:
    """飞书 Webhook 配置检查 — 仅检查 URL 是否填写."""
    try:
        url = getattr(settings, 'FEISHU_WEBHOOK_URL', '') or ''
        if not url:
            return {'ok': False, 'error': 'FEISHU_WEBHOOK_URL 未配置'}
        return {'ok': True, 'configured': True}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc)[:200]}


def healthz(request) -> JsonResponse:
    """轻量健康检查端点 — GET /healthz/

    返回:
      200 + {ok: true, checks: {...}}     全部依赖正常
      503 + {ok: false, checks: {...}}    任一关键依赖异常 (db/redis)
    """
    checks: dict[str, Any] = {
        'db': _check_db(),
        'redis': _check_redis(),
        'smtp': _check_smtp(),
        'llm': _check_llm(),
        'feishu': _check_feishu(),
    }
    # db / redis 任一失败 → 503; 其它仅展示, 不影响整体 ok
    critical = ['db', 'redis']
    ok = all(checks[k].get('ok') for k in critical)
    return JsonResponse(
        {'ok': ok, 'service': 'strategic-radar', 'checks': checks},
        status=200 if ok else 503,
        json_dumps_params={'ensure_ascii': False, 'indent': 2},
    )
