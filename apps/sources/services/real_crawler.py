"""真实 API 采集器 — 对接 FRED / World Bank / GDELT 三个完全免费的公开 REST API.

设计原则:
- 每个适配器函数接收 InfoSource 对象, 返回 (fetched, created) 元组;
- 成功创建的记录写入 RawInfo(is_simulated=False);
- URL 唯一冲突(重复情报)被安全跳过, 不计入 created;
- 任何网络/解析异常向上抛出, 由上层 _real_crawl 捕获走降级链路.

使用方式 (通过 spider_name 路由):
    spider_fred        → crawl_fred()
    spider_world_bank  → crawl_world_bank()
    spider_gdelt       → crawl_gdelt()
"""
from __future__ import annotations

import hashlib
import logging
import random
import ssl
import time
import urllib.request
import urllib.parse
import urllib.error
import json as _json
import xml.etree.ElementTree as _ET
from datetime import datetime, timezone as _tz
from typing import Tuple

from django.utils import timezone

logger = logging.getLogger(__name__)

# 最大单次请求条数 — 提升至 12 让真实数据更密集
MAX_ITEMS = 12

# 战略维度合法值 (与 RawInfo.DIMENSION_CHOICES 对齐)
# 采集器历史上误用了 'technology' / 'company' 等非法值 (Django choices 不在 save 时强校验,
# 会被直接落库, 导致前端图表出现未翻译的英文标签). 在落库前统一映射到合法枚举.
_VALID_DIMENSIONS = {
    'competition', 'product', 'platform', 'social',
    'regulation', 'macro', 'industry', 'other',
}
_DIMENSION_ALIAS = {
    'technology': 'industry',   # 科技行业资讯 (HN / GitHub / arxiv / Reddit / OpenAlex)
    'company': 'competition',   # 上市公司披露 (SEC EDGAR) → 竞争情报
    'artificial': 'industry',
}


def _normalize_dimension(dim: str) -> str:
    """把采集器传入的 dimension 规范化为模型允许的枚举值."""
    if not dim:
        return ''
    d = dim.strip().lower()
    d = _DIMENSION_ALIAS.get(d, d)
    return d if d in _VALID_DIMENSIONS else 'other'

# 多 UA 轮换降低被反爬概率
_UA_POOL = [
    'StrategicRadar/1.0 (+https://strategic-radar.local)',
    ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
     '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
     '(KHTML, like Gecko) Version/17.5 Safari/605.1.15'),
]


def _make_ssl_context() -> ssl.SSLContext:
    """构造 SSL Context — 优先用 certifi 证书链; 后续HTTPS 请求复用.

    Windows 上某些 Python 环境默认 SSL Context 不加载系统证书链 →
    造成 CERTIFICATE_VERIFY_FAILED. 优先使用 certifi (与 requests 同一证书包).
    """
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL_CTX = _make_ssl_context()

# FRED 免费指标列表 (需 API Key, 在 https://fred.stlouisfed.org/docs/api/api_key.html 免费申请)
FRED_SERIES = [
    ('CPIAUCSL', '美国 CPI — 城市所有消费者', 'US', 'macro'),
    ('UNRATE', '美国失业率', 'US', 'macro'),
    ('FEDFUNDS', '美联储基准利率', 'US', 'macro'),
    ('DEXUSEU', '美元/欧元汇率', 'EU', 'macro'),
    ('DEXCHUS', '人民币/美元汇率', 'global', 'macro'),
]


def _fred_api_key() -> str:
    """读取 FRED API Key (优先 settings.FRED_API_KEY → env → 演示默认 key).

    生产环境应在 .env 设置 FRED_API_KEY=xxx (在 fred.stlouisfed.org 免费申请).
    默认 key 可能被限流或失效 → 此时仅依赖 .env 中的 key.
    """
    import os
    from django.conf import settings
    return (getattr(settings, 'FRED_API_KEY', None)
            or os.environ.get('FRED_API_KEY', '')
            or '***REDACTED-FRED-KEY***')

# World Bank 免费指标
WB_INDICATORS = [
    ('NY.GDP.MKTP.CD', 'GDP (当前美元)', 'global', 'macro'),
    ('NE.EXP.GNFS.ZS', '出口占 GDP 比率', 'global', 'macro'),
    ('FP.CPI.TOTL.ZG', '消费者价格通胀', 'global', 'macro'),
]

# GDELT 查询关键词
GDELT_QUERIES = [
    ('trade tariff export', 'global', 'regulation'),
    ('amazon tiktok platform policy', 'US', 'platform'),
    ('ai artificial intelligence regulation', 'global', 'technology'),
]


# 统一 HTTP 默认超时 (P2-2): 替代散落的 15/20/30s, 与 Celery 任务节拍一致
HTTP_DEFAULT_TIMEOUT = 30


