/* 事件时间线页 — 跨市场时间轴串联关键事件 */
(function () {
  const { $, api, escapeHtml, fmtDt, toast,
          PEST_LABEL, DIM_LABEL, LEVEL_LABEL, OT_LABEL } = window.SR;

  let currentDetailId = null;

  function levelCls(lv) {
    return { H: 'verdict-fail', M: 'verdict-warn', L: 'verdict-info' }[lv] || 'verdict-pending';
  }
  function otCls(ot) {
    return { O: 'verdict-ok', T: 'verdict-fail' }[ot] || 'verdict-pending';
  }

  function renderItem(it) {
    const lvl = LEVEL_LABEL[it.level] || '';
    const ot = OT_LABEL[it.ot] || '';
    const pest = PEST_LABEL[it.pest] || '';
    const dim = it.dimension_label || it.dimension || '';
    const score = (it.impact_score || 0).toFixed(1);
    const sim = it.is_simulated ? '<span class="verdict verdict-info">仿真</span>' : '';
    return `
      <div class="tl-item" data-id="${it.id}">
        <div class="tl-item-h">
          <span class="verdict ${levelCls(it.level)}">${lvl}</span>
          <span class="verdict ${otCls(it.ot)}">${ot}</span>
          <span class="verdict verdict-pending">${pest}</span>
          <span class="verdict verdict-info">${escapeHtml(it.market || '—')}</span>
          ${dim ? `<span class="verdict verdict-pending">${escapeHtml(dim)}</span>` : ''}
          ${sim}
          <span class="muted" style="margin-left:auto;font-size:var(--fz-xxs);">${score}/10</span>
        </div>
        <div class="tl-item-title">${escapeHtml(it.title)}</div>
        <div class="tl-item-meta muted">
          ${fmtDt(it.published_at)} · ${escapeHtml(it.source || '未知来源')}
        </div>
      </div>`;
  }

  function renderDay(day) {
    const items = (day.items || []).map(renderItem).join('') ||
                  '<div class="muted" style="padding:6px 10px;font-size:var(--fz-xxs);">本日无显著事件</div>';
    return `
      <div class="tl-day">
        <div class="tl-day-h">
          <span class="tl-day-date">${escapeHtml(day.date)}</span>
          <span class="tl-day-count muted">${day.count} 条</span>
        </div>
        <div class="tl-day-items">${items}</div>
      </div>`;
  }

  async function loadTimeline() {
    const market = $('#tlMarket').value;
    const days = $('#tlDays').value;
    const minScore = $('#tlMinScore').value;
    const qs = new URLSearchParams();
    if (market) qs.append('market', market);
    qs.append('days', days);
    qs.append('min_score', minScore);

    let data;
    try { data = await api('/api/intel/timeline/?' + qs.toString()); }
    catch (e) {
      $('#timelineWrap').innerHTML = `<div class="list-empty"><i class="ri-error-warning-line"></i>加载失败: ${escapeHtml(e.message)}</div>`;
      toast.error('时间线加载失败', e.message);
      return;
    }

    $('#tlMeta').textContent =
      `${data.market === 'all' ? '全部市场' : data.market} · 共 ${data.total} 条 · 近 ${data.days} 天`;

    const html = (data.timeline || []).map(renderDay).join('');
    $('#timelineWrap').innerHTML = html ||
      '<div class="empty-state"><i class="ri-inbox-line"></i><div class="es-title">该窗口暂无事件</div><div class="es-sub">调整筛选或先采集数据</div></div>';

    $('#timelineWrap').querySelectorAll('.tl-item').forEach(el => {
      el.addEventListener('click', () => loadDetail(parseInt(el.dataset.id)));
    });
  }

  async function loadDetail(id) {
    currentDetailId = id;
    document.querySelectorAll('.tl-item').forEach(el => {
      el.classList.toggle('selected', parseInt(el.dataset.id) === id);
    });

    let info;
    try { info = await api('/api/intel/' + id + '/'); }
    catch (e) { toast.error('详情加载失败', e.message); return; }

    const tags = (info.tags || []).map(t =>
      `<span class="verdict verdict-pending">${escapeHtml(t)}</span>`).join(' ') ||
      '<span class="muted">无标签</span>';

    const chain = (info.analysis_chain || []).map((c, i) => `
      <div class="chain-step">
        <div class="chain-step-h">${i + 1}. ${escapeHtml(c.step || '')}</div>
        <div class="chain-step-resp">${escapeHtml(c.response || '')}</div>
      </div>`).join('') || '<div class="muted">无分析链</div>';

    $('#tlDetail').innerHTML = `
      <h3 style="margin:0 0 6px;font-size:var(--fz-lg);color:var(--text-1);">${escapeHtml(info.title)}</h3>
      <div class="muted" style="font-size:var(--fz-xxs);margin-bottom:8px;">
        ${fmtDt(info.published_at)} · ${escapeHtml((info.source && info.source.name) || '—')} ·
        <a href="${escapeHtml(info.url)}" target="_blank" rel="noopener" style="color:var(--accent-blue)"><i class="ri-external-link-line"></i> 查看原文</a>
      </div>

      <div style="margin:8px 0;display:flex;flex-wrap:wrap;gap:6px;">
        <span class="verdict ${levelCls(info.impact_level)}">${LEVEL_LABEL[info.impact_level] || ''}</span>
        <span class="verdict ${otCls(info.opportunity_or_threat)}">${OT_LABEL[info.opportunity_or_threat] || ''}</span>
        <span class="verdict verdict-pending">${PEST_LABEL[info.pest_type] || ''}</span>
        <span class="verdict verdict-info">${escapeHtml(info.target_market || '')}</span>
        <span class="verdict verdict-pending">${escapeHtml(info.strategic_dimension_label || '')}</span>
        <span class="verdict verdict-warn">影响 ${(info.impact_score || 0).toFixed(2)}/10</span>
      </div>

      <div class="section-title"><h2><i class="ri-bookmark-line"></i> 摘要</h2></div>
      <div>${escapeHtml((info.summary || info.content || '').slice(0, 400))}</div>

      <div class="section-title"><h2><i class="ri-target-line"></i> 行动建议</h2></div>
      <div style="white-space:pre-wrap;">${escapeHtml(info.action_advice || '暂无')}</div>

      <div class="section-title"><h2><i class="ri-brain-line"></i> 判断理由</h2></div>
      <div>${escapeHtml(info.impact_rationale || '暂无')}</div>

      <div class="section-title"><h2><i class="ri-link"></i> 分析链路（可追溯）</h2></div>
      <div class="chain-list">${chain}</div>

      <div class="section-title"><h2><i class="ri-price-tag-3-line"></i> 标签</h2></div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;">${tags}</div>
    `;
  }

  // 绑定事件
  $('#btnTlRefresh').addEventListener('click', loadTimeline);
  $('#tlMarket').addEventListener('change', loadTimeline);
  $('#tlDays').addEventListener('change', loadTimeline);
  $('#tlMinScore').addEventListener('change', loadTimeline);

  // 监听 WS: 新分析结果实时刷新当前页
  document.addEventListener('sr:ws', (e) => {
    const p = e.detail || {};
    if (p.type === 'intel.analyzed' || p.type === 'alert.high_impact') {
      // 节流: 简单 debounce
      clearTimeout(loadTimeline._t);
      loadTimeline._t = setTimeout(loadTimeline, 1500);
    }
  });

  // 首次加载
  loadTimeline();
})();
