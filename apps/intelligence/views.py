"""情报 REST API — 列表 / 详情 / 反馈 / 触发分析."""
from __future__ import annotations

import time
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.http import JsonResponse, Http404, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

import json

from apps.intelligence.models import RawInfo, UserFeedback


def _serialize_intel(info: RawInfo, full: bool = False) -> dict:
    # 列表也提供原文片段, 方便"原始数据"视角直接预览
    raw_text = (info.content or '').strip()
    preview = raw_text[:240] + ('…' if len(raw_text) > 240 else '')
    data = {
        'id': info.id,
        'title': info.title,
        'summary': info.summary,
        'content_preview': preview,
        'url': info.url,
        'published_at': info.published_at.isoformat() if info.published_at else None,
        'fetched_at': info.fetched_at.isoformat() if info.fetched_at else None,
        'language': info.language,
        'is_simulated': info.is_simulated,
        'target_market': info.target_market,
        'strategic_dimension': info.strategic_dimension,
        'strategic_dimension_label': info.get_strategic_dimension_display(),
        'pest_type': info.pest_type,
        'opportunity_or_threat': info.opportunity_or_threat,
        'impact_level': info.impact_level,
        'impact_score': info.impact_score,
        'impact_type': info.impact_type,
        'severity': info.severity,
        'sentiment': info.sentiment,
        'tags': info.tags or [],
        'value_grade': info.value_grade,
        'is_processed': info.is_processed,
        'source': {
            'id': info.source_id,
            'name': info.source.name if info.source_id else None,
        },
    }
    if full:
        data.update({
            'content': info.content,
            'reference_quote': info.reference_quote,
            'action_advice': info.action_advice,
            'impact_rationale': info.impact_rationale,
            'analysis_chain': info.analysis_chain,
            'affected_entities': info.affected_entities or [],
            'score_relevance': info.score_relevance,
            'score_urgency': info.score_urgency,
            'score_authority': info.score_authority,
            'score_scope': info.score_scope,
        })
    return data


@require_GET
def intel_list(request):
    qs = RawInfo.objects.select_related('source').all()

    market = request.GET.get('market')
    if market:
        qs = qs.filter(target_market=market)
    dim = request.GET.get('dimension')
    if dim:
        qs = qs.filter(strategic_dimension=dim)
    pest = request.GET.get('pest')
    if pest:
        qs = qs.filter(pest_type=pest)
    ot = request.GET.get('ot')
    if ot:
        qs = qs.filter(opportunity_or_threat=ot)
    level = request.GET.get('level')
    if level:
        qs = qs.filter(impact_level=level)
    # 是否已 LLM 分析: '1'/'true'=只看已分析, '0'/'false'=只看未分析, 缺省=全部
    processed = request.GET.get('processed')
    if processed is not None and processed != '':
        v = str(processed).lower()
        if v in ('1', 'true', 'yes'):
            qs = qs.filter(is_processed=True)
        elif v in ('0', 'false', 'no'):
            qs = qs.filter(is_processed=False)
    min_score = request.GET.get('min_score')
    if min_score:
        try:
            qs = qs.filter(impact_score__gte=float(min_score))
        except ValueError:
            pass
    # 时间窗口：hours 优先于 days，与驾驶舱 KPI 取同一参考字段 fetched_at
    hours_param = request.GET.get('hours')
    if hours_param:
        try:
            h = int(hours_param)
            if h > 0:
                qs = qs.filter(fetched_at__gte=timezone.now() - timedelta(hours=h))
        except ValueError:
            pass
    else:
        days_param = request.GET.get('days')
        if days_param:
            try:
                d = int(days_param)
                if d > 0:
                    qs = qs.filter(fetched_at__gte=timezone.now() - timedelta(days=d))
            except ValueError:
                pass
    keyword = request.GET.get('q')
    if keyword:
        qs = qs.filter(Q(title__icontains=keyword) | Q(content__icontains=keyword))

    order = request.GET.get('order', '-published_at')
    if order in {'-published_at', 'published_at', '-impact_score', 'impact_score'}:
        qs = qs.order_by(order)

    try:
        page = max(1, int(request.GET.get('page', '1')))
        size = min(100, max(1, int(request.GET.get('size', '20'))))
    except ValueError:
        page, size = 1, 20

    total = qs.count()
    start = (page - 1) * size
    items = [_serialize_intel(i) for i in qs[start:start + size]]

    return JsonResponse({
        'total': total,
        'page': page,
        'size': size,
        'items': items,
    })


