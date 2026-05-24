"""Mock LLM Provider — 黑客松默认实现, 不依赖任何外部 API.

策略: 基于关键词词典 + 启发式规则做"看上去合理"的判断, 输出可解释。
"""
from __future__ import annotations

import hashlib
import json
import random
import re

from .base import BaseLLMProvider, IntelInput


# ---- 关键词词典 (用于 PEST 分类启发) ----
PEST_KEYWORDS = {
    'P': [  # 政治/法律/政策
        '关税', '出口管制', '制裁', '法规', '立法', '监管', '合规', '政策',
        '政府', '海关', 'cbp', 'eu', 'ftc', 'sec', '签证', '反垄断',
        '召回', '认证', 'gdpr', '数据保护', '本地化', '执法', '诉讼',
    ],
    'E': [  # 经济
        'gdp', 'cpi', 'pmi', '加息', '降息', '通胀', '汇率', '贬值', '升值',
        '消费信贷', '失业率', '通胀回落', '利率', '财政', '经济增长',
        '原材料', '大宗商品', '关税', '到岸成本', '毛利', '佣金', '促销',
        '融资', '并购', '估值',
    ],
    'S': [  # 社会文化
        '消费者', 'kol', 'tiktok', 'reddit', '社交', '社媒', '差评',
        '口碑', 'nps', '舆论', '主流媒体', '可持续', '环保', 'z世代',
        '年轻人', '家庭', '健康', '审美', '国潮', '本地文化', '直播', '短视频',
    ],
    'T': [  # 技术
        'ai', '人工智能', '大模型', '生成式', '机器学习', 'matter', 'iot',
        '边缘计算', '智能家居', '芯片', '5g', '区块链', 'arvr', '云',
        '本地化部署', 'sdk', 'api', '协议', '专利', '技术标准',
    ],
}

OPPORTUNITY_HINTS = [
    '机会', '增长', '上涨', '回暖', '红利', '扶持', '简化', '优惠',
    '出圈', '正面', '加单', '替代', '空白', '抢占', '降本', '利好',
]
THREAT_HINTS = [
    '风险', '收紧', '上调', '加征', '下架', '封店', '召回', '处罚',
    '负面', '差评', '退货', '贬值', '加息', '管制', '挤压', '承压',
    '萎缩', '收缩', '下滑', '威胁',
]

LEVEL_HIGH_HINTS = [
    '关税', '管制', '加息', '召回', '封店', '立法', '处罚', '并购',
    '国家', '政府', '央行', '高额', '永久', '冻结资金',
]


def _stable_random(seed_str: str) -> random.Random:
    """根据字符串生成稳定的 Random — 同输入同输出, 便于复现."""
    h = hashlib.md5(seed_str.encode('utf-8')).hexdigest()
    return random.Random(int(h[:16], 16))


def _classify_pest(text: str) -> str:
    """基于关键词命中数返回 PEST 类型."""
    text_l = text.lower()
    scores = {p: 0 for p in 'PEST'}
    for p, kws in PEST_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in text_l:
                scores[p] += 1
    # 全部为 0 时按 dimension 兜底
    if all(v == 0 for v in scores.values()):
        return 'E'
    return max(scores, key=scores.get)


def _classify_ot(text: str, sentiment_hint: str = '') -> str:
    """O / T 启发式判断 — 命中正面/负面关键词."""
    text_l = text.lower()
    o = sum(1 for k in OPPORTUNITY_HINTS if k in text_l)
    t = sum(1 for k in THREAT_HINTS if k in text_l)
    if t > o:
        return 'T'
    if o > t:
        return 'O'
    if sentiment_hint == 'negative':
        return 'T'
    if sentiment_hint == 'positive':
        return 'O'
    return 'O'


def _classify_level(text: str, base_score: float) -> str:
    text_l = text.lower()
    high_hits = sum(1 for k in LEVEL_HIGH_HINTS if k in text_l)
    if high_hits >= 2 or base_score >= 8:
        return 'H'
    if high_hits == 1 or base_score >= 5:
        return 'M'
    return 'L'


def _detect_sentiment(text: str) -> str:
    text_l = text.lower()
    o = sum(1 for k in OPPORTUNITY_HINTS if k in text_l)
    t = sum(1 for k in THREAT_HINTS if k in text_l)
    if t > o + 1:
        return 'negative'
    if o > t + 1:
        return 'positive'
    return 'neutral'


def _extract_tags(text: str, max_n: int = 5) -> list:
    """从文本中抽取 1-5 个高频名词样关键词 (Mock 版: 基于词典命中)."""
    text_l = text.lower()
    candidate_pools = [
        ('AI', 'ai'), ('TikTok', 'tiktok'), ('Amazon', 'amazon'),
        ('关税', '关税'), ('合规', '合规'), ('召回', '召回'),
        ('消费降级', '保守'), ('品控', '品控'), ('物流', '物流'),
        ('社媒', '社媒'), ('KOL', 'kol'), ('促销', '促销'),
        ('降息', '降息'), ('加息', '加息'), ('汇率', '汇率'),
        ('可持续', '可持续'), ('Z世代', 'z世代'), ('本地化', '本地化'),
        ('品牌升级', '品牌力'),
    ]
    tags = []
    for show, kw in candidate_pools:
        if kw in text_l:
            tags.append(show)
        if len(tags) >= max_n:
            break
    return tags or ['出海情报']