def _http_get(url: str, timeout: int | None = None, headers: dict | None = None,
              retries: int = 1) -> bytes:
    """HTTP GET 原始字节.

    特性 (P2-2 收敛):
      - UA 轮换 + 指数回退重试 + certifi SSL 证书链
      - 默认 timeout=HTTP_DEFAULT_TIMEOUT (30s) 统一节拍
      - Accept-Encoding: gzip, deflate (自动解压, 减少 ~70% RSS/JSON 带宽)
      - Connection: keep-alive (HTTP/1.1 保持单次会话内连接)
      - 失败抛 RuntimeError
    """
    if timeout is None:
        timeout = HTTP_DEFAULT_TIMEOUT
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        ua = random.choice(_UA_POOL)
        h = {
            'User-Agent': ua,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9,zh;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                raw = resp.read()
                enc = (resp.headers.get('Content-Encoding') or '').lower()
                if enc == 'gzip':
                    import gzip as _gz
                    try:
                        raw = _gz.decompress(raw)
                    except Exception:
                        pass
                elif enc == 'deflate':
                    import zlib as _zl
                    try:
                        raw = _zl.decompress(raw)
                    except Exception:
                        try:
                            raw = _zl.decompress(raw, -_zl.MAX_WBITS)
                        except Exception:
                            pass
                return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < retries:
                # 指数回退: 0.6s, 1.2s
                time.sleep(0.6 * (2 ** attempt) + random.random() * 0.4)
                continue
    raise RuntimeError(f'GET {url} failed after {retries + 1} attempts: {last_exc}')


def _safe_get(url: str, timeout: int = 15) -> dict | list:
    """HTTP GET, 返回解析后的 JSON. 内置 UA 轮换 + 重试."""
    raw = _http_get(url, timeout=timeout)
    return _json.loads(raw.decode('utf-8', errors='replace'))


def _safe_get_text(url: str, timeout: int = 15, headers: dict | None = None) -> str:
    """HTTP GET, 返回文本(用于 RSS/XML/HTML)."""
    raw = _http_get(url, timeout=timeout, headers=headers)
    return raw.decode('utf-8', errors='replace')


def _snapshot_url(canonical: str, suffix: str = '') -> str:
    """在真实数据集页面 URL 上挂 ?snapshot=hash 凑成唯一、可点击跳转的 URL.

    适用于 “指标类” 采集 (FRED/WorldBank/IMF/ECB/Eurostat/Frankfurter 等) ,
    这些源本身只返回数值, 没有 “原文链接” 概念,
    但它们都有对应的公开数据集页面 (如 fred.stlouisfed.org/series/GDPC1) ,
    点进去就能看到同一序列的历史曲线。
    """
    slug = hashlib.md5(f'{canonical}|{suffix}'.encode()).hexdigest()[:12]
    sep = '&' if '?' in canonical else '?'
    return f'{canonical}{sep}snapshot={slug}'[:599]


def _pick_url(real_url: str | None, fallback_canonical: str,
              fallback_suffix: str = '') -> str:
    """优先使用真实原文 URL; 若为空 / 非 http 则在 fallback_canonical 上挂 snapshot."""
    if real_url and isinstance(real_url, str):
        u = real_url.strip()
        # 拒绝伪 URL 以及那个古老的错误域名
        if (u.startswith(('http://', 'https://'))
                and 'strategic-radar.local' not in u):
            return u[:599]
    return _snapshot_url(fallback_canonical, fallback_suffix)


def _make_url(base_title: str, source_name: str, suffix: str = '') -> str:
    """[废弃] 早期各采集器用的占位 URL 生成器, 已被 _pick_url/_snapshot_url 取代.

    仅为向后兼容保留, 并重定向到 _snapshot_url 以避免继续产生伪域名.
    新代码请不要再调用本函数.
    """
    canonical = f'https://data.strategic-radar.example/snapshot/{source_name}'
    return _snapshot_url(canonical, f'{base_title}|{suffix}')


def _upsert_raw_info(source, title: str, content: str, url: str,
                     published_at: datetime, market: str, dimension: str) -> bool:
    """创建 RawInfo, 遇 unique 冲突返回 False (已存在)."""
    from apps.intelligence.models import RawInfo
    try:
        RawInfo.objects.create(
            source=source,
            title=title[:499],
            content=content,
            url=url[:599],
            published_at=published_at,
            target_market=market,
            strategic_dimension=_normalize_dimension(dimension),
            is_simulated=False,
            is_processed=False,
        )
        return True
    except Exception:
        return False


# ============================================================
# FRED 采集器 (圣路易斯联储, 无需 API Key)
# ============================================================
def crawl_fred(source) -> Tuple[int, int]:
    """采集 FRED 最新宏观指标数据."""
    fetched = 0
    created = 0

    fred_key = _fred_api_key()
    for series_id, label, market, dimension in FRED_SERIES[:MAX_ITEMS]:
        url = (
            f'https://api.stlouisfed.org/fred/series/observations'
            f'?series_id={series_id}&limit=1&sort_order=desc'
            f'&file_type=json&api_key={fred_key}'
        )
        try:
            data = _safe_get(url)
            obs = data.get('observations', [])
            if not obs:
                continue
            obs = obs[0]
            value = obs.get('value', 'N/A')
            date_str = obs.get('date', '')

            try:
                pub_at = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=_tz.utc)
            except Exception:
                pub_at = timezone.now()

            title = f'[FRED] {label}: {value} ({date_str})'
            content = (
                f'{label} (FRED 系列 {series_id}) 最新数据:\n'
                f'日期: {date_str}\n数值: {value}\n'
                f'数据来源: 圣路易斯联储 FRED (fred.stlouisfed.org)'
            )
            raw_url = _snapshot_url(
                f'https://fred.stlouisfed.org/series/{series_id}',
                date_str)
            fetched += 1
            if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dimension):
                created += 1
        except Exception as exc:
            logger.warning('[FRED] series=%s error: %s', series_id, exc)
            continue

    if fetched == 0:
        raise RuntimeError('FRED: no data fetched from any series')
    return fetched, created


# ============================================================
# World Bank 采集器 (完全免费, 无需注册)
# ============================================================
def crawl_world_bank(source) -> Tuple[int, int]:
    """采集 World Bank 最新宏观指标."""
    fetched = 0
    created = 0

    # 取全球最近数据 (mrv=1 = most recent value)
    for indicator, label, market, dimension in WB_INDICATORS[:MAX_ITEMS]:
        url = (
            f'https://api.worldbank.org/v2/country/WLD/indicator/{indicator}'
            f'?format=json&mrv=1&per_page=1'
        )
        try:
            resp = _safe_get(url)
            if not isinstance(resp, list) or len(resp) < 2:
                continue
            records = resp[1]
            if not records:
                continue
            rec = records[0]
            value = rec.get('value')
            date_str = rec.get('date', '')
            country = rec.get('country', {}).get('value', 'Global')

            if value is None:
                continue

            try:
                pub_at = datetime.strptime(date_str, '%Y').replace(
                    month=12, day=31, tzinfo=_tz.utc)
            except Exception:
                pub_at = timezone.now()

            title = f'[World Bank] {label}: {value:.2e} ({date_str})'
            content = (
                f'{label} — {country} 最新数据:\n'
                f'年份: {date_str}\n数值: {value}\n指标代码: {indicator}\n'
                f'数据来源: 世界银行 Open Data (data.worldbank.org)'
            )
            raw_url = _snapshot_url(
                f'https://data.worldbank.org/indicator/{indicator}',
                date_str)
            fetched += 1
            if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dimension):
                created += 1
        except Exception as exc:
            logger.warning('[WorldBank] indicator=%s error: %s', indicator, exc)
            continue

    if fetched == 0:
        raise RuntimeError('World Bank: no data fetched')
    return fetched, created


# ============================================================
# GDELT 采集器 (DOC 2.0 API, 完全免费)
# ============================================================
def crawl_gdelt(source) -> Tuple[int, int]:
    """采集 GDELT 新闻事件 (按关键词搜索近期文章)."""
    fetched = 0
    created = 0

    for query, market, dimension in GDELT_QUERIES:
        encoded = urllib.parse.quote(query)
        url = (
            f'https://api.gdeltproject.org/api/v2/doc/doc'
            f'?query={encoded}&mode=artlist&maxrecords=5&format=json'
            f'&timespan=1d&sort=DateDesc'
        )
        try:
            data = _safe_get(url, timeout=20)
            articles = data.get('articles', [])
            if not articles:
                continue
            for art in articles[:5]:
                title_raw = (art.get('title') or '').strip()
                if not title_raw:
                    continue
                art_url = art.get('url', '')
                domain = art.get('domain', '')
                seendate = art.get('seendate', '')
                lang = art.get('language', 'EN')

                try:
                    pub_at = datetime.strptime(seendate, '%Y%m%dT%H%M%SZ').replace(
                        tzinfo=_tz.utc)
                except Exception:
                    pub_at = timezone.now()

                title = f'[GDELT] {title_raw[:150]}'
                content = (
                    f'来源: {domain}\n语言: {lang}\n标题: {title_raw}\n'
                    f'关联查询: {query}\n原文: {art_url}\n'
                    f'数据来源: GDELT Project (gdeltproject.org)'
                )
                raw_url = _pick_url(
                    art_url,
                    'https://api.gdeltproject.org/api/v2/doc',
                    f'{query}|{art_url[:60]}')
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dimension):
                    created += 1
        except Exception as exc:
            logger.warning('[GDELT] query=%s error: %s', query, exc)
            continue

    if fetched == 0:
        raise RuntimeError('GDELT: no articles fetched')
    return fetched, created


# ============================================================
# IMF DataMapper 采集器 (免费无 Key, 官方 REST API)
# ============================================================
IMF_INDICATORS = [
    ('NGDP_RPCH', 'GDP 实际增速', 'global', 'macro'),
    ('PCPIPCH', 'CPI 通胀率', 'global', 'macro'),
    ('LUR', '失业率', 'global', 'macro'),
    ('GGXWDG_NGDP', '一般政府总债务/GDP', 'global', 'macro'),
]
# IMF DataMapper 重点国家 (CHN/USA/EUR/JPN)
IMF_COUNTRIES = ['USA', 'CHN', 'JPN', 'DEU']


