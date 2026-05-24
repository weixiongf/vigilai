"""驾驶舱前端视图 — 7 步业务流程页面.

左侧侧栏严格对齐 7 步业务流程：
  01 情报蓝图(cockpit) / 02 今日简报(briefing) / 03 市场动态(feed)
  04 采集调度(scheduling) / 05 信息源配置(sources)
  06 通知记录(notifications) / 07 系统配置(settings)
另含跨市场视图: timeline(事件时间线，归属 03 市场动态).
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services import company_profile as cp
from .services import markets as mk
from .services import runtime_config as rc
from .services import briefing_schedule as bs


def cockpit(request):
    return render(request, 'dashboard/cockpit.html', {
        'page': 'cockpit', 'page_title': '情报蓝图'})


def briefing_page(request):
    return render(request, 'dashboard/briefing.html', {
        'page': 'briefing', 'page_title': '今日简报'})


def feed_page(request):
    resp = render(request, 'dashboard/feed.html', {
        'page': 'feed', 'page_title': '市场动态'})
    # 强制不缓存 — feed.html 内嵌了 SSE 浮窗劫持脚本, 调试阶段频繁修改,
    # 避免浏览器缓存 inline script 导致看不到最新调试日志
    resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp['Pragma'] = 'no-cache'
    resp['Expires'] = '0'
    return resp


def scheduling_page(request):
    return render(request, 'dashboard/scheduling.html', {
        'page': 'scheduling', 'page_title': '采集调度'})


def sources_page(request):
    """信息源配置页 — 信息源 CRUD / 触发 / 启停 / 模式切换."""
    return render(request, 'dashboard/sources.html', {
        'page': 'sources', 'page_title': '信息源配置'})


def source_create_page(request):
    """信息源添加页 — 独立表单, 提交后跳回列表页."""
    from apps.sources.models import InfoSource
    return render(request, 'dashboard/source_form.html', {
        'page': 'sources',
        'page_title': '添加信息源',
        'source_type_choices': InfoSource.SOURCE_TYPE_CHOICES,
        'priority_choices': InfoSource.PRIORITY_CHOICES,
        'difficulty_choices': InfoSource.DIFFICULTY_CHOICES,
    })


def notifications_page(request):
    """通知记录页 — 收件人管理 + 通知日志查询."""
    return render(request, 'dashboard/notifications.html', {
        'page': 'notifications', 'page_title': '通知记录'})


def settings_page(request):
    return render(request, 'dashboard/settings.html', {
        'page': 'settings', 'page_title': '系统配置'})


def timeline_page(request):
    """事件时间线页 — 跨市场时间轴串联因果变化."""
    return render(request, 'dashboard/timeline.html', {
        'page': 'timeline', 'page_title': '事件时间线'})


def agents_page(request):
    """多智能体控制台 — 触发 A2A Pipeline + 追溯 AgentMessageLog."""
    return render(request, 'dashboard/agents.html', {
        'page': 'agents', 'page_title': '智能体控制台'})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def company_profile_api(request):
    """公司战略画像配置 API — 文件型存储, 保存即时生效, 无需重启服务.

    GET  返回 ``{strengths, weaknesses, updated_at, path}``.
    POST body: ``{"strengths": [..]|"多行文本", "weaknesses": ..}`` 写入并返回最新值.
    """
    if request.method == 'GET':
        data = cp.load_profile()
        data['path'] = str(cp.PROFILE_PATH)
        return JsonResponse({'ok': True, **data})

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    saved = cp.save_profile(body.get('strengths'), body.get('weaknesses'))
    return JsonResponse({'ok': True, **saved, 'path': str(cp.PROFILE_PATH)})


# ---------- 运行时配置 (LLM / 邮箱 / 短信) ----------
_RC_DISPATCH = {
    'llm':   (rc.get_llm_config,   rc.save_llm_config),
    'email': (rc.get_email_config, rc.save_email_config),
    'sms':   (rc.get_sms_config,   rc.save_sms_config),
}


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def runtime_config_api(request, kind: str):
    """运行时配置 API — kind ∈ {llm, email, sms}.

    GET  返回 {use_custom, env, override, effective}, 敏感字段脱敏.
    POST body: {"use_custom": bool, "fields": {...}} 写入并返回最新值.
    """
    pair = _RC_DISPATCH.get(kind)
    if not pair:
        return JsonResponse({'ok': False, 'error': 'invalid_kind'}, status=400)
    getter, setter = pair
    if request.method == 'GET':
        return JsonResponse({'ok': True, 'kind': kind, **getter()})

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)
    saved = setter(bool(body.get('use_custom')), body.get('fields') or {})
    return JsonResponse({'ok': True, 'kind': kind, **saved})


# ---------- 目标市场 (全站唯一数据源) ----------
@require_http_methods(['GET'])
def markets_api(request):
    """目标市场列表 — 返回启用状态的 TargetMarket, 供前端下拉动态填充.

    Response: {'ok': True, 'items': [{code, name, region, flag_emoji}, ...]}
    数据库为空时回退到仿真语料库, 保证冷启动不为空.
    """
    items = mk.list_active_markets()
    return JsonResponse({'ok': True, 'items': items, 'total': len(items)})


# ---------- 简报调度配置 (日报/周报/月报 开关与发送规则) ----------
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def briefing_schedule_api(request):
    """简报调度配置 API — 文件型存储, 保存即时生效.

    GET  返回 ``{daily, weekly, monthly, updated_at}``.
    POST body: ``{"daily": {...}, "weekly": {...}, "monthly": {...}}`` 写入并返回最新值.
    """
    if request.method == 'GET':
        data = bs.load_schedule()
        data['path'] = str(bs.SCHEDULE_PATH)
        return JsonResponse({'ok': True, **data})

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    saved = bs.save_schedule(
        realtime=body.get('realtime'),
        market_briefing=body.get('market_briefing'),
        daily=body.get('daily'),
        weekly=body.get('weekly'),
        monthly=body.get('monthly'),
    )
    return JsonResponse({'ok': True, **saved, 'path': str(bs.SCHEDULE_PATH)})
