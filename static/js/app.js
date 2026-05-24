/* ============================================================
 * Strategic Radar · 全局工具 · 高仿 portmaster UI 行为
 *   $ / $$ / api / fmtDt / escapeHtml
 *   toast (success/error/warn/info, 带标题+描述+图标+关闭)
 *   dialog (通用模态框) / confirm (确认弹窗)
 *   WebSocket / clock
 * ============================================================ */
window.SR = (function () {
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function fmtDt(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('zh-CN', { hour12: false });
  }
  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('zh-CN');
  }
  function fmtTime(iso) {
    if (!iso) return '--:--';
    return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false });
  }

  const escapeHtml = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  /* -----------------------------------------------------------
   * 全局进度条 — SR.progress.start() / SR.progress.done()
   *   3px 绿色条，带并发计数器，多个请求同时进行不会提前收尾
   * ----------------------------------------------------------- */
  const progress = (function () {
    let bar = null, timer = null, val = 0, running = 0;
    function getBar() {
      if (!bar) bar = document.getElementById('globalProgress');
      return bar;
    }
    function start() {
      const el = getBar(); if (!el) return;
      running++;
      if (running > 1) return; // 已在运行，仅计数
      val = 8;
      el.classList.add('active');
      el.style.width = val + '%';
      clearInterval(timer);
      timer = setInterval(() => {
        if (!running) return;
        if (val < 90) { val += (90 - val) * 0.08; el.style.width = val + '%'; }
      }, 200);
    }
    function done() {
      const el = getBar(); if (!el) return;
      if (running > 0) running--;
      if (running > 0) return; // 仍有未完成请求
      clearInterval(timer);
      val = 100;
      el.style.width = '100%';
      setTimeout(() => { el.classList.remove('active'); el.style.width = '0%'; val = 0; }, 350);
    }
    return { start, done };
  })();

  async function api(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    progress.start();
    try {
      const r = await fetch(url, opts);
      if (!r.ok) {
        let msg = r.status + ' ' + r.statusText;
        try { const j = await r.json(); msg = j.error || JSON.stringify(j); } catch (e) {}
        throw new Error(msg);
      }
      return await r.json();
    } finally {
      progress.done();
    }
  }

  /* -----------------------------------------------------------
   * Toast (portmaster notification 风格 · 标题 + 描述 + 图标 + 关闭)
   *   SR.toast('已保存')
   *   SR.toast({ title: '保存成功', msg: '收件人已更新', type: 'success' })
   *   SR.toast.error / .success / .warn / .info
   * ----------------------------------------------------------- */
  function ensureToastStack() {
    let stack = $('#toastStack');
    if (!stack) {
      stack = document.createElement('div');
      stack.id = 'toastStack'; stack.className = 'toast-stack';
      document.body.appendChild(stack);
    }
    // 兼容旧 #toast 节点
    const legacy = $('#toast');
    if (legacy && legacy !== stack) legacy.style.display = 'none';
    return stack;
  }
  const TOAST_ICO = {
    success: 'ri-checkbox-circle-line',
    error:   'ri-close-circle-line',
    warn:    'ri-alert-line',
    info:    'ri-information-line',
  };
  function toast(input, type) {
    const stack = ensureToastStack();
    let opt;
    if (typeof input === 'string') opt = { title: input, type: type || 'info' };
    else opt = Object.assign({ type: 'info' }, input || {});
    opt.type = opt.type || 'info';
    const ico = TOAST_ICO[opt.type] || TOAST_ICO.info;
    const card = document.createElement('div');
    card.className = 'toast-card ' + opt.type;
    card.innerHTML = `
      <i class="ico ${ico}"></i>
      <div class="body">
        <div class="ttl">${escapeHtml(opt.title || '')}</div>
        ${opt.msg ? `<div class="msg">${escapeHtml(opt.msg)}</div>` : ''}
      </div>
      <i class="x ri-close-line"></i>`;
    const close = () => {
      card.classList.add('leaving');
      setTimeout(() => card.remove(), 200);
    };
    card.querySelector('.x').addEventListener('click', close);
    stack.appendChild(card);
    setTimeout(close, opt.duration || 3200);
    return { close };
  }
  toast.success = (t, m) => toast({ title: t, msg: m, type: 'success' });
  toast.error   = (t, m) => toast({ title: t, msg: m, type: 'error' });
  toast.warn    = (t, m) => toast({ title: t, msg: m, type: 'warn' });
  toast.info    = (t, m) => toast({ title: t, msg: m, type: 'info' });

  /* -----------------------------------------------------------
   * Dialog (通用模态框)
   *   SR.dialog({ title, body, foot, caption, onClose })
   *   const d = SR.dialog({...}); d.close();
   * ----------------------------------------------------------- */
  function dialog(opt) {
    opt = opt || {};
    const back = document.createElement('div');
    back.className = 'dialog-backdrop';
    const dlg = document.createElement('div');
    dlg.className = 'dialog';
    if (opt.width) dlg.style.minWidth = opt.width;
    dlg.innerHTML = `
      <div class="dialog-h">
        <div>
          ${opt.caption ? `<div class="caption">${escapeHtml(opt.caption)}</div>` : ''}
          <h2>${escapeHtml(opt.title || '')}</h2>
        </div>
        <i class="close-x ri-close-line"></i>
      </div>
      <div class="dialog-body"></div>
      ${opt.foot === false ? '' : `<div class="dialog-foot"></div>`}`;
    const $body = dlg.querySelector('.dialog-body');
    if (typeof opt.body === 'string') $body.innerHTML = opt.body;
    else if (opt.body instanceof HTMLElement) $body.appendChild(opt.body);

    const $foot = dlg.querySelector('.dialog-foot');
    if ($foot && Array.isArray(opt.actions)) {
      opt.actions.forEach((a) => {
        const b = document.createElement('button');
        b.className = 'btn ' + (a.cls || '');
        b.innerHTML = (a.icon ? `<i class="${a.icon}"></i>` : '') + escapeHtml(a.label || '确定');
        b.addEventListener('click', () => {
          if (a.onClick) a.onClick(close);
          else close();
        });
        $foot.appendChild(b);
      });
    }
    back.appendChild(dlg);
    document.body.appendChild(back);
    requestAnimationFrame(() => back.classList.add('show'));

    function close() {
      back.classList.remove('show');
      setTimeout(() => { back.remove(); opt.onClose && opt.onClose(); }, 160);
    }
    dlg.querySelector('.close-x').addEventListener('click', close);
    back.addEventListener('click', (e) => { if (e.target === back && opt.maskClose !== false) close(); });
    document.addEventListener('keydown', function esc(e) {
      if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
    });
    return { close, body: $body, root: dlg };
  }

  /* -----------------------------------------------------------
   * Confirm (确认弹窗) — 返回 Promise<boolean>
   * ----------------------------------------------------------- */
  function confirmDlg(opt) {
    opt = typeof opt === 'string' ? { title: opt } : (opt || {});
    return new Promise((resolve) => {
      const d = dialog({
        caption: opt.caption || '确认',
        title: opt.title || '请确认操作',
        body: `<div>${escapeHtml(opt.msg || '此操作不可撤销，是否继续？')}</div>`,
        actions: [
          { label: '取消', onClick: (close) => { close(); resolve(false); } },
          {
            label: opt.okText || '确认',
            cls: opt.danger ? 'btn-danger' : 'btn-primary',
            icon: opt.icon || (opt.danger ? 'ri-delete-bin-line' : 'ri-check-line'),
            onClick: (close) => { close(); resolve(true); },
          },
        ],
        onClose: () => resolve(false),
      });
    });
  }

  /* -----------------------------------------------------------
   * Searchbar 行为：自动给 .searchbar input 加清除按钮
   * ----------------------------------------------------------- */
  function setupSearchbars() {
    $$('.searchbar').forEach((bar) => {
      if (bar.dataset.bind) return;
      bar.dataset.bind = '1';
      const input = bar.querySelector('input');
      if (!input) return;
      // 注入图标（如未提供）
      if (!bar.querySelector('.searchbar-ico')) {
        const i = document.createElement('i');
        i.className = 'searchbar-ico ri-search-line';
        bar.insertBefore(i, bar.firstChild);
      }
      // 注入清除
      let clr = bar.querySelector('.clear-btn');
      if (!clr) {
        clr = document.createElement('i');
        clr.className = 'clear-btn ri-close-line';
        bar.appendChild(clr);
      }
      const sync = () => bar.classList.toggle('has-value', !!input.value);
      input.addEventListener('input', sync);
      clr.addEventListener('click', () => {
        input.value = ''; sync();
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.focus();
      });
      sync();
    });
  }

  /* -----------------------------------------------------------
   * Multi-Switch 行为
   *   <div class="multi-switch" data-name="mode">
   *     <button class="ms-item" data-value="auto">自动</button>...
   *   </div>
   *   document.addEventListener('sr:switch', e => { e.detail.name, e.detail.value })
   * ----------------------------------------------------------- */
  function setupMultiSwitch() {
    $$('.multi-switch').forEach((sw) => {
      if (sw.dataset.bind) return;
      sw.dataset.bind = '1';
      sw.addEventListener('click', (e) => {
        const it = e.target.closest('.ms-item');
        if (!it || it.classList.contains('disabled')) return;
        sw.querySelectorAll('.ms-item').forEach((x) => x.classList.remove('selected'));
        it.classList.add('selected');
        document.dispatchEvent(new CustomEvent('sr:switch', {
          detail: { name: sw.dataset.name, value: it.dataset.value, target: sw },
        }));
      });
    });
  }

  /* -----------------------------------------------------------
   * 维度 / 等级 / PEST 文案 (用 remixicon 替代 emoji)
   * ----------------------------------------------------------- */
  const PEST_LABEL = {
    P: '<i class="ri-government-line"></i> 政治法律',
    E: '<i class="ri-money-cny-circle-line"></i> 经济',
    S: '<i class="ri-group-line"></i> 社会文化',
    T: '<i class="ri-cpu-line"></i> 技术',
  };
  const DIM_LABEL = {
    competition: '<i class="ri-sword-line"></i> 竞争',
    product:     '<i class="ri-box-3-line"></i> 产品',
    platform:    '<i class="ri-store-2-line"></i> 平台',
    social:      '<i class="ri-megaphone-line"></i> 社媒',
    regulation:  '<i class="ri-scales-3-line"></i> 法规',
    macro:       '<i class="ri-earth-line"></i> 宏观',
    industry:    '<i class="ri-bar-chart-2-line"></i> 行业',
    other:       '<i class="ri-bookmark-line"></i> 其他',
  };
  const LEVEL_TAG = { H: 'tag-red', M: 'tag-orange', L: 'tag-yellow' };
  const LEVEL_LABEL = {
    H: '<i class="ri-fire-line"></i> 高',
    M: '<i class="ri-error-warning-line"></i> 中',
    L: '<i class="ri-information-line"></i> 低',
  };
  const OT_LABEL = {
    O: '<i class="ri-rocket-line"></i> 机会',
    T: '<i class="ri-shield-cross-line"></i> 威胁',
  };

  /* -----------------------------------------------------------
   * WebSocket / Clock
   * ----------------------------------------------------------- */
  function setupWS() {
    const dot = $('#wsDot'), label = $('#wsLabel'), badge = $('#feedLiveBadge');
    const indicator = $('.ws-indicator');
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws/notifications/`;
    let ws, retry = 0, alive = false;
    function connect() {
      try { ws = new WebSocket(url); } catch (e) { return setTimeout(connect, 2000); }
      ws.onopen = () => {
        retry = 0; alive = true;
        indicator && indicator.classList.add('online');
        indicator && indicator.classList.remove('offline');
        if (label) label.textContent = '实时已连接';
        if (badge) { badge.classList.add('online'); badge.textContent = '实时'; }
      };
      ws.onmessage = (ev) => {
        let payload;
        try { payload = JSON.parse(ev.data); } catch (e) { return; }
        document.dispatchEvent(new CustomEvent('sr:ws', { detail: payload }));
      };
      ws.onclose = () => {
        alive = false;
        indicator && indicator.classList.remove('online');
        indicator && indicator.classList.add('offline');
        if (label) label.textContent = '断开 — 重连中';
        if (badge) { badge.classList.remove('online'); badge.textContent = '离线'; }
        retry += 1;
        setTimeout(connect, Math.min(15000, 1500 * retry));
      };
      ws.onerror = () => ws && ws.close();
    }
    connect();
    return { send: (m) => alive && ws.send(typeof m === 'string' ? m : JSON.stringify(m)) };
  }

  function setupClock() {
    const el = $('#clockTime');
    if (!el) return;
    const tick = () => {
      const d = new Date();
      el.textContent = d.toLocaleTimeString('zh-CN', { hour12: false });
    };
    tick();
    setInterval(tick, 1000);
  }

  /* -----------------------------------------------------------
   * 未使用 — progress 已在 api() 上方声明
   * ----------------------------------------------------------- */

  document.addEventListener('DOMContentLoaded', () => {
    setupClock();
    setupSearchbars();
    setupMultiSwitch();
    setupWS();
  });

  return {
    $, $$, api, toast, dialog, confirm: confirmDlg,
    fmtDt, fmtDate, fmtTime, escapeHtml,
    setupSearchbars, setupMultiSwitch, progress,
    PEST_LABEL, DIM_LABEL, LEVEL_TAG, LEVEL_LABEL, OT_LABEL,
  };
})();
