/* 多智能体控制台 JS */
(function () {
  'use strict';

  const NODE_NAMES = ['collector', 'classifier', 'briefer', 'dispatcher'];
  const VERDICT_CLS = {
    done: 'verdict-ok', failed: 'verdict-fail', running: 'verdict-warn',
    pending: 'verdict-info', '': 'verdict-pending',
  };
  const VERDICT_LABEL = {
    done: '完成', failed: '失败', running: '执行中', pending: '待处理',
  };
  const LOGS_COLS = 'grid-template-columns: 28px 1.4fr 1fr 1.6fr 80px 2fr 130px;';

  let lastTraceId = null;

  /* ---- 节点状态 ---- */
  async function loadNodeStatus() {
    try {
      const data = await SR.api('/api/agents/nodes/');
      const nodeMap = {};
      (data.nodes || []).forEach(n => { nodeMap[n.node] = n; });

      NODE_NAMES.forEach((name, i) => {
        const n = nodeMap[name] || {};
        const total = document.getElementById(`ncTotal${i}`);
        const status = document.getElementById(`ncStatus${i}`);
        if (total) total.textContent = n.total ?? '--';
        if (status) {
          const s = n.last_status || '';
          const cls = VERDICT_CLS[s] || 'verdict-pending';
          const label = VERDICT_LABEL[s] || (s || '未知');
          status.innerHTML = `<span class="verdict ${cls}">${SR.escapeHtml(label)}</span>`;
        }
      });
    } catch (e) {
      SR.toast.error('节点状态加载失败', e.message);
    }
  }

  /* ---- 日志列表 ---- */
  async function loadLogs(traceId) {
    const tbody = document.getElementById('logsTbody');
    if (!tbody) return;
    try {
      let url = '/api/agents/logs/?size=50';
      if (traceId) url += '&trace_id=' + encodeURIComponent(traceId);
      const data = await SR.api(url);
      const items = data.items || [];
      if (!items.length) {
        tbody.innerHTML = '<div class="list-empty"><i class="ri-inbox-line"></i>暂无日志</div>';
        return;
      }
      tbody.innerHTML = items.map((log, idx) => {
        const cls = VERDICT_CLS[log.status] || 'verdict-pending';
        const label = VERDICT_LABEL[log.status] || (log.status || '未知');
        const output = log.output ? JSON.stringify(log.output).slice(0, 60) : '—';
        const shortTrace = (log.trace_id || '').slice(0, 8);
        const safeTrace = SR.escapeHtml(log.trace_id || '');
        return `<div class="list-row" style="${LOGS_COLS};cursor:pointer" data-trace="${safeTrace}" title="点击查看该 trace 链路">
          <span class="idx">${String(idx + 1).padStart(2, '0')}</span>
          <div><code class="mono" title="${safeTrace}">${SR.escapeHtml(shortTrace)}…</code></div>
          <div><span class="verdict verdict-info">${SR.escapeHtml(log.msg_type || '')}</span></div>
          <div class="muted ellipsis">${SR.escapeHtml(log.sender || '-')} → <b style="color:var(--text-1)">${SR.escapeHtml(log.receiver || '-')}</b></div>
          <div><span class="verdict ${cls}">${SR.escapeHtml(label)}</span></div>
          <div class="muted ellipsis" title="${SR.escapeHtml(output)}">${SR.escapeHtml(output)}</div>
          <div class="muted">${SR.fmtDt(log.created_at)}</div>
        </div>`;
      }).join('');
      // 整行点击 → 加载该 trace 链路到画布
      tbody.querySelectorAll('.list-row[data-trace]').forEach(row => {
        row.addEventListener('click', () => {
          const tid = row.getAttribute('data-trace');
          if (tid) agentsQueryTrace(tid);
        });
      });
    } catch (e) {
      tbody.innerHTML = `<div class="list-empty"><i class="ri-error-warning-line"></i>加载失败: ${SR.escapeHtml(e.message)}</div>`;
    }
  }

  /* ---- 追溯链路 (Canvas 节点编辑器) ---- */
  let traceCanvasState = null; // 全局画布状态

  function initTraceCanvas(container, steps, traceId) {
    // 布局参数（单行排列 + 随机扰动）
    const CARD_W = 200, CARD_H = 130, GAP_X = 80;
    const PADDING = 16; // 画布高度缩小后的边距
    // 随机偏移幅度（让排列看起来不千篇一律）
    const JIT_X = 40; // ±20px（较小，避免与相邻节点重叠）
    const JIT_Y = 50; // ±25px

    // 清空容器 + 启用画布样式
    container.innerHTML = '';
    container.classList.add('has-canvas');

    // 信息标签
    const infoEl = document.createElement('div');
    infoEl.className = 'trace-canvas-info';
    infoEl.innerHTML = `trace_id: <code class="mono">${SR.escapeHtml(traceId)}</code> · 共 ${steps.length} 步 <span class="muted">（拖拽节点 / 中键平移 / 滚轮缩放 / 空白拖动框选 / Shift 追加）</span>`;
    container.appendChild(infoEl);

    // Canvas 层 (画连接线)
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    // 节点 DOM 层
    const nodesLayer = document.createElement('div');
    nodesLayer.className = 'trace-nodes-layer';
    container.appendChild(nodesLayer);

    // 框选叠加层
    const selRectEl = document.createElement('div');
    selRectEl.className = 'trace-selection-rect';
    selRectEl.style.display = 'none';
    container.appendChild(selRectEl);

    // 计算初始节点位置（所有节点排在一行 + 随机上下左右偏移）
    const baseY = PADDING + 30;
    const MIN_GAP_X = 24; // 相邻卡片的最小水平间距，避免随机偏移后重叠
    let prevRight = -Infinity;
    const nodes = steps.map((s, i) => {
      const baseX = PADDING + i * (CARD_W + GAP_X);
      const dx = (Math.random() - 0.5) * JIT_X;
      const dy = (Math.random() - 0.5) * JIT_Y;
      let nodeX = baseX + dx;
      // 强制与上一个节点保持 MIN_GAP_X 间距，避免偏移后重叠
      if (i > 0 && nodeX < prevRight + MIN_GAP_X) {
        nodeX = prevRight + MIN_GAP_X;
      }
      prevRight = nodeX + CARD_W;
      return {
        id: i,
        x: nodeX,
        y: baseY + dy,
        w: CARD_W,
        h: CARD_H,
        step: s,
        el: null,
      };
    });

    // 画布状态
    const state = {
      panX: 0, panY: 0,
      zoom: 1,
      isPanning: false,
      panStartX: 0, panStartY: 0,
      dragNode: null,
      dragOffX: 0, dragOffY: 0,
      dragSnapshots: null,    // 多节点同步拖动快照
      dragStartNX: 0, dragStartNY: 0,
      dragMoved: false,       // 拖动是否产生位移
      isSelecting: false,
      selStartX: 0, selStartY: 0,
      selRectEl: selRectEl,
      selected: new Set(),    // 选中节点 id 集合
      nodes: nodes,
      canvas: canvas,
      container: container,
      nodesLayer: nodesLayer,
      detailEl: null,
    };
    traceCanvasState = state;

    // 尺寸适配（提前到 fit 之前，使 canvas 按容器实际尺寸初始化）
    function resizeCanvas() {
      const rect = container.getBoundingClientRect();
      canvas.width = rect.width * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      canvas.style.width = rect.width + 'px';
      canvas.style.height = rect.height + 'px';
      drawConnections(state);
    }
    resizeCanvas();
    const ro = new ResizeObserver(resizeCanvas);
    ro.observe(container);

    // 自适应缩放：按包围盒计算 zoom 与 pan，使所有卡片在一行内全部可见
    // useReal=true 时使用卡片实际尺寸（offsetWidth/Height），否则使用估算值
    function fitToView(useReal) {
      if (!state.nodes.length) return;
      const rect = container.getBoundingClientRect();
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      state.nodes.forEach(n => {
        const w = (useReal && n.el) ? n.el.offsetWidth  : n.w;
        const h = (useReal && n.el) ? n.el.offsetHeight : n.h;
        if (n.x < minX) minX = n.x;
        if (n.y < minY) minY = n.y;
        if (n.x + w > maxX) maxX = n.x + w;
        if (n.y + h > maxY) maxY = n.y + h;
      });
      const bw = (maxX - minX) + PADDING * 2;
      const bh = (maxY - minY) + PADDING * 2;
      const zx = rect.width / bw;
      const zy = rect.height / bh;
      state.zoom = Math.max(0.3, Math.min(1, zx, zy));
      state.panX = (rect.width  - (maxX - minX) * state.zoom) / 2 - minX * state.zoom;
      state.panY = (rect.height - (maxY - minY) * state.zoom) / 2 - minY * state.zoom;
      applyTransform(state);
      drawConnections(state);
    }

    // 【关键】在创建卡片 DOM 之前先用估算尺寸 fit 一次，
    // 让 state.zoom / pan 提前就位，避免先以 zoom=1 画一帧再跳动重置
    fitToView(false);

    // 创建节点卡片 DOM
    nodes.forEach((node) => {
      const s = node.step;
      const cls = VERDICT_CLS[s.status] || 'verdict-pending';
      const label = VERDICT_LABEL[s.status] || (s.status || '');
      const out = s.output ? JSON.stringify(s.output).slice(0, 60) : '';

      const card = document.createElement('div');
      card.className = 'trace-node-card';
      card.innerHTML = `
        <div class="tn-sender">${SR.escapeHtml(s.sender || 'start')}</div>
        <div class="tn-receiver">${SR.escapeHtml(s.receiver || '')}</div>
        <div><span class="verdict ${cls}">${SR.escapeHtml(label)}</span></div>
        ${out ? `<div class="tn-output">${SR.escapeHtml(out)}</div>` : ''}
        <div class="tn-time">${SR.fmtDt(s.created_at)}</div>
      `;
      nodesLayer.appendChild(card);
      node.el = card;
      updateCardPos(node, state);

      // 节点左键：选中 + 准备拖动
      card.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();

        // Shift 追加/反选；否则如果未选中则单选当前
        if (e.shiftKey) {
          if (state.selected.has(node.id)) {
            state.selected.delete(node.id);
            card.classList.remove('selected');
          } else {
            state.selected.add(node.id);
            card.classList.add('selected');
          }
        } else if (!state.selected.has(node.id)) {
          state.nodes.forEach(n => n.el && n.el.classList.remove('selected'));
          state.selected.clear();
          state.selected.add(node.id);
          card.classList.add('selected');
        }

        state.dragNode = node;
        state.dragMoved = false;
        state.dragOffX = (e.clientX - state.panX) / state.zoom - node.x;
        state.dragOffY = (e.clientY - state.panY) / state.zoom - node.y;
        state.dragStartNX = node.x;
        state.dragStartNY = node.y;
        // 多选拖动快照
        state.dragSnapshots = Array.from(state.selected).map(id => {
          const n = state.nodes[id];
          return { node: n, sx: n.x, sy: n.y };
        });
        card.classList.add('dragging');
      });

      // 双击展示详情
      card.addEventListener('dblclick', (e) => {
        e.preventDefault();
        e.stopPropagation();
        showNodeDetail(node, state);
      });
    });

    // 容器左键：空白处启动框选；中键：平移
    container.addEventListener('mousedown', (e) => {
      if (e.button === 1) {
        e.preventDefault();
        state.isPanning = true;
        state.panStartX = e.clientX - state.panX;
        state.panStartY = e.clientY - state.panY;
        container.classList.add('panning');
        return;
      }
      if (e.button !== 0) return;
      // 如果点在卡片上，由卡片自己的 mousedown 处理
      if (e.target.closest && e.target.closest('.trace-node-card')) return;
      // 点详情弹窗外 → 关闭详情
      if (state.detailEl && !state.detailEl.contains(e.target)) {
        closeNodeDetail(state);
      }
      // 未按 Shift 点空白 → 清空已选中
      if (!e.shiftKey) {
        state.selected.forEach(id => {
          const n = state.nodes[id];
          if (n && n.el) n.el.classList.remove('selected');
        });
        state.selected.clear();
      }
      // 开始框选
      const cr = container.getBoundingClientRect();
      state.isSelecting = true;
      state.selStartX = e.clientX - cr.left;
      state.selStartY = e.clientY - cr.top;
      selRectEl.style.display = 'block';
      selRectEl.style.left = state.selStartX + 'px';
      selRectEl.style.top = state.selStartY + 'px';
      selRectEl.style.width = '0px';
      selRectEl.style.height = '0px';
    });

    // 滚轮缩放
    container.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = container.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const oldZoom = state.zoom;
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      state.zoom = Math.min(3, Math.max(0.3, state.zoom * delta));
      state.panX = mx - (mx - state.panX) * (state.zoom / oldZoom);
      state.panY = my - (my - state.panY) * (state.zoom / oldZoom);
      applyTransform(state);
      drawConnections(state);
    }, { passive: false });

    document.addEventListener('mousemove', (e) => {
      // 框选进行中
      if (state.isSelecting) {
        const cr = container.getBoundingClientRect();
        const cx = e.clientX - cr.left;
        const cy = e.clientY - cr.top;
        const x = Math.min(cx, state.selStartX);
        const y = Math.min(cy, state.selStartY);
        const w = Math.abs(cx - state.selStartX);
        const h = Math.abs(cy - state.selStartY);
        selRectEl.style.left = x + 'px';
        selRectEl.style.top = y + 'px';
        selRectEl.style.width = w + 'px';
        selRectEl.style.height = h + 'px';
        return;
      }
      if (state.isPanning) {
        state.panX = e.clientX - state.panStartX;
        state.panY = e.clientY - state.panStartY;
        applyTransform(state);
        drawConnections(state);
      }
      if (state.dragNode) {
        const node = state.dragNode;
        const newX = (e.clientX - state.panX) / state.zoom - state.dragOffX;
        const newY = (e.clientY - state.panY) / state.zoom - state.dragOffY;
        const dx = newX - state.dragStartNX;
        const dy = newY - state.dragStartNY;
        if (Math.abs(dx) > 1 || Math.abs(dy) > 1) state.dragMoved = true;
        if (state.dragSnapshots && state.dragSnapshots.length > 1) {
          state.dragSnapshots.forEach(snap => {
            snap.node.x = snap.sx + dx;
            snap.node.y = snap.sy + dy;
            updateCardPos(snap.node, state);
          });
        } else {
          node.x = newX;
          node.y = newY;
          updateCardPos(node, state);
        }
        drawConnections(state);
      }
    });

    document.addEventListener('mouseup', (e) => {
      // 框选结束
      if (state.isSelecting) {
        state.isSelecting = false;
        const sr = selRectEl.getBoundingClientRect();
        // 只有拖出足够大才算有效框选
        if (sr.width > 3 && sr.height > 3) {
          state.nodes.forEach(n => {
            if (!n.el) return;
            const nr = n.el.getBoundingClientRect();
            const inter = !(nr.right < sr.left || nr.left > sr.right || nr.bottom < sr.top || nr.top > sr.bottom);
            if (inter) {
              state.selected.add(n.id);
              n.el.classList.add('selected');
            }
          });
        }
        selRectEl.style.display = 'none';
      }
      if (state.isPanning) {
        state.isPanning = false;
        container.classList.remove('panning');
      }
      if (state.dragNode) {
        state.dragNode.el.classList.remove('dragging');
        state.dragNode = null;
        state.dragSnapshots = null;
        state.dragMoved = false;
      }
    });

    // 防止中键默认行为
    container.addEventListener('auxclick', (e) => { if (e.button === 1) e.preventDefault(); });

    // 初始绘制 + 真实尺寸下的二次校正（卡片实际高度可能因文本换行与估算不同）
    applyTransform(state);
    drawConnections(state);
    requestAnimationFrame(() => requestAnimationFrame(() => fitToView(true)));
  }

  function updateCardPos(node, state) {
    if (!node.el) return;
    const tx = node.x * state.zoom + state.panX;
    const ty = node.y * state.zoom + state.panY;
    node.el.style.transform = `translate(${tx}px, ${ty}px) scale(${state.zoom})`;
    node.el.style.transformOrigin = '0 0';
  }

  function applyTransform(state) {
    state.nodes.forEach(n => updateCardPos(n, state));
    // 背景点阵跟随平移 + 缩放
    const bgSize = 24 * state.zoom;
    state.container.style.backgroundSize = `${bgSize}px ${bgSize}px`;
    state.container.style.backgroundPosition = `${state.panX}px ${state.panY}px`;
  }

  function drawConnections(state) {
    const canvas = state.canvas;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.scale(dpr, dpr);

    const DOT_R = 4 * state.zoom;

    for (let i = 0; i < state.nodes.length - 1; i++) {
      const from = state.nodes[i];
      const to = state.nodes[i + 1];

      // 使用实际渲染尺寸（卡片宽/高会随内容变化）
      // 以保证端点严格落在右边线 / 左边线的垂直中心
      const fromRealW = from.el ? from.el.offsetWidth : from.w;
      const fromRealH = from.el ? from.el.offsetHeight : from.h;
      const toRealH = to.el ? to.el.offsetHeight : to.h;

      // from 右边线中点 → to 左边线中点
      const fromX = (from.x + fromRealW) * state.zoom + state.panX;
      const fromY = (from.y + fromRealH / 2) * state.zoom + state.panY;
      const toX = to.x * state.zoom + state.panX;
      const toY = (to.y + toRealH / 2) * state.zoom + state.panY;

      // 根据目标节点状态决定颜色
      const nextStatus = to.step.status;
      let lineColor = '#888888';
      if (nextStatus === 'failed') lineColor = '#d12e2e';
      else if (nextStatus === 'running' || nextStatus === 'pending') lineColor = '#e9d31d';
      else if (nextStatus === 'done') lineColor = '#3df57f';

      // 画虚线 (bezier)
      ctx.beginPath();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 1.5 * state.zoom;
      ctx.moveTo(fromX, fromY);
      const cpX = (fromX + toX) / 2;
      ctx.bezierCurveTo(cpX, fromY, cpX, toY, toX, toY);
      ctx.stroke();
      ctx.setLineDash([]);

      // 起始端小圆点
      ctx.beginPath();
      ctx.arc(fromX, fromY, DOT_R, 0, Math.PI * 2);
      ctx.fillStyle = lineColor;
      ctx.fill();

      // 终止端小圆点
      ctx.beginPath();
      ctx.arc(toX, toY, DOT_R, 0, Math.PI * 2);
      ctx.fillStyle = lineColor;
      ctx.fill();
    }

    ctx.restore();
  }

  /* ---- 节点详情弹窗 ---- */
  function showNodeDetail(node, state) {
    closeNodeDetail(state);
    const s = node.step;
    const cls = VERDICT_CLS[s.status] || 'verdict-pending';
    const label = VERDICT_LABEL[s.status] || (s.status || '');

    const detail = document.createElement('div');
    detail.className = 'trace-node-detail';
    const outputStr = s.output ? JSON.stringify(s.output, null, 2) : '—';
    const payloadStr = s.payload ? JSON.stringify(s.payload, null, 2) : '—';
    const errorStr = s.error || '';

    detail.innerHTML = `
      <div class="tnd-head">
        <h4>${SR.escapeHtml(s.receiver || 'unknown')}</h4>
        <span class="tnd-close" title="关闭"><i class="ri-close-line"></i></span>
      </div>
      <div class="tnd-row"><span class="tnd-label">发送方</span><span class="tnd-val">${SR.escapeHtml(s.sender || '-')}</span></div>
      <div class="tnd-row"><span class="tnd-label">接收方</span><span class="tnd-val">${SR.escapeHtml(s.receiver || '-')}</span></div>
      <div class="tnd-row"><span class="tnd-label">状态</span><span class="tnd-val"><span class="verdict ${cls}">${SR.escapeHtml(label)}</span></span></div>
      <div class="tnd-row"><span class="tnd-label">消息类型</span><span class="tnd-val">${SR.escapeHtml(s.msg_type || '-')}</span></div>
      <div class="tnd-row"><span class="tnd-label">消息ID</span><span class="tnd-val mono" style="font-size:var(--fz-xxs)">${SR.escapeHtml(s.msg_id || '-')}</span></div>
      <div class="tnd-row"><span class="tnd-label">创建时间</span><span class="tnd-val">${SR.fmtDt(s.created_at)}</span></div>
      <div class="tnd-row"><span class="tnd-label">完成时间</span><span class="tnd-val">${SR.fmtDt(s.finished_at)}</span></div>
      ${errorStr ? `<div class="tnd-row"><span class="tnd-label" style="color:var(--info-red)">错误</span><span class="tnd-val" style="color:var(--info-red)">${SR.escapeHtml(errorStr)}</span></div>` : ''}
      <details open style="margin-top:6px"><summary style="cursor:pointer;color:var(--text-tertiary);font-size:var(--fz-xxs)">输出详情</summary><pre>${SR.escapeHtml(outputStr)}</pre></details>
      <details open style="margin-top:4px"><summary style="cursor:pointer;color:var(--text-tertiary);font-size:var(--fz-xxs)">载荷详情</summary><pre>${SR.escapeHtml(payloadStr)}</pre></details>
    `;

    // 右侧抽屉式：portal 到 body，CSS 控制位置与动画
    document.body.appendChild(detail);
    state.detailEl = detail;

    detail.querySelector('.tnd-close').addEventListener('click', () => closeNodeDetail(state));
  }

  function closeNodeDetail(state) {
    if (state.detailEl) {
      state.detailEl.remove();
      state.detailEl = null;
    }
  }

  async function loadTrace(traceId) {
    const container = document.getElementById('traceTimeline');
    if (!container) return;
    if (!traceId) {
      container.classList.remove('has-canvas');
      container.innerHTML = '<div class="empty-state"><i class="ri-flow-chart"></i><div class="es-title">请输入 trace_id</div></div>';
      return;
    }
    SR.api(`/api/agents/logs/${encodeURIComponent(traceId)}/`).then((data) => {
      const steps = data.steps || [];
      if (!steps.length) {
        container.classList.remove('has-canvas');
        container.innerHTML = '<div class="empty-state"><i class="ri-search-line"></i><div class="es-title">未找到链路</div><div class="es-sub">该 trace_id 没有日志记录</div></div>';
        return;
      }
      initTraceCanvas(container, steps, traceId);
    }).catch((e) => {
      container.classList.remove('has-canvas');
      container.innerHTML = `<div class="empty-state"><i class="ri-error-warning-line"></i><div class="es-title">查询失败</div><div class="es-sub">${SR.escapeHtml(e.message)}</div></div>`;
    });
  }

  /* ---- 触发 Pipeline ---- */
  async function runPipeline() {
    const market = document.getElementById('pipelineMarket')?.value || 'global';
    const period = document.getElementById('pipelinePeriod')?.value || 'daily';
    const limit = parseInt(document.getElementById('pipelineLimit')?.value || '3', 10);
    const statusEl = document.getElementById('pipelineStatus');
    const btns = [document.getElementById('btnRunPipeline'),
                  document.getElementById('btnRunPipelineInline')];

    btns.forEach(b => b && (b.disabled = true));
    if (statusEl) statusEl.innerHTML = '<span class="verdict verdict-warn">执行中</span> <span class="muted">Pipeline 执行中，请稍候…</span>';

    try {
      const data = await SR.api('/api/agents/run/', {
        method: 'POST',
        body: JSON.stringify({ market, period, limit }),
      });
      lastTraceId = data.trace_id;
      if (statusEl) statusEl.innerHTML = `<span class="verdict verdict-ok">完成</span> <span class="muted">trace_id:</span> <code class="mono" style="cursor:pointer" onclick="agentsQueryTrace('${SR.escapeHtml(data.trace_id)}')">${SR.escapeHtml(data.trace_id)}</code> <span class="muted">· ${data.steps} 步</span>`;
      SR.toast.success('Pipeline 执行完成', `共 ${data.steps} 步`);
      // 自动填入 trace_id 并加载链路
      const ti = document.getElementById('traceInput');
      if (ti) ti.value = data.trace_id;
      await loadTrace(data.trace_id);
      await loadLogs(data.trace_id);
      await loadNodeStatus();
    } catch (e) {
      if (statusEl) statusEl.innerHTML = `<span class="verdict verdict-fail">失败</span> <span class="muted">${SR.escapeHtml(e.message)}</span>`;
      SR.toast.error('Pipeline 执行失败', e.message);
    } finally {
      btns.forEach(b => b && (b.disabled = false));
    }
  }

  /* ---- 供 HTML 内联调用 ---- */
  window.agentsQueryTrace = function (traceId) {
    const ti = document.getElementById('traceInput');
    if (ti) ti.value = traceId;
    loadTrace(traceId);
    loadLogs(traceId);
  };

  /* ---- WebSocket 监听 agent.pipeline_done ---- */
  document.addEventListener('sr:ws', function (ev) {
    const d = ev.detail || {};
    if (d.type === 'agent.pipeline_done') {
      SR.toast.success('Agent Pipeline 完成', `共 ${d.steps} 步`);
      loadNodeStatus();
      loadLogs();
    }
  });

  /* ---- 初始化 ---- */
  document.addEventListener('DOMContentLoaded', function () {
    loadNodeStatus();
    loadLogs();

    document.getElementById('btnRefreshNodes')?.addEventListener('click', loadNodeStatus);
    document.getElementById('btnRefreshLogs')?.addEventListener('click', () => loadLogs());
    document.getElementById('btnRunPipeline')?.addEventListener('click', runPipeline);
    document.getElementById('btnRunPipelineInline')?.addEventListener('click', runPipeline);
    document.getElementById('btnQueryTrace')?.addEventListener('click', function () {
      const tid = document.getElementById('traceInput')?.value.trim();
      if (tid) { loadTrace(tid); loadLogs(tid); }
    });
    document.getElementById('traceInput')?.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        const tid = this.value.trim();
        if (tid) { loadTrace(tid); loadLogs(tid); }
      }
    });
  });
})();
