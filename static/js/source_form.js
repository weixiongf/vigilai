/* 添加信息源表单 — 提交到 /api/sources/create/ 后跳回列表页 */
(function () {
  const { $, api, toast } = window.SR;

  // 实时预览 access_tier
  function refreshTierPreview() {
    const paid = $('#fIsPaid').checked;
    const reg = $('#fNeedsRegister').checked || $('#fNeedsLogin').checked;
    const el = $('#tierPreview');
    if (!el) return;
    if (paid) {
      el.className = 'verdict verdict-fail';
      el.textContent = '付费 API';
    } else if (reg) {
      el.className = 'verdict verdict-warn';
      el.textContent = '需注册/登录 (免费)';
    } else {
      el.className = 'verdict verdict-ok';
      el.textContent = '免费 (无需注册)';
    }
  }
  ['fNeedsRegister', 'fNeedsLogin', 'fIsPaid'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const sync = () => {
      const t = document.querySelector(`.toggle-inline[data-for="${id}"]`);
      if (t) t.classList.toggle('on', el.checked);
    };
    el.addEventListener('change', () => { sync(); refreshTierPreview(); });
    sync();
  });
  refreshTierPreview();

  const form = $('#srcForm');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = $('#formMsg');
    if (msg) msg.textContent = '';

    const payload = {
      name: $('#fName').value.trim(),
      category: $('#fCategory').value.trim(),
      official_url: $('#fOfficialUrl').value.trim(),
      list_url: $('#fListUrl').value.trim(),
      source_type: $('#fSourceType').value,
      priority: $('#fPriority').value,
      update_frequency: $('#fUpdateFreq').value.trim(),
      crawl_interval: Number($('#fInterval').value) || 3600,
      difficulty: Number($('#fDifficulty').value) || 2,
      spider_name: $('#fSpider').value.trim(),
      needs_register: $('#fNeedsRegister').checked,
      needs_login: $('#fNeedsLogin').checked,
      is_paid: $('#fIsPaid').checked,
      notes: $('#fNotes').value,
      is_active: true,
    };

    if (!payload.name) {
      if (msg) msg.textContent = '名称必填';
      $('#fName').focus();
      return;
    }
    if (!payload.official_url) {
      if (msg) msg.textContent = '官方网址必填';
      $('#fOfficialUrl').focus();
      return;
    }

    const btn = form.querySelector('button[type="submit"]');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="ri-loader-4-line"></i> 保存中…'; }

    try {
      const d = await api('/api/sources/create/', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      toast.success('已保存',
        `${d.name} · ${d.priority_label || d.priority} · ${d.access_tier || ''}`);
      // 跳回列表页并高亮新建项
      setTimeout(() => {
        window.location.href = `/dashboard/sources/?highlight=${d.id}`;
      }, 600);
    } catch (e) {
      const text = e && e.message ? e.message : String(e);
      toast.error('保存失败', text);
      if (msg) msg.textContent = text;
      if (btn) { btn.disabled = false; btn.innerHTML = '<i class="ri-save-line"></i> 保存信息源'; }
    }
  });
})();
