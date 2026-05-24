/* 战略简报页 — 列表/详情 + PEST/SWOT */
(function () {
  const { $, api, escapeHtml, fmtDt, fmtDate, toast } = window.SR;
  let currentId = null;
  // 预览模式: 'briefing' (简报模板, 与邮件/分发同源) | 'phone' (手机短信)
  let previewMode = 'briefing';
  // 简报详情与渲染结果缓存: { detail: {...}, html: {briefing} }
  const detailCache = new Map();

  // ---- ISO 周计算 ----
  function getISOWeek(dateStr) {
    const d = new Date(dateStr + 'T00:00:00Z');
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const week = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return { year: d.getUTCFullYear(), week };
  }
  // 该 ISO 周的周一 / 周日 (yyyy-mm-dd)
  function getISOWeekRange(dateStr) {
    const d = new Date(dateStr + 'T00:00:00Z');
    const dayNum = d.getUTCDay() || 7;
    const monday = new Date(d);
    monday.setUTCDate(d.getUTCDate() - dayNum + 1);
    const sunday = new Date(monday);
    sunday.setUTCDate(monday.getUTCDate() + 6);
    const fmt = (x) => x.toISOString().slice(0, 10);
    return { start: fmt(monday), end: fmt(sunday) };
  }

  async function loadList() {
    const period = $('#briefingPeriodFilter').value;
    const market = $('#briefingMarketFilter').value;
    const qs = new URLSearchParams();
    if (period) qs.append('period', period);
    if (market) qs.append('market', market);
    let data;
    try { data = await api('/api/briefings/?' + qs.toString()); }
    catch (e) {
      $('#briefingList').innerHTML = `<div class="list-empty"><i class="ri-error-warning-line"></i>加载失败: ${escapeHtml(e.message)}</div>`;
      return;
    }
    const wrap = $('#briefingList');
    const items = data.items || [];
    const meta = $('#briefingListMeta');
    if (meta) meta.textContent = items.length ? `共 ${items.length} 份` : '';
    const DSP_ICON = {
      sent:    { i: 'ri-checkbox-circle-fill', cls: 'dsp-sent',    t: '已发送' },
      failed:  { i: 'ri-close-circle-fill',    cls: 'dsp-failed',  t: '发送失败' },
      pending: { i: 'ri-time-line',            cls: 'dsp-pending', t: '未发送' },
    };
    const today = new Date().toISOString().slice(0, 10);

    // ---- 按 ISO 周分组 ----
    // weekKey -> { year, week, range, weekly: [], days: { date: [briefings] } }
    const groups = new Map();
    items.forEach(b => {
      const refDate = b.period_end || today;
      const { year, week } = getISOWeek(refDate);
      const key = `${year}-W${String(week).padStart(2, '0')}`;
      if (!groups.has(key)) {
        groups.set(key, {
          year, week, key,
          range: getISOWeekRange(refDate),
          weekly: [],
          days: new Map(),
        });
      }
      const g = groups.get(key);
      if (b.period_type === 'weekly' || b.period_type === 'monthly') {
        g.weekly.push(b);
      } else {
        const dKey = b.period_end || today;
        if (!g.days.has(dKey)) g.days.set(dKey, []);
        g.days.get(dKey).push(b);
      }
    });

    // 按周倒序, 同周内日报按日期倒序, 同日内 global 置顶
    const sortedGroups = Array.from(groups.values())
      .sort((a, b) => (b.year - a.year) || (b.week - a.week));

    const renderItem = (b, idx) => {
      const dsp = DSP_ICON[b.dispatch_status] || DSP_ICON.pending;
      const isGlobal = b.target_market === 'global';
      const isWeekly = b.period_type === 'weekly';
      const marketTag = isGlobal
        ? `<span class="verdict verdict-positive" title="全市场综合简报"><i class="ri-earth-line"></i> 综合</span>`
        : `<span class="verdict verdict-pending">${escapeHtml(b.target_market || '')}</span>`;
      const cls = ['briefing-item'];
      if (isGlobal) cls.push('is-global');
      if (isWeekly) cls.push('is-weekly');
      return `
      <div class="${cls.join(' ')}" data-id="${b.id}">
        <span class="idx">${String(idx + 1).padStart(2, '0')}</span>
        <span class="verdict verdict-info" title="${escapeHtml(b.period_type_label || '')}">${escapeHtml(shortPeriod(b.period_type, b.period_type_label))}</span>
        ${marketTag}
        <span class="b-time muted">${escapeHtml(b.period_start || '')} ~ ${escapeHtml(b.period_end || '')}</span>
        <span class="b-dispatch ${dsp.cls}" title="${dsp.t}" aria-label="${dsp.t}"><i class="${dsp.i}"></i></span>
      </div>`;
    };

    let globalIdx = 0;
    const html = sortedGroups.map(g => {
      const dayList = Array.from(g.days.entries())
        .sort((a, b) => (a[0] < b[0] ? 1 : -1));
      // 同日内 global 置顶
      dayList.forEach(([, arr]) => {
        arr.sort((a, b) => {
          const ag = a.target_market === 'global' ? 0 : 1;
          const bg = b.target_market === 'global' ? 0 : 1;
          if (ag !== bg) return ag - bg;
          return (b.created_at || '').localeCompare(a.created_at || '');
        });
      });

      const weeklyHtml = g.weekly.map(b => renderItem(b, globalIdx++)).join('');
      const daysHtml = dayList.map(([dKey, arr]) => {
        const isToday = dKey === today;
        const items = arr.map(b => renderItem(b, globalIdx++)).join('');
        return `
          <div class="bf-day-header">
            <i class="ri-calendar-line"></i>
            <span>${escapeHtml(dKey)}</span>
            ${isToday ? '<span class="bf-today-badge">今日</span>' : ''}
          </div>
          ${items}`;
      }).join('');

      return `
        <div class="bf-week-group">
          <div class="bf-week-header">
            <span class="bf-week-badge"><i class="ri-calendar-event-line"></i> ${g.year} 年第 ${g.week} 周</span>
            <span class="bf-week-range muted">${g.range.start} ~ ${g.range.end}</span>
          </div>
          ${weeklyHtml}
          ${daysHtml}
        </div>`;
    }).join('');

    wrap.innerHTML = html || '<div class="empty-state"><i class="ri-inbox-line"></i><div class="es-title">暂无简报</div><div class="es-sub">调度页/手动触发即可生成</div></div>';
    wrap.querySelectorAll('.briefing-item').forEach(el => {
      el.addEventListener('click', () => loadDetail(parseInt(el.dataset.id)));
    });
    // 默认加载最新一条的详情
    if (items.length && !currentId) {
      loadDetail(items[0].id);
    }
  }

  // ---- 迷你 sparkline (纯 SVG, 无依赖) ----
  function sparkSVG(values, opts = {}) {
    const w = opts.w || 110, h = opts.h || 28, pad = 2;
    const max = Math.max(1, ...values);
    const min = Math.min(0, ...values);
    const range = (max - min) || 1;
    const stepX = (w - pad * 2) / Math.max(1, values.length - 1);
    const pts = values.map((v, i) => {
      const x = pad + i * stepX;
      const y = h - pad - ((v - min) / range) * (h - pad * 2);
      return [x, y];
    });
    const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    const area = path + ` L${pts[pts.length - 1][0].toFixed(1)},${h - pad} L${pts[0][0].toFixed(1)},${h - pad} Z`;
    const last = pts[pts.length - 1];
    const color = opts.color || '#16a34a';
    return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" preserveAspectRatio="none">
      <path d="${area}" fill="${color}" opacity="0.12"/>
      <path d="${path}" fill="none" stroke="${color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2" fill="${color}"/>
    </svg>`;
  }

  function deltaTag(pct, trend, invertGood = false) {
    if (pct === null || pct === undefined) return '<span class="k-delta k-delta-flat">—</span>';
    const arrow = trend === 'up' ? '↑' : (trend === 'down' ? '↓' : '→');
    const isGood = invertGood ? trend === 'down' : trend === 'up';
    const cls = trend === 'flat' ? 'k-delta-flat' : (isGood ? 'k-delta-good' : 'k-delta-bad');
    const sign = pct > 0 ? '+' : '';
    return `<span class="k-delta ${cls}">${arrow} ${sign}${pct}%</span>`;
  }

  // 数据高亮: 仅针对决策语义数据 (评分/数量/百分比等) 染色
  // 语义判别: 机会语境 → 三级绿, 风险/威胁语境 → 三级红, 其余 → 中性默认色
  // 排除日期时间: 前后为 -/.:~ 的数字不染色 (如 2026-05-23 / 12:30)
  // tone: 'good' / 'bad' / null(自动检测)
  function hilite(text, tone) {
    const safe = escapeHtml(String(text == null ? '' : text));
    const POS_KW = /机会|利好|正面|增长|提升|看好|顺势|红利|机遇/;
    const NEG_KW = /风险|威胁|告警|紧急|高影响|下降|不利|危险|损失|衰退|压力|负面/;
    const SEP = /[\-\/.:~～]/;
    return safe.replace(
      /(\d+(?:\.\d+)?(?:\s*%|\s*条|\s*份|\s*次|\s*天|\s*小时|\s*分钟|\s*倍|\s*分|\s*个|\s*项|\s*市场|\s*话题|\s*人|\/\d+)?)/g,
      (match, _g1, offset) => {
        // 跳过日期/时间: 前一字符或后一字符是 -/.:~～
        const before = offset > 0 ? safe.charAt(offset - 1) : '';
        const after = safe.charAt(offset + match.length);
        if (SEP.test(before) || SEP.test(after)) return match;
        let cls = 'data-hl';
        if (tone === 'good') cls = 'data-hl-good';
        else if (tone === 'bad') cls = 'data-hl-bad';
        else {
          const around = safe.slice(Math.max(0, offset - 25), offset + match.length + 25);
          const isPos = POS_KW.test(around);
          const isNeg = NEG_KW.test(around);
          if (isPos && !isNeg) cls = 'data-hl-good';
          else if (isNeg) cls = 'data-hl-bad';
        }
        return `<span class="${cls}">${match}</span>`;
      }
    );
  }

  // 列表中的周期标签简写 (节约横向空间): 周报→周 / 日报→日 / 临时→临 / 月报→月
  function shortPeriod(periodType, label) {
    const map = { weekly: '周', daily: '日', adhoc: '临', monthly: '月' };
    if (periodType && map[periodType]) return map[periodType];
    const t = String(label || '').trim();
    if (t.startsWith('周')) return '周';
    if (t.startsWith('日')) return '日';
    if (t.startsWith('临')) return '临';
    if (t.startsWith('月')) return '月';
    return t.charAt(0) || '—';
  }

  // 机会/威胁 小标签 (独立样式, 不依赖 verdict)
  function otTag(ot) {
    if (ot === 'O') return '<span class="pri-ot pri-ot-o" title="机会">机</span>';
    if (ot === 'T') return '<span class="pri-ot pri-ot-t" title="威胁">威</span>';
    return '<span class="pri-ot pri-ot-n" title="未标注">·</span>';
  }

  async function loadDetail(id) {
    currentId = id;
    document.querySelectorAll('.briefing-item').forEach(el => {
      el.classList.toggle('selected', parseInt(el.dataset.id) === id);
    });
    $('#btnDispatch').disabled = false;
    await renderPreview();
  }

  // 根据当前 previewMode 渲染简报详情区
  async function renderPreview() {
    if (!currentId) return;
    const id = currentId;
    const host = $('#briefingDetail');
    if (!host) return;
    let entry = detailCache.get(id);
    if (!entry) entry = { detail: null, html: {} };

    if (previewMode === 'briefing') {
      // 简报模板 — 服务端统一渲染 (templates/briefings/_briefing_full.html)
      // 与邮件发送内容同源, 仅差 standalone 包裹
      if (!entry.html.briefing) {
        host.innerHTML = `<div class="empty-state"><i class="ri-loader-4-line ri-spin"></i><div class="es-title">加载中…</div></div>`;
        try {
          const p = await api('/api/briefings/' + id + '/render/?mode=web');
          entry.html.briefing = p.html || '';
        } catch (e) {
          toast.error('加载失败', e.message);
          host.innerHTML = `<div class="empty-state"><i class="ri-error-warning-line"></i><div class="es-title">加载失败</div><div class="es-sub">${escapeHtml(e.message)}</div></div>`;
          return;
        }
      }
      host.innerHTML = entry.html.briefing;
    } else if (previewMode === 'phone') {
      if (!entry.detail) {
        host.innerHTML = `<div class="empty-state"><i class="ri-loader-4-line ri-spin"></i><div class="es-title">加载中…</div></div>`;
        try {
          entry.detail = await api('/api/briefings/' + id + '/');
        } catch (e) {
          toast.error('加载失败', e.message);
          host.innerHTML = `<div class="empty-state"><i class="ri-error-warning-line"></i><div class="es-title">加载失败</div><div class="es-sub">${escapeHtml(e.message)}</div></div>`;
          return;
        }
      }
      host.innerHTML = renderSmsPreview(entry.detail);
    }
    detailCache.set(id, entry);
  }

  // 短信预览: 从简报数据拼接 140字以内文案 + 手机气泡样式
  function renderSmsPreview(b) {
    const periodLabel = b.period_type_label || '战略简报';
    const market = (b.target_market === 'global') ? '全市场' : (b.target_market || '');
    const period = `${b.period_start || ''} ~ ${b.period_end || ''}`;
    const r = (b.top_risks || [])[0];
    const o = (b.top_opportunities || [])[0];
    const top1 = r ? (r.title || '').slice(0, 28) : '';
    const opp1 = o ? (o.title || '').slice(0, 28) : '';
    const lines = [`【战略情报】${market}${periodLabel}已生成`];
    if (period.trim() !== '~') lines.push(`周期:${period}`);
    if (top1) lines.push(`Top风险:${top1}`);
    if (opp1) lines.push(`Top机会:${opp1}`);
    lines.push('登录驾驶舱查看完整简报与推荐行动。');
    const text = lines.join('\n');
    const len = text.length;
    const split = Math.ceil(len / 70);
    const subject = b.title || `${market}${periodLabel}`;
    const now = new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5);
    return `
      <div class="tpl-meta">
        <span><i class="ri-smartphone-line"></i> 短信 (SMS)</span>
        <span><i class="ri-bookmark-line"></i> 主题: ${escapeHtml(subject)}</span>
        <span class="muted verdict verdict-pending">短信通道为预留接口, 当前仅提供文案预览</span>
      </div>
      <div class="sms-phone">
        <div class="sms-phone__bar">
          <span><i class="ri-signal-tower-line"></i> 中国移动</span>
          <span>${now}</span>
          <span><i class="ri-battery-line"></i></span>
        </div>
        <div class="sms-phone__title"><i class="ri-message-3-line"></i> 1069·企业短信</div>
        <div class="sms-bubble">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
        <div class="sms-meta">字符 ${len} · 计费条数 ${split} · 长短信拼接</div>
        <div class="sms-meta muted-2">主题(内部标识): ${escapeHtml(subject)}</div>
      </div>`;
  }

  // 切换预览模式按钮事件
  function bindPreviewSwitch() {
    document.querySelectorAll('#briefingPreviewSwitch [data-bp-mode]').forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.bpMode;
        if (mode === previewMode) return;
        previewMode = mode;
        document.querySelectorAll('#briefingPreviewSwitch [data-bp-mode]').forEach(b2 => {
          b2.classList.toggle('active', b2.dataset.bpMode === mode);
        });
        if (currentId) renderPreview();
      });
    });
  }

  async function loadPestSwot() {
    const market = $('#pestSwotMarket').value;
    let d;
    try { d = await api('/api/briefings/pest-swot/?market=' + market); }
    catch (e) { return toast.error('加载失败', e.message); }

    if (!d.pest) {
      $('#pestGrid').innerHTML = `<div class="empty-state"><i class="ri-database-2-line"></i><div class="es-title">${escapeHtml(market)} 暂无 PEST 快照</div></div>`;
      $('#swotGrid').innerHTML = '';
      return;
    }
    const cell = (icon, label, summary, items) => `
      <div class="pest-cell">
        <h5><i class="${icon}"></i> ${label}</h5>
        ${summary ? `<div style="font-size:var(--fz-sm);color:var(--text-1);margin-bottom:6px;">${escapeHtml(summary)}</div>` : ''}
        <ul>${(items || []).slice(0, 5).map(x =>
          `<li>${escapeHtml(typeof x === 'string' ? x : (x.title || x.summary || ''))}</li>`
        ).join('') || '<li class="muted">无</li>'}</ul>
      </div>
    `;
    $('#pestGrid').innerHTML =
      cell('ri-government-line', 'P · 政治法律', d.pest.political_summary, d.pest.political) +
      cell('ri-money-dollar-circle-line', 'E · 经济', d.pest.economic_summary, d.pest.economic) +
      cell('ri-team-line', 'S · 社会文化', d.pest.social_summary, d.pest.social) +
      cell('ri-cpu-line', 'T · 技术', d.pest.technological_summary, d.pest.technological);

    if (!d.swot) {
      $('#swotGrid').innerHTML = '<div class="empty-state"><i class="ri-inbox-line"></i><div class="es-title">无 SWOT</div></div>';
      $('#swotStrategies').innerHTML = '';
      return;
    }
    const list = (xs) => '<ul>' +
      (xs || []).map(x =>
        `<li>${escapeHtml(typeof x === 'string' ? x : (x.title || x.item || ''))}</li>`
      ).join('') + '</ul>';

    $('#swotGrid').innerHTML = `
      <div class="swot-cell s"><h5><i class="ri-shield-star-line"></i> Strengths 优势</h5>${list(d.swot.strengths)}</div>
      <div class="swot-cell w"><h5><i class="ri-alarm-warning-line"></i> Weaknesses 劣势</h5>${list(d.swot.weaknesses)}</div>
      <div class="swot-cell o"><h5><i class="ri-rocket-2-line"></i> Opportunities 机会</h5>${list(d.swot.opportunities)}</div>
      <div class="swot-cell t"><h5><i class="ri-skull-2-line"></i> Threats 威胁</h5>${list(d.swot.threats)}</div>
    `;

    $('#swotStrategies').innerHTML = `
      <div class="swot-strategies">
        <pre><b>SO 增长策略:</b> ${escapeHtml(d.swot.so_strategies || '—')}

<b>ST 防御策略:</b> ${escapeHtml(d.swot.st_strategies || '—')}

<b>WO 扭转策略:</b> ${escapeHtml(d.swot.wo_strategies || '—')}

<b>WT 规避策略:</b> ${escapeHtml(d.swot.wt_strategies || '—')}</pre>
        <div class="muted">整体建议: ${escapeHtml(d.swot.overall_recommendation || '—')} ·
          置信度 ${(d.swot.confidence_score || 0).toFixed(2)}</div>
      </div>
    `;
  }

  $('#btnRefreshBriefing').addEventListener('click', loadList);
  $('#briefingPeriodFilter').addEventListener('change', loadList);
  $('#briefingMarketFilter').addEventListener('change', loadList);

  // 周报强制 global — 选周报时锁定市场为 global 并禁用下拉
  function syncGenMarketByPeriod() {
    const isWeekly = $('#genPeriod').value === 'weekly';
    const sel = $('#genMarket');
    if (isWeekly) {
      sel.value = 'global';
      sel.disabled = true;
      sel.title = '周报仅生成 1 份综合简报(含各市场分区)';
    } else {
      sel.disabled = false;
      sel.title = '';
    }
  }
  $('#genPeriod').addEventListener('change', syncGenMarketByPeriod);
  syncGenMarketByPeriod();

  $('#btnGenBriefing').addEventListener('click', async () => {
    const market = $('#genMarket').value;
    const period = $('#genPeriod').value;
    try {
      await api('/api/briefings/trigger/', {
        method: 'POST',
        body: JSON.stringify({ target_market: market, period_type: period }),
      });
      toast.success('已触发生成', `${market} · ${period} · 后台生成中`);
      setTimeout(loadList, 2000);
    } catch (e) { toast.error('触发失败', e.message); }
  });

  $('#btnDispatch').addEventListener('click', async () => {
    if (!currentId) return;
    try {
      await api(`/api/briefings/${currentId}/dispatch/`, { method: 'POST' });
      toast.success('分发已提交', '已加入飞书 + 邮件队列');
    } catch (e) { toast.error('分发失败', e.message); }
  });

  $('#pestSwotMarket').addEventListener('change', loadPestSwot);

  // 实时刷新: 收到 briefing.published 时刷新列表
  document.addEventListener('sr:ws', (ev) => {
    if (ev.detail && ev.detail.type === 'briefing.published') {
      toast.success('新简报已发布', ev.detail.title || '');
      loadList();
    }
  });

  loadList();
  loadPestSwot();
  bindPreviewSwitch();
})();
