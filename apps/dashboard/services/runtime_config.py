"""运行时配置 — LLM / 邮箱 / 短信 三类可覆盖参数.

默认全部读取 .env (即 ``settings.LLM_*`` / ``settings.EMAIL_*``),
但允许在 settings 页面通过表单写入用户自定义值, 持久化到 ``SystemSetting``,
LLM Provider / 邮件发送服务在调用前先查这里, 找不到再回落 .env.

存储结构 (SystemSetting.value, JSON)::

    {
      "use_custom": true|false,        # 是否启用用户覆盖
      "fields": { ... 各类配置字段 ... }
    }

接口:
- get_llm_config()   -> {use_custom, env, override, effective}
- get_email_config() -> {use_custom, env, override, effective}
- get_sms_config()   -> {use_custom, env, override, effective}
- save_*_config(use_custom, fields) -> dict (同上)
"""
from __future__ import annotations

import logging
import os
from typing import Dict

from django.conf import settings


logger = logging.getLogger(__name__)


# ---------- SystemSetting key ----------
KEY_LLM = 'runtime_llm_config'
KEY_EMAIL = 'runtime_email_config'
KEY_SMS = 'runtime_sms_config'


# ---------- 字段模板 (空字符串占位, 用于前端回填) ----------
LLM_FIELDS = ('provider', 'api_key', 'base_url', 'model')
EMAIL_FIELDS = ('host', 'port', 'username', 'password', 'use_tls', 'use_ssl', 'from_email')
SMS_FIELDS = ('access_key_id', 'access_key_secret', 'sign_name', 'template_code')


# ---------- 内部 helper ----------
def _load_setting(key: str) -> dict:
    """读取 SystemSetting 行, 异常或不存在返回空 dict."""
    try:
        from apps.dashboard.models import SystemSetting
        row = SystemSetting.objects.filter(key=key).only('value').first()
        if not row:
            return {}
        val = row.value or {}
        return val if isinstance(val, dict) else {}
    except Exception as exc:
        logger.debug('[runtime_config] load %s failed: %s', key, exc)
        return {}


def _save_setting(key: str, payload: dict, description: str = '') -> dict:
    """upsert SystemSetting 行."""
    from apps.dashboard.models import SystemSetting
    obj, _ = SystemSetting.objects.update_or_create(
        key=key,
        defaults={'value': payload, 'description': description},
    )
    return obj.value


def _mask(value: str, head: int = 4, tail: int = 4) -> str:
    """脱敏长字符串 (api_key / password) — 仅展示首尾, 中段用 ``***``."""
    if not value:
        return ''
    s = str(value)
    if len(s) <= head + tail:
        return '*' * len(s)
    return f'{s[:head]}***{s[-tail:]}'


def _pick(fields: tuple, src: dict) -> dict:
    """从 src 提取 fields 中存在的键, 缺失键填空字符串."""
    return {k: src.get(k, '') if src.get(k, '') is not None else '' for k in fields}


def _merge_effective(env: dict, override: dict, use_custom: bool) -> dict:
    """生成实际生效值 — use_custom=True 时优先 override 非空字段, 否则全 env."""
    if not use_custom:
        return dict(env)
    eff = dict(env)
    for k, v in (override or {}).items():
        if v not in (None, '', False) or isinstance(v, bool):
            eff[k] = v
    # use_tls / use_ssl 等 bool 字段需显式赋值
    for bk in ('use_tls', 'use_ssl'):
        if bk in (override or {}):
            eff[bk] = bool(override.get(bk))
    return eff


# ---------- LLM ----------
def _llm_env() -> dict:
    return {
        'provider': getattr(settings, 'LLM_PROVIDER', 'mock') or 'mock',
        'api_key': getattr(settings, 'LLM_API_KEY', '') or '',
        'base_url': getattr(settings, 'LLM_BASE_URL', '') or '',
        'model': getattr(settings, 'LLM_MODEL', '') or '',
    }


def get_llm_config() -> dict:
    raw = _load_setting(KEY_LLM)
    use_custom = bool(raw.get('use_custom'))
    override = _pick(LLM_FIELDS, raw.get('fields') or {})
    env = _llm_env()
    effective = _merge_effective(env, override, use_custom)
    return {
        'use_custom': use_custom,
        'env': {**env, 'api_key_mask': _mask(env['api_key'])},
        'override': {**override, 'api_key_mask': _mask(override.get('api_key', ''))},
        'effective': {**effective, 'api_key_mask': _mask(effective.get('api_key', ''))},
    }


def save_llm_config(use_custom: bool, fields: dict) -> dict:
    payload = {
        'use_custom': bool(use_custom),
        'fields': _pick(LLM_FIELDS, fields or {}),
    }
    _save_setting(KEY_LLM, payload, 'LLM 自定义配置 — 覆盖 .env 中 LLM_*')
    return get_llm_config()


