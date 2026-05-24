# SSE 真流式落地复盘

> 日期：2026-05-24
> 适用范围：Django 4.x + Daphne (ASGI) + StreamingHttpResponse 流式接口
> 关联接口：`/api/intel/<id>/analyze-stream/`

---

## 一、症状

前端打开 SSE 连接后：
- TTFB（首字节时间）≈ 整个 LLM 调用耗时（10s+）
- 所有 `event: token` 事件**在响应结束的瞬间一次性到达**
- 浏览器/`urllib` 客户端均观察到相同行为
- 浮窗"思考"和"正文"两栏长时间一片空白，最后秒级"跳出来"

显然不是真流式，而是被某一层全量缓冲后才一次性发送。

## 二、根因（最隐蔽的一层）

**Django 4.x 在 ASGI（Daphne）下，同步 view 返回 `StreamingHttpResponse(generator)` 时，会用 `sync_to_async(generator)` 把整个生成器在线程池中消费完，再把组装好的全量响应交给 ASGI handler 发送。**

也就是说：

> "换 Daphne 就能流" 是**假命题** — view 本身**必须是 `async def`**，generator 也必须是 `async generator`，才能让每个 `yield` 立刻流到对端。

这一层不会有任何错误日志，行为也没有官方文档明确描述，是这次卡两天的主因。

## 三、之前误诊过的几层（按时间）

| # | 假设的原因 | 处理 | 结果 |
|---|---|---|---|
| 1 | runserver 不支持流式 | 切换 Daphne | 治标不治本（仍是同步 view） |
| 2 | 小 chunk 被 ASGI 聚合 | 每个 event 加 256B padding | 缓解但根因仍在 |
| 3 | `ASGIStaticFilesHandler` 全局缓冲 HTTP | URLRouter 路径分流 | 路对了但还有第二层 |
| 4 | **同步 view 在 ASGI 下被全量缓冲** | **改 `async def` + `asyncio.to_thread` 桥接 queue** | ✅ 彻底解决 |

## 四、翻盘的关键诊断手段

写两个**最小可复现样本**接口，每秒 yield 一个 `tick` 事件：

- `/api/intel/probe-sync/`：`def view(...) → StreamingHttpResponse(sync_gen)`
- `/api/intel/probe-async/`：`async def view(...) → StreamingHttpResponse(async_gen)`

用 `urllib.request` 字符级读取（不要 `readlines`，会等响应结束）观察每个 event 的相对到达时间：

```
sync  探测 TTFB = 10.4s （全部一起到达）
async 探测 TTFB = 0.02s （tick 间隔 ~1.0s，真流）
```

铁证如山，不再瞎猜。

> **方法论沉淀**：玄学问题用"做最小可复现样本对比"绝大多数时候能一击毙命。

## 五、最终落地方案

### 1. View 必须 async

```python
import asyncio
from django.http import StreamingHttpResponse

async def analyze_stream_view(request, info_id):
    queue = asyncio.Queue()

    def on_token(tok):
        # LLM 在 worker 线程里同步调用，这里把数据扔进 asyncio Queue
        asyncio.run_coroutine_threadsafe(queue.put(tok), loop)

    async def event_stream():
        # 把同步的 LLM 调用桥接到线程池，主协程继续从 queue 取数据流出去
        task = asyncio.create_task(asyncio.to_thread(do_llm_blocking, on_token))
        while not task.done() or not queue.empty():
            try:
                tok = await asyncio.wait_for(queue.get(), timeout=0.1)
                yield f'event: token\ndata: {json.dumps({"token": tok})}\n\n'
            except asyncio.TimeoutError:
                continue
        yield 'event: done\ndata: {}\n\n'

    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
```

### 2. 必备响应头

```python
response['Cache-Control'] = 'no-cache, no-transform'
response['X-Accel-Buffering'] = 'no'   # nginx 反代时关键
response['Connection'] = 'keep-alive'
```

### 3. 客户端配套

- 前端 `EventSource` 即开即流（无需改造）
- 浏览器对 < 2KB 响应有时不渲染，必要时仍保留 padding（256B 已足够）

## 六、检查清单（避免再次踩坑）

新增 SSE 接口前确认：

- [ ] view 是 `async def`，**不是** `def`
- [ ] generator 是 `async def event_stream()`，**不是**普通函数
- [ ] 阻塞调用（LLM、DB）一律用 `asyncio.to_thread` 或 `sync_to_async` 包
- [ ] 路由经过 `URLRouter`，没被 `ASGIStaticFilesHandler` 拦截
- [ ] 响应头包含 `X-Accel-Buffering: no`
- [ ] 用 `urllib.request.urlopen(...).read(1)` 字符级读取验证 TTFB < 100ms（参考第四节）

## 七、前端版本指纹

最终上线版本：

| 文件 | 版本指纹 |
|---|---|
| `templates/dashboard/feed.html` (inline) | `v=2026-05-24-stable` |
| `static/js/feed.js` | `v=stream-20260524-async-view` |

`Ctrl+Shift+R` 硬刷可在 console 看到上述绿色日志，用于确认浏览器加载到的不是缓存旧版。
