# -*- coding: utf-8 -*-
"""快速探测 DeepSeek v4-pro 流式行为: TTFB / 首个 reasoning / 首个 content / 总耗时."""
import urllib.request
import json
import time

t0 = time.time()
body = {
    'model': 'deepseek-v4-pro',
    'messages': [
        {'role': 'system', 'content': '你是出海企业战略情报分析师, 严格按用户要求返回 JSON.'},
        {'role': 'user', 'content': '''请对下面这条情报做一次产品级的深度战略分析, 返回如下 JSON:
{"pest_type":"P|E|S|T","opportunity_or_threat":"O|T","impact_level":"H|M|L","summary":"60~120字","rationale":"300~500字","action_advice":"500~800字, 用 1)/2)/3) 分条","tags":["5~8 个标签"]}

【情报】
标题: 美联储 9 月降息 25bp, 鲍尔金表示不排除后续进一步宽松
正文: 2026-09-18 美联储宊会以 8:1 投票比例决定将联邦基金利率下调 25bp 至 4.75%–5.00%区间, 这是本轮加息周期以来首次降息. 鲍尔在记者会上表示通胀指数近 6 个月鲁棒下行、劳动力市场限冷信号增强, 委员会将限据数据判断后续路径, 不排除进一步宽松. 殊后美股三大指数隶雪, 纳指涨近 1.4%, 10年期美债收益率下行至 3.62%, 美元指数跳水 0.6%, 黄金创新高.
目标市场: global
战略维度: macro_finance
信息源: Reuters

【公司情况】
优势: 东南亚本地供应链, 全渠道品牌运营能力
劣势: 资金成本高, 外汇对冲能力弱

只返回 JSON, 不要解释、不要 markdown 代码块.'''},
    ],
    'temperature': 0.4,
    'max_tokens': 16384,
    'stream': True,
}
req = urllib.request.Request(
    'https://api.deepseek.com/v1/chat/completions',
    data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
    headers={
        'Authorization': 'Bearer ***REDACTED-DEEPSEEK-KEY***',
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'text/event-stream',
    },
    method='POST',
)

print('connecting...')
resp = urllib.request.urlopen(req, timeout=180)
print('TTFB=%.3fs' % (time.time() - t0))

rc_count = 0
ct_count = 0
first_rc = None
first_ct = None
chunk_count = 0
last_log = time.time()

for raw_line in resp:
    s = raw_line.decode('utf-8', 'ignore').strip()
    if not s.startswith('data:'):
        continue
    p = s[5:].strip()
    if p == '[DONE]':
        break
    try:
        d = json.loads(p)
    except Exception:
        continue
    chunk_count += 1
    choices = d.get('choices') or []
    if not choices:
        continue
    delta = choices[0].get('delta') or {}
    rc = delta.get('reasoning_content') or ''
    ct = delta.get('content') or ''
    if rc:
        rc_count += len(rc)
        if first_rc is None:
            first_rc = time.time() - t0
            print('first reasoning @%.3fs len=%d  preview=%r' % (first_rc, len(rc), rc[:30]))
    if ct:
        ct_count += len(ct)
        if first_ct is None:
            first_ct = time.time() - t0
            print('first content   @%.3fs len=%d  preview=%r' % (first_ct, len(ct), ct[:30]))
    # 每 2 秒打一次进度
    if time.time() - last_log > 2:
        last_log = time.time()
        print('  ...@%.1fs reasoning=%d  content=%d  chunks=%d' % (
            time.time() - t0, rc_count, ct_count, chunk_count))

elapsed = time.time() - t0
print('=' * 60)
print('DONE @%.3fs' % elapsed)
print('  reasoning_chars = %d' % rc_count)
print('  content_chars   = %d' % ct_count)
print('  chunks          = %d' % chunk_count)
print('  reasoning rate  = %.1f chars/s' % (rc_count / max(elapsed, 0.001)))
print('  content rate    = %.1f chars/s' % (ct_count / max(elapsed, 0.001)))
