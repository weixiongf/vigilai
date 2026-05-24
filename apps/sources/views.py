"""信息源 REST API."""
from __future__ import annotations

from django.db.models import Count, Sum, Q, Case, When, IntegerField, Value
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.sources.models import InfoSource, CrawlJob
from apps.sources.services import fallback as fb
from apps.sources.services import tier_switch as tier
from apps.sources.management.commands.import_sources import (
    derive_access_tier, derive_spider_name,
)


def _source_real_capable(src) -> bool:
    """判断该信息源是否能路由到真实爬虫 (基于 spider_name 与关键词路由)。"""
    if not src:
        return False
    try:
        from apps.sources.services.real_crawler import (
            SPIDER_REGISTRY, _KEYWORD_ROUTES, _route_haystack,
        )
        spider = (src.spider_name or '').strip().lower()
        if spider and spider in SPIDER_REGISTRY:
            return True
        hay = _route_haystack(src)
        for keys, _fn, _label in _KEYWORD_ROUTES:
            if any(k.lower() in hay for k in keys):
                return True
    except Exception:
        return False
    return False


def _job_used_simulation(job) -> bool:
    """判断本次采集任务是否走了仿真分支。"""
    triggered = (job.triggered_by or '').lower()
    err = (job.error_log or '').lower()
    return ':sim' in triggered or 'fallback' in err


def _serialize_source(s: InfoSource) -> dict:
    return {
        'id': s.id,
        'name': s.name,
        'category': s.category,
        'source_type': s.source_type,
        'source_type_label': s.get_source_type_display(),
        'priority': s.priority,
        'priority_label': s.get_priority_display(),
        'difficulty': s.difficulty,
        'crawl_interval': s.crawl_interval,
        'update_frequency': s.update_frequency,
        'access_tier': s.access_tier,
        'access_tier_label': s.get_access_tier_display(),
        'is_active': s.is_active,
        'needs_register': s.needs_register,
        'needs_login': s.needs_login,
        'is_paid': s.is_paid,
        'last_crawled_at': s.last_crawled_at.isoformat() if s.last_crawled_at else None,
        'last_status': s.last_status,
        'last_message': s.last_message,
        'official_url': s.official_url,
        'spider_name': s.spider_name,
        'real_capable': _source_real_capable(s),
    }


@require_GET
def source_list(request):
    qs = InfoSource.objects.all()
    type_f = request.GET.get('type')
    if type_f:
        qs = qs.filter(source_type=type_f)
    pri_f = request.GET.get('priority')
    if pri_f:
        qs = qs.filter(priority=pri_f)
    active = request.GET.get('active')
    if active in ('1', 'true'):
        qs = qs.filter(is_active=True)
    elif active in ('0', 'false'):
        qs = qs.filter(is_active=False)
    keyword = request.GET.get('q')
    if keyword:
        qs = qs.filter(Q(name__icontains=keyword) | Q(category__icontains=keyword))

    # 排序：启用优先（未启用沉底）→ 推荐度高到低 → 名称
    pri_rank = Case(
        When(priority='critical', then=Value(1)),
        When(priority='high',     then=Value(2)),
        When(priority='medium',   then=Value(3)),
        When(priority='low',      then=Value(4)),
        default=Value(9),
        output_field=IntegerField(),
    )
    qs = qs.annotate(_pri_rank=pri_rank).order_by('-is_active', '_pri_rank', 'name')
    return JsonResponse({
        'total': qs.count(),
        'items': [_serialize_source(s) for s in qs],
    })


@require_GET
def source_detail(request, pk: int):
    try:
        s = InfoSource.objects.get(id=pk)
    except InfoSource.DoesNotExist:
        raise Http404()
    data = _serialize_source(s)
    data['recent_jobs'] = [
        {
            'id': j.id,
            'started_at': j.started_at.isoformat(),
            'finished_at': j.finished_at.isoformat() if j.finished_at else None,
            'status': j.status,
            'items_fetched': j.items_fetched,
            'items_new': j.items_new,
            'triggered_by': j.triggered_by,
        }
        for j in s.jobs.order_by('-started_at')[:10]
    ]
    return JsonResponse(data)


