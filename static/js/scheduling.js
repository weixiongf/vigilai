/* 采集调度页 — KPI + 最近任务 (信息源 CRUD 已迁出到 sources 页) */
(function () {
  const { $, api, escapeHtml, fmtDt, toast } = window.SR;

  /* 本地缓存 + KPI 卡片过滤状态
     activeFilter: null 不过滤 | 'all' 全部（信息源卡片）
                   | 'running' | 'completed' | 'failed' */
  let allJobs = [];
  let activeFilter = null;

  function renderJobs(items) {
    const tb = $('#tblJobsBody');
    if (!tb) return;
    const cols = 'grid-template-columns: 28px 22px 1.6fr 1.4fr 110px 1fr 100px;';
    if (!items.length) {
      tb.innerHTML = activeFilter
        ? '<div class="list-empty"><i class="ri-filter-3-line"></i>当前筛选下暂无任务</div>'
        : '<div class="list-empty"><i class="ri-time-line"></i>暂无任务</div>';
      return;
    }
    tb.innerHTML = items.map((j, idx) => {
      const st = {
        running:   '<span class="verdict verdict-info">运行中</span>',
        completed: '<span class="verdict verdict-ok">完成</span>',
        failed:    '<span class="verdict verdict-fail">失败</span>',
        pending:   '<span class="verdict verdict-warn">排队</span>',
      }[j.status] || `<span class="verdict verdict-pending">${escapeHtml(j.status)}</span>`;
      const isReal = !!j.is_real;
      const dotColor = isReal ? 'var(--success, #22c55e)' : 'var(--gray-600, #6b7280)';
      const dotTitle = isReal
        ? '真实采集'
        : (j.used_simulation ? '仿真降级' : (j.real_capable ? '未走真实分支' : '仿真 / 未接入'));
      const dot = `<span class="src-dot" title="${dotTitle}" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${dotColor};box-shadow:0 0 0 2px rgba(255,255,255,.04);"></span>`;
      return `<div class="list-row" data-id="${j.id}" style="${cols}cursor:pointer;" title="点击查看采集详情">
        <span class="idx">${String(idx + 1).padStart(2, '0')}</span>
        <div style="display:flex;align-items:center;justify-content:center;">${dot}</div>
        <div><b>${escapeHtml(j.source_name)}</b></div>
        <div>${fmtDt(j.started_at)}</div>
        <div>${st}</div>
        <div>+${j.items_new} / ${j.items_fetched}</div>
        <div><span class="muted">${escapeHtml(j.triggered_by)}</span></div>
      </div>`;
    }).join('');
  }

  function applyFilter() {
    let items = allJobs;
    if (activeFilter && activeFilter !== 'all') {
      items = allJobs.filter(j => j.status === activeFilter);
    }
    // 真实采集任务置顶（稳定排序：内部仍按 started_at desc）
    items = items.slice().sort((a, b) => (b.is_real ? 1 : 0) - (a.is_real ? 1 : 0));
    renderJobs(items);
  }

  async function loadOverview() {
    let d;
    try { d = await api('/api/sources/overview/'); }
    catch (e) { return; }
    $('#kpiSrcTotal').textContent = d.total;
    $('#kpiSrcActive').textContent = d.active;
    const ag = d.items_aggregate || {};
    $('#kpiFetched').textContent = ag.fetched || 0;
    $('#kpiNewItems').textContent = ag.n || 0;

    const js = d.jobs_status || [];
    const get = k => (js.find(x => x.status === k) || {}).cnt || 0;
    $('#kpiJobsRunning').textContent = get('running');
    $('#kpiJobsDone').textContent = get('completed');
    $('#kpiJobsFail').textContent = get('failed');
  }

  async function loadJobs() {
    let d;
    try { d = await api('/api/sources/jobs/'); }
    catch (e) { return; }
    allJobs = d.items || [];
    applyFilter();
  }

  /* KPI 卡片 → 点击高亮 + 列表过滤；再次点击同一卡片退出过滤 */
  function bindKpiCards() {
    document.querySelectorAll('.mini-stat[data-filter]').forEach(card => {
      card.addEventListener('click', () => {
        const f = card.dataset.filter;
        activeFilter = (activeFilter === f) ? null : f;
        document.querySelectorAll('.mini-stat[data-filter]').forEach(c => {
          c.classList.toggle('is-active', c.dataset.filter === activeFilter);
        });
        applyFilter();
      });
    });
  }

  document.addEventListener('sr:ws', (ev) => {
    const d = ev.detail || {};
    if (d.type === 'crawl.completed' || d.type === 'crawl.failed' || d.type === 'intel.analyzed') {
      loadJobs();
      loadOverview();
    }
  });

  /* ============ 右侧抽屉 — 采集任务详情 ============ */
  function openDrawer() {
    const dr = $('#jobDrawer');
    if (!dr) return;
    dr.hidden = false;
    dr.setAttribute('aria-hidden', 'false');
    void dr.offsetWidth;
    dr.classList.add('open');
    document.addEventListener('keydown', onDrawerKey);
  }
  function closeDrawer() {
    const dr = $('#jobDrawer');
    if (!dr) return;
    dr.classList.remove('open');
    dr.setAttribute('aria-hidden', 'true');
    setTimeout(() => { if (!dr.classList.contains('open')) dr.hidden = true; }, 260);
    document.removeEventListener('keydown', onDrawerKey);
    document.querySelectorAll('#tblJobsBody .list-row.selected')
      .forEach(r => r.classList.remove('selected'));
  }
  function onDrawerKey(e) { if (e.key === 'Escape') closeDrawer(); }
  const _jdClose = $('#jobDrawerClose');
  if (_jdClose) _jdClose.addEventListener('click', closeDrawer);

  function fmtElapsed(startIso, endIso) {
    if (!startIso || !endIso) return '—';
    const ms = new Date(endIso) - new Date(startIso);
    if (!(ms >= 0)) return '—';
    if (ms < 1000) return ms + ' ms';
    if (ms < 60000) return (ms / 1000).toFixed(1) + ' s';
    return Math.floor(ms / 60000) + ' 分 ' + Math.round((ms % 60000) / 1000) + ' 秒';
  }

  function renderJobItems(d) {
    const tb = $('#jdItemsBody');
    if (!tb) return;
    const items = d.items || [];
    const hint = $('#jdItemsHint');
    if (hint) {
      // 优先看本任务实际是否走了仿真分支 (used_simulation),
      // 其次看该信息源是否能路由到真实爬虫 (real_capable)
      const usedSim = !!d.used_simulation;
      const isReal = !!d.real_capable && !usedSim;
      const realLabel = usedSim
        ? '<span class="verdict verdict-warn" style="margin-right:6px;">仿真降级</span>'
        : (isReal
            ? '<span class="verdict verdict-ok" style="margin-right:6px;">真实采集</span>'
            : '<span class="verdict verdict-pending" style="margin-right:6px;">未接入真实爬虫</span>');
      hint.innerHTML = `${realLabel}展示 ${items.length} 条 / 本任务抽取 ${d.items_fetched}`;
    }
    if (!items.length) {
      tb.innerHTML = '<div class="list-empty"><i class="ri-inbox-line"></i>本任务未入库新记录（可能全部去重）</div>';
      return;
    }
    tb.innerHTML = items.map((it, i) => {
      const sevCls = { high: 'verdict-fail', medium: 'verdict-warn', low: 'verdict-info' }[it.severity] || 'verdict-pending';
      const impCls = { opportunity: 'verdict-ok', risk: 'verdict-fail', watch: 'verdict-warn', neutral: 'verdict-pending' }[it.impact_type] || 'verdict-pending';
      const tags = (it.tags || []).slice(0, 5).map(t =>
        `<span class="chip" style="font-size:var(--fz-xxs);margin-right:4px;">${escapeHtml(t)}</span>`
      ).join('');
      const simBadge = it.is_simulated
        ? '<span class="verdict verdict-warn" style="margin-left:6px;">仿真</span>'
        : '<span class="verdict verdict-ok" style="margin-left:6px;">真实</span>';
      const meta = [
        it.target_market && `<span class="muted">市场：${escapeHtml(it.target_market)}</span>`,
        it.country && `<span class="muted">国家：${escapeHtml(it.country)}</span>`,
        it.language && `<span class="muted">语言：${escapeHtml(it.language)}</span>`,
        it.published_at && `<span class="muted">发布：${fmtDt(it.published_at)}</span>`,
      ].filter(Boolean).join(' · ');
      const score = (it.impact_score != null) ? it.impact_score.toFixed(1) : '—';
      return `<div class="list-row" style="display:block;padding:10px 8px;border-bottom:1px solid var(--gray-500);">
        <div style="display:flex;align-items:flex-start;gap:6px;">
          <span class="idx" style="flex-shrink:0;">${String(i + 1).padStart(2, '0')}</span>
          <div style="flex:1;min-width:0;">
            <div style="font-weight:600;color:var(--text-primary);line-height:1.4;word-break:break-word;">
              ${escapeHtml(it.title || '无标题')}${simBadge}
            </div>
            ${it.summary ? `<div class="muted" style="margin-top:4px;line-height:1.5;word-break:break-word;">${escapeHtml(it.summary)}</div>` : ''}
            <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
              ${it.impact_type ? `<span class="verdict ${impCls}">${escapeHtml(it.impact_type)}</span>` : ''}
              ${it.severity ? `<span class="verdict ${sevCls}">${escapeHtml(it.severity)}</span>` : ''}
              ${it.pest_type ? `<span class="verdict verdict-info">PEST：${escapeHtml(it.pest_type)}</span>` : ''}
              <span class="muted" style="font-size:var(--fz-xxs);">影响分：${score}</span>
            </div>
            ${tags ? `<div style="margin-top:6px;">${tags}</div>` : ''}
            ${meta ? `<div style="margin-top:4px;font-size:var(--fz-xxs);">${meta}</div>` : ''}
            ${it.url ? `<div style="margin-top:4px;"><a href="${escapeHtml(it.url)}" target="_blank" rel="noopener" class="linklike" style="font-size:var(--fz-xxs);word-break:break-all;"><i class="ri-external-link-line"></i> ${escapeHtml(it.url)}</a></div>` : ''}
          </div>
        </div>
      </div>`;
    }).join('');
  }

  async function loadJobDetail(id) {
    openDrawer();
    $('#jobDetailHint').textContent = `#${id}`;
    $('#jdItemsBody').innerHTML = '<div class="list-empty"><i class="ri-loader-4-line"></i>加载中…</div>';
    let d;
    try { d = await api(`/api/sources/jobs/${id}/`); }
    catch (e) { return toast(e.message || '加载详情失败', 'error'); }

    const stMap = {
      running:   { cls: 'verdict-info', txt: '运行中' },
      completed: { cls: 'verdict-ok',   txt: '完成' },
      failed:    { cls: 'verdict-fail', txt: '失败' },
      pending:   { cls: 'verdict-warn', txt: '排队' },
    };
    const stInfo = stMap[d.status] || { cls: 'verdict-pending', txt: d.status || '—' };
    const stEl = $('#jdStatus');
    stEl.className = 'verdict ' + stInfo.cls;
    stEl.textContent = stInfo.txt;

    $('#jdSource').textContent = d.source_name || '—';
    $('#jdSpider').textContent = d.source_spider || '—';
    const realBadge = $('#jdRealBadge');
    const usedSim = !!d.used_simulation;
    if (usedSim) {
      realBadge.className = 'verdict verdict-warn';
      realBadge.textContent = '仿真降级';
    } else if (d.real_capable) {
      realBadge.className = 'verdict verdict-ok';
      realBadge.textContent = '真实采集';
    } else {
      realBadge.className = 'verdict verdict-pending';
      realBadge.textContent = '未接入';
    }
    $('#jdStarted').textContent = d.started_at ? fmtDt(d.started_at) : '—';
    $('#jdFinished').textContent = d.finished_at ? fmtDt(d.finished_at) : '进行中…';
    $('#jdElapsed').textContent = fmtElapsed(d.started_at, d.finished_at);
    $('#jdItemsNew').textContent = d.items_new || 0;
    $('#jdItemsFetched').textContent = d.items_fetched || 0;
    $('#jdTrigger').textContent = d.triggered_by || '—';
    const a = $('#jdOfficial');
    a.href = d.source_official_url || '#';
    a.textContent = d.source_official_url || '—';

    const errWrap = $('#jdErrorWrap');
    if (d.error_log && d.error_log.trim()) {
      errWrap.style.display = '';
      $('#jdError').textContent = d.error_log;
    } else {
      errWrap.style.display = 'none';
    }

    renderJobItems(d);

    document.querySelectorAll('#tblJobsBody .list-row').forEach(row => {
      row.classList.toggle('selected', Number(row.dataset.id) === Number(id));
    });
  }

  /* 任务行点击 → 打开抽屉 */
  const _tblBody = $('#tblJobsBody');
  if (_tblBody) {
    _tblBody.addEventListener('click', (ev) => {
      const row = ev.target.closest('.list-row');
      if (!row || !row.dataset.id) return;
      loadJobDetail(row.dataset.id);
    });
  }

  bindKpiCards();
  loadOverview();
  loadJobs();
  setInterval(loadOverview, 30000);
  setInterval(loadJobs, 30000);
})();