@require_GET
def intel_detail(request, pk: int):
    try:
        info = RawInfo.objects.select_related('source').get(id=pk)
    except RawInfo.DoesNotExist:
        raise Http404()
    return JsonResponse(_serialize_intel(info, full=True))


@csrf_exempt
@require_POST
def intel_feedback(request, pk: int):
    try:
        info = RawInfo.objects.get(id=pk)
    except RawInfo.DoesNotExist:
        raise Http404()
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid_json'}, status=400)

    fb = UserFeedback.objects.create(
        raw_info=info,
        action=payload.get('action', 'confirmed'),
        correction_note=payload.get('note', ''),
        created_by=payload.get('user', 'anonymous'),
    )
    return JsonResponse({'ok': True, 'id': fb.id})


@csrf_exempt
@require_POST
def intel_trigger_analyze(request, pk: int):
    """单条“立即分析” — 复用 batch 同样的流式推送链路.

    以前走 Celery analyze_one_intel.delay(), 但那条路径不传 on_token,
    导致点单条分析后前端看不到 LLM 流式输出.
    现在统一走 run_batch_analyze([pk]), 同一条 token 推送管道.
    """
    try:
        from apps.intelligence.batch import run_batch_analyze
        run_batch_analyze([int(pk)])
        return JsonResponse({'ok': True, 'queued': pk})
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=500)


# ---------------------------------------------------------------
# SSE 流式分析 + 批量分析
# ---------------------------------------------------------------
# Padding 不是"过度防御", 是触发 ASGI(Daphne) 将小 chunk 即时 flush 出的必要手段.
# 没有 padding 时 token (~30B) 会被聚合缓冲 → 前端长时间哑火.
# 256B 是经验值: 1500 events * 256B = 384KB 响应体, 在可接受范围.
# 低频关键事件 (start/thinking/result/done/error) 用 1KB padding 防中间代理.
_HIGH_FREQ_EVENTS = {'token', 'reasoning', 'heartbeat', 'chain'}


def _sse(event: str, data: dict) -> str:
    body = f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'
    if event in _HIGH_FREQ_EVENTS:
        # 高频事件: 256B padding (于响应体大小与即时 flush 之间取平衡)
        pad = ':' + (' ' * 256) + '\n'
        return pad + body
    pad = ':' + (' ' * 1024) + '\n'
    return pad + body


def _intel_result_payload(info: RawInfo) -> dict:
    return {
        'id': info.id,
        'pest_type': info.pest_type,
        'opportunity_or_threat': info.opportunity_or_threat,
        'impact_level': info.impact_level,
        'impact_score': info.impact_score,
        'score_relevance': info.score_relevance,
        'score_urgency': info.score_urgency,
        'score_authority': info.score_authority,
        'score_scope': info.score_scope,
        'summary': info.summary,
        'action_advice': info.action_advice,
        'impact_rationale': info.impact_rationale,
        'tags': info.tags or [],
        'analysis_chain': info.analysis_chain or [],
        'is_processed': info.is_processed,
        'sentiment': info.sentiment,
        'severity': info.severity,
        'impact_type': info.impact_type,
    }