@csrf_exempt
@require_POST
def source_trigger(request, pk: int):
    try:
        from apps.sources.tasks import crawl_one_source
        crawl_one_source.delay(pk)
        return JsonResponse({'ok': True, 'queued': pk})
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=500)


@csrf_exempt
@require_POST
def source_toggle(request, pk: int):
    """切换 is_active."""
    try:
        s = InfoSource.objects.get(id=pk)
    except InfoSource.DoesNotExist:
        raise Http404()
    s.is_active = not s.is_active
    s.save(update_fields=['is_active', 'updated_at'])
    return JsonResponse({'ok': True, 'id': s.id, 'is_active': s.is_active})


# ---------------- 添加 / 删除 信息源 ----------------

_VALID_TYPES = {c[0] for c in InfoSource.SOURCE_TYPE_CHOICES}
_VALID_PRIORITIES = {c[0] for c in InfoSource.PRIORITY_CHOICES}


@csrf_exempt
@require_POST
def source_create(request):
    """创建信息源.

    POST body (JSON):
      必填: name (唯一), official_url
      选填: category, list_url, source_type, priority, update_frequency,
            crawl_interval, needs_register, needs_login, is_paid,
            spider_name, notes, is_active, difficulty
    返回: { ok: True, id, ...序列化后的完整记录 }.
    """
    import json as _json
    try:
        body = _json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'name_required'}, status=400)
    if InfoSource.objects.filter(name=name).exists():
        return JsonResponse({
            'ok': False, 'error': 'name_duplicated',
            'message': f'名称 "{name}" 已存在'
        }, status=400)

    official_url = (body.get('official_url') or '').strip()
    if not official_url:
        return JsonResponse({'ok': False, 'error': 'official_url_required'}, status=400)
    if not official_url.startswith(('http://', 'https://')):
        official_url = 'https://' + official_url

    list_url = (body.get('list_url') or '').strip()
    if list_url and not list_url.startswith(('http://', 'https://')):
        list_url = 'https://' + list_url

    source_type = (body.get('source_type') or 'web').strip()
    if source_type not in _VALID_TYPES:
        source_type = 'web'

    priority = (body.get('priority') or 'medium').strip()
    if priority not in _VALID_PRIORITIES:
        priority = 'medium'

    try:
        crawl_interval = int(body.get('crawl_interval') or 3600)
    except (TypeError, ValueError):
        crawl_interval = 3600
    crawl_interval = max(60, min(crawl_interval, 86400 * 7))

    try:
        difficulty = int(body.get('difficulty') or 2)
    except (TypeError, ValueError):
        difficulty = 2
    difficulty = max(1, min(difficulty, 5))

    payload = {
        'name': name[:200],
        'category': (body.get('category') or '')[:80],
        'official_url': official_url[:500],
        'list_url': list_url[:500],
        'source_type': source_type,
        'interface_type': (body.get('interface_type') or '')[:80],
        'data_format': (body.get('data_format') or '')[:40],
        'update_frequency': (body.get('update_frequency') or '')[:80],
        'crawl_method': (body.get('crawl_method') or '')[:200],
        'rate_limit_hint': (body.get('rate_limit_hint') or '')[:120],
        'crawl_interval': crawl_interval,
        'needs_register': bool(body.get('needs_register')),
        'needs_login': bool(body.get('needs_login')),
        'is_paid': bool(body.get('is_paid')),
        'needs_custom_spider': bool(body.get('needs_custom_spider', True)),
        'difficulty': difficulty,
        'priority': priority,
        'relevance': (body.get('relevance') or '')[:120],
        'notes': (body.get('notes') or ''),
        'spider_name': ((body.get('spider_name') or '').strip()
                        or derive_spider_name(name))[:120],
        'is_active': bool(body.get('is_active', True)),
    }
    payload['access_tier'] = derive_access_tier(payload)

    s = InfoSource.objects.create(**payload)
    return JsonResponse({'ok': True, **_serialize_source(s),
                         'access_tier': s.access_tier}, status=201)


