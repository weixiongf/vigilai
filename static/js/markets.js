/* ============================================================
 * Strategic Radar · 全站目标市场下拉 · 唯一数据源
 *
 *   数据来自 GET /dashboard/api/markets/, 由数据库 TargetMarket 表驱动.
 *   首次请求结果在内存中缓存, 同页面多个 select 共享一次拉取.
 *
 *   使用:
 *     SR.markets.fillSelect(document.getElementById('xxxMarket'), {
 *       includeAll:    false,   // 是否在最前插入 <option value="">全部市场</option>
 *       includeGlobal: false,   // 是否在最前插入 <option value="global">Global (全市场)</option>
 *       globalLabel:   'Global (全市场)',
 *       selected:      'global',// 默认选中值, 不填则保持 select 当前值
 *       withFlag:      false,   // option 文案是否拼上国旗 emoji
 *     });
 *
 *   行为:
 *     - 数据加载前先用骨架 (loading) 占位, 避免布局抖动
 *     - 加载完成自动恢复用户的 selected 值 (若仍存在)
 *     - 失败时不清空已有 option, 控制台报警, 不打扰用户
 * ============================================================ */
(function () {
  if (!window.SR) window.SR = {};

  const ENDPOINT = '/dashboard/api/markets/';
  let cachePromise = null;

  function fetchMarkets(force) {
    if (force) cachePromise = null;
    if (cachePromise) return cachePromise;
    cachePromise = fetch(ENDPOINT, { headers: { 'Accept': 'application/json' } })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(d => Array.isArray(d.items) ? d.items : [])
      .catch(err => {
        console.warn('[SR.markets] 拉取市场列表失败:', err);
        cachePromise = null;
        return [];
      });
    return cachePromise;
  }

  function buildOption(value, label, selected) {
    const o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    if (selected != null && String(selected) === String(value)) o.selected = true;
    return o;
  }

  /**
   * 给 select 元素动态填充市场选项.
   * @param {HTMLSelectElement} sel
   * @param {object} [opts]
   * @returns {Promise<HTMLSelectElement>}
   */
  async function fillSelect(sel, opts) {
    if (!sel) return sel;
    opts = opts || {};
    const includeAll    = !!opts.includeAll;
    const includeGlobal = !!opts.includeGlobal;
    const globalLabel   = opts.globalLabel || 'Global (全市场)';
    const withFlag      = !!opts.withFlag;
    // 默认选中值: 优先取 opts.selected, 否则保留 select 当前值 (用户已交互)
    const desired = (opts.selected !== undefined && opts.selected !== null)
      ? String(opts.selected)
      : (sel.value || '');

    // 占位, 避免空 select 出现布局抖动
    sel.innerHTML = '<option value="">加载中...</option>';
    sel.disabled = true;
    const beforeValue = sel.value;

    const items = await fetchMarkets();

    sel.innerHTML = '';
    if (includeAll)    sel.appendChild(buildOption('',       '全部市场',  desired));
    if (includeGlobal) sel.appendChild(buildOption('global', globalLabel, desired));
    items.forEach(m => {
      const label = withFlag && m.flag_emoji
        ? `${m.flag_emoji} ${m.code}`
        : m.code;
      sel.appendChild(buildOption(m.code, label, desired));
    });
    sel.disabled = false;

    // 还原选中: 若 desired 不在新选项中, 退回第一个
    if (desired && Array.from(sel.options).every(o => o.value !== desired)) {
      if (sel.options.length) sel.selectedIndex = 0;
    }
    // 仅在值发生变化时触发 change, 避免初始化时重复请求
    if (sel.value !== beforeValue) {
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    }
    return sel;
  }

  /** 一次填充多个 select. */
  function fillAll(specs) {
    return Promise.all((specs || []).map(s => fillSelect(s.el, s.opts)));
  }

  /**
   * 扫描页面内 <select data-fill="markets"> 节点, 依据 data-* 指令填充.
   *   data-include-all="1"     → includeAll: true
   *   data-include-global="1"  → includeGlobal: true
   *   data-default="global"    → selected: 'global'
   *   data-with-flag="1"       → withFlag: true
   *   data-global-label="..."  → globalLabel: '...'
   * 已填充过的节点会带上 data-filled="1", 避免重复填充.
   */
  function autoFill(root) {
    const scope = root || document;
    const nodes = scope.querySelectorAll('select[data-fill="markets"]:not([data-filled])');
    const tasks = [];
    nodes.forEach(el => {
      el.dataset.filled = '1';
      tasks.push(fillSelect(el, {
        includeAll:    el.dataset.includeAll    === '1',
        includeGlobal: el.dataset.includeGlobal === '1',
        withFlag:      el.dataset.withFlag      === '1',
        globalLabel:   el.dataset.globalLabel || undefined,
        selected:      el.dataset.default !== undefined ? el.dataset.default : undefined,
      }));
    });
    return Promise.all(tasks);
  }

  // DOM 就绪后自动扫描一次; 加载迟于 DOMContentLoaded 也能处理.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => autoFill());
  } else {
    autoFill();
  }

  window.SR.markets = { fetch: fetchMarkets, fillSelect, fillAll, autoFill };
})();
