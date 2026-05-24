"""DeepSeek LLM Provider — OpenAI 兼容协议的真实大模型调用.

策略: 单次完整 prompt 让模型一次性返回 PEST + 4 维评分 + 摘要 + 行动建议
的 JSON; 失败时自动降级到 MockLLMProvider 兜底, 永不阻塞业务链路.
"""
from __future__ import annotations

import json as _json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings

from .base import BaseLLMProvider, IntelInput, IntelAnalysis


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    '你是出海企业战略情报分析师. '
    '请先输出一段思考过程, 用 <thinking>...</thinking> 标签包裹 '
    '(不少于 200 字, 包含: 事件拆解 / PEST 维度划分依据 / '
    '对公司影响推演 / 机会还是威胁的反复较量 / 4 维评分思路推演). '
    '思考结束后, 紧接严格按用户要求的 JSON 结构输出结果. '
    '除 <thinking> 块和最后的 JSON 以外, 不要输出任何其他字符 '
    '(不要 markdown 代码块, 不要补充解释).'
)

USER_PROMPT_TEMPLATE = '''请对下面这条情报做一次产品级的深度战略分析, 返回如下 JSON:

{{
  "pest_type": "P|E|S|T",
  "opportunity_or_threat": "O|T",
  "impact_level": "H|M|L",
  "sentiment": "positive|neutral|negative",
  "score_relevance": 0~4 数值 (业务相关度, 与公司主营品类/目标市场匹配度),
  "score_urgency": 0~3 数值 (时效紧迫度, 需多快采取行动),
  "score_authority": 0~2 数值 (信息源权威性),
  "score_scope": 0~1 数值 (影响地理/市场范围),
  "summary": "一句话超短摘要 (60~120 字, 概括事件+影响+量级)",
  "rationale": "详细判断理由 (300~500 字, 结合事件本身/PEST维度/公司优勿势多角度论证为何这个评分、为何这个机会/威胁判断、为何这个紧迫度, 需引用原文关键信息)",
  "action_advice": "3~5 条可落地的战略行动建议 (500~800 字总长, 每条以 1)/2)/3) 开头 + 换行分隔; 每条要包含具体动作+责任人可能部门/人员+时间节点+衡量指标, 不要只说 评估、监控、关注 这种空话)",
  "tags": ["5~8 个主题标签: 业务品类/地区/技术/政策类型等"]
}}

【情报】
标题: {title}
正文: {content}
目标市场: {target_market}
战略维度: {strategic_dimension}
信息源: {source_name}

【公司情况】
优势: {strengths}
劣势: {weaknesses}

只返回 JSON, 不要解释、不要 markdown 代码块、不要任何 JSON 之外的字符.'''


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek (OpenAI 兼容) Provider — 单轮完整分析."""

    name = 'deepseek'

    def __init__(self):
        # 优先读取 settings 页中用户保存的运行时配置 (覆盖 .env)
        cfg = {}
        try:
            from apps.dashboard.services.runtime_config import llm_effective
            cfg = llm_effective() or {}
        except Exception:
            cfg = {}
        self.api_key = (cfg.get('api_key')
                        or getattr(settings, 'LLM_API_KEY', '') or '')
        self.base_url = ((cfg.get('base_url')
                          or getattr(settings, 'LLM_BASE_URL', '')
                          or 'https://api.deepseek.com').rstrip('/'))
        self.model = (cfg.get('model')
                      or getattr(settings, 'LLM_MODEL', '')
                      or 'deepseek-v4-flash')
        # v4-flash 非思考模式, 响应快; v4-pro 是 thinking 模型, TTFB 可达几十秒.
        # 统一调高 timeout 避免 urllib socket timeout 划拉思考过程.
        self.timeout = 180

    # ---- 抽象方法占位实现 (本 Provider 直接覆盖 analyze_intel, 用不到) ----
    def _complete(self, prompt: str, step: str = '', **kwargs) -> str:
        return self._chat(prompt, step=step)

    def _parse_pest(self, resp: str) -> dict:
        return {'pest': 'E', 'ot': 'O', 'level': 'M'}

    def _parse_score(self, resp: str) -> dict:
        return {'relevance': 2.0, 'urgency': 1.0,
                'authority': 1.0, 'scope': 0.5}

    def _parse_summary(self, resp: str):
        return resp[:120], '', []

    def _parse_action(self, resp: str) -> str:
        return resp[:300]

    # ---- 核心: 单轮完整分析 ----
    def analyze_intel(self, intel: IntelInput, on_token=None,
                      on_thinking=None) -> IntelAnalysis:
        """单轮调用 DeepSeek 拿到完整结构化结果; 失败自动降级 Mock.

        on_token: 可选回调 fn(token: str), 传入后启用流式调用,
        LLM 每返回一段正文 delta 就实时调一次 on_token 供前端 SSE 透传.
        on_thinking: 可选回调 fn(token: str), 仅接收思考过程片段 (<thinking>...</thinking>
        包裹的内容 或 deepseek-reasoner 模型的 reasoning_content 字段).
        不传 on_token 时保持原有同步调用 (快路径 / Celery 后台场景).
        """
        prompt = USER_PROMPT_TEMPLATE.format(
            title=(intel.title or '')[:300],
            content=(intel.content or '')[:4000],
            target_market=intel.target_market or 'global',
            strategic_dimension=intel.strategic_dimension or '',
            source_name=intel.source_name or '',
            strengths=', '.join(intel.company_strengths or []) or '—',
            weaknesses=', '.join(intel.company_weaknesses or []) or '—',
        )

        if on_token is not None:
            raw = self._chat_stream(prompt, step='full_analysis',
                                    on_token=on_token,
                                    on_thinking=on_thinking)
        else:
            raw = self._chat(prompt, step='full_analysis')
        # 剥除 <thinking>...</thinking> 块后再走 JSON 提取, 避免思考文本干扰解析
        raw_for_json = re.sub(r'<thinking>.*?</thinking>', '', raw or '',
                              flags=re.S).strip()
        parsed = self._extract_json(raw_for_json)

        if not parsed:
            logger.warning(
                '[DeepSeek] empty/invalid response, fallback to Mock. raw=%r',
                (raw or '')[:200])
            from .mock_provider import MockLLMProvider
            return MockLLMProvider().analyze_intel(
                intel, on_token=on_token, on_thinking=on_thinking)

        try:
            return self._build_analysis(intel, parsed, raw_response=raw,
                                        prompt=prompt)
        except Exception as exc:
            logger.warning('[DeepSeek] build_analysis failed (%s), '
                           'fallback to Mock', exc)
            from .mock_provider import MockLLMProvider
            return MockLLMProvider().analyze_intel(
                intel, on_token=on_token, on_thinking=on_thinking)

    # ---- HTTP ----
    def _chat(self, prompt: str, step: str = '') -> str:
        """同步调用 (非流式); 网络拖动时指数退避重试 max 2 次."""
        if not self.api_key:
            logger.warning('[DeepSeek] LLM_API_KEY 未配置, 跳过真实调用')
            return ''

        url = f'{self.base_url}/v1/chat/completions'
        body = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.4,
            # v4-pro thinking 模式下 reasoning_content 会吃掉几千 token额度,
            # 4096 会导致 finish_reason=length + content='', 这里提高到 16384.
            'max_tokens': 16384,
            'stream': False,
        }
        data = _json.dumps(body, ensure_ascii=False).encode('utf-8')
        last_exc: Exception | None = None
        # 最多 3 次 (首次 + 2 次重试), 退避 0.5s / 1.5s
        import time as _time
        for attempt in range(3):
            req = urllib.request.Request(
                url, data=data,
                headers={
                    'Content-Type': 'application/json; charset=utf-8',
                    'Authorization': f'Bearer {self.api_key}',
                    'Accept': 'application/json',
                },
                method='POST',
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = _json.loads(resp.read().decode('utf-8'))
                choices = payload.get('choices') or []
                if not choices:
                    return ''
                return (choices[0].get('message') or {}).get('content', '') or ''
            except urllib.error.HTTPError as exc:
                try:
                    err_body = exc.read().decode('utf-8', errors='ignore')[:300]
                except Exception:
                    err_body = ''
                logger.warning('[DeepSeek] HTTP %s step=%s attempt=%s body=%s',
                               exc.code, step, attempt + 1, err_body)
                # 4xx 不重试 (鉴权/参数错误重试也无效)
                if 400 <= exc.code < 500 and exc.code != 429:
                    return ''
                last_exc = exc
            except Exception as exc:
                logger.warning('[DeepSeek] step=%s attempt=%s err=%s',
                               step, attempt + 1, exc)
                last_exc = exc
            if attempt < 2:
                _time.sleep(0.5 * (3 ** attempt))  # 0.5s, 1.5s
        if last_exc is not None:
            logger.warning('[DeepSeek] all retries exhausted step=%s', step)
        return ''

    def _chat_stream(self, prompt: str, step: str = '',
                     on_token=None, on_thinking=None) -> str:
        """流式调用 DeepSeek/OpenAI Chat Completions (stream=True),
        逐行解析 SSE 中的 delta token, 每拿到一个就调 on_token(token);
        返回拼接后的完整文本. 未配置 API Key 或调用失败返回 ''.

        收到的 token 会按以下规则分流:
        - delta 字段含 reasoning_content (deepseek-reasoner) → on_thinking
        - 文本处于 <thinking>...</thinking> 标签内 → on_thinking
        - 其余正文 → on_token
        """
        if not self.api_key:
            logger.warning('[DeepSeek][stream] LLM_API_KEY 未配置, 跳过真实调用')
            return ''

        url = f'{self.base_url}/v1/chat/completions'
        body = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.4,
            # v4-pro thinking 模式下 reasoning_content 会吃掉几千 token额度,
            # 4096 会导致 finish_reason=length + content='', 这里提高到 16384.
            'max_tokens': 16384,
            'stream': True,
        }
        data = _json.dumps(body, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            url, data=data,
            headers={
                'Content-Type': 'application/json; charset=utf-8',
                'Authorization': f'Bearer {self.api_key}',
                'Accept': 'text/event-stream',
            },
            method='POST',
        )

        full_text: list[str] = []
        # 状态机: 跟踪当前是否在 <thinking>块内, 并处理跨 chunk 裁切的标签
        in_thinking = False
        # 阅后余量: 未能判别是否要进入/退出标签的尾部字符 (最多保留 <thinking> 长度 - 1 = 9 字符)
        pending = ''
        OPEN_TAG = '<thinking>'
        CLOSE_TAG = '</thinking>'

        def _emit(text: str, thinking: bool):
            if not text:
                return
            if thinking:
                if on_thinking is not None:
                    try:
                        on_thinking(text)
                    except Exception as cb_exc:
                        logger.debug('on_thinking callback err: %s', cb_exc)
            else:
                full_text.append(text)
                if on_token is not None:
                    try:
                        on_token(text)
                    except Exception as cb_exc:
                        logger.debug('on_token callback err: %s', cb_exc)

        def _consume(chunk_text: str):
            """加入一段 delta, 按状态机拆分为 thinking/normal 并调回调."""
            nonlocal in_thinking, pending
            buf = pending + chunk_text
            pending = ''
            while buf:
                if in_thinking:
                    idx = buf.find(CLOSE_TAG)
                    if idx == -1:
                        # 尾部保留最多 len(CLOSE_TAG)-1 字符备拼接
                        keep = len(CLOSE_TAG) - 1
                        if len(buf) > keep:
                            _emit(buf[:-keep], thinking=True)
                            pending = buf[-keep:]
                        else:
                            pending = buf
                        return
                    # 吃掉 close tag 之前的全部思考文本
                    _emit(buf[:idx], thinking=True)
                    buf = buf[idx + len(CLOSE_TAG):]
                    in_thinking = False
                else:
                    idx = buf.find(OPEN_TAG)
                    if idx == -1:
                        keep = len(OPEN_TAG) - 1
                        if len(buf) > keep:
                            _emit(buf[:-keep], thinking=False)
                            pending = buf[-keep:]
                        else:
                            pending = buf
                        return
                    _emit(buf[:idx], thinking=False)
                    buf = buf[idx + len(OPEN_TAG):]
                    in_thinking = True

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw_line in resp:
                    if not raw_line:
                        continue
                    line = raw_line.decode('utf-8', errors='ignore').strip()
                    if not line or not line.startswith('data:'):
                        continue
                    payload_str = line[5:].strip()
                    if payload_str == '[DONE]':
                        break
                    try:
                        chunk = _json.loads(payload_str)
                    except _json.JSONDecodeError:
                        continue
                    choices = chunk.get('choices') or []
                    if not choices:
                        continue
                    delta = choices[0].get('delta') or {}
                    # 1) deepseek-reasoner 原生思考字段
                    rc = delta.get('reasoning_content') or ''
                    if rc and on_thinking is not None:
                        try:
                            on_thinking(rc)
                        except Exception as cb_exc:
                            logger.debug('on_thinking err: %s', cb_exc)
                    # 2) 正文 / 包含 <thinking>标签的提示词思考
                    content_delta = delta.get('content') or ''
                    if content_delta:
                        _consume(content_delta)
            # 刷 pending 残余 (不可能是完整标签了)
            if pending:
                _emit(pending, thinking=in_thinking)
                pending = ''
            return ''.join(full_text)
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode('utf-8', errors='ignore')[:300]
            except Exception:
                err_body = ''
            logger.warning('[DeepSeek][stream] HTTP %s step=%s body=%s',
                           exc.code, step, err_body)
            return ''.join(full_text)
        except Exception as exc:
            logger.warning('[DeepSeek][stream] step=%s err=%s', step, exc)
            return ''.join(full_text)

    # ---- 解析 ----
    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """从 LLM 返回中提取首个 JSON 对象, 容忍 markdown 包裹."""
        if not text:
            return None
        # 去 markdown 代码块
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.S)
        candidate = m.group(1) if m else None
        if not candidate:
            # 兜底: 抓第一个 { 到最后一个 } 之间的内容
            i, j = text.find('{'), text.rfind('}')
            if i >= 0 and j > i:
                candidate = text[i:j + 1]
        if not candidate:
            return None
        try:
            obj = _json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except _json.JSONDecodeError:
            return None

    @staticmethod
    def _clip(value, lo, hi, default):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return float(default)
        return float(max(lo, min(hi, v)))

    def _build_analysis(self, intel: IntelInput, parsed: dict,
                        raw_response: str, prompt: str) -> IntelAnalysis:
        pest = (parsed.get('pest_type') or 'E').strip().upper()[:1]
        if pest not in {'P', 'E', 'S', 'T'}:
            pest = 'E'

        ot = (parsed.get('opportunity_or_threat') or 'O').strip().upper()[:1]
        if ot not in {'O', 'T'}:
            ot = 'O'

        level = (parsed.get('impact_level') or 'M').strip().upper()[:1]
        if level not in {'H', 'M', 'L'}:
            level = 'M'

        sentiment = (parsed.get('sentiment') or 'neutral').strip().lower()
        if sentiment not in {'positive', 'neutral', 'negative'}:
            sentiment = 'neutral'

        score_relevance = round(self._clip(parsed.get('score_relevance'),
                                           0, 4, 2.0), 2)
        score_urgency = round(self._clip(parsed.get('score_urgency'),
                                         0, 3, 1.0), 2)
        score_authority = round(self._clip(parsed.get('score_authority'),
                                           0, 2, 1.0), 2)
        score_scope = round(self._clip(parsed.get('score_scope'),
                                       0, 1, 0.5), 2)
        impact_score = round(score_relevance + score_urgency
                             + score_authority + score_scope, 2)

        impact_type = ('opportunity' if ot == 'O'
                       else ('risk' if level == 'H' else 'watch'))
        severity = {'H': 'high', 'M': 'medium', 'L': 'low'}[level]

        summary = str(parsed.get('summary') or intel.title or '')[:300]
        rationale = str(parsed.get('rationale') or '')[:1500]
        action = str(parsed.get('action_advice') or '')[:2000]
        tags_raw = parsed.get('tags') or []
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in re.split(r'[,，;；]', tags_raw) if t.strip()]
        else:
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        tags = tags[:8]

        chain = [
            {'step': 'deepseek_full_analysis',
             'prompt': prompt[:600] + ('...' if len(prompt) > 600 else ''),
             'response': raw_response[:2000]},
            {'step': 'parsed',
             'prompt': '结构化解析',
             'response': (
                 f'PEST={pest} OT={ot} LEVEL={level} '
                 f'相关度={score_relevance} 紧迫度={score_urgency} '
                 f'权威性={score_authority} 规模={score_scope} '
                 f'总分={impact_score}/10')},
        ]

        return IntelAnalysis(
            pest_type=pest,
            opportunity_or_threat=ot,
            impact_level=level,
            impact_type=impact_type,
            severity=severity,
            sentiment=sentiment,
            score_relevance=score_relevance,
            score_urgency=score_urgency,
            score_authority=score_authority,
            score_scope=score_scope,
            impact_score=impact_score,
            summary=summary,
            rationale=rationale,
            action_advice=action,
            tags=tags,
            chain=chain,
        )
