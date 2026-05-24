/* 信息源配置页 — 全宽列表 + 右侧抽屉详情 + 触发/启停 */
(function () {
  const { $, api, escapeHtml, fmtDt, fmtTime, toast } = window.SR;

  let currentSourceId = null;

  // ---------- 右侧抽屉 (与 agents canvas 节点详情一致) ----------
  function openDrawer() {
    const dr = $('#srcDrawer');
    if (!dr) return;
    dr.hidden = false;
    dr.setAttribute('aria-hidden', 'false');
    // 强制重启进场过渡
    void dr.offsetWidth;
    dr.classList.add('open');
    document.addEventListener('keydown', onDrawerKey);
  }
  function closeDrawer() {
    const dr = $('#srcDrawer');
    if (!dr) return;
    dr.classList.remove('open');
    dr.setAttribute('aria-hidden', 'true');
    // 等动画结束后隐藏，避免遮挡列表点击
    setTimeout(() => { if (!dr.classList.contains('open')) dr.hidden = true; }, 260);
    document.removeEventListener('keydown', onDrawerKey);
  }
  function onDrawerKey(e) { if (e.key === 'Escape') closeDrawer(); }
  const _closeBtn = $('#srcDrawerClose');
  if (_closeBtn) _closeBtn.addEventListener('click', closeDrawer);

  // ---------- KPI ----------
  async function loadOverview() {
    try {
      const d = await api('/api/sources/overview/');
      $('#kpiSrcTotal').textContent = d.total;
      $('#kpiSrcActive').textContent = d.active;
      const ag = d.items_aggregate || {};
      $('#kpiSrcFetch24').textContent = ag.fetched || 0;
      $('#kpiSrcNew24').textContent = ag.n || 0;

      const types = (d.by_type || []).map(x => `${x.source_type}:${x.cnt}`).join(' · ');
      $('#kpiSrcTypes').textContent = (d.by_type || []).length;
      $('#kpiSrcTypesFoot').textContent = types || '—';
    } catch (e) { /* ignore */ }

    try {
      const m = await api('/api/sources/simulation-mode/');
      const labels = { auto: '自动', simulated: '仿真', real: '真实' };
      $('#kpiSrcMode').textContent = labels[m.mode] || m.mode;
      $('#kpiSrcFailing').textContent = m.failing_count || 0;
    } catch (e) { /* ignore */ }
  }

  // ---------- 已选筛选标签条 ----------
  function renderTagbar() {
    const wrap = $('#srcTagbar'); if (!wrap) return;
    const items = [];
    const k = $('#srcQ').value.trim();
    if (k) items.push({ key: '关键词', val: k, clear: () => { $('#srcQ').value = ''; $('#srcQ').dispatchEvent(new Event('input', { bubbles: true })); } });
    if ($('#srcType').value) items.push({ key: '类型', val: $('#srcType').selectedOptions[0].text, clear: () => { $('#srcType').value = ''; } });
    if ($('#srcPriority').value) items.push({ key: '优先级', val: $('#srcPriority').selectedOptions[0].text, clear: () => { $('#srcPriority').value = ''; } });
    if ($('#srcActive').value) items.push({ key: '状态', val: $('#srcActive').selectedOptions[0].text, clear: () => { $('#srcActive').value = ''; } });
    if (!items.length) {
      wrap.innerHTML = '<span class="tagbar-empty">未应用筛选条件</span>';
      return;
    }
    wrap.innerHTML = items.map((it, i) => `
      <span class="filter-chip" data-i="${i}" title="${escapeHtml(it.key)}: ${escapeHtml(it.val)}">
        <span class="key">${escapeHtml(it.key)}</span>
        <span class="val">${escapeHtml(it.val)}</span>
        <i class="x ri-close-line" title="移除此条件"></i>
      </span>`).join('') +
      `<span class="tagbar-clear" id="srcTagClear" title="清除全部筛选"><i class="ri-close-circle-line"></i> 清除全部</span>`;
    wrap.querySelectorAll('.filter-chip').forEach((el) => {
      el.querySelector('.x').onclick = () => { items[Number(el.dataset.i)].clear(); loadSources(); };
    });
    const clearAll = $('#srcTagClear');
    if (clearAll) clearAll.onclick = () => {
      $('#srcQ').value = ''; $('#srcType').value = '';
      $('#srcPriority').value = ''; $('#srcActive').value = '';
      $('#srcQ').dispatchEvent(new Event('input', { bubbles: true }));
      loadSources();
    };
  }

  // ---------- 列表 ----------
  async function loadSources() {
    const qs = new URLSearchParams();
    const k = $('#srcQ').value.trim(); if (k) qs.append('q', k);
    if ($('#srcType').value) qs.append('type', $('#srcType').value);
    if ($('#srcPriority').value) qs.append('priority', $('#srcPriority').value);
    if ($('#srcActive').value) qs.append('active', $('#srcActive').value);

    let d;
    try { d = await api('/api/sources/?' + qs.toString()); }
    catch (e) { return toast(e.message, 'error'); }

    $('#srcTotalLabel').textContent = `共 ${d.total} 个信息源`;
    $('#srcCountTag').textContent = `（${d.total} 项）`;
    const tb = $('#tblSourcesBody');
    const cols = 'grid-template-columns: 36px 22px minmax(220px, 3fr) 110px 90px 110px 130px 80px 120px 96px;';
    const TIER_CLS = {
      'free':     'verdict verdict-ok',
      'register': 'verdict verdict-warn',
      'paid':     'verdict verdict-fail',
    };
    const TIER_TXT = {
      'free':     '免费',
      'register': '需注册',
      'paid':     '付费',
    };
    // 模糊文案识别：源始表述不能明确告知用户节奏时回退到我们的 crawl_interval
    const VAGUE_FREQ_RE = /按源数据频率|不定期|不固定|视情况|不一定/;
    function fmtInterval(sec) {
      sec = +sec || 0;
      if (sec <= 0) return '—';
      if (sec < 60)    return `每 ${sec} 秒`;
      if (sec < 3600)  return `每 ${Math.round(sec / 60)} 分`;
      if (sec < 86400) return `每 ${Math.round(sec / 3600)} 小时`;
      const d = Math.round(sec / 86400);
      return d === 1 ? '每日' : `每 ${d} 天`;
    }
    function buildFreqCell(s) {
      const raw = (s.update_frequency || '').trim();
      const interval = fmtInterval(s.crawl_interval);
      const isVague = !raw || VAGUE_FREQ_RE.test(raw);
      const display = isVague ? interval : raw;
      const title = raw
        ? `源声明：${raw}\n采集间隔：${interval}`
        : `采集间隔：${interval}`;
      return { display, title };
    }
    tb.innerHTML = (d.items || [])
      .slice()
      // 真实采集能力的信息源置顶（稳定排序，其余保持后端返回顺序）
      .sort((a, b) => (b.real_capable ? 1 : 0) - (a.real_capable ? 1 : 0))
      .map((s, idx) => {
      const stCls = s.is_active ? 'verdict verdict-ok' : 'verdict verdict-pending';
      const stars = '★'.repeat(Math.max(1, Math.min(5, s.difficulty || 0)));
      const tierCls = TIER_CLS[s.access_tier] || 'verdict verdict-pending';
      const tierTxt = TIER_TXT[s.access_tier] || (s.access_tier_label || '—');
      const freq = buildFreqCell(s);
      const cat = s.category || '';
      const isReal = !!s.real_capable;
      const dotColor = isReal ? 'var(--success, #22c55e)' : 'var(--gray-600, #6b7280)';
      const dotTitle = isReal ? '真实采集' : '仿真 / 未接入';
      const dot = `<span class="src-dot" title="${dotTitle}" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${dotColor};box-shadow:0 0 0 2px rgba(255,255,255,.04);"></span>`;
      return `
      <div class="list-row${s.is_active ? '' : ' row-inactive'}" data-id="${s.id}" style="${cols}">
        <span class="idx">${String(idx + 1).padStart(2, '0')}</span>
        <div style="display:flex;align-items:center;justify-content:center;">${dot}</div>
        <div class="src-name-cell">
          <div class="src-name-line">
            <b>${escapeHtml(s.name)}</b>
            <span class="src-stars" title="采集难度">${stars}</span>
          </div>
          <div class="muted text-xxs src-meta-line">
            ${cat ? `<span>${escapeHtml(cat)}</span>` : ''}
            ${s.spider_name ? `<span class="sep">·</span><code class="src-spider">${escapeHtml(s.spider_name)}</code>` : ''}
          </div>
        </div>
        <div>${escapeHtml(s.source_type_label || s.source_type)}</div>
        <div>${escapeHtml(s.priority_label || s.priority)}</div>
        <div><span class="${tierCls}">${escapeHtml(tierTxt)}</span></div>
        <div class="src-freq" title="${escapeHtml(freq.title)}">${escapeHtml(freq.display)}</div>
        <div><span class="${stCls}">${s.is_active ? '启用' : '禁用'}</span></div>
        <div>${s.last_crawled_at ? fmtTime(s.last_crawled_at) : '<span class="muted">—</span>'}</div>
        <div class="actions">
          <button class="btn btn-ghost btn-sm" data-act="trigger" data-id="${s.id}" title="立即触发">
            <i class="ri-play-line"></i>
          </button>
          <button class="btn btn-ghost btn-sm" data-act="toggle" data-id="${s.id}" title="${s.is_active ? '停用' : '启用'}">
            <i class="ri-${s.is_active ? 'pause-line' : 'play-circle-line'}"></i>
          </button>
        </div>
      </div>`;
    }).join('') || '<div class="list-empty"><i class="ri-inbox-line"></i>无数据</div>';

    tb.querySelectorAll('.list-row[data-id]').forEach(row => {
      if (Number(row.dataset.id) === currentSourceId) row.classList.add('selected');
      row.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        loadDetail(Number(row.dataset.id));
      });
    });
    renderTagbar();
    tb.querySelectorAll('button[data-act]').forEach(btn => {
      btn.onclick = async () => {
        const id = Number(btn.dataset.id);
        const act = btn.dataset.act;
        if (act === 'view') return loadDetail(id);
        if (act === 'trigger') {
          const row = btn.closest('.list-row');
          if (row) {
            row.classList.remove('is-fetching');
            void row.offsetWidth; // 重置动画
            row.classList.add('is-fetching');
            setTimeout(() => row.classList.remove('is-fetching'), 1700);
          }
        }
        try {
          await api(`/api/sources/${id}/${act}/`, { method: 'POST' });
          toast(act === 'trigger' ? '已加入采集队列' : '状态已切换', 'success');
          if (act === 'toggle') loadSources();
          if (act === 'trigger' && currentSourceId === id) {
            setTimeout(() => loadDetail(id), 1500);
          }
        } catch (e) { toast(e.message, 'error'); }
      };
    });
  }

  // ---------- 详情 ----------
  async function loadDetail(id) {
    currentSourceId = id;
    openDrawer();
    let d;
    try { d = await api(`/api/sources/${id}/`); }
    catch (e) { return toast(e.message, 'error'); }

    $('#srcDetailEmpty').style.display = 'none';
    $('#srcDetailContent').style.display = '';
    $('#dName').textContent = d.name || '—';
    $('#dCategory').textContent = d.category || '—';
    $('#dType').textContent = d.source_type_label || d.source_type;
    $('#dPriority').textContent = d.priority_label || d.priority;
    // 源声明为模糊文案时同步附上我们的实际采集间隔，避免抽屉中也出现“按源数据频率”这种不可读文案
    {
      const _raw = (d.update_frequency || '').trim();
      const _vague = /按源数据频率|不定期|不固定|视情况|不一定/.test(_raw);
      const _sec = +d.crawl_interval || 0;
      const _itv = _sec <= 0 ? '—'
        : _sec < 60    ? `每 ${_sec} 秒`
        : _sec < 3600  ? `每 ${Math.round(_sec / 60)} 分`
        : _sec < 86400 ? `每 ${Math.round(_sec / 3600)} 小时`
        : (Math.round(_sec / 86400) === 1 ? '每日' : `每 ${Math.round(_sec / 86400)} 天`);
      $('#dFreq').textContent = !_raw ? _itv
        : _vague ? `${_raw}（我们采集：${_itv}）`
        : _raw;
    }
    $('#dInterval').textContent = d.crawl_interval ?? '—';
    $('#dRegister').textContent = d.needs_register ? '是' : '否';
    $('#dLogin').textContent = d.needs_login ? '是' : '否';
    $('#dPaid').textContent = d.is_paid ? '是' : '否';
    $('#dSpider').textContent = d.spider_name || '—';
    const a = $('#dOfficial');
    a.href = d.official_url || '#';
    a.textContent = d.official_url || '—';
    const vClass = d.last_status === 'completed' ? 'verdict verdict-ok'
                  : d.last_status === 'failed' ? 'verdict verdict-fail'
                  : d.last_status === 'simulated' ? 'verdict verdict-warn'
                  : d.last_status === 'fallback' ? 'verdict verdict-warn'
                  : 'verdict verdict-pending';
    $('#dLastStatus').className = vClass;
    $('#dLastStatus').textContent = d.last_status || '—';
    if ($('#dStatusBadge')) {
      const _b = $('#dStatusBadge');
      _b.className = '';
      _b.style.cursor = 'pointer';
      _b.style.display = 'inline-flex';
      _b.style.alignItems = 'center';
      _b.style.gap = '6px';
      _b.innerHTML =
        `<span class="toggle-inline ${d.is_active ? 'on' : ''}"></span>` +
        `<span class="muted" style="font-size:var(--fz-xxs);">${d.is_active ? '启用' : '禁用'}</span>`;
      _b.title = d.is_active ? '点击立即禁用' : '点击立即启用';
    }
    $('#dLastTime').textContent = d.last_crawled_at ? fmtDt(d.last_crawled_at) : '';
    $('#dLastMsg').textContent = d.last_message || '';

    const tb = $('#tblDetailJobsBody');
    const colsJ = 'grid-template-columns: 1.4fr 0.8fr 1fr 0.8fr;';
    tb.innerHTML = (d.recent_jobs || []).map(j => {
      const st = {
        running:   '<span class="verdict verdict-info">运行中</span>',
        completed: '<span class="verdict verdict-ok">完成</span>',
        failed:    '<span class="verdict verdict-fail">失败</span>',
        pending:   '<span class="verdict verdict-warn">排队</span>',
      }[j.status] || `<span class="verdict verdict-pending">${escapeHtml(j.status)}</span>`;
      return `<div class="list-row" style="${colsJ}">
        <div>${fmtDt(j.started_at)}</div>
        <div>${st}</div>
        <div>+${j.items_new} / ${j.items_fetched}</div>
        <div><span class="muted">${escapeHtml(j.triggered_by)}</span></div>
      </div>`;
    }).join('') || '<div class="list-empty"><i class="ri-time-line"></i>暂无任务</div>';

    document.querySelectorAll('#tblSourcesBody .list-row').forEach(row => {
      row.classList.toggle('selected', Number(row.dataset.id) === id);
    });
  }

  // ---------- 详情面板按钮 ----------
  $('#btnTrigger').onclick = async () => {
    if (!currentSourceId) return;
    try {
      await api(`/api/sources/${currentSourceId}/trigger/`, { method: 'POST' });
      toast('已加入采集队列', 'success');
      setTimeout(() => loadDetail(currentSourceId), 1500);
    } catch (e) { toast(e.message, 'error'); }
  };
  $('#btnToggle').onclick = async () => {
    if (!currentSourceId) return;
    try {
      await api(`/api/sources/${currentSourceId}/toggle/`, { method: 'POST' });
      toast('状态已切换', 'success');
      loadSources();
      loadDetail(currentSourceId);
    } catch (e) { toast(e.message, 'error'); }
  };
  // 抽屉头部状态 pill 点击即切换启停（与 btnToggle 同逻辑）
  if ($('#dStatusBadge')) {
    $('#dStatusBadge').addEventListener('click', () => {
      if (!currentSourceId) return;
      $('#btnToggle').click();
    });
  }
  $('#btnRefreshDetail').onclick = () => currentSourceId && loadDetail(currentSourceId);
  $('#btnDelete').onclick = async () => {
    if (!currentSourceId) return;
    const name = ($('#dName').textContent || '').trim();
    if (!name) return;
    const input = window.prompt(
      `删除信息源将级联清除其全部采集任务记录, 该操作不可撤销。\n请输入信息源名称以确认: ${name}`,
      ''
    );
    if (input === null) return; // 用户点了取消
    if (input.trim() !== name) {
      return toast('确认名称不匹配, 已取消删除', 'error');
    }
    try {
      await api(`/api/sources/${currentSourceId}/delete/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: name }),
      });
      toast(`已删除「${name}」`, 'success');
      currentSourceId = null;
      closeDrawer();
      $('#srcDetailContent').style.display = 'none';
      $('#srcDetailEmpty').style.display = '';
      loadOverview();
      loadSources();
    } catch (e) { toast(e.message, 'error'); }
  };

  // ---------- 工具栏交互 ----------
  $('#btnSrcSearch').onclick = loadSources;
  const btnReload = $('#btnSrcReload'); if (btnReload) btnReload.onclick = () => { loadOverview(); loadSources(); };
  ['srcType', 'srcPriority', 'srcActive'].forEach(id =>
    $('#' + id).addEventListener('change', loadSources));
  $('#srcQ').addEventListener('keyup', e => { if (e.key === 'Enter') loadSources(); });
  $('#srcQ').addEventListener('input', () => renderTagbar());

  document.addEventListener('sr:ws', (ev) => {
    const d = ev.detail || {};
    if (d.type === 'crawl.completed' || d.type === 'crawl.failed') {
      loadOverview();
      loadSources();
      if (currentSourceId) loadDetail(currentSourceId);
    }
  });

  loadOverview();
  loadSources().then(() => {
    // 来自添加页的高亮跳转: /dashboard/sources/?highlight=<id>
    const m = new URLSearchParams(location.search).get('highlight');
    const hid = m ? Number(m) : 0;
    if (hid) {
      loadDetail(hid);
      const row = document.querySelector(`.list-row[data-id="${hid}"]`);
      if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  });
  setInterval(loadOverview, 30000);
})();
