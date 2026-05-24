"""邮件发送 — 高影响告警 / 战略简报 HTML 邮件."""
from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import escape


logger = logging.getLogger(__name__)


FILE_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'


def _runtime_email_cfg() -> dict:
    """读取 settings 页邮箱 TAB 中保存的运行时配置 — 覆盖 .env.

    返回 {use_custom, fields...} 形式, 异常时返回空 dict.
    """
    try:
        from apps.dashboard.services.runtime_config import (
            get_email_config as _get,
        )
        cfg = _get() or {}
        return {
            'use_custom': bool(cfg.get('use_custom')),
            **(cfg.get('effective') or {}),
        }
    except Exception:
        return {}


def _normalize_secure(port: int, use_tls: bool, use_ssl: bool) -> tuple[bool, bool]:
    """按端口校正加密方式 — 互斥, 465 默认 SSL, 587 默认 TLS.

    smtplib 限制: use_ssl/use_tls 不能同时为 True; 否则连接异常.
    """
    p = int(port or 0)
    if use_ssl and use_tls:
        # 互斥时优先 SSL (端口 465 行为)
        use_tls = False
    if not use_ssl and not use_tls:
        if p == 465:
            use_ssl = True
        else:
            use_tls = True
    return bool(use_tls), bool(use_ssl)


def _real_mode_active() -> bool:
    """读取全链路真实化总开关 — 安全兜底为 False (走仿真文件后端)."""
    try:
        from apps.sources.services import fallback as fb
        return fb.is_real_mode()
    except Exception:
        return False


def _runtime_smtp_connection():
    """运行时自定义 SMTP 连接 (settings 页邮箱 TAB 保存的配置).

    未启用 use_custom / 未填 host 返回 None — 上层会回退到 .env.
    """
    cfg = _runtime_email_cfg()
    if not (cfg.get('use_custom') and cfg.get('host')):
        return None
    port = int(cfg.get('port') or 465)
    use_tls, use_ssl = _normalize_secure(
        port, bool(cfg.get('use_tls')), bool(cfg.get('use_ssl')),
    )
    return get_connection(
        backend=SMTP_BACKEND,
        host=cfg.get('host') or '',
        port=port,
        username=cfg.get('username') or '',
        password=cfg.get('password') or '',
        use_tls=use_tls,
        use_ssl=use_ssl,
        timeout=15,
    )


def _env_smtp_connection():
    """.env 中 EMAIL_* 显式构造的 SMTP 连接 (兑底配置). host 未配返回 None."""
    host = getattr(settings, 'EMAIL_HOST', '') or ''
    if not host:
        return None
    port = int(getattr(settings, 'EMAIL_PORT', 465) or 465)
    use_tls, use_ssl = _normalize_secure(
        port,
        bool(getattr(settings, 'EMAIL_USE_TLS', False)),
        bool(getattr(settings, 'EMAIL_USE_SSL', False)),
    )
    return get_connection(
        backend=SMTP_BACKEND,
        host=host,
        port=port,
        username=getattr(settings, 'EMAIL_HOST_USER', '') or '',
        password=getattr(settings, 'EMAIL_HOST_PASSWORD', '') or '',
        use_tls=use_tls,
        use_ssl=use_ssl,
        timeout=15,
    )


def _file_connection():
    """filebased 后端 — 价仿演示场景下邮件落盘到 tmp/sent_emails."""
    return get_connection(
        backend=FILE_BACKEND,
        file_path=getattr(settings, 'EMAIL_FILE_PATH', None),
    )


def _resolve_connection(prefer: str = 'runtime'):
    """返回选定后端的连接:

    - 非 real 模式 → 强制 filebased
    - real 模式 + prefer == 'runtime' → 优先运行时自定义, 其次 .env
    - real 模式 + prefer == 'env'     → 直接用 .env (兑底路径)
    """
    if not _real_mode_active():
        return _file_connection()
    if prefer == 'env':
        return _env_smtp_connection() or None
    # 默认: 运行时 → .env
    return _runtime_smtp_connection() or _env_smtp_connection() or None


def _from_address() -> str:
    cfg = _runtime_email_cfg()
    if cfg.get('use_custom') and cfg.get('from_email'):
        return cfg.get('from_email')
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@strategic-radar.local') \
        or 'no-reply@strategic-radar.local'