@csrf_exempt
@require_http_methods(['DELETE', 'POST'])
def source_delete(request, pk: int):
    """删除信息源 (需严谨二步: 前端传 confirm=name 匹配才执行删除).

    接受 DELETE 或 POST 请求; body 可传 {"confirm": "<信息源名称>"} 以二次确认.
    会级联删除其 CrawlJob (model on_delete=CASCADE).
    """
    try:
        s = InfoSource.objects.get(id=pk)
    except InfoSource.DoesNotExist:
        raise Http404()

    import json as _json
    confirm = ''
    try:
        body = _json.loads(request.body.decode('utf-8') or '{}')
        confirm = (body.get('confirm') or '').strip()
    except Exception:
        pass
    # confirm 可选; 若提供了则必须严格一致
    if confirm and confirm != s.name:
        return JsonResponse({
            'ok': False, 'error': 'confirm_mismatch',
            'message': f'确认名称不匹配 (应为 "{s.name}")'
        }, status=400)

    name = s.name
    fb.reset_failure(s)
    s.delete()
    return JsonResponse({'ok': True, 'deleted': pk, 'name': name})


@require_GET
def jobs_recent(request):
    """最近的采集任务列表."""
    qs = CrawlJob.objects.select_related('source') \
        .order_by('-started_at')[:30]
    items = []
    for j in qs:
        used_sim = _job_used_simulation(j)
        real_capable = _source_real_capable(j.source)
        items.append({
            'id': j.id,
            'source_id': j.source_id,
            'source_name': j.source.name,
            'started_at': j.started_at.isoformat(),
            'finished_at': j.finished_at.isoformat() if j.finished_at else None,
            'items_new': j.items_new,
            'items_fetched': j.items_fetched,
            'status': j.status,
            'triggered_by': j.triggered_by,
            'real_capable': real_capable,
            'used_simulation': used_sim,
            'is_real': bool(real_capable and not used_sim),
        })
    return JsonResponse({'items': items})


@require_GET
def job_detail(request, pk):
    """采集任务详情 — 含该任务时间窗内入库的 RawInfo 预览."""
    try:
        job = CrawlJob.objects.select_related('source').get(pk=pk)
    except CrawlJob.DoesNotExist:
        raise Http404

    from apps.intelligence.models import RawInfo
    qs = RawInfo.objects.all()
    if job.source_id:
        qs = qs.filter(source_id=job.source_id)
    qs = qs.filter(fetched_at__gte=job.started_at)
    if job.finished_at:
        # 给完成时间加 60s 宽容，避免微差丢失
        from datetime import timedelta
        qs = qs.filter(fetched_at__lte=job.finished_at + timedelta(seconds=60))
    qs = qs.order_by('-fetched_at')[:30]

    items = [{
        'id': r.id,
        'title': r.title,
        'url': r.url,
        'summary': (r.summary or r.content or '')[:280],
        'published_at': r.published_at.isoformat() if r.published_at else None,
        'fetched_at': r.fetched_at.isoformat() if r.fetched_at else None,
        'language': r.language,
        'target_market': r.target_market,
        'country': r.country,
        'strategic_dimension': r.strategic_dimension,
        'impact_type': r.impact_type,
        'severity': r.severity,
        'impact_score': r.impact_score,
        'sentiment': r.sentiment,
        'pest_type': r.pest_type,
        'tags': list(r.tags or []),
        'is_simulated': r.is_simulated,
        'is_processed': r.is_processed,
    } for r in qs]

    # 判断该任务是否为真实采集: 同时看 1) 任务记录 2) 该源是否能路由到真实爬虫
    src = job.source
    real_capable = _source_real_capable(src)
    used_simulation = _job_used_simulation(job)
    return JsonResponse({
        'id': job.id,
        'source_id': job.source_id,
        'source_name': src.name if src else '—',
        'source_spider': src.spider_name if src else '',
        'source_official_url': src.official_url if src else '',
        'real_capable': real_capable,
        'used_simulation': used_simulation,
        'started_at': job.started_at.isoformat(),
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'items_fetched': job.items_fetched,
        'items_new': job.items_new,
        'status': job.status,
        'triggered_by': job.triggered_by,
        'error_log': job.error_log or '',
        'items': items,
        'items_count': len(items),
    })