def crawl_imf(source) -> Tuple[int, int]:
    """采集 IMF DataMapper 最新宏观指标 (免费无 Key)."""
    fetched = 0
    created = 0
    for indicator, label, _market, dimension in IMF_INDICATORS:
        url = (
            f'https://www.imf.org/external/datamapper/api/v1/'
            f'{indicator}/{"/".join(IMF_COUNTRIES)}'
        )
        try:
            data = _safe_get(url, timeout=20)
            values = (data or {}).get('values', {}).get(indicator, {})
            for country, year_map in values.items():
                if not isinstance(year_map, dict) or not year_map:
                    continue
                # 取最新年份
                latest_year = max(year_map.keys(), key=lambda y: str(y))
                value = year_map.get(latest_year)
                if value is None:
                    continue
                try:
                    pub_at = datetime(int(latest_year), 12, 31, tzinfo=_tz.utc)
                except Exception:
                    pub_at = timezone.now()
                title = f'[IMF] {country} {label}: {value} ({latest_year})'
                content = (
                    f'IMF DataMapper 最新数据:\n'
                    f'国家: {country}\n指标: {label} ({indicator})\n'
                    f'年份: {latest_year}\n数值: {value}\n'
                    f'数据来源: IMF (imf.org/external/datamapper)'
                )
                raw_url = _snapshot_url(
                    f'https://www.imf.org/external/datamapper/'
                    f'{indicator}@{country}',
                    str(latest_year))
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at,
                                    country.lower(), dimension):
                    created += 1
        except Exception as exc:
            logger.warning('[IMF] indicator=%s error: %s', indicator, exc)
            continue
    if fetched == 0:
        raise RuntimeError('IMF: no data fetched')
    return fetched, created


# ============================================================
# Hacker News Firebase 采集器 (免费无 Key, 官方 Firebase)
# ============================================================
def crawl_hacker_news(source) -> Tuple[int, int]:
    """采集 HN 首页 topstories 前 N 条 (免费无 Key)."""
    fetched = 0
    created = 0
    try:
        ids = _safe_get(
            'https://hacker-news.firebaseio.com/v0/topstories.json', timeout=15)
    except Exception as exc:
        raise RuntimeError(f'HN topstories fetch failed: {exc}')
    if not isinstance(ids, list):
        raise RuntimeError('HN topstories: unexpected response shape')

    for story_id in ids[:MAX_ITEMS]:
        try:
            item = _safe_get(
                f'https://hacker-news.firebaseio.com/v0/item/{story_id}.json',
                timeout=10)
            if not isinstance(item, dict):
                continue
            title_raw = (item.get('title') or '').strip()
            if not title_raw:
                continue
            art_url = item.get('url') or f'https://news.ycombinator.com/item?id={story_id}'
            score = item.get('score', 0)
            ts = item.get('time')
            try:
                pub_at = datetime.fromtimestamp(int(ts), tz=_tz.utc) if ts else timezone.now()
            except Exception:
                pub_at = timezone.now()
            title = f'[HN] {title_raw[:160]}'
            content = (
                f'标题: {title_raw}\n点赞: {score}\n作者: {item.get("by", "-")}\n'
                f'评论数: {item.get("descendants", 0)}\n原文: {art_url}\n'
                f'数据来源: Hacker News Firebase API'
            )
            raw_url = _pick_url(
                art_url,
                f'https://news.ycombinator.com/item?id={story_id}',
                str(story_id))
            fetched += 1
            if _upsert_raw_info(source, title, content, raw_url, pub_at,
                                'US', 'technology'):
                created += 1
        except Exception as exc:
            logger.warning('[HN] story=%s error: %s', story_id, exc)
            continue
    if fetched == 0:
        raise RuntimeError('HN: no items fetched')
    return fetched, created


# ============================================================
# Algolia HN Search 采集器 (免费无 Key)
# ============================================================
HN_SEARCH_QUERIES = ['AI regulation', 'tariff', 'antitrust']


def crawl_algolia_hn(source) -> Tuple[int, int]:
    """通过 Algolia HN Search API 按关键词检索近期热门 HN 话题."""
    fetched = 0
    created = 0
    for query in HN_SEARCH_QUERIES:
        encoded = urllib.parse.quote(query)
        url = (f'https://hn.algolia.com/api/v1/search_by_date'
               f'?query={encoded}&tags=story&hitsPerPage=5')
        try:
            data = _safe_get(url, timeout=15)
            for hit in (data or {}).get('hits', [])[:5]:
                title_raw = (hit.get('title') or hit.get('story_title') or '').strip()
                if not title_raw:
                    continue
                art_url = hit.get('url') or hit.get('story_url') or ''
                pts = hit.get('points', 0)
                created_at = hit.get('created_at')
                try:
                    pub_at = datetime.fromisoformat(
                        created_at.replace('Z', '+00:00')) if created_at else timezone.now()
                except Exception:
                    pub_at = timezone.now()
                title = f'[Algolia HN] {title_raw[:160]}'
                content = (
                    f'检索词: {query}\n标题: {title_raw}\n点赞: {pts}\n'
                    f'原文: {art_url}\n数据来源: Algolia HN Search API'
                )
                raw_url = _pick_url(
                    art_url,
                    f'https://news.ycombinator.com/item?id='
                    f'{hit.get("objectID", "")}',
                    hit.get('objectID', '') or art_url[:60])
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at,
                                    'global', 'technology'):
                    created += 1
        except Exception as exc:
            logger.warning('[AlgoliaHN] query=%s error: %s', query, exc)
            continue
    if fetched == 0:
        raise RuntimeError('AlgoliaHN: no items fetched')
    return fetched, created


# ============================================================
# SEC EDGAR 采集器 (免费无 Key, 仅需 User-Agent)
# ============================================================
# 追踪重点上市公司 — CIK 号
EDGAR_TARGETS = [
    ('0000320193', 'Apple Inc.'),
    ('0000789019', 'Microsoft Corp.'),
    ('0001018724', 'Amazon.com Inc.'),
    ('0001652044', 'Alphabet Inc.'),
]