def llm_effective() -> dict:
    """供 LLM Provider 直接调用 — 仅返回 effective 配置 (不含 mask)."""
    cfg = get_llm_config()
    return cfg['effective']


# ---------- Email ----------
def _email_env() -> dict:
    return {
        'host': getattr(settings, 'EMAIL_HOST', '') or '',
        'port': int(getattr(settings, 'EMAIL_PORT', 465) or 465),
        'username': getattr(settings, 'EMAIL_HOST_USER', '') or '',
        'password': getattr(settings, 'EMAIL_HOST_PASSWORD', '') or '',
        'use_tls': bool(getattr(settings, 'EMAIL_USE_TLS', False)),
        'use_ssl': bool(getattr(settings, 'EMAIL_USE_SSL', False)),
        'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '',
    }


def get_email_config() -> dict:
    raw = _load_setting(KEY_EMAIL)
    use_custom = bool(raw.get('use_custom'))
    override = _pick(EMAIL_FIELDS, raw.get('fields') or {})
    # 端口规范化
    try:
        override['port'] = int(override.get('port') or 0) or ''
    except (TypeError, ValueError):
        override['port'] = ''
    override['use_tls'] = bool((raw.get('fields') or {}).get('use_tls'))
    override['use_ssl'] = bool((raw.get('fields') or {}).get('use_ssl'))
    env = _email_env()
    effective = _merge_effective(env, override, use_custom)
    # 端口最终强制 int
    try:
        effective['port'] = int(effective.get('port') or env['port'])
    except (TypeError, ValueError):
        effective['port'] = env['port']
    return {
        'use_custom': use_custom,
        'env': {**env, 'password_mask': _mask(env['password'])},
        'override': {**override, 'password_mask': _mask(override.get('password', ''))},
        'effective': {**effective, 'password_mask': _mask(effective.get('password', ''))},
    }


def save_email_config(use_custom: bool, fields: dict) -> dict:
    raw = dict(fields or {})
    # 类型规范化
    try:
        raw['port'] = int(raw.get('port') or 0) or ''
    except (TypeError, ValueError):
        raw['port'] = ''
    raw['use_tls'] = bool(raw.get('use_tls'))
    raw['use_ssl'] = bool(raw.get('use_ssl'))
    payload = {
        'use_custom': bool(use_custom),
        'fields': _pick(EMAIL_FIELDS, raw),
    }
    payload['fields']['use_tls'] = raw['use_tls']
    payload['fields']['use_ssl'] = raw['use_ssl']
    payload['fields']['port'] = raw['port']
    _save_setting(KEY_EMAIL, payload, '邮箱 SMTP 自定义配置 — 覆盖 .env 中 EMAIL_*')
    return get_email_config()


def email_effective() -> dict:
    cfg = get_email_config()
    return cfg['effective']


# ---------- SMS ----------
def _sms_env() -> dict:
    return {
        'access_key_id': os.environ.get('ALIYUN_ACCESS_KEY_ID', '') or '',
        'access_key_secret': os.environ.get('ALIYUN_ACCESS_KEY_SECRET', '') or '',
        'sign_name': os.environ.get('ALIYUN_SMS_SIGN_NAME', '') or '',
        'template_code': os.environ.get('ALIYUN_SMS_TEMPLATE_CODE', '') or '',
    }


def get_sms_config() -> dict:
    raw = _load_setting(KEY_SMS)
    use_custom = bool(raw.get('use_custom'))
    override = _pick(SMS_FIELDS, raw.get('fields') or {})
    env = _sms_env()
    effective = _merge_effective(env, override, use_custom)
    return {
        'use_custom': use_custom,
        'env': {
            **env,
            'access_key_secret_mask': _mask(env['access_key_secret']),
            'access_key_id_mask': _mask(env['access_key_id']),
        },
        'override': {
            **override,
            'access_key_secret_mask': _mask(override.get('access_key_secret', '')),
            'access_key_id_mask': _mask(override.get('access_key_id', '')),
        },
        'effective': {
            **effective,
            'access_key_secret_mask': _mask(effective.get('access_key_secret', '')),
            'access_key_id_mask': _mask(effective.get('access_key_id', '')),
        },
    }


def save_sms_config(use_custom: bool, fields: dict) -> dict:
    payload = {
        'use_custom': bool(use_custom),
        'fields': _pick(SMS_FIELDS, fields or {}),
    }
    _save_setting(KEY_SMS, payload, '短信 (阿里云) 自定义配置 — 覆盖 .env 中 ALIYUN_*')
    return get_sms_config()


def sms_effective() -> dict:
    cfg = get_sms_config()
    return cfg['effective']