# ======================================================================
class MockLLMProvider(BaseLLMProvider):
    """确定性 Mock LLM — 同样输入永远得到一致输出."""

    name = 'mock'

    def _complete(self, prompt: str, step: str = '', **kwargs) -> str:
        """构造确定性 JSON 字符串作为响应 — 实际逻辑写在分析阶段."""
        # 这里我们直接将 prompt 哈希作为 token 信号; 真正逻辑在 analyze_intel 改写
        return json.dumps({'mock': True, 'step': step, 'len': len(prompt)})

    # 重写 analyze_intel: 直接基于规则产出, 比走 4 段 prompt+解析更稳
    def analyze_intel(self, intel: IntelInput, on_token=None,
                      on_thinking=None):
        """Mock 分析; 如传入 on_token 则采用伪流式逐字后告知前端,
        传入 on_thinking 同时会先伪流式吐一段思考过程.
        保证在未配置真 LLM Key 的演示场景下依然能看到字符逐个流出的效果.
        """
        from .base import IntelAnalysis

        rng = _stable_random(intel.title + '|' + intel.target_market)
        full_text = f'{intel.title}\n{intel.content}\n{intel.strategic_dimension}'
        sentiment = _detect_sentiment(full_text)

        # PEST
        pest = _classify_pest(full_text)
        ot = _classify_ot(full_text, sentiment_hint=sentiment)

        # 4 维评分
        # 相关度: 维度匹配 + 出现关键词
        score_relevance = round(2.5 + rng.uniform(0, 1.5), 2)
        if intel.strategic_dimension in ('competition', 'platform', 'regulation'):
            score_relevance = min(4.0, score_relevance + 0.5)

        # 紧迫度: 命中"立即/月内/30天/即将"等
        urgency_keys = ['立即', '即将', '月内', '30天', '60天', '生效',
                        '紧急', '过渡期', '当日', '本周']
        urgency_hits = sum(1 for k in urgency_keys if k in full_text)
        score_urgency = round(min(3.0, 1.0 + 0.4 * urgency_hits + rng.uniform(0, 0.6)), 2)

        # 权威性: 信息源含央行/官方/政府/Reuters 等
        authority_keys = ['央行', '官方', '政府', '海关', 'reuters', 'fed', 'ecb',
                          'bls', 'bea', '欧盟委员会', 'sec', 'ftc', '咨询机构', '白皮书']
        auth_hits = sum(1 for k in authority_keys if k.lower() in full_text.lower())
        score_authority = round(min(2.0, 0.6 + 0.35 * auth_hits + rng.uniform(0, 0.4)), 2)

        # 规模: 有"全球/区域/多国"
        scope_keys = ['全球', '多国', '区域', '欧盟', '东南亚', '北美', '亚太', '拉美']
        scope_hits = sum(1 for k in scope_keys if k in full_text)
        score_scope = round(min(1.0, 0.3 + 0.2 * scope_hits + rng.uniform(0, 0.2)), 2)

        impact_score = round(score_relevance + score_urgency + score_authority + score_scope, 2)

        level = _classify_level(full_text, impact_score)
        impact_type = 'opportunity' if ot == 'O' else ('risk' if level == 'H' else 'watch')
        severity = {'H': 'high', 'M': 'medium', 'L': 'low'}[level]

        # 摘要
        summary = re.split(r'[。；;]', intel.content)[0][:120]
        if not summary:
            summary = intel.title[:120]

        # 判断理由
        rationale = (
            f'PEST 分类: {pest} (基于关键词匹配); '
            f'机会/威胁: {ot} (情感倾向 {sentiment}); '
            f'影响等级: {level} (综合分 {impact_score}/10).'
        )

        # 行动建议(基于 ot+维度)
        if ot == 'O':
            advice = self._build_opportunity_advice(intel)
        else:
            advice = self._build_threat_advice(intel)

        # 标签
        tags = _extract_tags(full_text)

        # 伪流式: 如果传入 on_token, 按字符逐个吐出 summary + advice,
        # 让前端 SSE 页面也能在 Mock 模式下看到流式效果 (与 DeepSeek 接口对齐)
        if on_token is not None:
            import time as _time
            try:
                # 0) 先吐一段伪思考 (仅在 on_thinking 存在时) — 让前端左侧"思考模式"也能看到流式
                if on_thinking is not None:
                    think_text = (
                        f'[思考] 首先拆解此条情报: 标题为《{intel.title[:60]}》, '
                        f'关联战略维度={intel.strategic_dimension or "未指定"}, '
                        f'目标市场={intel.target_market or "global"}.\n'
                        f'判断 PEST 分类: 在文本中检索到与 {pest} 类型相关的关键词, '
                        f'因此划入 {pest}.\n'
                        f'机会/威胁: 情感倒向呈 {sentiment}, 综合出 {ot}.\n'
                        f'4 维评分推演: 相关度 {score_relevance}/4 (维度匹配), '
                        f'紧迫度 {score_urgency}/3 (函数词命中 {urgency_hits} 个), '
                        f'权威性 {score_authority}/2 (信息源 {auth_hits} 个), '
                        f'范围 {score_scope}/1 (地理关键词 {scope_hits} 个), '
                        f'总分 {impact_score}/10 → 影响等级 {level}.\n'
                        f'下面输出结构化结果。'
                    )
                    for ch in think_text:
                        try:
                            on_thinking(ch)
                        except Exception:
                            break
                        _time.sleep(0.005)
                preview = (
                    f'[Mock LLM] PEST={pest} OT={ot} LEVEL={level} '
                    f'总分={impact_score}/10\n\n'
                    f'摘要: {summary}\n\n'
                    f'判断理由: {rationale}\n\n'
                    f'行动建议:\n{advice}'
                )
                for ch in preview:
                    try:
                        on_token(ch)
                    except Exception:
                        break
                    _time.sleep(0.008)
            except Exception:
                pass

        # 构造 chain (供前端"分析过程"展示)
        chain = [
            {'step': 'pest_classify',
             'prompt': self._build_pest_prompt(intel)[:200] + '...',
             'response': f'PEST={pest}, OT={ot}, LEVEL={level}'},
            {'step': 'value_score',
             'prompt': '4维价值评分',
             'response': (f'相关度={score_relevance} 紧迫度={score_urgency} '
                          f'权威性={score_authority} 规模={score_scope} '
                          f'总分={impact_score}')},
            {'step': 'summary',
             'prompt': '生成摘要+理由',
             'response': summary},
            {'step': 'action',
             'prompt': '战略行动建议',
             'response': advice},
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
            action_advice=advice,
            tags=tags,
            chain=chain,
        )

    def _build_opportunity_advice(self, intel: IntelInput) -> str:
        d = intel.strategic_dimension
        market = intel.target_market or '目标市场'
        if d == 'competition':
            return f'1) 立即评估在 {market} 的差异化定位;\n2) 加速本地达人合作放大窗口期;\n3) 增加广告预算 1-2 倍 5 天内复盘 ROI.'
        if d == 'product':
            return f'1) 在 {market} 开启该品类的小批量试投放;\n2) 锁定 3-5 个本地 KOL 联名推广;\n3) 配合本地化包装迭代.'
        if d == 'platform':
            return f'1) 30 天内完成 {market} 平台新规配套改造;\n2) 申报官方扶持项目;\n3) 评估广告位投放节奏调整.'
        if d == 'social':
            return f'1) 借势热点话题在 {market} 发布短视频;\n2) 联动 2-3 位本地 KOL 二次传播;\n3) 评估官方账号矩阵化运营.'
        if d == 'regulation':
            return f'1) 法务团队 7 天内对照新规自查;\n2) 申请 {market} 自贸/便利化资质;\n3) 调整 HS 编码与申报策略.'
        return '1) 评估机会量级与可达人群;\n2) 制定 30/60/90 天行动方案;\n3) 设置关键里程碑与责任人.'

    def _build_threat_advice(self, intel: IntelInput) -> str:
        d = intel.strategic_dimension
        market = intel.target_market or '目标市场'
        if d == 'competition':
            return f'1) 30 天内完成 {market} 同类产品对比分析;\n2) 推出限时差异化卖点应对竞品促销;\n3) 储备 2 个备选爆款防止单点失守.'
        if d == 'product':
            return f'1) 排查 {market} 对应品类品控风险;\n2) 建立差评闭环与售后兜底机制;\n3) 评估替代材料/工艺降本 5-10%.'
        if d == 'platform':
            return f'1) 立即排查 {market} 平台合规风险;\n2) 备份资金与库存关键数据;\n3) 评估多平台分散运营对冲风险.'
        if d == 'social':
            return f'1) 启动 {market} 公关响应预案;\n2) 准备官方说明 + 本地账号澄清;\n3) 加强达人内容审核流程.'
        if d == 'regulation':
            return f'1) 法务联合财务 72 小时内重新核算 {market} 到岸成本;\n2) 评估转口/转单可行性;\n3) 准备客户沟通与价格调整方案.'
        return '1) 评估风险敞口;\n2) 制定应急预案;\n3) 同步关键利益相关方.'

    # 兼容 base 的解析钩子 (Mock 不会调用)
    def _parse_pest(self, resp): return {'pest': 'E', 'ot': 'O', 'level': 'M'}
    def _parse_score(self, resp): return {'relevance': 2.5, 'urgency': 1.5, 'authority': 1.0, 'scope': 0.5, 'sentiment': 'neutral'}
    def _parse_summary(self, resp): return ('summary', 'rationale', ['tag'])
    def _parse_action(self, resp): return 'mock advice'