# ---------- 公共发送 ----------
def send_html_email(
    subject: str,
    html: str,
    to: Iterable[str],
    text_alt: str = '',
) -> dict:
    """发送 HTML 邮件 (附带纯文本回退).

    【全链路真实化总开关】非 real 模式下临时使用 filebased 后端,
    避免仿真演示场景下意外发出真实邮件.
    """
    to_list = [t for t in to if t]
    if not to_list:
        return {'ok': False, 'error': 'no_recipients'}

    # 优先运行时自定义配置 → 失败后用 .env 兑底 → 再失败才返回错误
    cfg = _runtime_email_cfg()
    custom_enabled = bool(cfg.get('use_custom') and cfg.get('host')) and _real_mode_active()
    plan = ['runtime', 'env'] if custom_enabled else ['env']

    last_err = None
    used_plan = None
    for idx, prefer in enumerate(plan):
        connection = _resolve_connection(prefer=prefer)
        # filebased / 未配置 — 跳过后续兑底路径 (已是终态)
        is_file = bool(
            connection is not None
            and getattr(connection, '__class__', None)
            and 'filebased' in connection.__class__.__module__
        )
        simulated = is_file
        # 运行时阶段: 同一连接重试 1 次 (间隔 1.2s) — 减轻偏发断连
        attempts = 2 if (not is_file and prefer == 'runtime') else 1
        for attempt in range(attempts):
            msg = EmailMultiAlternatives(
                subject=subject[:200],
                body=text_alt or _strip_tags(html),
                from_email=_from_address(),
                to=to_list,
                connection=connection,
            )
            msg.attach_alternative(html, 'text/html')
            try:
                sent = msg.send(fail_silently=False)
                used_plan = prefer
                result = {'ok': bool(sent), 'sent': sent, 'recipients': to_list}
                if simulated:
                    result['simulated'] = True
                if used_plan == 'env' and custom_enabled:
                    result['fallback'] = 'env'  # 运行时跳兑底生效
                if attempt > 0:
                    result['retried'] = attempt
                return result
            except Exception as exc:
                last_err = exc
                logger.warning(
                    'send_html_email [%s] attempt %s failed: %s',
                    prefer, attempt + 1, exc,
                )
                if attempt + 1 < attempts:
                    import time
                    time.sleep(1.2)
                    connection = _resolve_connection(prefer=prefer)
        # 此层全部失败 — 进入下一 plan (env 兑底)
        if idx + 1 < len(plan):
            logger.warning('send_html_email runtime SMTP failed, fallback to .env')
    logger.exception('send_html_email failed after fallback: %s', last_err)
    return {'ok': False, 'error': str(last_err) if last_err else 'no_connection'}


def _strip_tags(html: str) -> str:
    import re
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ---------- 业务邮件 ----------
def send_high_impact_alert_email(info, subject: str, body: str, to: Iterable[str]) -> dict:
    """高影响告警邮件 — 红/橙色卡片风格 HTML."""
    score = float(info.impact_score or 0)
    color = '#dc2626' if score >= 8 else ('#f59e0b' if score >= 5 else '#6b7280')
    ot_label = '🔻 威胁' if info.opportunity_or_threat == 'T' else '🟢 机会'
    level_map = {'H': '🔴 高', 'M': '🟡 中', 'L': '🟢 低'}
    level_label = level_map.get(info.impact_level, '—')

    title = escape(info.title or '')
    summary = escape(info.summary or info.title or '')
    advice = escape(info.action_advice or '—')
    market = escape(info.target_market or '—')
    dim = escape(info.strategic_dimension or '—')
    pest = escape(info.pest_type or '—')
    src_name = escape(info.source.name if info.source_id else 'Mock')
    pub = info.published_at.strftime('%Y-%m-%d %H:%M') if info.published_at else '—'

    html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,'Segoe UI',sans-serif;color:#111827;">
<div style="max-width:680px;margin:24px auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:{color};color:#fff;padding:16px 20px;font-size:16px;font-weight:600;">
    [高影响告警] {title}
  </div>
  <div style="padding:18px 20px;">
    <table cellpadding="6" cellspacing="0" style="width:100%;font-size:13px;color:#374151;border-collapse:collapse;">
      <tr>
        <td style="width:33%;background:#f9fafb;"><strong>目标市场</strong><br>{market}</td>
        <td style="width:33%;background:#f9fafb;"><strong>战略维度</strong><br>{dim}</td>
        <td style="width:33%;background:#f9fafb;"><strong>PEST</strong><br>{pest}</td>
      </tr>
      <tr>
        <td><strong>机会 / 威胁</strong><br>{ot_label}</td>
        <td><strong>影响等级</strong><br>{level_label}</td>
        <td><strong>影响分数</strong><br><span style="color:{color};font-weight:700;font-size:15px;">{score:.1f} / 10</span></td>
      </tr>
    </table>

    <h3 style="font-size:14px;color:#111827;margin:18px 0 6px;">📌 摘要</h3>
    <p style="font-size:13px;color:#374151;line-height:1.7;margin:0;">{summary}</p>

    <h3 style="font-size:14px;color:#111827;margin:18px 0 6px;">🎯 行动建议</h3>
    <p style="font-size:13px;color:#374151;line-height:1.7;margin:0;white-space:pre-line;">{advice}</p>

    <hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0;">
    <p style="font-size:12px;color:#9ca3af;margin:0;">
      信息源: {src_name} · 发布: {pub}
    </p>
  </div>
</div>
</body></html>
"""
    return send_html_email(subject, html, to, text_alt=body)


def send_briefing_email(briefing, to: Iterable[str]) -> dict:
    """战略简报邮件 — 复用 apps.briefings.services.templates 统一渲染器.

    邮件 / 详情页 / 通知预览 三处使用同一模板文件:
      templates/briefings/_briefing_full.html
    修改一处即可同步三处表现.
    """
    period_label = {'daily': '战略日报', 'weekly': '战略周报',
                    'monthly': '战略月报', 'adhoc': '临时简报'}.get(
        briefing.period_type, '战略简报')

    try:
        from apps.briefings.services.templates import render_briefing_html
        html = render_briefing_html(briefing, mode='email')
    except Exception as exc:
        logger.exception('render_briefing_html failed: %s', exc)
        # 兑底: 渲染器异常时返回简易 HTML, 避免完全发不出
        html = (f'<html><body><h2>{escape(briefing.title or period_label)}</h2>'
                f'<p>{escape(briefing.executive_summary or "")}</p>'
                f'</body></html>')

    return send_html_email(briefing.title or period_label, html, to)