def _edgar_get(url: str, timeout: int = 15) -> dict:
    """EDGAR 要求 User-Agent 包含合理联系人信息."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'StrategicRadar research@strategic-radar.local',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _json.loads(resp.read().decode('utf-8'))


def crawl_sec_edgar(source) -> Tuple[int, int]:
    """采集 SEC EDGAR 重点公司最新 8-K/10-Q/10-K 披露 (免费)."""
    fetched = 0
    created = 0
    for cik, company in EDGAR_TARGETS:
        url = f'https://data.sec.gov/submissions/CIK{cik}.json'
        try:
            data = _edgar_get(url, timeout=20)
            recent = (data or {}).get('filings', {}).get('recent', {})
            forms = recent.get('form', []) or []
            dates = recent.get('filingDate', []) or []
            primary = recent.get('primaryDocument', []) or []
            accession = recent.get('accessionNumber', []) or []
            n = min(len(forms), len(dates), 5)
            for i in range(n):
                form = forms[i]
                date = dates[i]
                doc = primary[i] if i < len(primary) else ''
                acc = (accession[i] if i < len(accession) else '').replace('-', '')
                try:
                    pub_at = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=_tz.utc)
                except Exception:
                    pub_at = timezone.now()
                title = f'[SEC EDGAR] {company} {form} 披露 ({date})'
                doc_url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}'
                content = (
                    f'公司: {company} (CIK {cik})\n表格类型: {form}\n披露日: {date}\n'
                    f'原始文档: {doc_url}\n数据来源: SEC EDGAR (data.sec.gov)'
                )
                raw_url = _pick_url(
                    doc_url,
                    'https://www.sec.gov/cgi-bin/browse-edgar',
                    f'{cik}|{form}|{date}')
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at,
                                    'US', 'company'):
                    created += 1
        except Exception as exc:
            logger.warning('[EDGAR] cik=%s error: %s', cik, exc)
            continue
    if fetched == 0:
        raise RuntimeError('SEC EDGAR: no filings fetched')
    return fetched, created


# ============================================================
# REST Countries 采集器 (免费无 Key)
# ============================================================
RC_REGIONS = ['europe', 'asia', 'americas']


def crawl_rest_countries(source) -> Tuple[int, int]:
    """采集各区域主要国家经济/人口画像."""
    fetched = 0
    created = 0
    for region in RC_REGIONS:
        url = (f'https://restcountries.com/v3.1/region/{region}'
               f'?fields=name,population,region,subregion,currencies,capital,cca2')
        try:
            arr = _safe_get(url, timeout=20)
            if not isinstance(arr, list):
                continue
            # 按人口取 Top 4
            arr.sort(key=lambda c: -(c.get('population') or 0))
            for c in arr[:4]:
                name = (c.get('name') or {}).get('common') or ''
                if not name:
                    continue
                pop = c.get('population') or 0
                cap_list = c.get('capital') or []
                cap = cap_list[0] if cap_list else '-'
                cur_keys = list((c.get('currencies') or {}).keys())
                cur = cur_keys[0] if cur_keys else '-'
                title = f'[REST Countries] {name} 画像: 人口 {pop:,} | 首都 {cap}'
                content = (
                    f'国家: {name} ({c.get("cca2", "-")})\n'
                    f'区域: {c.get("region")}/{c.get("subregion")}\n'
                    f'人口: {pop:,}\n首都: {cap}\n货币: {cur}\n'
                    f'数据来源: REST Countries API (restcountries.com)'
                )
                raw_url = _snapshot_url(
                    f'https://restcountries.com/v3.1/name/'
                    f'{urllib.parse.quote(name)}',
                    name)
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, timezone.now(),
                                    region, 'macro'):
                    created += 1
        except Exception as exc:
            logger.warning('[RESTCountries] region=%s error: %s', region, exc)
            continue
    if fetched == 0:
        raise RuntimeError('REST Countries: no data fetched')
    return fetched, created


# ============================================================
# Federal Register 采集器 (美国联邦公报, 免费无 Key)
# ============================================================
def crawl_federal_register(source) -> Tuple[int, int]:
    """采集美国联邦公报最新法规/拟规则 (免费无 Key)."""
    url = (
        'https://www.federalregister.gov/api/v1/documents.json'
        '?per_page=10&order=newest&conditions[type][]=RULE'
        '&conditions[type][]=PRORULE'
    )
    try:
        data = _safe_get(url, timeout=20)
    except Exception as exc:
        raise RuntimeError(f'FederalRegister fetch failed: {exc}')
    fetched = 0
    created = 0
    for doc in (data or {}).get('results', [])[:MAX_ITEMS]:
        title_raw = (doc.get('title') or '').strip()
        if not title_raw:
            continue
        agency = ', '.join([a.get('name', '') for a in (doc.get('agencies') or [])])
        pub_date = doc.get('publication_date') or ''
        doc_type = doc.get('type') or ''
        html_url = doc.get('html_url') or ''
        try:
            pub_at = datetime.strptime(pub_date, '%Y-%m-%d').replace(tzinfo=_tz.utc)
        except Exception:
            pub_at = timezone.now()
        title = f'[FedReg] {doc_type}: {title_raw[:140]}'
        content = (
            f'标题: {title_raw}\n机构: {agency}\n类型: {doc_type}\n'
            f'公报日: {pub_date}\n原文: {html_url}\n'
            f'数据来源: Federal Register API (federalregister.gov)'
        )
        raw_url = _pick_url(
            html_url,
            'https://www.federalregister.gov/documents',
            doc.get('document_number', '') or html_url[:60])
        fetched += 1
        if _upsert_raw_info(source, title, content, raw_url, pub_at,
                            'US', 'regulation'):
            created += 1
    if fetched == 0:
        raise RuntimeError('FederalRegister: no documents fetched')
    return fetched, created


# ============================================================
# USGS Science Data 采集器 (免费无 Key)
# ============================================================
def crawl_usgs(source) -> Tuple[int, int]:
    """采集 USGS 地震事件 (免费无 Key, 近 24h 全球 M4.5+)."""
    url = ('https://earthquake.usgs.gov/earthquakes/feed/v1.0/'
           'summary/4.5_day.geojson')
    try:
        data = _safe_get(url, timeout=20)
    except Exception as exc:
        raise RuntimeError(f'USGS fetch failed: {exc}')
    fetched = 0
    created = 0
    for feat in (data or {}).get('features', [])[:MAX_ITEMS]:
        props = feat.get('properties') or {}
        title_raw = (props.get('title') or props.get('place') or '').strip()
        if not title_raw:
            continue
        mag = props.get('mag')
        place = props.get('place', '')
        ts = props.get('time')
        art_url = props.get('url', '')
        try:
            pub_at = datetime.fromtimestamp(int(ts) / 1000, tz=_tz.utc) if ts else timezone.now()
        except Exception:
            pub_at = timezone.now()
        title = f'[USGS] M{mag} {place}'[:200]
        content = (
            f'震级: M{mag}\n地点: {place}\n时间: {pub_at.isoformat()}\n'
            f'原文: {art_url}\n数据来源: USGS Earthquake Hazards Program'
        )
        raw_url = _pick_url(
            art_url,
            'https://earthquake.usgs.gov/earthquakes/eventpage',
            feat.get('id', '') or art_url[:60])
        fetched += 1
        if _upsert_raw_info(source, title, content, raw_url, pub_at,
                            'global', 'risk'):
            created += 1
    if fetched == 0:
        raise RuntimeError('USGS: no events fetched')
    return fetched, created


# ============================================================
# ECB Data Portal 采集器 (欧洲央行, 免费无 Key, SDMX-JSON)
# ============================================================
# 选取三个高战略性序列: EUR/USD 汇率 / EUR/CNY 汇率 / 主利率
ECB_SERIES = [
    ('EXR/D.USD.EUR.SP00.A', 'EUR/USD 汇率', 'EU', 'macro'),
    ('EXR/D.CNY.EUR.SP00.A', 'EUR/CNY 汇率', 'EU', 'macro'),
    ('EXR/D.JPY.EUR.SP00.A', 'EUR/JPY 汇率', 'EU', 'macro'),
    ('EXR/D.GBP.EUR.SP00.A', 'EUR/GBP 汇率', 'EU', 'macro'),
    ('FM/B.U2.EUR.4F.KR.MRR_FR.LEV', 'ECB 主利率', 'EU', 'macro'),
]


def crawl_ecb(source) -> Tuple[int, int]:
    """采集 ECB 欧洲央行最新宏观数据 (免费无 Key)."""
    fetched = 0
    created = 0
    for series, label, market, dim in ECB_SERIES[:MAX_ITEMS]:
        url = (f'https://data-api.ecb.europa.eu/service/data/{series}'
               f'?format=jsondata&lastNObservations=1')
        try:
            data = _safe_get(url, timeout=20)
            data_sets = (data or {}).get('dataSets') or []
            structure = (data or {}).get('structure') or {}
            if not data_sets:
                continue
            series_map = data_sets[0].get('series') or {}
            time_dims = (structure.get('dimensions') or {}).get('observation') or []
            time_values = (time_dims[0] if time_dims else {}).get('values') or []
            for skey, sval in series_map.items():
                obs = sval.get('observations') or {}
                if not obs:
                    continue
                obs_key, obs_val = next(iter(obs.items()))
                value = obs_val[0] if isinstance(obs_val, list) and obs_val else None
                if value is None:
                    continue
                date_str = ''
                try:
                    idx = int(obs_key.split(':')[0])
                    date_str = (time_values[idx] or {}).get('id', '')
                except Exception:
                    pass
                try:
                    pub_at = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=_tz.utc)
                except Exception:
                    pub_at = timezone.now()
                title = f'[ECB] {label}: {value} ({date_str or "latest"})'
                content = (
                    f'{label} 最新数据:\n日期: {date_str}\n数值: {value}\n'
                    f'序列: {series}\n数据来源: 欧洲央行 ECB Data Portal '
                    f'(data-api.ecb.europa.eu)')
                raw_url = _snapshot_url(
                    f'https://data.ecb.europa.eu/data-detail-api/{series}',
                    date_str)
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dim):
                    created += 1
                break  # 每个 series 取一条最新
        except Exception as exc:
            logger.warning('[ECB] series=%s error: %s', series, exc)
            continue
    if fetched == 0:
        raise RuntimeError('ECB: no data fetched')
    return fetched, created


# ============================================================
# Eurostat 采集器 (欧盟统计局, 免费无 Key, JSON-stat 2.0)
# ============================================================
# 三个核心指标: HICP 通胀率 / 失业率 / GDP 增速
EUROSTAT_DATASETS = [
    ('prc_hicp_manr', '?lastTimePeriod=1&geo=EA&coicop=CP00',
     'HICP 同比通胀率(欧元区)', 'EU', 'macro'),
    ('une_rt_m', '?lastTimePeriod=1&geo=EA&age=TOTAL&sex=T&unit=PC_ACT&s_adj=SA',
     '欧元区失业率', 'EU', 'macro'),
    ('namq_10_gdp', '?lastTimePeriod=1&geo=EA&unit=CLV_PCH_PRE&s_adj=SCA&na_item=B1GQ',
     '欧元区 GDP 环比增速', 'EU', 'macro'),
]


def crawl_eurostat(source) -> Tuple[int, int]:
    """采集 Eurostat 欧盟统计局最新宏观指标 (免费无 Key)."""
    fetched = 0
    created = 0
    for dataset, qs, label, market, dim in EUROSTAT_DATASETS[:MAX_ITEMS]:
        url = (f'https://ec.europa.eu/eurostat/api/dissemination/'
               f'statistics/1.0/data/{dataset}{qs}')
        try:
            data = _safe_get(url, timeout=20)
            values = (data or {}).get('value') or {}
            if not values:
                continue
            time_dim = ((data.get('dimension') or {}).get('time') or {})
            time_idx = (time_dim.get('category') or {}).get('index') or {}
            # 取最新时间点
            latest_period = max(time_idx.keys(), default='') if time_idx else ''
            for k, v in list(values.items())[:5]:
                if v is None:
                    continue
                title = f'[Eurostat] {label}: {v} ({latest_period})'
                content = (
                    f'指标: {label}\n数据集: {dataset}\n期间: {latest_period}\n'
                    f'数值: {v}\n数据来源: 欧盟统计局 Eurostat '
                    f'(ec.europa.eu/eurostat)')
                pub_at = timezone.now()
                try:
                    if latest_period and len(latest_period) >= 4:
                        pub_at = datetime.strptime(latest_period[:7], '%Y-%m').replace(
                            tzinfo=_tz.utc) if '-' in latest_period else \
                            datetime(int(latest_period[:4]), 12, 31, tzinfo=_tz.utc)
                except Exception:
                    pass
                raw_url = _snapshot_url(
                    f'https://ec.europa.eu/eurostat/databrowser/view/{dataset}',
                    f'{latest_period}|{k}')
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dim):
                    created += 1
                break
        except Exception as exc:
            logger.warning('[Eurostat] dataset=%s error: %s', dataset, exc)
            continue
    if fetched == 0:
        raise RuntimeError('Eurostat: no data fetched')
    return fetched, created


# ============================================================
# GitHub Public API 采集器 (免费未认证: 60 次/小时)
# ============================================================
GITHUB_QUERIES = [
    ('stars:>50000 pushed:>2024-01-01', 'global', 'technology'),
    ('topic:llm sort:stars', 'global', 'technology'),
    ('topic:ai-agent sort:stars', 'global', 'technology'),
]


def crawl_github(source) -> Tuple[int, int]:
    """采集 GitHub 热门开源项目 (免费未认证)."""
    fetched = 0
    created = 0
    for query, market, dim in GITHUB_QUERIES:
        encoded = urllib.parse.quote(query)
        url = (f'https://api.github.com/search/repositories'
               f'?q={encoded}&sort=stars&order=desc&per_page=5')
        try:
            data = _safe_get(url, timeout=20)
            for repo in (data or {}).get('items', [])[:5]:
                full_name = repo.get('full_name') or ''
                desc = (repo.get('description') or '').strip()
                stars = repo.get('stargazers_count', 0)
                lang = repo.get('language') or '-'
                html_url = repo.get('html_url') or ''
                pushed_at = repo.get('pushed_at') or ''
                try:
                    pub_at = datetime.fromisoformat(
                        pushed_at.replace('Z', '+00:00')) if pushed_at else timezone.now()
                except Exception:
                    pub_at = timezone.now()
                title = f'[GitHub] {full_name} ★{stars:,}'[:200]
                content = (
                    f'仓库: {full_name}\n语言: {lang}\n★ Stars: {stars:,}\n'
                    f'描述: {desc[:300]}\n最后推送: {pushed_at}\n'
                    f'原文: {html_url}\n数据来源: GitHub Public API (api.github.com)'
                )
                raw_url = _pick_url(
                    html_url,
                    'https://github.com/search',
                    f'{full_name}|{pushed_at}')
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dim):
                    created += 1
        except Exception as exc:
            logger.warning('[GitHub] query=%s error: %s', query, exc)
            continue
    if fetched == 0:
        raise RuntimeError('GitHub: no repos fetched')
    return fetched, created


# ============================================================
# Reddit 采集器 (公开 .json 尾缀, 无需认证)
# ============================================================
REDDIT_SUBS = [
    ('technology', 'global', 'technology'),
    ('worldnews', 'global', 'social'),
    ('business', 'global', 'industry'),
    ('artificial', 'global', 'technology'),
    ('geopolitics', 'global', 'regulation'),
]


def crawl_reddit(source) -> Tuple[int, int]:
    """采集 Reddit 热门贴子 (免费 .json 接口)."""
    fetched = 0
    created = 0
    for sub, market, dim in REDDIT_SUBS:
        url = f'https://www.reddit.com/r/{sub}/hot.json?limit=5'
        try:
            data = _safe_get(url, timeout=20)
            for child in (data or {}).get('data', {}).get('children', [])[:5]:
                d = child.get('data') or {}
                title_raw = (d.get('title') or '').strip()
                if not title_raw:
                    continue
                ups = d.get('ups', 0)
                num_c = d.get('num_comments', 0)
                permalink = d.get('permalink', '')
                full_url = f'https://www.reddit.com{permalink}'
                ts = d.get('created_utc')
                try:
                    pub_at = datetime.fromtimestamp(int(ts), tz=_tz.utc) if ts else timezone.now()
                except Exception:
                    pub_at = timezone.now()
                title = f'[Reddit r/{sub}] {title_raw[:160]}'
                content = (
                    f'板块: r/{sub}\n标题: {title_raw}\n'
                    f'点赞: {ups:,} | 评论: {num_c:,}\n原文: {full_url}\n'
                    f'数据来源: Reddit 公开 JSON 接口'
                )
                raw_url = _pick_url(
                    full_url,
                    f'https://www.reddit.com/r/{sub}',
                    d.get('id', '') or permalink[:60])
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dim):
                    created += 1
        except Exception as exc:
            logger.warning('[Reddit] sub=%s error: %s', sub, exc)
            continue
    if fetched == 0:
        raise RuntimeError('Reddit: no posts fetched')
    return fetched, created


# ============================================================
# arXiv 采集器 (学术论文, 免费无 Key, Atom XML)
# ============================================================
ARXIV_QUERIES = [
    ('cat:cs.AI', 'global', 'technology'),
    ('cat:cs.CL', 'global', 'technology'),
    ('cat:econ.GN', 'global', 'macro'),
]


def crawl_arxiv(source) -> Tuple[int, int]:
    """采集 arXiv 最新论文摄要 (免费无 Key, Atom XML)."""
    fetched = 0
    created = 0
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    for query, market, dim in ARXIV_QUERIES:
        encoded = urllib.parse.quote(query)
        url = (f'https://export.arxiv.org/api/query?search_query={encoded}'
               f'&sortBy=submittedDate&sortOrder=descending&max_results=5')
        try:
            text = _safe_get_text(url, timeout=20)
            root = _ET.fromstring(text)
            for entry in root.findall('a:entry', ns)[:5]:
                title_el = entry.find('a:title', ns)
                title_raw = (title_el.text or '').strip() if title_el is not None else ''
                if not title_raw:
                    continue
                summary_el = entry.find('a:summary', ns)
                summary = (summary_el.text or '').strip()[:400] if summary_el is not None else ''
                published_el = entry.find('a:published', ns)
                published_str = (published_el.text or '').strip() if published_el is not None else ''
                link_el = entry.find('a:id', ns)
                art_url = (link_el.text or '').strip() if link_el is not None else ''
                authors = ', '.join([
                    (a.find('a:name', ns).text or '').strip()
                    for a in entry.findall('a:author', ns)[:3]
                    if a.find('a:name', ns) is not None
                ])
                try:
                    pub_at = datetime.fromisoformat(
                        published_str.replace('Z', '+00:00')) if published_str else timezone.now()
                except Exception:
                    pub_at = timezone.now()
                title = f'[arXiv {query.split(":")[-1]}] {title_raw[:160]}'
                content = (
                    f'领域: {query}\n标题: {title_raw}\n作者: {authors}\n'
                    f'摄要: {summary}\n提交: {published_str}\n原文: {art_url}\n'
                    f'数据来源: arXiv.org 学术预印本服务'
                )
                raw_url = _pick_url(
                    art_url,
                    'https://arxiv.org/list',
                    f'{query}|{art_url[:80]}')
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dim):
                    created += 1
        except Exception as exc:
            logger.warning('[arXiv] query=%s error: %s', query, exc)
            continue
    if fetched == 0:
        raise RuntimeError('arXiv: no entries fetched')
    return fetched, created


# ============================================================
# CoinGecko 采集器 (加密资产市场, 免费无 Key)
# ============================================================
def crawl_coingecko(source) -> Tuple[int, int]:
    """采集 CoinGecko Top 市值加密资产行情 (免费无 Key)."""
    url = ('https://api.coingecko.com/api/v3/coins/markets'
           '?vs_currency=usd&order=market_cap_desc&per_page=10&page=1'
           '&price_change_percentage=24h')
    try:
        data = _safe_get(url, timeout=20)
    except Exception as exc:
        raise RuntimeError(f'CoinGecko fetch failed: {exc}')
    fetched = 0
    created = 0
    if not isinstance(data, list):
        raise RuntimeError('CoinGecko: unexpected response shape')
    for coin in data[:MAX_ITEMS]:
        sym = (coin.get('symbol') or '').upper()
        name = coin.get('name') or ''
        price = coin.get('current_price')
        chg = coin.get('price_change_percentage_24h')
        mcap = coin.get('market_cap', 0)
        last_updated = coin.get('last_updated') or ''
        try:
            pub_at = datetime.fromisoformat(
                last_updated.replace('Z', '+00:00')) if last_updated else timezone.now()
        except Exception:
            pub_at = timezone.now()
        chg_str = f'{chg:+.2f}%' if isinstance(chg, (int, float)) else 'N/A'
        title = f'[CoinGecko] {sym} ({name}): ${price} {chg_str}'[:200]
        content = (
            f'资产: {name} ({sym})\n价格 (USD): ${price}\n'
            f'24h 涨跌: {chg_str}\n市值: ${mcap:,}\n更新时间: {last_updated}\n'
            f'数据来源: CoinGecko Public API (api.coingecko.com)'
        )
        raw_url = _snapshot_url(
            f'https://www.coingecko.com/en/coins/{coin.get("id", sym.lower())}',
            f'{sym}|{last_updated[:19]}')
        fetched += 1
        if _upsert_raw_info(source, title, content, raw_url, pub_at, 'global', 'macro'):
            created += 1
    if fetched == 0:
        raise RuntimeError('CoinGecko: no coins fetched')
    return fetched, created


# ============================================================
# Frankfurter 采集器 (外汇货币汇率, 免费无 Key)
# ============================================================
def crawl_frankfurter(source) -> Tuple[int, int]:
    """采集外汇汇率 (基于欧洲央行参考汇率, 免费无 Key)."""
    bases_targets = [
        ('USD', 'CNY,EUR,JPY,GBP,HKD,SGD,KRW,AUD,CAD,CHF', 'global', 'macro'),
        ('CNY', 'USD,EUR,JPY,HKD,SGD', 'CN', 'macro'),
    ]
    fetched = 0
    created = 0
    for base, targets, market, dim in bases_targets:
        url = f'https://api.frankfurter.app/latest?from={base}&to={targets}'
        try:
            data = _safe_get(url, timeout=15)
            rates = (data or {}).get('rates') or {}
            date_str = (data or {}).get('date') or ''
            try:
                pub_at = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=_tz.utc)
            except Exception:
                pub_at = timezone.now()
            for cur, rate in rates.items():
                title = f'[Frankfurter] {base}/{cur}: {rate} ({date_str})'
                content = (
                    f'基本货币: {base}\n目标货币: {cur}\n汇率: {rate}\n日期: {date_str}\n'
                    f'数据来源: Frankfurter API (参考欧洲央行汇率, api.frankfurter.app)'
                )
                raw_url = _snapshot_url(
                    f'https://www.frankfurter.app/{date_str}'
                    f'?from={base}&to={cur}',
                    f'{base}|{cur}|{date_str}')
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dim):
                    created += 1
        except Exception as exc:
            logger.warning('[Frankfurter] base=%s error: %s', base, exc)
            continue
    if fetched == 0:
        raise RuntimeError('Frankfurter: no rates fetched')
    return fetched, created


# ============================================================
# OpenAlex 采集器 (全球学术论文开放数据库, 免费无 Key)
# ============================================================
OPENALEX_QUERIES = [
    ('artificial intelligence', 'global', 'technology'),
    ('supply chain risk', 'global', 'industry'),
    ('renewable energy policy', 'global', 'regulation'),
]


def crawl_openalex(source) -> Tuple[int, int]:
    """采集 OpenAlex 最新学术论文 (免费无 Key, 全球取代 Microsoft Academic)."""
    fetched = 0
    created = 0
    for query, market, dim in OPENALEX_QUERIES:
        encoded = urllib.parse.quote(query)
        url = (f'https://api.openalex.org/works?search={encoded}'
               f'&filter=publication_year:2024|2025&sort=publication_date:desc'
               f'&per-page=5')
        try:
            data = _safe_get(url, timeout=20)
            for w in (data or {}).get('results', [])[:5]:
                title_raw = (w.get('title') or '').strip()
                if not title_raw:
                    continue
                pub_date = w.get('publication_date') or ''
                cited_by = w.get('cited_by_count', 0)
                doi = w.get('doi') or ''
                authorships = w.get('authorships') or []
                authors = ', '.join([
                    (a.get('author') or {}).get('display_name', '')
                    for a in authorships[:3]
                ])
                try:
                    pub_at = datetime.strptime(pub_date, '%Y-%m-%d').replace(tzinfo=_tz.utc)
                except Exception:
                    pub_at = timezone.now()
                title = f'[OpenAlex] {title_raw[:160]}'
                content = (
                    f'检索词: {query}\n标题: {title_raw}\n作者: {authors}\n'
                    f'发表日: {pub_date}\n被引用: {cited_by}\n'
                    f'DOI: {doi}\n数据来源: OpenAlex (api.openalex.org)'
                )
                openalex_id = w.get('id') or ''
                raw_url = _pick_url(
                    openalex_id or doi,
                    'https://openalex.org/works',
                    title_raw[:80])
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dim):
                    created += 1
        except Exception as exc:
            logger.warning('[OpenAlex] query=%s error: %s', query, exc)
            continue
    if fetched == 0:
        raise RuntimeError('OpenAlex: no works fetched')
    return fetched, created


# ============================================================
# RSS 新闻采集器 (通用 RSS/Atom XML, 免费无 Key)
# ============================================================
# (RSS_URL, 源名, market, dim, max_items)
# 覆盖赛题五大战略维度: 社媒/社会 + 竞争行业 + 平台政策 + 法规监管 + 宏观贸易.
# 所有源均为官方公开 RSS, 免费、免注册、不需 Key.
RSS_FEEDS = [
    # ---- 社会/主流新闻 (原有) ----
    ('https://feeds.bbci.co.uk/news/world/rss.xml',
     'BBC World', 'global', 'social', 6),
    ('https://feeds.bbci.co.uk/news/business/rss.xml',
     'BBC Business', 'global', 'industry', 6),
    ('https://www.theguardian.com/world/rss',
     'The Guardian World', 'global', 'social', 6),
    ('https://www.theguardian.com/business/rss',
     'The Guardian Business', 'global', 'industry', 6),
    ('https://feeds.npr.org/1004/rss.xml',
     'NPR World', 'US', 'social', 5),
    ('https://rss.cnn.com/rss/edition_world.rss',
     'CNN World', 'global', 'social', 5),
    ('https://www.aljazeera.com/xml/rss/all.xml',
     'Al Jazeera', 'global', 'social', 5),
    # ---- 法规/监管 (赛题核心维度) ----
    # FDA 新闻室 (药品/食品/医疗器械监管) — 出海品牌合规必看
    ('https://www.fda.gov/about-fda/contact-fda/stay-informed/'
     'rss-feeds/press-releases/rss.xml',
     'FDA Press Releases', 'US', 'regulation', 6),
    # FTC 新闻室 (反垄断/消费者保护)
    ('https://www.ftc.gov/feeds/press-release.xml',
     'FTC Press Releases', 'US', 'regulation', 5),
    # USTR 贸易代表办公室 (关税/贸易政策)
    ('https://ustr.gov/about-us/policy-offices/press-office/'
     'press-releases/rss.xml',
     'USTR Press', 'US', 'regulation', 5),
    # EU Commission 新闻 (欧盟政策/贸易决定)
    ('https://ec.europa.eu/commission/presscorner/api/rss?language=en',
     'EU Commission Press', 'EU', 'regulation', 6),
    # ---- 平台政策/竞品 (赛题核心维度) ----
    # Amazon Seller Central News 公告 (卖家平台规则变动)
    ('https://sellercentral.amazon.com/forums/c/news-announcements.rss',
     'Amazon Seller News', 'global', 'platform', 6),
    # eBay Seller News
    ('https://community.ebay.com/t5/Announcements/bg-p/Announcements/'
     'rss/board?board.id=Announcements',
     'eBay Seller News', 'global', 'platform', 5),
    # Shopify News
    ('https://www.shopify.com/news.atom',
     'Shopify News', 'global', 'platform', 5),
    # ---- 宏观经济/产业 (补充) ----
    # Reuters Business
    ('https://feeds.reuters.com/reuters/businessNews',
     'Reuters Business', 'global', 'industry', 5),
    # Reuters Markets
    ('https://feeds.reuters.com/reuters/marketsNews',
     'Reuters Markets', 'global', 'industry', 5),
    # ---- 社媒/技术趋势 (赛题社媒维度补充) ----
    # TechCrunch (创业/品牌/技术)
    ('https://techcrunch.com/feed/',
     'TechCrunch', 'global', 'industry', 5),
]


def _parse_rss_pub(date_str: str) -> datetime:
    """容错解析 RSS pubDate (RFC822 或 ISO)."""
    if not date_str:
        return timezone.now()
    fmts = ['%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S %Z',
            '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ']
    for fmt in fmts:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except Exception:
        return timezone.now()


def crawl_rss_feeds(source) -> Tuple[int, int]:
    """通用 RSS/Atom 采集器: 贯穿 BBC / Guardian / NPR / CNN / Al Jazeera."""
    fetched = 0
    created = 0
    for feed_url, feed_name, market, dim, top_n in RSS_FEEDS:
        try:
            text = _safe_get_text(feed_url, timeout=20)
            root = _ET.fromstring(text)
            # RSS 2.0: rss/channel/item ; Atom: feed/entry
            items = root.findall('.//item')
            atom_ns = {'a': 'http://www.w3.org/2005/Atom'}
            if not items:
                items = root.findall('.//a:entry', atom_ns)
            for it in items[:top_n]:
                title_el = (it.find('title') if it.find('title') is not None
                            else it.find('a:title', atom_ns))
                title_raw = (title_el.text or '').strip() if title_el is not None else ''
                if not title_raw:
                    continue
                desc_el = (it.find('description') if it.find('description') is not None
                           else it.find('a:summary', atom_ns))
                desc = (desc_el.text or '').strip()[:400] if desc_el is not None else ''
                link_el = it.find('link')
                if link_el is not None and link_el.text:
                    art_url = link_el.text.strip()
                else:
                    atom_link = it.find('a:link', atom_ns)
                    art_url = atom_link.get('href', '') if atom_link is not None else ''
                pub_el = (it.find('pubDate') if it.find('pubDate') is not None
                          else it.find('a:published', atom_ns)
                          or it.find('a:updated', atom_ns))
                pub_str = (pub_el.text or '').strip() if pub_el is not None else ''
                pub_at = _parse_rss_pub(pub_str)
                title = f'[{feed_name}] {title_raw[:160]}'
                content = (
                    f'源: {feed_name}\n标题: {title_raw}\n摄要: {desc}\n'
                    f'发布时间: {pub_str}\n原文: {art_url}\n'
                    f'数据来源: {feed_url}'
                )
                raw_url = _pick_url(
                    art_url, feed_url, title_raw[:80])
                fetched += 1
                if _upsert_raw_info(source, title, content, raw_url, pub_at, market, dim):
                    created += 1
        except Exception as exc:
            logger.warning('[RSS] feed=%s error: %s', feed_url, exc)
            continue
    if fetched == 0:
        raise RuntimeError('RSS: no items fetched')
    return fetched, created


# ============================================================
# 路由表 — spider_name → 对应采集函数
# ============================================================
SPIDER_REGISTRY = {
    # 原有 (宏观/新闻)
    'spider_fred': crawl_fred,
    'spider_world_bank': crawl_world_bank,
    'spider_gdelt': crawl_gdelt,
    # 免费 API 采集器
    'spider_imf_data_api': crawl_imf,
    'spider_imf_datamapper_api': crawl_imf,
    'spider_hacker_news_firebase_api': crawl_hacker_news,
    'spider_algolia_hacker_news_api': crawl_algolia_hn,
    'spider_sec_edgar_company_filings': crawl_sec_edgar,
    'spider_rest_countries_api': crawl_rest_countries,
    'spider_usgs_science_data_catalog': crawl_usgs,
    # Federal Register 中文 spider_name 不够稳定, 同时提供 ASCII alias
    'spider_federal_register': crawl_federal_register,
    # 新增高价值免费源 (宏观/金融/科技/社交/新闻)
    'spider_ecb': crawl_ecb,
    'spider_ecb_data_portal': crawl_ecb,
    'spider_eurostat': crawl_eurostat,
    'spider_github': crawl_github,
    'spider_github_public_api': crawl_github,
    'spider_reddit': crawl_reddit,
    'spider_arxiv': crawl_arxiv,
    'spider_coingecko': crawl_coingecko,
    'spider_frankfurter': crawl_frankfurter,
    'spider_currency_rate': crawl_frankfurter,
    'spider_openalex': crawl_openalex,
    'spider_rss_news': crawl_rss_feeds,
    'spider_bbc_news': crawl_rss_feeds,
    'spider_the_guardian': crawl_rss_feeds,
    # 新增: 平台政策 / 法规 / 贸易 / 竞品 赛题核心维度 (复用通用 RSS 采集器)
    'spider_amazon_seller_news': crawl_rss_feeds,
    'spider_ebay_seller_news': crawl_rss_feeds,
    'spider_shopify_news': crawl_rss_feeds,
    'spider_fda_press_releases': crawl_rss_feeds,
    'spider_ftc_press_releases': crawl_rss_feeds,
    'spider_ustr_press': crawl_rss_feeds,
    'spider_eu_commission_press': crawl_rss_feeds,
    'spider_reuters_business': crawl_rss_feeds,
    'spider_reuters_markets': crawl_rss_feeds,
    'spider_techcrunch': crawl_rss_feeds,
}


# 关键词 → 采集函数 的模糊路由表.
# 匹配顺序以 (spider_name + source.name + source.official_url) 拼接后的 lower() 字串 进行 substring 匹配.
# 该机制让 import_sources 自动生成的 spider_name (含中文) 也能正确路由到真实采集器.
_KEYWORD_ROUTES: list = [
    # (keywords_tuple, crawler_fn, label)
    (('fred', 'stlouisfed', '圣路易斯联储'), crawl_fred, 'FRED'),
    (('world_bank', 'worldbank', 'world bank', '世界银行'), crawl_world_bank, 'World Bank'),
    (('gdelt',), crawl_gdelt, 'GDELT'),
    (('imf', '国际货币基金', 'datamapper'), crawl_imf, 'IMF'),
    (('algolia',), crawl_algolia_hn, 'Algolia HN'),
    (('hacker_news', 'hackernews', 'hacker news', 'ycombinator', 'hn_firebase',
      'hn firebase', '黑客新闻'), crawl_hacker_news, 'HN Firebase'),
    (('sec_edgar', 'edgar', 'sec.gov', '美国sec', 'sec披露'),
     crawl_sec_edgar, 'SEC EDGAR'),
    (('rest_countries', 'restcountries', 'rest countries'),
     crawl_rest_countries, 'REST Countries'),
    (('usgs', 'earthquake', '地震'), crawl_usgs, 'USGS'),
    (('federal_register', 'federalregister', '联邦公报'),
     crawl_federal_register, 'Federal Register'),
    # 新增
    (('ecb', '欧洲央行', 'european_central_bank', 'data-api.ecb', 'ecb_data_portal'),
     crawl_ecb, 'ECB'),
    (('eurostat', '欧盟统计局', '欧盟统计', 'ec.europa.eu/eurostat'),
     crawl_eurostat, 'Eurostat'),
    (('github', '开源仓库'), crawl_github, 'GitHub'),
    (('reddit', 'r/'), crawl_reddit, 'Reddit'),
    (('arxiv', '预印本'), crawl_arxiv, 'arXiv'),
    (('coingecko', 'coinmarketcap', 'crypto', '加密货币', '加密资产'),
     crawl_coingecko, 'CoinGecko'),
    (('frankfurter', 'exchangerate', 'exchange_rate', '汇率', 'forex',
     'currency'), crawl_frankfurter, 'Frankfurter FX'),
    (('openalex', '学术论文'), crawl_openalex, 'OpenAlex'),
    # RSS 类主流新闻质成 — 任何包含以下关键词的源都走通用 RSS 采集器
    (('bbc', 'guardian', 'reuters', 'cnn', 'npr', 'aljazeera', 'rss', 'atom_feed',
      '路透社', '卫报'), crawl_rss_feeds, 'RSS Feeds'),
    # 新增: 赛题核心五大维度的专属关键词
    (('amazon_seller', 'amazon seller', 'sellercentral', '亚马逊卖家',
      'ebay_seller', 'ebay seller', 'shopify_news', 'shopify',
      '平台政策', '卖家公告'), crawl_rss_feeds, 'Platform RSS'),
    (('fda', 'ftc', 'ustr', 'eu_commission', 'ec.europa.eu',
      '美国食品药品', '联邦贸易委员会', '美国贸易代表',
      '欧盟委员会'), crawl_rss_feeds, 'Regulation RSS'),
    (('techcrunch', 'tech crunch', '科技创业'),
     crawl_rss_feeds, 'TechCrunch'),
]


def _route_haystack(source) -> str:
    """拼接三个匹配面用于关键词路由: spider_name + name + official_url + list_url."""
    parts = [
        getattr(source, 'spider_name', '') or '',
        getattr(source, 'name', '') or '',
        getattr(source, 'official_url', '') or '',
        getattr(source, 'list_url', '') or '',
    ]
    return ' '.join(parts).lower()


def dispatch(source) -> Tuple[int, int]:
    """路由到对应采集函数: 优先精确匹配, 其次 spider_name+name+url 关键词模糊匹配.

    设计要点:
    - 精确匹配 (SPIDER_REGISTRY): 适用 import_sources 产生了标准 ASCII spider_name 的场景.
    - 关键词模糊匹配: 对于 "FRED（圣路易斯联储）" 这种中文名产生的
      spider_fred_圣路易斯联储_, 仍能正确命中 crawl_fred 走真实采集.
    - 未命中任何路由 → NotImplementedError (交给上层降级链路).
    """
    spider = (source.spider_name or '').strip().lower()
    if spider in SPIDER_REGISTRY:
        return SPIDER_REGISTRY[spider](source)
    haystack = _route_haystack(source)
    for keys, fn, _label in _KEYWORD_ROUTES:
        for k in keys:
            if k.lower() in haystack:
                return fn(source)
    raise NotImplementedError(
        f'spider "{spider}" not in real_crawler registry — '
        f'available: {list(SPIDER_REGISTRY.keys())}'
    )


def supported_spider_names() -> list[str]:
    """返回当前所有已注册的真实爬虫名 (供 views.py / 调试面板读取)."""
    return sorted(set(SPIDER_REGISTRY.keys()))

