"""信息源 App 的 Celery 异步任务 — 触发采集 / 模拟新数据增量 / 降级兜底."""
import logging
import random

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.sources.models import CrawlJob, InfoSource
from apps.sources.services import fallback as fb
from apps.sources.services import tier_switch as tier


logger = logging.getLogger(__name__)


@shared_task(name='apps.sources.tasks.crawl_active_sources')
def crawl_active_sources(limit: int = 5) -> dict:
    """周期性触发活跃信息源的采集 — 仅调度被允许 access_tier 的信息源.

    访问层级开关 (free / register / paid) 由 settings 页面 toggle 控制;
    未启用的 tier 下的信息源不会进入采集队列, 从源头避免未注册 spider 产生异常噪音.
    """
    allowed = tier.enabled_tiers()
    qs = (InfoSource.objects
          .filter(is_active=True, access_tier__in=allowed)
          .order_by('?')[:limit])
    triggered = []
    for src in qs:
        crawl_one_source.delay(src.id)
        triggered.append(src.name)
    logger.info('crawl_active_sources triggered=%s mode=%s allowed_tiers=%s',
                triggered, fb.get_mode(), allowed)
    return {'triggered': triggered, 'count': len(triggered),
            'mode': fb.get_mode(), 'allowed_tiers': allowed}


@shared_task(name='apps.sources.tasks.crawl_one_source', bind=True)
def crawl_one_source(self, source_id: int) -> dict:
    """单源采集任务: 按 DATA_SOURCE_MODE 决定真实采集 / 仿真兑底.

    流程:
      0. Redis 分布式锁 (SETNX): 同一源同一时刻只允许一个 worker 上手,
         避免 Beat 与手动触发并发重复采集 / 重复插入 RawInfo.
      1. 读取全局模式 + 该源连续失败次数 -> 决定本次走真实 or 仿真
      2. 真实分支调用 _real_crawl (已接入多个官方 RSS/API); 失败累计计数
      3. auto 模式下真实失败且开启 FALLBACK_ON_FAILURE 时再用仿真补一条, 简报永不空
    """
    try:
        src = InfoSource.objects.get(id=source_id)
    except InfoSource.DoesNotExist:
        return {'error': 'source_not_found', 'source_id': source_id}

    # ---- 分布式锁: 同一 source 同时只允许一个 worker 进入采集 ----
    # TTL 与 crawl_interval 对齐, 避免锁泄露后又被同调度周期抢到
    lock_key = f'crawl:lock:source:{source_id}'
    lock_ttl = max(60, int(getattr(src, 'crawl_interval', 0) or 600))
    try:
        from django.core.cache import cache
        # cache.add() 是原子 SETNX 语义: 仅在 key 不存在时才写入
        if not cache.add(lock_key, '1', timeout=lock_ttl):
            logger.info('[crawl] skip: another worker holding lock for %s',
                        src.name)
            return {'skipped': True, 'reason': 'locked',
                    'source': src.name, 'source_id': source_id}
    except Exception as exc:  # 锁服务异常不能阻断业务, 记警告后继续
        logger.warning('[crawl] lock acquire failed (continuing): %s', exc)

    try:
        return _do_crawl_one_source(self, src)
    finally:
        try:
            from django.core.cache import cache
            cache.delete(lock_key)
        except Exception:
            pass


