"""情报批量分析 — 多线程并发 + WebSocket 实时 token 流式推送.

设计:
- run_batch_analyze(ids): 提交后台守护线程, 不阻塞 HTTP 响应.
- 线程池 ThreadPoolExecutor 并发执行 analyze_one(单条 LLM 链路).
- 每条情报开始/结束时通过 channels.layers.group_send 向
  notifications.broadcast 群组推送 intel.analyzing / intel.analyzed
  事件, 前端 sr:ws 监听后实时切换列表项的状态指示.
- 同时 LLM 每产出一段 delta token 都会立即推送 intel.token 事件 —
  带上 info_id 供前端按 id 分流显示“流式输出”面板.
  为避免 WebSocket 频道被淹没, 按 80ms 或 ≥8 个 token 批量刷出.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# 默认并发线程数 — 与 LLM Mock 计算量匹配, 太大反而上下文切换抖动
_MAX_WORKERS = 4

# token 批量刷出节流参数
_TOKEN_FLUSH_MS = 80
_TOKEN_FLUSH_N = 8


def run_batch_analyze(ids: list[int]) -> None:
    """启动后台线程池执行批量分析."""
    t = threading.Thread(
        target=_worker, args=(list(ids),),
        daemon=True, name='intel-batch-analyze')
    t.start()


def _worker(ids: list[int]) -> None:
    from apps.intelligence.models import RawInfo
    from apps.analysis.services.analyzer import analyze_one

    _push({'type': 'intel.batch_start',
           'count': len(ids), 'ids': ids})

    # 提前广播每条 analyzing 状态, 让前端列表立即转圈
    for i in ids:
        _push({'type': 'intel.analyzing', 'id': i})

    success = 0
    failed = 0
    lock = threading.Lock()

    def _make_token_pusher(info_id: int):
        """为某条情报创建一个节流的 on_token 回调 — 80ms 或 ≥8 token 批量刷出."""
        buffer: list[str] = []
        last_flush = [time.time()]
        idx = [0]
        b_lock = threading.Lock()

        def _flush():
            if not buffer:
                return
            text = ''.join(buffer)
            buffer.clear()
            last_flush[0] = time.time()
            idx[0] += 1
            logger.info('[batch.token] id=%s idx=%s len=%s sample=%r',
                        info_id, idx[0], len(text), text[:30])
            _push({
                'type': 'intel.token',
                'id': info_id,
                'token': text,
                'idx': idx[0],
            })

        def cb(tok: str):
            with b_lock:
                buffer.append(tok)
                now = time.time()
                if (len(buffer) >= _TOKEN_FLUSH_N
                        or (now - last_flush[0]) * 1000 >= _TOKEN_FLUSH_MS):
                    _flush()

        def cb_finalize():
            with b_lock:
                _flush()

        return cb, cb_finalize

    def _do(info_id: int) -> None:
        nonlocal success, failed
        try:
            info = RawInfo.objects.get(id=info_id)

            # ---- LLM 结果缓存 (按 content_hash + provider + model) ----
            # 同一条情报 + 同一模型近期已分析过 -> 直接复用结果, 不重复消耗 token.
            # TTL 24h, 必要时业务可调用 cache.delete 强刷.
            cache_payload = _try_load_cached_analysis(info)
            if cache_payload is not None:
                _apply_cached_analysis(info, cache_payload)
                if on_token := _make_token_pusher(info.id)[0]:
                    pass  # 不需要 token 流 (缓存命中)
                with lock:
                    success += 1
                _push({
                    'type': 'intel.analyzed',
                    'id': info.id,
                    'title': info.title[:80],
                    'impact_score': info.impact_score,
                    'pest': info.pest_type,
                    'ot': info.opportunity_or_threat,
                    'level': info.impact_level,
                    'market': info.target_market,
                    'cached': True,
                })
                return

            on_token, finalize = _make_token_pusher(info.id)
            # 同步传入 on_token 回调, LLM 每输出一段 delta 就推 WebSocket
            analyze_one(info, save=True, on_token=on_token)
            finalize()  # 刷出末尾未达阈值的 buffer
            # 分析成功后写缓存 (以 content_hash 为 key)
            try:
                _save_cached_analysis(info)
            except Exception:  # noqa: BLE001
                logger.debug('save cached analysis failed id=%s', info_id)
            with lock:
                success += 1
            _push({
                'type': 'intel.analyzed',
                'id': info.id,
                'title': info.title[:80],
                'impact_score': info.impact_score,
                'pest': info.pest_type,
                'ot': info.opportunity_or_threat,
                'level': info.impact_level,
                'market': info.target_market,
            })
            # 高影响则调度推送链路 (飞书/邮件/WS), 与单条分析 SSE 保持一致
            try:
                if info.impact_score is not None and info.impact_score >= 8:
                    from apps.notifications.tasks import send_high_impact_alert
                    send_high_impact_alert.delay(info.id)
                else:
                    from apps.notifications.tasks import dispatch_realtime_intel
                    dispatch_realtime_intel.delay(info.id)
            except Exception:  # noqa: BLE001
                logger.exception('batch dispatch notification fail id=%s', info_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception('batch analyze fail id=%s', info_id)
            with lock:
                failed += 1
            _push({'type': 'intel.analyze_failed',
                   'id': info_id, 'error': str(exc)})

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS,
                            thread_name_prefix='ai-worker') as pool:
        for fid in ids:
            pool.submit(_do, fid)

    _push({'type': 'intel.batch_done',
           'count': len(ids), 'success': success, 'failed': failed})


def _push(payload: dict) -> None:
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            logger.warning('[batch._push] channel_layer is None, payload=%s',
                           payload.get('type'))
            return
        async_to_sync(layer.group_send)(
            'notifications.broadcast',
            {'type': 'notify', 'payload': payload},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('push intel event failed: %s payload=%s',
                       exc, payload.get('type'))


# ============================================================
# LLM 结果缓存 — 按 content_hash 避免重复消耗 token
# ============================================================
_LLM_CACHE_TTL = 24 * 3600  # 24h
_LLM_CACHE_VERSION = 'v1'


def _llm_cache_key(info) -> str:
    """生成缓存 key: 包含 content_hash + LLM provider + model + version.
    换 provider/model 或 加载新 prompt 版本时 key 变动 → 自动失效旧缓存.
    """
    import hashlib
    from django.conf import settings
    text = ((info.title or '') + '|' + (info.content or ''))[:8000]
    h = hashlib.md5(text.encode('utf-8')).hexdigest()
    provider = (getattr(settings, 'LLM_PROVIDER', '') or 'mock').lower()
    model = getattr(settings, 'LLM_MODEL', '') or ''
    return f'llm:analysis:{_LLM_CACHE_VERSION}:{provider}:{model}:{h}'


def _try_load_cached_analysis(info) -> dict | None:
    try:
        from django.core.cache import cache
        return cache.get(_llm_cache_key(info))
    except Exception:  # noqa: BLE001
        return None


def _save_cached_analysis(info) -> None:
    """从已分析完的 RawInfo 提取结构化字段并写缓存."""
    try:
        from django.core.cache import cache
        payload = {
            'pest_type': info.pest_type,
            'opportunity_or_threat': info.opportunity_or_threat,
            'impact_level': info.impact_level,
            'impact_type': info.impact_type,
            'severity': info.severity,
            'sentiment': info.sentiment,
            'score_relevance': info.score_relevance,
            'score_urgency': info.score_urgency,
            'score_authority': info.score_authority,
            'score_scope': info.score_scope,
            'impact_score': info.impact_score,
            'summary': info.summary,
            'rationale': getattr(info, 'rationale', ''),
            'action_advice': info.action_advice,
            'tags': list(info.tags or []),
            'analysis_chain': list(getattr(info, 'analysis_chain', []) or []),
        }
        cache.set(_llm_cache_key(info), payload, timeout=_LLM_CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass


def _apply_cached_analysis(info, payload: dict) -> None:
    """将缓存中的结果回填到 RawInfo 并落库."""
    fields = []
    for k, v in (payload or {}).items():
        if hasattr(info, k):
            try:
                setattr(info, k, v)
                fields.append(k)
            except Exception:
                continue
    info.is_processed = True
    fields.append('is_processed')
    try:
        info.save(update_fields=list(set(fields)))
    except Exception:
        info.save()  # 字段冲突时全量保存兑底