def _push_notify(payload: dict) -> None:
    """向 notifications.broadcast 推状态事件 (供前端 sr:ws 使用)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            'notifications.broadcast',
            {'type': 'notify', 'payload': payload},
        )
    except Exception:
        pass


async def intel_analyze_stream(request, pk: int):
    """SSE 流式分析 — 实时透传 LLM 原生 delta token 到前端,
    分析完成后写回 RawInfo + 推送 notifications.broadcast.

    【关键】必须是 async view —— Django 4.x 在 ASGI(Daphne) 下,
    sync view 返回的 StreamingHttpResponse 会被 ASGI 适配层完整消费
    后才发响应头与 body, 表现为 SSE 一次性跳出, 看不到流式 token.
    只有 async view + async 生成器才能逐块 flush.

    实现: queue.Queue + threading.Thread 桥接 ——
    子线程调用 analyze_one(on_token=...), token 进队;
    主 async 生成器用 asyncio.to_thread 非阻塞地从队列取 token,
    yield SSE event, 从而让前端动态看到 LLM 逐字的输出.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'method_not_allowed'}, status=405)

    import asyncio
    from asgiref.sync import sync_to_async

    try:
        info = await sync_to_async(
            lambda: RawInfo.objects.select_related('source').get(id=pk),
            thread_sensitive=False,
        )()
    except RawInfo.DoesNotExist:
        return JsonResponse({'error': 'not_found'}, status=404)

    async def event_stream():
        import queue as _queue
        import threading as _threading
        from django.db import close_old_connections
        from apps.analysis.services.analyzer import analyze_one
        from apps.analysis.llm.base import get_provider

        q: _queue.Queue = _queue.Queue()
        SENTINEL_DONE = object()
        result_holder = {'error': None}

        def _worker():
            try:
                analyze_one(
                    info, save=True,
                    on_token=lambda t: q.put(('token', t)),
                    on_thinking=lambda t: q.put(('reasoning', t)),
                )
            except Exception as exc:  # noqa: BLE001
                result_holder['error'] = str(exc)
            finally:
                close_old_connections()
                q.put(('__done__', SENTINEL_DONE))

        try:
            yield _sse('start', {'id': info.id, 'title': info.title})
            await sync_to_async(_push_notify, thread_sensitive=False)(
                {'type': 'intel.analyzing', 'id': info.id})

            # 提示使用的 Provider (让前端可识别 mock vs deepseek)
            try:
                _prov = await sync_to_async(
                    get_provider, thread_sensitive=False)()
                prov_name = _prov.name
                prov_model = getattr(_prov, 'model', '') or ''
            except Exception:
                prov_name = 'unknown'
                prov_model = ''
            yield _sse('thinking', {
                'step': 'llm_call',
                'icon': 'ri-cpu-line',
                'text': (f'[调用 {prov_name} 模型' +
                         (f' / {prov_model}' if prov_model else '') + '] '
                         f'正在将原始情报送入 LLM 进行 '
                         f'PEST 分类 + 4维评分 + 摘要提炼 + 行动建议生成…'),
            })

            # 启动子线程调用真 LLM
            t = _threading.Thread(target=_worker, daemon=True)
            t.start()

            # 从队列透传 token — heartbeat 间隔 1 秒,
            # 使思考阶段 (没有 token 出来) 也能以 1Hz 频率击穿 buffer +
            # 让前端从 F12 Network 即时看到 "响应进行中".
            _t_start = time.time()
            _last_log = _t_start
            _n_token = 0
            _n_reasoning = 0
            while True:
                try:
                    kind, payload = await asyncio.to_thread(
                        q.get, True, 1)
                except _queue.Empty:
                    yield _sse('heartbeat', {
                        'ts': int(time.time()),
                        'elapsed': round(time.time() - _t_start, 1),
                        'tok': _n_token,
                        'rea': _n_reasoning,
                    })
                    continue
                if kind == 'token':
                    _n_token += 1
                    yield _sse('token', {'step': 'llm_call', 'token': payload})
                elif kind == 'reasoning':
                    _n_reasoning += 1
                    # 思考过程专用事件, 前端浮窗左侧"思考模式"双轨流式渲染
                    yield _sse('reasoning', {'step': 'llm_call', 'token': payload})
                elif kind == '__done__':
                    break
                # 每 2 秒后端控制台打一行进度, 方便诊断
                if time.time() - _last_log > 2:
                    print(f'[SSE #{info.id}] +{time.time()-_t_start:.1f}s '
                          f'reasoning={_n_reasoning} token={_n_token}', flush=True)
                    _last_log = time.time()

            await asyncio.to_thread(t.join, 2)

            if result_holder['error']:
                yield _sse('error', {'error': result_holder['error']})
                return

            # 分析完成, 重读 DB
            await sync_to_async(
                info.refresh_from_db, thread_sensitive=False)()

            # 后推思维链 (provider 写回的 chain), 供前端展示"推理过程"
            for st in (info.analysis_chain or []):
                yield _sse('chain', {
                    'step': st.get('step'),
                    'prompt': str(st.get('prompt', ''))[:300],
                    'response': str(st.get('response', '')),
                })

            yield _sse('result', _intel_result_payload(info))
            await sync_to_async(_push_notify, thread_sensitive=False)({
                'type': 'intel.analyzed',
                'id': info.id,
                'title': info.title[:80],
                'impact_score': info.impact_score,
                'pest': info.pest_type,
                'ot': info.opportunity_or_threat,
                'level': info.impact_level,
                'market': info.target_market,
            })

            # 高影响 → 自动调用推送链路 (飞书/邮件/WebSocket)
            try:
                if info.impact_score is not None and info.impact_score >= 8:
                    from apps.notifications.tasks import (
                        send_high_impact_alert,
                    )
                    # bind=True 的 task 不能直接同步调用, 用 .delay()
                    # 调度 (Celery worker 未起时 settings里会 fallback eager)
                    await sync_to_async(
                        send_high_impact_alert.delay,
                        thread_sensitive=False)(info.id)
                    yield _sse('notify', {
                        'channel': 'high_impact',
                        'impact_score': info.impact_score,
                        'message': '高影响情报已调度推送 (飞书/邮件/WebSocket)',
                    })
                else:
                    # 实时推送 (仅当订阅开启时生效)
                    from apps.notifications.tasks import (
                        dispatch_realtime_intel,
                    )
                    await sync_to_async(
                        dispatch_realtime_intel.delay,
                        thread_sensitive=False)(info.id)
                    yield _sse('notify', {
                        'channel': 'realtime',
                        'impact_score': info.impact_score or 0,
                        'message': '实时推送已调度 (仅当实时订阅开启时生效)',
                    })
            except Exception as exc:  # noqa: BLE001
                yield _sse('notify', {
                    'channel': 'error',
                    'message': f'推送调度异常: {exc}',
                })

            yield _sse('done', {'id': info.id})
        except Exception as exc:
            yield _sse('error', {'error': str(exc)})

    async def _wrapped():
        # 起手先发 16KB 注释 padding -- 击穿浏览器/ASGI/Daphne 接收侧缓冲,
        # 否则部分 client 会等 buffer 攒到一定量才触发 onmessage/事件 listener,
        # 表现为 'F12 看到流但 UI 一次性跳出'
        yield ':' + (' ' * 16384) + '\n\n'
        async for chunk in event_stream():
            yield chunk

    response = StreamingHttpResponse(
        _wrapped(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['X-Accel-Buffering'] = 'no'  # Nginx 退出缓冲
    return response


@csrf_exempt
@require_POST
def intel_batch_analyze(request):
    """批量分析: 按 scope 与筛选条件选取 IDs, 后台多线程并发分析.

    Body 示例: {"scope": "today|7d|unanalyzed|top20|top50",
                  "filters": {market, dimension, pest, ot, level, min_score, q, order}}
    """
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        payload = {}

    scope = (payload.get('scope') or 'unanalyzed').strip()
    filters = payload.get('filters') or {}

    qs = RawInfo.objects.all()
    field_map = {
        'market': 'target_market',
        'dimension': 'strategic_dimension',
        'pest': 'pest_type',
        'ot': 'opportunity_or_threat',
        'level': 'impact_level',
    }
    for k, dbf in field_map.items():
        v = filters.get(k)
        if v:
            qs = qs.filter(**{dbf: v})
    if filters.get('min_score'):
        try:
            qs = qs.filter(impact_score__gte=float(filters['min_score']))
        except (TypeError, ValueError):
            pass
    if filters.get('q'):
        kw = str(filters['q'])
        qs = qs.filter(Q(title__icontains=kw) | Q(content__icontains=kw))

    today = timezone.localdate()
    if scope == 'today':
        qs = qs.filter(published_at__date=today)
    elif scope == '7d':
        qs = qs.filter(published_at__date__gte=today - timedelta(days=6))
    elif scope == 'unanalyzed':
        qs = qs.filter(is_processed=False)

    order = filters.get('order') or '-published_at'
    if order in {'-published_at', 'published_at',
                 '-impact_score', 'impact_score'}:
        qs = qs.order_by(order)

    if scope == 'top20':
        qs = qs[:20]
    elif scope == 'top50':
        qs = qs[:50]
    else:
        qs = qs[:200]   # 防御性上限

    ids = list(qs.values_list('id', flat=True))
    if not ids:
        return JsonResponse({'ok': True, 'count': 0,
                             'ids': [], 'scope': scope})

    from apps.intelligence.batch import run_batch_analyze
    run_batch_analyze(ids)
    return JsonResponse({'ok': True, 'count': len(ids),
                         'ids': ids, 'scope': scope})


@require_GET
def intel_timeline(request):
    """事件时间线 API — 按市场与日期返回近 N 天的关键事件.

    查询参数:
        market: 目标市场 (可选, 为空则返回全部)
        days:   回溯天数 (默认 7)
        min_score: 最小影响分 (默认 3)
        limit:  每天最多返回条数 (默认 8)

    返回格式:
        {market, days, total, days: [{date, count, items: [...]}]}
    """
    market = (request.GET.get('market') or '').strip()
    try:
        days = max(1, min(30, int(request.GET.get('days', '7'))))
    except ValueError:
        days = 7
    try:
        min_score = float(request.GET.get('min_score', '3'))
    except ValueError:
        min_score = 3.0
    try:
        per_day = max(1, min(50, int(request.GET.get('limit', '8'))))
    except ValueError:
        per_day = 8

    today = timezone.now().date()
    start = today - timedelta(days=days - 1)

    qs = (RawInfo.objects.filter(
        is_processed=True,
        published_at__date__gte=start,
        published_at__date__lte=today,
    ).select_related('source'))
    if market:
        qs = qs.filter(target_market=market)
    if min_score:
        qs = qs.filter(impact_score__gte=min_score)

    # 按日期分桶, 同一天内按 impact_score 降序
    bucket: dict = {}
    for info in qs.order_by('-impact_score', '-published_at'):
        d = info.published_at.date().isoformat()
        bucket.setdefault(d, []).append(info)

    days_payload = []
    total = 0
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).isoformat()
        items = bucket.get(d, [])[:per_day]
        days_payload.append({
            'date': d,
            'count': len(bucket.get(d, [])),
            'items': [{
                'id': info.id,
                'title': info.title[:120],
                'summary': (info.summary or '')[:160],
                'pest': info.pest_type,
                'ot': info.opportunity_or_threat,
                'level': info.impact_level,
                'impact_score': info.impact_score,
                'dimension': info.strategic_dimension,
                'dimension_label': info.get_strategic_dimension_display(),
                'market': info.target_market,
                'advice': (info.action_advice or '')[:200],
                'published_at': info.published_at.isoformat()
                                if info.published_at else None,
                'source': info.source.name if info.source_id else None,
                'url': info.url,
                'is_simulated': info.is_simulated,
            } for info in items],
        })
        total += len(bucket.get(d, []))

    return JsonResponse({
        'market': market or 'all',
        'days': days,
        'min_score': min_score,
        'total': total,
        'timeline': days_payload,
    })


@require_GET
def intel_kpi(request):
    """驾驶舱核心 KPI."""
    today = timezone.now().date()
    last_7d = timezone.now() - timedelta(days=7)
    last_24h = timezone.now() - timedelta(hours=24)

    base = RawInfo.objects.filter(is_processed=True)

    total = base.count()
    new_24h = base.filter(fetched_at__gte=last_24h).count()
    high_impact = base.filter(impact_score__gte=8).count()
    high_impact_24h = base.filter(impact_score__gte=8,
                                  fetched_at__gte=last_24h).count()

    pest_dist = list(
        base.filter(fetched_at__gte=last_7d)
        .exclude(pest_type='')
        .values('pest_type').annotate(cnt=Count('id')))

    dim_dist = list(
        base.filter(fetched_at__gte=last_7d)
        .exclude(strategic_dimension='')
        .values('strategic_dimension').annotate(cnt=Count('id'))
        .order_by('-cnt'))

    market_dist = list(
        base.filter(fetched_at__gte=last_7d)
        .exclude(target_market='')
        .values('target_market').annotate(
            cnt=Count('id'), avg_score=Avg('impact_score'))
        .order_by('-cnt')[:10])

    ot_dist = list(
        base.filter(fetched_at__gte=last_7d)
        .exclude(opportunity_or_threat='')
        .values('opportunity_or_threat').annotate(cnt=Count('id')))

    level_dist = list(
        base.filter(fetched_at__gte=last_7d)
        .exclude(impact_level='')
        .values('impact_level').annotate(cnt=Count('id')))

    daily_trend = []
    for i in range(7):
        d = today - timedelta(days=6 - i)
        cnt = base.filter(fetched_at__date=d).count()
        daily_trend.append({'date': d.isoformat(), 'count': cnt})

    return JsonResponse({
        'total': total,
        'new_24h': new_24h,
        'high_impact': high_impact,
        'high_impact_24h': high_impact_24h,
        'pest_distribution': pest_dist,
        'dimension_distribution': dim_dist,
        'market_top10': market_dist,
        'ot_distribution': ot_dist,
        'level_distribution': level_dist,
        'daily_trend': daily_trend,
    })
