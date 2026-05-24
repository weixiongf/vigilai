# ============================================================
# 作者：冯伟雄
# 项目：深圳 AI for Human 企业 Agent 挑战赛
# 时间：2026-05-23 12:30:00
# ============================================================

"""SSE 流式探测脚本 — 直接 HTTP 连本地 Daphne, 看每个 chunk 何时到达.

用法:
    .venv\\Scripts\\python.exe tests\\probe_sse_local.py sync
    .venv\\Scripts\\python.exe tests\\probe_sse_local.py async

预期:
    每秒收到一个 'tick' 事件, ts 间隔 ~1.0s
    如果 10 个 tick 同时到达 → 后端缓冲了响应
"""
from __future__ import annotations

import sys
import time
import urllib.request

mode = sys.argv[1] if len(sys.argv) > 1 else 'sync'
url = f'http://127.0.0.1:8000/api/intel/probe-{mode}/'

print(f'connecting {url} ...')
t0 = time.time()
req = urllib.request.Request(url, headers={'Accept': 'text/event-stream'})
resp = urllib.request.urlopen(req, timeout=120)
print(f'TTFB={time.time()-t0:.3f}s  status={resp.status}')

# 不要 readlines — 那会等响应结束. 用 read(1) 字符级读, 才能真实看到流式
buf = b''
n_events = 0
while True:
    ch = resp.read(1)
    if not ch:
        break
    buf += ch
    if buf.endswith(b'\n\n'):
        # 一个完整的 SSE event
        text = buf.decode('utf-8', errors='replace')
        if 'event:' in text:
            n_events += 1
            elapsed = time.time() - t0
            # 提取 event 名 + data
            ev = ''
            data = ''
            for line in text.split('\n'):
                if line.startswith('event: '):
                    ev = line[7:]
                elif line.startswith('data: '):
                    data = line[6:]
            print(f'  +{elapsed:6.3f}s  event={ev:8s}  data={data[:80]}')
            if ev == 'done':
                break
        buf = b''
print(f'==== total events={n_events}  elapsed={time.time()-t0:.3f}s ====')