@require_GET
def sources_overview(request):
    """信息源汇总指标 (调度页 KPI)."""
    total = InfoSource.objects.count()
    active = InfoSource.objects.filter(is_active=True).count()
    by_type = list(
        InfoSource.objects.values('source_type').annotate(cnt=Count('id'))
    )
    by_priority = list(
        InfoSource.objects.values('priority').annotate(cnt=Count('id'))
    )
    last_jobs_status = list(
        CrawlJob.objects.values('status').annotate(cnt=Count('id'))
    )
    items_today = CrawlJob.objects.aggregate(
        n=Sum('items_new'), fetched=Sum('items_fetched'))
    return JsonResponse({
        'total': total,
        'active': active,
        'by_type': by_type,
        'by_priority': by_priority,
        'jobs_status': last_jobs_status,
        'items_aggregate': items_today,
    })


# ---------------- 降级 / 仿真切换 ----------------

@csrf_exempt
def simulation_mode(request):
    """GET 查看当前模式 / POST 切换模式.

    POST body 示例: {"mode": "simulated"} 或 {"action": "reset", "source_id": 12}
    """
    if request.method == 'GET':
        return JsonResponse(fb.snapshot())

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'method_not_allowed'}, status=405)

    import json
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        body = {}

    action = (body.get('action') or '').strip()
    if action == 'reset':
        sid = body.get('source_id')
        if not sid:
            return JsonResponse({'ok': False, 'error': 'missing source_id'}, status=400)
        try:
            src = InfoSource.objects.get(id=int(sid))
        except (InfoSource.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': 'source_not_found'}, status=404)
        fb.reset_failure(src)
        return JsonResponse({'ok': True, 'reset': src.id, 'snapshot': fb.snapshot()})

    mode = (body.get('mode') or '').strip()
    if mode not in fb.VALID_MODES:
        return JsonResponse({
            'ok': False, 'error': 'invalid_mode',
            'allowed': list(fb.VALID_MODES),
        }, status=400)
    fb.set_mode(mode)
    return JsonResponse({'ok': True, 'snapshot': fb.snapshot()})


# ---------------- access_tier 开关 (免费 / 需注册 / 付费) ----------------

@csrf_exempt
def tier_switch_view(request):
    """GET 返回三档开关快照 + 各档信息源计数 / POST 切换单个档位.

    POST body: {"tier": "register", "enabled": true}
    """
    if request.method == 'GET':
        snap = tier.snapshot()
        # 同时返回每个 tier 下的 信息源总数 / 活跃数
        counts = {}
        for t in tier.VALID_TIERS:
            qs = InfoSource.objects.filter(access_tier=t)
            counts[t] = {
                'total': qs.count(),
                'active': qs.filter(is_active=True).count(),
            }
        return JsonResponse({
            'tiers': snap,
            'counts': counts,
            'enabled_tiers': tier.enabled_tiers(),
        })

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'method_not_allowed'}, status=405)

    import json
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        body = {}

    t = (body.get('tier') or '').strip().lower()
    if t not in tier.VALID_TIERS:
        return JsonResponse({
            'ok': False, 'error': 'invalid_tier',
            'allowed': list(tier.VALID_TIERS),
        }, status=400)
    enabled = bool(body.get('enabled'))
    tier.set_tier_enabled(t, enabled)
    return JsonResponse({
        'ok': True, 'tier': t, 'enabled': enabled,
        'tiers': tier.snapshot(),
    })
