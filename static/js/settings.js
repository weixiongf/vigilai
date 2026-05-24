/* 系统配置页 — 数据源模式 (multi-switch) + 公司画像 */
(function () {
  const { $, $$, api, escapeHtml, fmtDt, toast } = window.SR;

  // 当前选中的异常源数据
  let selectedFailing = null;
  // 缓存当次加载的 failing_sources 列表
  let failingList = [];

  // ---------- 数据源模式 / 降级开关 ----------
  async function loadModeSnapshot() {
    let d;
    try { d = await api('/api/sources/simulation-mode/'); }
    catch (e) { return; }

    const VERDICT = {
      auto:      { cls: 'verdict-ok',   label: '自动' },
      simulated: { cls: 'verdict-warn', label: '强制仿真' },
      real:      { cls: 'verdict-info', label: '强制真实' },
    };
    const v = VERDICT[d.mode] || { cls: 'verdict-pending', label: d.mode };
    const badge = $('#modeBadge');
    if (badge) {
      badge.className = 'verdict ' + v.cls;
      const text = $('#modeBadgeText');
      if (text) text.textContent = v.label;
      else badge.textContent = v.label;
    }
    const meta = $('#modeMeta');
    if (meta) {
      meta.textContent =
        `阈值=${d.threshold} · fallback_on_failure=${d.fallback_on_failure ? '开' : '关'} · 异常 ${d.failing_count}`;
    }
    const actual = $('#modeActualLabel');
    if (actual) {
      actual.textContent = (d.mode === 'auto')
        ? `auto · 异常源 ${d.failing_count}`
        : `${v.label} · 全量信息源`;
    }

    // 全链路 4 个通道的状态提示 (随 mode 实时切换)
    const isReal = d.mode === 'real';
    const realTag  = '<span class="verdict verdict-ok" style="display:inline-flex;align-items:center;gap:4px;"><i class="ri-global-line"></i> 真实</span>';
    const fakeTag  = '<span class="verdict verdict-warn" style="display:inline-flex;align-items:center;gap:4px;"><i class="ri-play-circle-line"></i> 仿真</span>';
    const channels = {
      modeChCrawl:  isReal ? `${realTag} <span class="muted">FRED / WorldBank / GDELT 真接入</span>`
                           : `${fakeTag} <span class="muted">本地模板生成，不走外网</span>`,
      modeChLlm:    isReal ? `${realTag} <span class="muted">DeepSeek (真实大模型)</span>`
                           : `${fakeTag} <span class="muted">MockLLMProvider 本地启发式</span>`,
      modeChEmail:  isReal ? `${realTag} <span class="muted">SMTP (送达收件人邮箱)</span>`
                           : `${fakeTag} <span class="muted">filebased，落盘 tmp/sent_emails</span>`,
      modeChFeishu: isReal ? `${realTag} <span class="muted">Webhook 真实 POST 到飞书群</span>`
                           : `${fakeTag} <span class="muted">跳过实际 HTTP，仅记日志</span>`,
    };
    Object.entries(channels).forEach(([id, html]) => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = html;
    });

    const failingTotal = $('#failingTotal');
    if (failingTotal) failingTotal.textContent = `${d.failing_count || 0} 个异常源`;

    // multi-switch 选中态
    $$('#modeSwitch .ms-item').forEach((it) => {
      it.classList.toggle('selected', it.dataset.value === d.mode);
    });

    // 异常源列表（list-grid 范式 + 点击查看详情）
    failingList = d.failing_sources || [];
    const tb = $('#tblFailingBody');
    if (tb) {
      const cols = 'grid-template-columns: 28px 2fr 80px 100px;';
      tb.innerHTML = failingList.map((it, idx) => `
        <div class="list-row" data-sid="${it.source_id}" style="${cols};cursor:pointer;">
          <span class="idx">${String(idx + 1).padStart(2, '0')}</span>
          <div>
            <div><b>${escapeHtml(it.name)}</b></div>
            <div class="muted text-xxs">${escapeHtml(it.source_type || '')} · ${escapeHtml(it.category || '')}</div>
          </div>
          <div><span class="verdict verdict-fail">${it.consecutive_failures}</span></div>
          <div class="actions">
            <button class="btn btn-ghost btn-sm" data-reset="${it.source_id}" title="重置失败计数">
              <i class="ri-restart-line"></i>
            </button>
          </div>
        </div>
      `).join('') ||
        '<div class="list-empty"><i class="ri-checkbox-circle-line"></i>全部信息源状态正常</div>';

      // 点击行显示详情
      tb.querySelectorAll('.list-row[data-sid]').forEach(row => {
        row.addEventListener('click', (e) => {
          if (e.target.closest('button')) return;
          const sid = Number(row.dataset.sid);
          const item = failingList.find(x => x.source_id === sid);
          if (item) showFailDetail(item);
          tb.querySelectorAll('.list-row').forEach(r => r.classList.remove('selected'));
          row.classList.add('selected');
        });
      });

      // 重置按钮
      tb.querySelectorAll('button[data-reset]').forEach(btn => {
        btn.onclick = async (e) => {
          e.stopPropagation();
          try {
            await api('/api/sources/simulation-mode/', {
              method: 'POST',
              body: JSON.stringify({ action: 'reset', source_id: Number(btn.dataset.reset) }),
            });
            toast.success('已重置失败计数', `信息源 #${btn.dataset.reset}`);
            hideFailDetail();
            loadModeSnapshot();
          } catch (e) { toast.error('重置失败', e.message); }
        };
      });

      // 如果当前选中的源仍在列表中，保持高亮
      if (selectedFailing) {
        const row = tb.querySelector(`.list-row[data-sid="${selectedFailing.source_id}"]`);
        if (row) row.classList.add('selected');
      }
    }
  }

  // ---------- 异常源详情面板 ----------
  function showFailDetail(item) {
    selectedFailing = item;
    $('#failDetailEmpty').style.display = 'none';
    $('#failDetailContent').style.display = '';

    $('#fdName').textContent = item.name || '—';
    $('#fdCategory').textContent = item.category || '—';
    $('#fdType').textContent = item.source_type || '—';
    $('#fdPriority').textContent = item.priority || '—';
    $('#fdFailCount').innerHTML = `<span class="verdict verdict-fail">${item.consecutive_failures} 次</span>`;

    const stEl = $('#fdLastStatus');
    const stMap = {
      completed: 'verdict-ok', failed: 'verdict-fail',
      simulated: 'verdict-warn', fallback: 'verdict-warn',
    };
    stEl.className = 'verdict ' + (stMap[item.last_status] || 'verdict-pending');
    stEl.textContent = item.last_status || '—';

    $('#fdLastTime').textContent = item.last_crawled_at ? fmtDt(item.last_crawled_at) : '无记录';
    $('#fdErrorMsg').textContent = item.last_error || '无错误信息';

    // 重置按钮
    const btnReset = $('#btnFailReset');
    btnReset.onclick = async () => {
      try {
        await api('/api/sources/simulation-mode/', {
          method: 'POST',
          body: JSON.stringify({ action: 'reset', source_id: item.source_id }),
        });
        toast.success('已重置失败计数', `${item.name}`);
        hideFailDetail();
        loadModeSnapshot();
      } catch (e) { toast.error('重置失败', e.message); }
    };

    // 跳转链接
    const btnGo = $('#btnFailGoSource');
    btnGo.href = `/dashboard/sources/?highlight=${item.source_id}`;
  }

  function hideFailDetail() {
    selectedFailing = null;
    $('#failDetailEmpty').style.display = '';
    $('#failDetailContent').style.display = 'none';
    const tb = $('#tblFailingBody');
    if (tb) tb.querySelectorAll('.list-row').forEach(r => r.classList.remove('selected'));
  }

  // ---------- multi-switch 模式切换 ----------
  document.addEventListener('sr:switch', async (ev) => {
    const { name, value } = ev.detail || {};
    if (name !== 'srcMode') return;
    try {
      await api('/api/sources/simulation-mode/', {
        method: 'POST',
        body: JSON.stringify({ mode: value }),
      });
      const labels = { auto: '自动 (仿真链路)', simulated: '强制仿真', real: '强制真实 (全链路启用)' };
      toast.success('已切换总开关', labels[value] || value);
      loadModeSnapshot();
    } catch (e) { toast.error('切换失败', e.message); }
  });

  const btnRefresh = $('#btnRefreshMode');
  if (btnRefresh) btnRefresh.onclick = loadModeSnapshot;

  // ---------- 数据源启用 · 三档 toggle (free / register / paid) ----------
  const TIER_META = {
    free:     { label: '免费 · 无需注册',   icon: 'ri-checkbox-circle-line', color: 'c-green',  hint: '公开 REST API，默认开启' },
    register: { label: '需注册 / 登录 (免费)', icon: 'ri-key-2-line',           color: 'c-yellow', hint: '需在 .env 配置 API Key，启用后才会调度' },
    paid:     { label: '付费 API',           icon: 'ri-vip-crown-line',       color: 'c-red',    hint: '需购买额度，启用后产生费用' },
  };

  async function loadTierSwitch() {
    let d;
    try { d = await api('/api/sources/tier-switch/'); }
    catch (e) { return; }

    const tiers = d.tiers || {};
    const counts = d.counts || {};
    const cardsEl = $('#tierCards');
    if (!cardsEl) return;

    cardsEl.innerHTML = ['free', 'register', 'paid'].map(t => {
      const meta = TIER_META[t];
      const enabled = !!tiers[t];
      const c = counts[t] || { total: 0, active: 0 };
      const stateCls = enabled ? 'verdict-ok' : 'verdict-pending';
      const stateLabel = enabled ? '已启用' : '已关闭';
      return `
        <div class="panel tier-card ${enabled ? 'is-on' : ''}" data-tier="${t}">
          <div class="panel-body">
            <div class="flex items-center gap-2" style="margin-bottom:6px;">
              <i class="${meta.icon} ${meta.color}" style="font-size:18px;"></i>
              <b>${meta.label}</b>
              <div class="flex-1"></div>
              <span class="toggle-inline ${enabled ? 'on' : ''}"
                    data-tier="${t}"
                    data-target="${enabled ? 'false' : 'true'}"
                    role="switch" aria-checked="${enabled}"
                    title="${enabled ? '点击关闭' : '点击启用'}"></span>
            </div>
            <div class="muted text-xxs" style="margin-bottom:8px;">${meta.hint}</div>
            <div class="kv-grid" style="font-size:var(--fz-sm);">
              <div class="k">信息源总数</div><div class="v"><b>${c.total}</b></div>
              <div class="k">中活跃</div><div class="v">${c.active}</div>
              <div class="k">状态</div>
              <div class="v"><span class="verdict ${stateCls}">${stateLabel}</span></div>
            </div>
          </div>
        </div>
      `;
    }).join('');

    cardsEl.querySelectorAll('.toggle-inline[data-tier]').forEach(sw => {
      sw.onclick = async () => {
        const tname = sw.dataset.tier;
        const target = sw.dataset.target === 'true';
        // 乐观更新视觉 (避免点击延迟感)
        sw.classList.toggle('on', target);
        try {
          await api('/api/sources/tier-switch/', {
            method: 'POST',
            body: JSON.stringify({ tier: tname, enabled: target }),
          });
          toast.success('已更新启用状态',
            `${TIER_META[tname].label} → ${target ? '启用' : '关闭'}`);
          loadTierSwitch();
          loadModeSnapshot();
        } catch (e) {
          // 回滚视觉
          sw.classList.toggle('on', !target);
          toast.error('切换失败', e.message);
        }
      };
    });

    const meta = $('#tierMeta');
    if (meta) {
      const allowed = (d.enabled_tiers || []).map(t => TIER_META[t]?.label || t).join(' + ');
      meta.textContent = `当前允许: ${allowed || '无'}`;
    }
  }

  // ---------- 公司战略画像 (文件型配置・即时生效) ----------
  function _updateProfileCounts() {
    const sCnt = ($('#taStrengths').value.split('\n').filter(s => s.trim()).length);
    const wCnt = ($('#taWeaknesses').value.split('\n').filter(s => s.trim()).length);
    const sEl = $('#cntStrengths'); if (sEl) sEl.textContent = `· ${sCnt} 条`;
    const wEl = $('#cntWeaknesses'); if (wEl) wEl.textContent = `· ${wCnt} 条`;
  }

  async function loadCompanyProfile() {
    try {
      const d = await api('/dashboard/api/company-profile/');
      $('#taStrengths').value = (d.strengths || []).join('\n');
      $('#taWeaknesses').value = (d.weaknesses || []).join('\n');
      const u = $('#profileUpdatedAt');
      if (u) u.textContent = d.updated_at
        ? `最近保存：${fmtDt(d.updated_at)}`
        : '使用默认基线（尚未保存）';
      _updateProfileCounts();
    } catch (e) { /* ignore */ }
  }

  async function saveCompanyProfile() {
    const strengths = $('#taStrengths').value;
    const weaknesses = $('#taWeaknesses').value;
    try {
      const d = await api('/dashboard/api/company-profile/', {
        method: 'POST',
        body: JSON.stringify({ strengths, weaknesses }),
      });
      // 回写已去重/去空后的规范化结果
      $('#taStrengths').value = (d.strengths || []).join('\n');
      $('#taWeaknesses').value = (d.weaknesses || []).join('\n');
      const u = $('#profileUpdatedAt');
      if (u && d.updated_at) u.textContent = `最近保存：${fmtDt(d.updated_at)}`;
      _updateProfileCounts();
      toast.success('公司战略画像已保存',
        `优势 ${d.strengths.length} 条 · 劣势 ${d.weaknesses.length} 条 · 即时生效`);
    } catch (e) { toast.error('保存失败', e.message); }
  }

  ['taStrengths', 'taWeaknesses'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', _updateProfileCounts);
  });
  const btnSave = $('#btnSaveProfile'); if (btnSave) btnSave.onclick = saveCompanyProfile;
  const btnReload = $('#btnReloadProfile'); if (btnReload) btnReload.onclick = loadCompanyProfile;

  loadModeSnapshot();
  loadCompanyProfile();
  loadTierSwitch();
  loadBriefingSchedule();
  setInterval(loadModeSnapshot, 30000);

  // ---------- 简报调度配置 (日报/周报/月报 开关与发送规则) ----------
  // 初始化小时下拉列表 (0-23)
  ['schedMarketHour', 'schedDailyHour', 'schedWeeklyHour', 'schedMonthlyHour'].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    for (let h = 0; h <= 23; h++) {
      const opt = document.createElement('option');
      opt.value = h;
      opt.textContent = String(h).padStart(2, '0') + ':00';
      sel.appendChild(opt);
    }
  });

  const SCHED_DOW_LABEL = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

  function _renderSchedToggle(id, enabled) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.toggle('on', enabled);
    el.setAttribute('aria-checked', String(enabled));
  }

  function _renderSchedBadge(id, enabled) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = enabled ? 'verdict verdict-ok' : 'verdict verdict-pending';
    el.textContent = enabled ? '已启用' : '已禁用';
  }

  async function loadBriefingSchedule() {
    let d;
    try { d = await api('/dashboard/api/briefing-schedule/'); }
    catch (e) { return; }

    const realtime = d.realtime || {};
    const market = d.market_briefing || {};
    const daily = d.daily || {};
    const weekly = d.weekly || {};
    const monthly = d.monthly || {};

    // toggle 状态
    _renderSchedToggle('schedRealtimeToggle', realtime.enabled);
    _renderSchedToggle('schedMarketToggle', market.enabled);
    _renderSchedToggle('schedDailyToggle', daily.enabled);
    _renderSchedToggle('schedWeeklyToggle', weekly.enabled);
    _renderSchedToggle('schedMonthlyToggle', monthly.enabled);

    // badge
    _renderSchedBadge('schedRealtimeBadge', realtime.enabled);
    _renderSchedBadge('schedMarketBadge', market.enabled);
    _renderSchedBadge('schedDailyBadge', daily.enabled);
    _renderSchedBadge('schedWeeklyBadge', weekly.enabled);
    _renderSchedBadge('schedMonthlyBadge', monthly.enabled);

    // 填充下拉值
    const ml = document.getElementById('schedMarketLevel');
    if (ml) ml.value = market.level || 'all';
    const mhr = document.getElementById('schedMarketHour');
    if (mhr) mhr.value = market.hour != null ? market.hour : 9;

    // 填充下拉值
    const dh = document.getElementById('schedDailyHour');
    if (dh) dh.value = daily.hour != null ? daily.hour : 8;
    const wd = document.getElementById('schedWeeklyDay');
    if (wd) wd.value = weekly.day_of_week != null ? weekly.day_of_week : 0;
    const wh = document.getElementById('schedWeeklyHour');
    if (wh) wh.value = weekly.hour != null ? weekly.hour : 14;
    const md = document.getElementById('schedMonthlyDay');
    if (md) md.value = monthly.day_of_month != null ? monthly.day_of_month : -1;
    const mh = document.getElementById('schedMonthlyHour');
    if (mh) mh.value = monthly.hour != null ? monthly.hour : 14;

    // meta
    const meta = document.getElementById('schedMeta');
    if (meta) {
      const parts = [];
      if (realtime.enabled) parts.push('✅ 实时推送已开启，定时简报全部关闭');
      if (market.enabled) {
        const lvLabel = {all: '全部', threat: '威胁', opportunity: '机会'}[market.level] || '全部';
        parts.push(`单市场[${lvLabel}] ${String(market.hour).padStart(2,'0')}:00`);
      }
      if (daily.enabled) parts.push(`日报 ${String(daily.hour).padStart(2,'0')}:00`);
      if (weekly.enabled) parts.push(`周报 ${SCHED_DOW_LABEL[weekly.day_of_week]} ${String(weekly.hour).padStart(2,'0')}:00`);
      if (monthly.enabled) {
        const dayLabel = monthly.day_of_month === -1 ? '月末' : `${monthly.day_of_month}号`;
        parts.push(`月报 ${dayLabel} ${String(monthly.hour).padStart(2,'0')}:00`);
      }
      meta.textContent = parts.length ? parts.join(' · ') : '全部已禁用';
    }

    // updated_at
    const ua = document.getElementById('schedUpdatedAt');
    if (ua) ua.textContent = d.updated_at
      ? `最近保存：${fmtDt(d.updated_at)}`
      : '使用默认配置';
  }

  async function saveBriefingSchedule() {
    const realtimeEnabled = document.getElementById('schedRealtimeToggle')?.classList.contains('on') ?? false;
    const marketEnabled = document.getElementById('schedMarketToggle')?.classList.contains('on') ?? true;
    const dailyEnabled = document.getElementById('schedDailyToggle')?.classList.contains('on') ?? true;
    const weeklyEnabled = document.getElementById('schedWeeklyToggle')?.classList.contains('on') ?? true;
    const monthlyEnabled = document.getElementById('schedMonthlyToggle')?.classList.contains('on') ?? true;

    const payload = {
      realtime: {
        enabled: realtimeEnabled,
      },
      market_briefing: {
        enabled: marketEnabled,
        level: document.getElementById('schedMarketLevel')?.value || 'all',
        hour: parseInt(document.getElementById('schedMarketHour')?.value || '9'),
      },
      daily: {
        enabled: dailyEnabled,
        hour: parseInt(document.getElementById('schedDailyHour')?.value || '8'),
      },
      weekly: {
        enabled: weeklyEnabled,
        day_of_week: parseInt(document.getElementById('schedWeeklyDay')?.value || '0'),
        hour: parseInt(document.getElementById('schedWeeklyHour')?.value || '14'),
      },
      monthly: {
        enabled: monthlyEnabled,
        day_of_month: parseInt(document.getElementById('schedMonthlyDay')?.value || '-1'),
        hour: parseInt(document.getElementById('schedMonthlyHour')?.value || '14'),
      },
    };

    try {
      await api('/dashboard/api/briefing-schedule/', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      toast.success('简报调度配置已保存', '下次触发时将使用新规则');
      loadBriefingSchedule();
    } catch (e) { toast.error('保存失败', e.message); }
  }

  // toggle 点击事件 — 实时发送开启时自动关闭其他所有开关
  const SCHED_TOGGLE_BADGE_MAP = {
    schedRealtimeToggle: 'schedRealtimeBadge',
    schedMarketToggle: 'schedMarketBadge',
    schedDailyToggle: 'schedDailyBadge',
    schedWeeklyToggle: 'schedWeeklyBadge',
    schedMonthlyToggle: 'schedMonthlyBadge',
  };
  const SCHED_OTHER_TOGGLES = ['schedMarketToggle', 'schedDailyToggle', 'schedWeeklyToggle', 'schedMonthlyToggle'];

  function _syncBadgeFromToggle(toggleId) {
    const t = document.getElementById(toggleId);
    const badgeId = SCHED_TOGGLE_BADGE_MAP[toggleId];
    if (!t || !badgeId) return;
    const on = t.classList.contains('on');
    _renderSchedBadge(badgeId, on);
  }

  function _syncAllBadges() {
    Object.keys(SCHED_TOGGLE_BADGE_MAP).forEach(_syncBadgeFromToggle);
  }

  const realtimeEl = document.getElementById('schedRealtimeToggle');
  if (realtimeEl) {
    realtimeEl.onclick = () => {
      const willBeOn = !realtimeEl.classList.contains('on');
      realtimeEl.classList.toggle('on');
      if (willBeOn) {
        // 开启实时 → 自动关闭其他所有开关
        SCHED_OTHER_TOGGLES.forEach(id => {
          const t = document.getElementById(id);
          if (t) t.classList.remove('on');
        });
      }
      _syncAllBadges();
    };
  }

  SCHED_OTHER_TOGGLES.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.onclick = () => {
      el.classList.toggle('on');
      // 开启任何定时开关时，自动关闭实时发送
      if (el.classList.contains('on') && realtimeEl) {
        realtimeEl.classList.remove('on');
      }
      _syncAllBadges();
    };
  });

  const btnSaveSched = document.getElementById('btnSaveSched');
  if (btnSaveSched) btnSaveSched.onclick = saveBriefingSchedule;
  const btnReloadSched = document.getElementById('btnReloadSched');
  if (btnReloadSched) btnReloadSched.onclick = loadBriefingSchedule;

  // ==================== 运行时配置 (LLM / 邮箱 / 短信) ====================
  // 表单字段映射 — kind → {DOM ids, env hint formatter, effective formatter}
  const RC_BIND = {
    llm: {
      use: 'rcLlmUseCustom', badge: 'rcLlmBadge', envHint: 'rcLlmEnvHint',
      effHint: 'rcLlmEffective',
      fields: {
        provider: 'rcLlmProvider', api_key: 'rcLlmApiKey',
        base_url: 'rcLlmBaseUrl', model: 'rcLlmModel',
      },
      env: (e) => `${e.provider || '-'} · ${e.model || '-'} · ${e.base_url || '-'} · key=${e.api_key_mask || '未设置'}`,
      eff: (e) => `生效值：${e.provider} · ${e.model} · key=${e.api_key_mask || '未设置'}`,
    },
    email: {
      use: 'rcEmailUseCustom', badge: 'rcEmailBadge', envHint: 'rcEmailEnvHint',
      effHint: 'rcEmailEffective',
      fields: {
        host: 'rcEmailHost', port: 'rcEmailPort',
        username: 'rcEmailUser', password: 'rcEmailPass',
        use_tls: 'rcEmailUseTls', use_ssl: 'rcEmailUseSsl',
        from_email: 'rcEmailFrom',
      },
      env: (e) => `${e.host || '-'}:${e.port || '-'} · user=${e.username || '-'} · pwd=${e.password_mask || '未设置'} · from=${e.from_email || '-'}`,
      eff: (e) => `生效值：${e.host}:${e.port} · ${e.username} · ${e.use_ssl ? 'SSL' : (e.use_tls ? 'TLS' : '明文')}`,
    },
    sms: {
      use: 'rcSmsUseCustom', badge: 'rcSmsBadge', envHint: 'rcSmsEnvHint',
      effHint: 'rcSmsEffective',
      fields: {
        access_key_id: 'rcSmsAkId', access_key_secret: 'rcSmsAkSecret',
        sign_name: 'rcSmsSign', template_code: 'rcSmsTpl',
      },
      env: (e) => `id=${e.access_key_id_mask || '未设置'} · sign=${e.sign_name || '-'} · tpl=${e.template_code || '-'}`,
      eff: (e) => `生效值：${e.sign_name || '-'} · ${e.template_code || '-'}`,
    },
  };

  function _setVal(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.type === 'checkbox') el.checked = !!val;
    else el.value = (val === undefined || val === null) ? '' : String(val);
  }
  function _getVal(id) {
    const el = document.getElementById(id);
    if (!el) return '';
    return (el.type === 'checkbox') ? !!el.checked : el.value;
  }

  // 演示遥蔽符 — 三个配置卡片中的所有字段值 (包含 .env hint / effective hint)
  // 在前端全部显示为 `****`, 仅防演示场景走光.
  const RC_MASK = '****';
  function _maskIfNotEmpty(v) {
    if (v === undefined || v === null) return '';
    if (typeof v === 'boolean') return v;  // checkbox 保持原状态
    return String(v).length > 0 ? RC_MASK : '';
  }

  function _renderRC(kind, data) {
    const cfg = RC_BIND[kind];
    if (!cfg || !data) return;
    // 总开关
    _setVal(cfg.use, data.use_custom);
    // 字段回填 — 原本会填 override / env, 现为演示都遥蔽为 ****
    const ov = data.override || {};
    const env = data.env || {};
    Object.entries(cfg.fields).forEach(([k, id]) => {
      let v = ov[k];
      const sensitive = ['api_key', 'password', 'access_key_secret'].includes(k);
      if ((v === '' || v === undefined || v === null) && !sensitive) {
        v = env[k];
      }
      // checkbox (use_tls) 保留原状态, 其他文本字段遥蔽为 ****
      const el = document.getElementById(id);
      if (el && el.type === 'checkbox') {
        _setVal(id, !!v);
      } else {
        _setVal(id, _maskIfNotEmpty(v));
      }
    });
    // 徽章 + env hint + effective hint — hint 文案同样遥蔽
    const badge = document.getElementById(cfg.badge);
    if (badge) {
      if (data.use_custom) {
        badge.className = 'verdict verdict-info';
        badge.textContent = '自定义已启用';
      } else {
        badge.className = 'verdict verdict-pending';
        badge.textContent = '使用 .env 默认';
      }
    }
    const envEl = document.getElementById(cfg.envHint);
    if (envEl) envEl.textContent = RC_MASK;
    const effEl = document.getElementById(cfg.effHint);
    if (effEl) effEl.textContent = `生效值：${RC_MASK}`;
  }

  async function loadRC(kind) {
    try {
      const d = await api(`/dashboard/api/runtime-config/${kind}/`);
      _renderRC(kind, d);
    } catch (e) { /* ignore */ }
  }

  async function saveRC(kind) {
    const cfg = RC_BIND[kind];
    if (!cfg) return;
    const fields = {};
    Object.entries(cfg.fields).forEach(([k, id]) => {
      const v = _getVal(id);
      // 空字符串不传 — 后端会当作 "未填写" 处理, 避免覆盖 .env
      // `****` 是遥蔽占位, 同样不传避免脱敏文本被写回后端
      if (v === RC_MASK) return;
      if (v !== '' && v !== undefined && v !== null) fields[k] = v;
    });
    try {
      const d = await api(`/dashboard/api/runtime-config/${kind}/`, {
        method: 'POST',
        body: JSON.stringify({ use_custom: _getVal(cfg.use), fields }),
      });
      _renderRC(kind, d);
      const labels = { llm: 'LLM 配置', email: '邮箱配置', sms: '短信配置' };
      toast.success(`已保存${labels[kind]}`,
        d.use_custom ? '当前使用自定义参数' : '当前使用 .env 默认');
    } catch (e) { toast.error('保存失败', e.message); }
  }

  document.querySelectorAll('[data-rc-save]').forEach(btn => {
    btn.addEventListener('click', () => saveRC(btn.dataset.rcSave));
  });
  document.querySelectorAll('[data-rc-reset]').forEach(btn => {
    btn.addEventListener('click', () => loadRC(btn.dataset.rcReset));
  });

  // SSL / TLS 互斥: 勾一个自动取消另一个 + 同步端口
  const _sslEl = document.getElementById('rcEmailUseSsl');
  const _tlsEl = document.getElementById('rcEmailUseTls');
  const _portEl = document.getElementById('rcEmailPort');
  if (_sslEl && _tlsEl) {
    _sslEl.addEventListener('change', () => {
      if (_sslEl.checked) {
        _tlsEl.checked = false;
        if (_portEl && (!_portEl.value || _portEl.value === '****' || _portEl.value === '587')) _portEl.value = '465';
      }
    });
    _tlsEl.addEventListener('change', () => {
      if (_tlsEl.checked) {
        _sslEl.checked = false;
        if (_portEl && (!_portEl.value || _portEl.value === '****' || _portEl.value === '465')) _portEl.value = '587';
      }
    });
  }

  // TAB 切换（卡片头即 TAB 栏）
  const rcTabs = document.querySelectorAll('#rcTabs .tab');
  const rcPanes = document.querySelectorAll('.tab-pane[data-pane]');
  rcTabs.forEach(t => {
    t.addEventListener('click', () => {
      const key = t.dataset.tab;
      rcTabs.forEach(x => x.classList.toggle('active', x === t));
      rcPanes.forEach(p => {
        p.style.display = (p.dataset.pane === key) ? '' : 'none';
      });
    });
  });

  loadRC('llm');
  loadRC('email');
  loadRC('sms');
})();
