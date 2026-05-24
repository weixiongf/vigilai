/* 情报动态 — 列表 + 详情 + 实时推送 */
(function () {
  // 版本标记: 浏览器 console 立即可见, 用于确认加载到的是带流式的最新版
  console.info('%c[feed.js] v=stream-20260524-daphne', 'color:#4ea1ff;font-weight:bold;font-size:14px;',
               '· 顶部浮窗 sseFloatPanel · Daphne ASGI · 极简 startStream');
  // 全局注入 blink/spin 动画 (仅初始化一次)
  if (!document.getElementById('feedStreamKeyframes')) {
    const _styleEl = document.createElement('style');
    _styleEl.id = 'feedStreamKeyframes';
    _styleEl.textContent = '@keyframes blink { 0%,49% { opacity: 1 } 50%,100% { opacity: 0 } }';
    document.head.appendChild(_styleEl);
  }
  const { $, api, escapeHtml, fmtDt, toast,
          DIM_LABEL, LEVEL_TAG, LEVEL_LABEL, OT_LABEL, PEST_LABEL } = window.SR;
  let page = 1, total = 0;
  let currentId = null;
  // 列表项当前 AI 状态: { [id]: 'analyzing' | 'analyzed' | 'failed' }
  const aiStatus = Object.create(null);
  // 批量分析时累积的 LLM 输出缓存 (抽屉迟打开也能看到完整流)
  const streamBuffer = Object.create(null);
  // 当前进行中的 SSE 流, 切换情报时关闭旧流
  let activeStream = null;
  // 批量分析当前范围
  let batchScope = 'unanalyzed';
  // 原始数据状态筛选: '' = 全部 / '0' = 未分析 / '1' = 已分析
  let processedFilter = '';
  const SCOPE_LABEL = {
    today: '今天', '7d': '七天', unanalyzed: '未分析',
    top20: '前 20 条', top50: '前 50 条',
  };

  const OT_VERDICT = { O: 'verdict-ok', T: 'verdict-fail' };
  const LEVEL_VERDICT = { H: 'verdict-fail', M: 'verdict-warn', L: 'verdict-info' };

  // ---------- 右侧抽屉（与 sources/agents 详情抽屉一致）----------
  function openDrawer() {
    const dr = $('#feedDrawer');
    if (!dr) return;
    dr.hidden = false;
    dr.setAttribute('aria-hidden', 'false');
    void dr.offsetWidth;
    dr.classList.add('open');
    document.addEventListener('keydown', onDrawerKey);
  }
  function closeDrawer() {
    const dr = $('#feedDrawer');
    if (!dr) return;
    dr.classList.remove('open');
    dr.setAttribute('aria-hidden', 'true');
    setTimeout(() => { if (!dr.classList.contains('open')) dr.hidden = true; }, 260);
    document.removeEventListener('keydown', onDrawerKey);
    // 退出时关闭进行中的 SSE 流
    if (activeStream) { try { activeStream.close(); } catch (e) {} activeStream = null; }
    document.querySelectorAll('.feed-item.selected').forEach(el => el.classList.remove('selected'));
    currentId = null;
  }
  function onDrawerKey(e) { if (e.key === 'Escape') closeDrawer(); }
  const _feedDrawerClose = $('#feedDrawerClose');
  if (_feedDrawerClose) _feedDrawerClose.addEventListener('click', closeDrawer);

  // 时间窗口（不在页面表单中，由 URL 参数或 chip 关闭驱动）
  const timeWindow = { days: 0, hours: 0 };
  // 市场过滤（由驾驶舱 Top10 市场行点击传入）
  let marketFilter = '';

  // 从 URL 查询参数初始化筛选项（驾驶舱 KPI 卡片跳转场景）
  function parseInitFiltersFromURL() {
    const sp = new URLSearchParams(location.search);
    if (!sp.toString()) return;
    const setVal = (id, key) => {
      if (sp.has(key)) {
        const el = $('#' + id);
        if (!el) return;
        const v = sp.get(key);
        if (el.tagName === 'SELECT') {
          if ([...el.options].some(o => o.value === v)) el.value = v;
        } else {
          el.value = v;
        }
      }
    };
    setVal('feedQ', 'q');
    setVal('feedDim', 'dimension');
    setVal('feedPest', 'pest');
    setVal('feedOT', 'ot');
    setVal('feedLevel', 'level');
    setVal('feedMinScore', 'min_score');
    setVal('feedOrder', 'order');
    // market 参数 —— 页面没有 select，用内部变量维护
    if (sp.has('market')) marketFilter = sp.get('market');
    if (sp.has('hours')) {
      const h = parseInt(sp.get('hours'), 10);
      if (h > 0) timeWindow.hours = h;
    } else if (sp.has('days')) {
      const d = parseInt(sp.get('days'), 10);
      if (d > 0) timeWindow.days = d;
    }
  }
  parseInitFiltersFromURL();

  function buildQS() {
    const qs = new URLSearchParams();
    qs.append('page', page);
    qs.append('size', 20);
    const k = $('#feedQ').value.trim();
    if (k) qs.append('q', k);
    if ($('#feedDim').value) qs.append('dimension', $('#feedDim').value);
    if ($('#feedPest').value) qs.append('pest', $('#feedPest').value);
    if ($('#feedOT').value) qs.append('ot', $('#feedOT').value);
    if ($('#feedLevel').value) qs.append('level', $('#feedLevel').value);
    if ($('#feedMinScore').value) qs.append('min_score', $('#feedMinScore').value);
    if (timeWindow.hours) qs.append('hours', timeWindow.hours);
    else if (timeWindow.days) qs.append('days', timeWindow.days);
    if (marketFilter) qs.append('market', marketFilter);
    if (processedFilter !== '') qs.append('processed', processedFilter);
    qs.append('order', $('#feedOrder').value);
    return qs.toString();
  }

  function renderTagbar() {
    const wrap = $('#feedTagbar');
    if (!wrap) return;
    const items = [];
    const k = $('#feedQ').value.trim();
    if (k) items.push({ key: '关键词', val: k, clear: () => { $('#feedQ').value = ''; } });
    [['feedDim', '维度'], ['feedPest', 'PEST'], ['feedOT', '机会/威胁'], ['feedLevel', '等级'], ['feedMinScore', '最小分']].forEach(([id, key]) => {
      const el = $('#' + id);
      if (el && el.value) {
        const val = el.tagName === 'SELECT' ? el.selectedOptions[0].text : el.value;
        items.push({ key, val, clear: () => { el.value = ''; } });
      }
    });
    if (timeWindow.hours) {
      items.push({
        key: '时间窗口',
        val: `近 ${timeWindow.hours} 小时`,
        clear: () => { timeWindow.hours = 0; },
      });
    } else if (timeWindow.days) {
      items.push({
        key: '时间窗口',
        val: `近 ${timeWindow.days} 天`,
        clear: () => { timeWindow.days = 0; },
      });
    }
    if (marketFilter) {
      items.push({
        key: '市场',
        val: marketFilter,
        clear: () => { marketFilter = ''; },
      });
    }
    if (!items.length) {
      wrap.innerHTML = '<span class="tagbar-empty">未应用筛选条件</span>';
      return;
    }
    wrap.innerHTML = items.map((it, i) => `
      <span class="filter-chip" data-i="${i}" title="${escapeHtml(it.key)}: ${escapeHtml(it.val)}">
        <span class="key">${escapeHtml(it.key)}</span>
        <span class="val">${escapeHtml(it.val)}</span>
        <i class="x ri-close-line" title="移除此条件"></i>
      </span>`).join('') + '<span class="tagbar-clear" id="feedTagClear" title="清除全部筛选"><i class="ri-close-circle-line"></i> 清除全部</span>';
    wrap.querySelectorAll('.filter-chip').forEach(chip => {
      chip.querySelector('.x').addEventListener('click', () => {
        items[parseInt(chip.dataset.i)].clear();
        page = 1; loadList();
      });
    });
    const clearAll = $('#feedTagClear');
    if (clearAll) clearAll.addEventListener('click', () => {
      items.forEach(it => it.clear());
      page = 1; loadList();
    });
  }

  async function loadList() {
    let d;
    try { d = await api('/api/intel/?' + buildQS()); }
    catch (e) {
      $('#feedList').innerHTML = `<div class="list-empty"><i class="ri-error-warning-line"></i>加载失败: ${escapeHtml(e.message)}</div>`;
      return toast.error('加载失败', e.message);
    }
    total = d.total;
    $('#feedTotal').textContent = total + ' 条';
    $('#feedPage').textContent = `第 ${page} / ${Math.max(1, Math.ceil(total / 20))} 页`;
    // 顶部原始数据状态统计提示
    const procStat = $('#feedProcStat');
    if (procStat) {
      const lbl = processedFilter === '0' ? '未分析'
                : (processedFilter === '1' ? '已分析' : '全部');
      procStat.textContent = `${lbl} · 共 ${total} 条`;
    }

    renderTagbar();

    const wrap = $('#feedList');
    wrap.innerHTML = (d.items || []).map((it, idx) => {
      const otCls = OT_VERDICT[it.opportunity_or_threat] || 'verdict-pending';
      const lvCls = LEVEL_VERDICT[it.impact_level] || 'verdict-pending';
      const score = (it.impact_score || 0).toFixed(1);
      const st = aiStatus[it.id];
      const statusHtml = st === 'analyzing'
        ? `<span class="ai-status ai-running" title="分析中…"><i class="ri-loader-4-line spin"></i></span>`
        : (st === 'analyzed'
          ? `<span class="ai-status ai-done" title="分析完成"><i class="ri-checkbox-circle-fill"></i></span>`
          : (st === 'failed'
            ? `<span class="ai-status ai-failed" title="分析失败"><i class="ri-error-warning-fill"></i></span>`
            : ''));
      // 原始数据视角: 已分析 / 未分析 两态徽章 (meta 行内, 不带小圆点)
      const procBadge = it.is_processed
        ? '<span class="verdict verdict-ok no-dot" title="已完成 LLM 分析"><i class="ri-checkbox-circle-line"></i> 已分析</span>'
        : '<span class="verdict verdict-pending no-dot" title="尚未调用 LLM 分析, 点“立即分析”一键调用"><i class="ri-time-line"></i> 未分析</span>';
      // 列表最右侧的醒目状态图标 (已分析=绿 / 未分析=灰 / 分析中=蓝) — 即时可见, 复用 verdict 色体系, 不带小圆点
      const rightProcBadge = (st === 'analyzing')
        ? '<span class="proc-dot verdict verdict-info no-dot" title="分析中…"><i class="ri-loader-4-line spin"></i> 分析中</span>'
        : (it.is_processed
          ? '<span class="proc-dot verdict verdict-ok no-dot" title="已完成 LLM 分析"><i class="ri-checkbox-circle-fill"></i> 已分析</span>'
          : '<span class="proc-dot verdict verdict-pending no-dot" title="尚未调用 LLM 分析"><i class="ri-time-line"></i> 未分析</span>');
      // 序号: 分析中显示 spinner, 其它显示数字 (data-idx 保留原序号)
      const idxNum = String(idx + 1).padStart(2, '0');
      const idxInner = (st === 'analyzing')
        ? '<i class="ri-loader-4-line spin"></i>'
        : idxNum;
      const simBadge = it.is_simulated
        ? '<i class="sim-dot sim-dot-sim" title="仿真兑底产生的演示数据"></i>'
        : '<i class="sim-dot sim-dot-real" title="真实采集"></i>';
      const urlBtn = it.url
        ? `<a class="btn btn-ghost btn-xs" target="_blank" rel="noopener"
              href="${escapeHtml(it.url)}" title="跳转原文" onclick="event.stopPropagation()">
             <i class="ri-external-link-line"></i> 原文
           </a>`
        : '';
      const urlLink = it.url
        ? `<a class="fi-source-link" target="_blank" rel="noopener"
              href="${escapeHtml(it.url)}" title="跳转原文页面" onclick="event.stopPropagation()">
             查看原文 <i class="ri-external-link-line"></i>
           </a>`
        : '';
      const preview = escapeHtml(it.content_preview || it.summary || '').slice(0, 220);
      const sourceName = escapeHtml((it.source && it.source.name) || '—');
      const sourceDesc = escapeHtml((it.source && (it.source.description || it.source.intro)) || '');
      return `
        <div class="feed-item" data-id="${it.id}">
          <div class="fi-idx" data-idx="${idxNum}">${idxInner}</div>
          <div class="fi-body">
            <div class="fi-head">
              <span class="fi-market verdict verdict-info no-dot" title="目标市场"><i class="ri-map-pin-line"></i> ${escapeHtml(it.target_market || '—')}</span>
              <h4 class="ti" title="${escapeHtml(it.title)}">${escapeHtml(it.title)}</h4>
              <span class="fi-flags">${simBadge}</span>
            </div>
            <div class="fi-meta">
              <span class="meta-chip" title="原文发布时间"><i class="ri-calendar-line"></i> ${fmtDt(it.published_at)}</span>
              <span class="meta-chip" title="系统采集时间"><i class="ri-download-cloud-line"></i> 采集 ${fmtDt(it.fetched_at)}</span>
              <span class="meta-chip" title="原文来源"><i class="ri-rss-line"></i> ${sourceName}${sourceDesc ? ` <em class="meta-sub">· ${sourceDesc}</em>` : ''}</span>
            </div>
            ${(preview || urlLink) ? `<div class="fi-preview" title="原文摘要预览">${preview}${urlLink ? ` ${urlLink}` : ''}</div>` : ''}
            <div class="fi-actions">
              <div class="feed-ops">
                <button class="btn btn-ghost btn-xs ai-btn" data-id="${it.id}"
                        title="立即对该原始条目调用 LLM 流式分析">
                  <i class="ri-flashlight-line"></i> 立即分析
                </button>
                ${statusHtml}
                ${rightProcBadge}
              </div>
            </div>
          </div>
          <div class="feed-item-tags feed-tags-right">
            <div class="tags-stack">
              <span class="mini-tag" title="战略维度"><em>维度</em><b>${DIM_LABEL[it.strategic_dimension] || escapeHtml(it.strategic_dimension || '—')}</b></span>
              <span class="mini-tag" title="PEST 分类"><em>PEST</em><b>${PEST_LABEL[it.pest_type] || escapeHtml(it.pest_type || '—')}</b></span>
              <span class="mini-tag mini-${otCls.replace('verdict-','')}" title="机会/威胁"><em>机/威</em><b>${OT_LABEL[it.opportunity_or_threat] || '—'}</b></span>
              <span class="mini-tag mini-${lvCls.replace('verdict-','')}" title="影响等级"><em>等级</em><b>${LEVEL_LABEL[it.impact_level] || '—'}</b></span>
            </div>
            <div class="impact-display impact-${(it.impact_level || 'pending').toLowerCase()}" title="影响指数 (0–10)">
              <div class="impact-score">${score}</div>
              <div class="impact-text">影响指数</div>
              <div class="impact-bar"><span style="width:${Math.min(100, (it.impact_score || 0) * 10)}%"></span></div>
            </div>
          </div>
        </div>
      `;
    }).join('') || '<div class="empty-state"><i class="ri-inbox-line"></i><div class="es-title">无符合条件的原始数据</div><div class="es-sub">去数据源/采集调度页点「立即触发采集」拉几条</div></div>';
    wrap.querySelectorAll('.feed-item').forEach(el => {
      el.addEventListener('click', () => loadDetail(parseInt(el.dataset.id)));
    });
    // 立即分析按钮: 阻止冒泡, 触发 SSE
    // ⚠️ 关键: 不要同时调 loadDetail() —— 它是 async fetch,
    // 100-300ms 后返回会用详情卡片覆盖 startStream 已写入的
    // 流式面板, 导致中间过程 token 全部丢失, 用户只能看到
    // result 事件一次性塑进去的结果 ("跳出来"). 改为由 startStream
    // done 事件后再 loadDetail 拉最终详情.
    wrap.querySelectorAll('.ai-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = parseInt(btn.dataset.id);
        currentId = id;
        document.querySelectorAll('.feed-item').forEach(el => {
          el.classList.toggle('selected', parseInt(el.dataset.id) === id);
        });
        startStream(id);
      });
    });
  }

  async function loadDetail(id) {
    currentId = id;
    openDrawer();
    document.querySelectorAll('.feed-item').forEach(el => {
      el.classList.toggle('selected', parseInt(el.dataset.id) === id);
    });
    let it;
    try { it = await api('/api/intel/' + id + '/'); }
    catch (e) { return toast.error('加载失败', e.message); }

    const tags = (it.tags || []).map(t => `<span class="verdict verdict-pending">${escapeHtml(t)}</span>`).join(' ');
    const score = (it.impact_score || 0).toFixed(1);
    const otCls = OT_VERDICT[it.opportunity_or_threat] || 'verdict-pending';
    const lvCls = LEVEL_VERDICT[it.impact_level] || 'verdict-pending';
    const chain = (it.analysis_chain || []).map(s =>
      `${s.step ? '[' + s.step + '] ' : ''}${s.output || s.input || JSON.stringify(s)}`
    ).join('\n\n');

    $('#feedDetail').innerHTML = `
      <h3 style="margin:0 0 6px;font-size:var(--fz-lg);color:var(--text-1);">${escapeHtml(it.title)}</h3>

      <div id="drawerStreamPanel" data-stream-id="${it.id}" style="display:${(aiStatus[it.id] === 'analyzing' || streamBuffer[it.id]) ? '' : 'none'};margin:8px 0 12px;padding:10px 12px;background:rgba(80,160,255,.08);border:1px solid rgba(80,160,255,.25);border-left:3px solid var(--color-info,#4ea1ff);border-radius:6px;">
        <div class="drawer-stream-head" style="display:flex;align-items:center;gap:8px;font-size:var(--fz-xs);color:var(--text-1);margin-bottom:6px;">
          <i class="${aiStatus[it.id] === 'analyzing' ? 'ri-cpu-line spin' : 'ri-checkbox-circle-fill'}" id="drawerStreamIcon"></i>
          <b id="drawerStreamTitle">${aiStatus[it.id] === 'analyzing' ? 'LLM 实时流式输出中…' : 'LLM 输出记录'}</b>
          <span class="muted" style="font-size:11px;margin-left:auto;" id="drawerStreamMeta">${streamBuffer[it.id] ? streamBuffer[it.id].length + ' 字' : ''}</span>
        </div>
        <div id="drawerStreamBody" style="max-height:220px;overflow:auto;padding:8px 10px;background:rgba(0,0,0,.18);border-radius:4px;font-size:var(--fz-xs);line-height:1.65;color:var(--text-1);white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">${escapeHtml(streamBuffer[it.id] || '')}</div>
      </div>
      <table class="kv-table">
        <tbody>
          <tr><th>市场</th>      <td><span class="verdict verdict-info">${escapeHtml(it.target_market || '—')}</span></td></tr>
          <tr><th>维度</th>      <td>${DIM_LABEL[it.strategic_dimension] || escapeHtml(it.strategic_dimension || '—')}</td></tr>
          <tr><th>PEST</th>      <td>${PEST_LABEL[it.pest_type] || escapeHtml(it.pest_type || '—')}</td></tr>
          <tr><th>机会/威胁</th> <td><span class="verdict ${otCls}">${OT_LABEL[it.opportunity_or_threat] || '—'}</span></td></tr>
          <tr><th>等级</th>      <td><span class="verdict ${lvCls}">${LEVEL_LABEL[it.impact_level] || '—'}</span></td></tr>
          <tr><th>影响分</th>    <td><b style="color:var(--text-1)">${score} / 10</b></td></tr>
          <tr><th>发布</th>      <td>${fmtDt(it.published_at)}</td></tr>
          <tr><th>来源</th>      <td>${escapeHtml((it.source && it.source.name) || '—')}</td></tr>
        </tbody>
      </table>

      <div class="section-title"><h2><i class="ri-bookmark-line"></i> 摘要</h2></div>
      <div class="summary">${escapeHtml(it.summary || it.title)}</div>

      <div class="section-title"><h2><i class="ri-target-line"></i> 行动建议</h2></div>
      <div class="advice">${escapeHtml(it.action_advice || '—')}</div>

      <div class="section-title"><h2><i class="ri-bar-chart-2-line"></i> 价值评分</h2></div>
      <div class="meta-grid kv-grid">
        <div><span class="label-key">业务相关</span> ${(it.score_relevance || 0).toFixed(1)} / 4</div>
        <div><span class="label-key">时效紧迫</span> ${(it.score_urgency || 0).toFixed(1)} / 3</div>
        <div><span class="label-key">权威性</span> ${(it.score_authority || 0).toFixed(1)} / 2</div>
        <div><span class="label-key">影响规模</span> ${(it.score_scope || 0).toFixed(1)} / 1</div>
      </div>

      ${tags ? '<div class="section-title"><h2><i class="ri-price-tag-3-line"></i> 标签</h2></div><div style="display:flex;flex-wrap:wrap;gap:6px;">' + tags + '</div>' : ''}

      <div class="section-title"><h2><i class="ri-link"></i> LLM 分析链</h2></div>
      <div class="chain">${escapeHtml(chain || '—')}</div>

      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn btn-ghost btn-sm" id="btnConfirm"><i class="ri-checkbox-circle-line"></i> 确认判断</button>
        <button class="btn btn-ghost btn-sm" id="btnIgnore"><i class="ri-eye-off-line"></i> 忽略</button>
        <button class="btn btn-ghost btn-sm" id="btnReanalyze"><i class="ri-refresh-line"></i> 重分析</button>
        <a class="btn btn-ghost btn-sm" target="_blank" rel="noopener" href="${escapeHtml(it.url || '#')}"><i class="ri-external-link-line"></i> 原文</a>
      </div>
    `;
    document.getElementById('btnConfirm').onclick = () => feedback(id, 'confirmed');
    document.getElementById('btnIgnore').onclick = () => feedback(id, 'ignored');
    document.getElementById('btnReanalyze').onclick = async () => {
      try {
        await api(`/api/intel/${id}/analyze/`, { method: 'POST' });
        toast.success('已提交', '已加入分析队列');
      } catch (e) { toast.error('提交失败', e.message); }
    };
  }

  async function feedback(id, action) {
    try {
      await api(`/api/intel/${id}/feedback/`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      toast.success('反馈已记录', action === 'confirmed' ? '确认判断' : '忽略');
    } catch (e) { toast.error('反馈失败', e.message); }
  }

  $('#btnFeedSearch').onclick = () => { page = 1; loadList(); };
  $('#btnFeedReset').onclick = () => {
    ['feedQ', 'feedDim', 'feedPest', 'feedOT', 'feedLevel', 'feedMinScore']
      .forEach(id => { const el = $('#' + id); if (el) el.value = ''; });
    $('#feedOrder').value = '-published_at';
    timeWindow.days = 0; timeWindow.hours = 0;
    marketFilter = '';
    processedFilter = '';
    document.querySelectorAll('#feedProcessedSwitch .proc-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.proc === '');
    });
    page = 1; loadList();
  };

  // 原始数据状态三态切换 (全部 / 未分析 / 已分析)
  document.querySelectorAll('#feedProcessedSwitch .proc-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      processedFilter = btn.dataset.proc || '';
      document.querySelectorAll('#feedProcessedSwitch .proc-btn').forEach(b => {
        b.classList.toggle('active', b === btn);
      });
      page = 1;
      loadList();
    });
  });
  $('#feedQ').addEventListener('keyup', e => { if (e.key === 'Enter') { page = 1; loadList(); } });
  ['feedDim', 'feedPest', 'feedOT', 'feedLevel', 'feedOrder'].forEach(id => {
    const el = $('#' + id);
    if (el) el.addEventListener('change', () => { page = 1; loadList(); });
  });
  $('#feedPrev').onclick = () => { if (page > 1) { page -= 1; loadList(); } };
  $('#feedNext').onclick = () => {
    if (page < Math.ceil(total / 20)) { page += 1; loadList(); }
  };

  document.addEventListener('sr:ws', (ev) => {
    const d = ev.detail || {};
    // 调试: 把所有与情报分析相关的 ws 事件打印到 console
    if (d && d.type && /^intel\.|^alert\./.test(d.type)) {
      if (d.type === 'intel.token') {
        // token 事件量大, 只打印简短摘要
        console.debug('[ws] intel.token id=%s idx=%s len=%s', d.id, d.idx,
                      (d.token || '').length);
      } else {
        console.debug('[ws]', d.type, d);
      }
    }
    // 抽屉流式面板 (当前打开的详情 == d.id 时才刷)
    const drawerSync = (kind, payload) => {
      if (!d.id || currentId !== d.id) return;
      const panel = document.getElementById('drawerStreamPanel');
      if (!panel || String(panel.dataset.streamId) !== String(d.id)) return;
      const body = document.getElementById('drawerStreamBody');
      const titleEl = document.getElementById('drawerStreamTitle');
      const iconEl = document.getElementById('drawerStreamIcon');
      const metaEl = document.getElementById('drawerStreamMeta');
      if (kind === 'analyzing') {
        panel.style.display = '';
        if (body) body.textContent = '';
        if (titleEl) titleEl.textContent = 'LLM 实时流式输出中…';
        if (iconEl) iconEl.className = 'ri-cpu-line spin';
        if (metaEl) metaEl.textContent = '';
      } else if (kind === 'token') {
        if (panel.style.display === 'none') panel.style.display = '';
        if (body) {
          body.textContent += payload || '';
          body.scrollTop = body.scrollHeight;
          if (metaEl) metaEl.textContent = `${body.textContent.length} 字`;
        }
      } else if (kind === 'analyzed') {
        if (titleEl) titleEl.textContent = 'LLM 输出完成 ✓ (正在刷新详情…)';
        if (iconEl) iconEl.className = 'ri-checkbox-circle-fill';
      } else if (kind === 'failed') {
        if (titleEl) titleEl.textContent = `LLM 分析失败: ${payload || ''}`;
        if (iconEl) iconEl.className = 'ri-error-warning-line';
      }
    };

    if (d.type === 'intel.analyzed' || d.type === 'alert.high_impact') {
      // 状态变为已完成
      if (d.id) {
        aiStatus[d.id] = 'analyzed';
        updateRowStatus(d.id);
        // 分析完成后保留流式面板 3 秒, 让用户看到全部输出, 然后收起
        const sNode = document.querySelector(`.feed-stream[data-stream-id="${d.id}"]`);
        if (sNode) {
          const head = sNode.querySelector('.feed-stream-head span');
          if (head) head.textContent = 'LLM 输出完成 ✓';
          const icon = sNode.querySelector('.feed-stream-head i');
          if (icon) { icon.classList.remove('spin'); icon.className = 'ri-checkbox-circle-fill'; }
          setTimeout(() => { sNode.style.display = 'none'; }, 3000);
        }
        drawerSync('analyzed');
        // 如果抽屉当前打开的就是该 id, 重新拉取详情 (刷新评分/摄要/行动建议)
        if (currentId === d.id) {
          setTimeout(() => {
            if (currentId === d.id) {
              delete streamBuffer[d.id];
              loadDetail(d.id);
            }
          }, 1200);
        } else {
          // 未打开抽屉也清一下缓存, 避免下次启动看到旧内容
          setTimeout(() => { delete streamBuffer[d.id]; }, 5000);
        }
      }
      if (page === 1) loadList();
    } else if (d.type === 'intel.analyzing' && d.id) {
      aiStatus[d.id] = 'analyzing';
      streamBuffer[d.id] = '';
      updateRowStatus(d.id);
      // 打开该行的流式面板 + 重置占位/计数器
      const sNode = document.querySelector(`.feed-stream[data-stream-id="${d.id}"]`);
      if (sNode) {
        sNode.style.display = '';
        const body = sNode.querySelector('.feed-stream-body');
        if (body) {
          body.dataset.empty = '1';
          body.innerHTML = '<span class="muted" style="opacity:.6;font-style:italic;">等待 LLM 返回第一段 token…</span>';
        }
        const head = sNode.querySelector('.feed-stream-head span');
        if (head) head.textContent = 'LLM 流式输出中…';
        const icon = sNode.querySelector('.feed-stream-head i');
        if (icon) { icon.className = 'ri-cpu-line spin'; }
        const counter = sNode.querySelector('.feed-stream-counter');
        if (counter) counter.textContent = '0 段 / 0 字';
      }
      drawerSync('analyzing');
    } else if (d.type === 'intel.token' && d.id && typeof d.token === 'string') {
      // 批量分析时 LLM 每输出一段 delta 的实时追加
      streamBuffer[d.id] = (streamBuffer[d.id] || '') + d.token;
      // 首个正文 token 抵达 → 抽屉插队展示该情报
      if (window.SR_openIntel && currentId !== d.id) {
        try { window.SR_openIntel(d.id); } catch (_) {}
      }
      drawerSync('token', d.token);
    } else if (d.type === 'intel.reasoning' && d.id && typeof d.token === 'string') {
      // 思考流 — 仅走顶部外浮窗对应的 Tab，不进抽屉
      if (window.SR_pushReasoning) {
        try { window.SR_pushReasoning(d.id, d.token); } catch (_) {}
      }
    } else if (d.type === 'intel.analyze_failed' && d.id) {
      aiStatus[d.id] = 'failed';
      updateRowStatus(d.id);
      const sNode = document.querySelector(`.feed-stream[data-stream-id="${d.id}"]`);
      if (sNode) {
        const head = sNode.querySelector('.feed-stream-head span');
        if (head) head.textContent = `LLM 分析失败: ${d.error || ''}`;
        const icon = sNode.querySelector('.feed-stream-head i');
        if (icon) { icon.classList.remove('spin'); icon.className = 'ri-error-warning-line'; }
      }
      drawerSync('failed', d.error || '');
    } else if (d.type === 'intel.batch_start') {
      toast.info('批量分析已启动', `共 ${d.count || 0} 条 · ${SCOPE_LABEL[batchScope] || ''} · LLM 将逐条流式输出`);
    } else if (d.type === 'intel.batch_done') {
      toast.success('批量分析完成',
        `成功 ${d.success || 0} / 失败 ${d.failed || 0}`);
      if (page === 1) loadList();
    }
  });

  // ========================================================
  // 列表项状态点 — 局部更新避免整列表重渲染
  // ========================================================
  function updateRowStatus(id) {
    const row = document.querySelector(`.feed-item[data-id="${id}"]`);
    if (!row) return;
    // 状态徽章 (.ai-status / .proc-dot) 现在放在左侧操作行的 .feed-ops 容器中
    const tags = row.querySelector('.feed-ops') || row.querySelector('.feed-item-tags');
    if (!tags) return;
    let badge = tags.querySelector('.ai-status');
    const st = aiStatus[id];
    const html = st === 'analyzing'
      ? `<i class="ri-loader-4-line spin"></i>`
      : (st === 'analyzed'
        ? `<i class="ri-checkbox-circle-fill"></i>`
        : (st === 'failed'
          ? `<i class="ri-error-warning-fill"></i>` : ''));
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'ai-status';
      tags.appendChild(badge);
    }
    badge.classList.remove('ai-running', 'ai-done', 'ai-failed');
    if (st === 'analyzing') badge.classList.add('ai-running');
    else if (st === 'analyzed') badge.classList.add('ai-done');
    else if (st === 'failed') badge.classList.add('ai-failed');
    badge.title = st === 'analyzing' ? '分析中…'
      : (st === 'analyzed' ? '分析完成'
        : (st === 'failed' ? '分析失败' : ''));
    badge.innerHTML = html;

    // 一、序号 idx 在分析中转圈, 完成/失败后恢复原数字
    const idxEl = row.querySelector('.fi-idx') || row.querySelector('.idx');
    if (idxEl) {
      const orig = idxEl.dataset.idx || idxEl.textContent.trim();
      if (st === 'analyzing') {
        idxEl.classList.add('idx-running');
        idxEl.innerHTML = '<i class="ri-loader-4-line spin"></i>';
      } else {
        idxEl.classList.remove('idx-running');
        idxEl.textContent = orig;
      }
    }

    // 二、最右侧 已分析/未分析/分析中 徽章同步刷新 (复用 verdict 色体系)
    let dot = tags.querySelector('.proc-dot');
    if (!dot) {
      dot = document.createElement('span');
      dot.className = 'proc-dot verdict verdict-info no-dot';
      tags.appendChild(dot);
    } else if (!dot.classList.contains('no-dot')) {
      dot.classList.add('no-dot');
    }
    dot.classList.remove('verdict-info', 'verdict-ok', 'verdict-warn', 'verdict-fail');
    if (st === 'analyzing') {
      dot.classList.add('verdict-info');
      dot.title = '分析中…';
      dot.innerHTML = '<i class="ri-loader-4-line spin"></i> 分析中';
    } else if (st === 'analyzed') {
      dot.classList.add('verdict-ok');
      dot.title = '已完成 LLM 分析';
      dot.innerHTML = '<i class="ri-checkbox-circle-fill"></i> 已分析';
    } else if (st === 'failed') {
      dot.classList.add('verdict-fail');
      dot.title = '分析失败';
      dot.innerHTML = '<i class="ri-error-warning-fill"></i> 分析失败';
    }
    // 未设状态时保留原初始渲染的 已/未分析 徽章不动
  }

  // ========================================================
  // SSE 流式分析 — 详情页实时展示 LLM 思维链
  // ========================================================
  function startStream(id) {
    if (activeStream) { try { activeStream.close(); } catch (e) {} activeStream = null; }
    aiStatus[id] = 'analyzing';
    streamBuffer[id] = '';
    updateRowStatus(id);
    openDrawer();

    const url = `/api/intel/${id}/analyze-stream/`;
    const es = new EventSource(url);
    activeStream = es;

    // 以下事件仅用于状态跟踪, 不创建任何 UI:
    // 所有流式 token 由 feed.html 中 inline monkey-patch 负责
    // 写入顶部搜索框 #feedQ.

    es.addEventListener('token', (e) => {
      try {
        const d = JSON.parse(e.data);
        const tok = d.token || '';
        streamBuffer[id] = (streamBuffer[id] || '') + tok;
      } catch (_) {}
    });

    es.addEventListener('result', () => {
      aiStatus[id] = 'analyzed';
    });

    es.addEventListener('done', () => {
      aiStatus[id] = 'analyzed';
      updateRowStatus(id);
      try { toast.success('分析完成', `#${id} 已写入数据库`); } catch (_) {}
      try { es.close(); } catch (e) {}
      if (activeStream === es) activeStream = null;
    });

    es.addEventListener('error', (e) => {
      try { const d = JSON.parse(e.data || '{}'); toast.error('分析异常', d.error || ''); } catch (_) {}
      aiStatus[id] = 'failed';
      updateRowStatus(id);
      try { es.close(); } catch (er) {}
      if (activeStream === es) activeStream = null;
    });
  }

  // ========================================================
  // 批量分析 — 下拉选范围 + POST /batch-analyze/
  // ========================================================
  function setupBatchAnalyze() {
    const wrap = $('#batchAnalyzeWrap');
    if (!wrap) return;
    const btnMain = $('#btnBatchAnalyze');
    const btnCaret = $('#btnBatchCaret');
    const menu = $('#batchScopeMenu');
    const tag = $('#batchScopeTag');

    const closeMenu = () => {
      menu.hidden = true;
      btnCaret.setAttribute('aria-expanded', 'false');
    };
    btnCaret.addEventListener('click', (e) => {
      e.stopPropagation();
      const willOpen = menu.hidden;
      menu.hidden = !willOpen;
      btnCaret.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });
    document.addEventListener('click', (e) => {
      if (!wrap.contains(e.target)) closeMenu();
    });
    menu.querySelectorAll('li[data-scope]').forEach(li => {
      li.addEventListener('click', () => {
        batchScope = li.dataset.scope;
        menu.querySelectorAll('li').forEach(x => x.classList.toggle('selected',
          x.dataset.scope === batchScope));
        if (tag) tag.textContent = SCOPE_LABEL[batchScope] || batchScope;
        closeMenu();
      });
    });

    btnMain.addEventListener('click', async () => {
      const filters = {
        market: '', // 页面未隐藏该筛选, 预留
        dimension: $('#feedDim').value,
        pest: $('#feedPest').value,
        ot: $('#feedOT').value,
        level: $('#feedLevel').value,
        min_score: $('#feedMinScore').value,
        q: $('#feedQ').value.trim(),
        order: $('#feedOrder').value,
      };
      btnMain.disabled = true;
      btnMain.classList.add('loading');
      try {
        const r = await api('/api/intel/batch-analyze/', {
          method: 'POST',
          body: JSON.stringify({ scope: batchScope, filters }),
        });
        if (!r.count) {
          toast.warn('无匹配情报', `当前范围(${SCOPE_LABEL[batchScope]})下为空`);
        } else {
          toast.success('已提交批量分析',
            `${r.count} 条 · ${SCOPE_LABEL[batchScope]} · 并发执行中`);
          (r.ids || []).forEach(i => { aiStatus[i] = 'analyzing'; updateRowStatus(i); });
        }
      } catch (e) {
        toast.error('提交失败', e.message);
      } finally {
        btnMain.disabled = false;
        btnMain.classList.remove('loading');
      }
    });
  }
  setupBatchAnalyze();

  loadList();

  // ============================================================
  // 对外暴露 — feed.html 顶部多 Tab 浮窗 inline 脚本调用
  //   · SR_openIntel(id)        : 以该 id 打开抽屉 (插队式, 不等当前动画)
  //   · SR_closeDrawer()        : 关闭抽屉
  //   · SR_streamBuffer        : 共享的 LLM token 累积区 (抽屉迟打开不丢 token)
  //   · SR_pushReasoning(id,t) : 预留 hook — 思考流在浮窗处理, 本文件不发送
  // ============================================================
  window.SR_openIntel = function (id) {
    if (!id) return;
    const nid = parseInt(id);
    if (currentId === nid) { openDrawer(); return; }
    loadDetail(nid);
  };
  window.SR_closeDrawer = closeDrawer;
  window.SR_streamBuffer = streamBuffer;
})();