def _do_crawl_one_source(task_self, src: InfoSource) -> dict:
    """单源采集的实际业务逻辑 — 从 crawl_one_source 中剖出,
    以便在上层统一加锁 / 释锁.
    """
    source_id = src.id

    # 访问层级开关 — 未启用的 tier 直接跳过, 不走采集也不走仿真
    # (避免未接入的 register/paid 源产生错误噪音 + 污染失败计数)
    if not tier.is_source_allowed(src):
        try:
            fb.reset_failure(src)  # 顺手清掍可能的历史脏数据
            src.last_status = 'skipped'
            src.last_message = (
                f'access_tier={src.access_tier} 已在配置页关闭; '
                f'启用后才会进入采集队列')
            src.save(update_fields=['last_status', 'last_message', 'updated_at'])
        except Exception:
            pass
        return {'skipped': True, 'reason': 'tier_disabled',
                'access_tier': src.access_tier, 'source': src.name}

    mode = fb.get_mode()
    use_sim = fb.should_use_simulation(src)
    job = CrawlJob.objects.create(
        source=src, status='running',
        triggered_by=f'celery:{mode}{":sim" if use_sim else ""}')

    created = 0
    fetched = 0
    fallback_used = False
    error_msg = ''

    try:
        if use_sim:
            # 仿真分支 — 强制走模板生成, 不会失败
            created = fb.run_simulation(src)
            fetched = created
            src.last_status = 'simulated'
            src.last_message = f'仿真兜底 +{created} 条'
        else:
            # 真实分支 — 仅 FRED / WorldBank / GDELT 三个有真实实现
            try:
                fetched, created = _real_crawl(src)
                fb.reset_failure(src)
                src.last_status = 'completed'
                src.last_message = f'真实采集 +{created} 条'
            except NotImplementedError as exc:
                # 该信息源未注册真实 spider — 不计失败计数, 直接仿真兜底
                # (在 "强制真实" 总开关下避免大量未接入源报错, 仅 INFO 日志)
                logger.info('[crawl] no real spider for source=%s, '
                            'use simulation: %s', src.name, exc)
                # 关键: 主动清除可能由早期版本遗留的脏失败计数/错误文案,
                # 避免在 settings 页面 "异常信息源" 列表里一直资考老错误消息.
                fb.reset_failure(src)
                created = fb.run_simulation(src)
                fetched = created
                fallback_used = True
                src.last_status = 'fallback'
                src.last_message = f'未注册真实采集器; 仿真兜底 +{created} 条'
            except Exception as exc:
                error_msg = str(exc)
                fail_n = fb.record_failure(src, error_msg)
                logger.warning('[crawl] real failed source=%s err=%s n=%s',
                               src.name, error_msg, fail_n)
                # auto 模式: 真实失败但允许兜底, 立即用仿真补一条避免简报为空
                if mode == 'auto' and getattr(settings, 'FALLBACK_ON_FAILURE', True):
                    created = fb.run_simulation(src)
                    fetched = created
                    fallback_used = True
                    src.last_status = 'fallback'
                    src.last_message = f'真实失败({error_msg[:80]}); 仿真兜底 +{created} 条'
                else:
                    raise

        # 触发下游分析
        if created:
            from apps.intelligence.tasks import analyze_pending_intel
            analyze_pending_intel.delay()

        # 更新 job
        job.status = 'completed'
        job.finished_at = timezone.now()
        job.items_fetched = fetched
        job.items_new = created
        if fallback_used:
            job.error_log = f'real_fail_then_simulated: {error_msg}'
        job.save()

        # 更新 source
        src.last_crawled_at = timezone.now()
        src.save(update_fields=[
            'last_crawled_at', 'last_status', 'last_message', 'updated_at'])

        _push_dashboard_event({
            'type': 'crawl.completed',
            'source': src.name,
            'items_new': created,
            'mode': mode,
            'simulated': use_sim or fallback_used,
            'fallback_used': fallback_used,
        })

        return {
            'source': src.name,
            'created': created,
            'mode': mode,
            'simulated': use_sim or fallback_used,
            'fallback_used': fallback_used,
        }

    except Exception as exc:
        job.status = 'failed'
        job.error_log = str(exc)
        job.finished_at = timezone.now()
        job.save()
        logger.exception('crawl failed: %s', exc)
        _push_dashboard_event({
            'type': 'crawl.failed',
            'source': src.name,
            'error': str(exc)[:160],
            'mode': mode,
        })
        return {'error': str(exc), 'source_id': source_id, 'mode': mode}


def _real_crawl(src: InfoSource) -> tuple[int, int]:
    """真实采集入口 — 按 spider_name + name + url 关键词路由到对应采集器.

    已实现的采集器 (按领域):
      宏观金融:  FRED / World Bank / IMF / ECB / Eurostat / Frankfurter 汇率
      事件新闻:  GDELT / RSS 联播 (BBC/Guardian/CNN/NPR/Al Jazeera)
      公司披露:  SEC EDGAR (Apple/Microsoft/Amazon/Alphabet)
      科技趋势:  GitHub / Hacker News (Firebase + Algolia) / arXiv / OpenAlex
      社交舆情:  Reddit (热门贴子)
      加密市场:  CoinGecko
      法规:        Federal Register (美国联邦公报)
      限险:        USGS Earthquake (全球地震事件)
      国家画像:  REST Countries

    dispatch 内部先使用 SPIDER_REGISTRY 精确匹配, 未命中则用
    spider_name + InfoSource.name + InfoSource.official_url + list_url
    拼接后的 lower() 字串进行关键词 substring 匹配, 让中文名下的
    spider_name (如 spider_fred_圣路易斯联储_) 也能正确路由.
    未命中任何路由 → NotImplementedError, 交上层降级链路处理.
    返回: (fetched_count, created_count)
    """
    from apps.sources.services.real_crawler import dispatch
    return dispatch(src)


def _push_dashboard_event(payload: dict):
    """通过 Channels Group 推送驾驶舱事件(同步上下文)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            'dashboard.broadcast',
            {'type': 'dashboard.event', 'payload': payload},
        )
    except Exception as exc:
        logger.warning('push dashboard event failed: %s', exc)
