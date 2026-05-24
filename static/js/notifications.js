/* 通知记录页 — 收件人 CRUD + 通知日志 (从原 settings.js 拆出) */
(function () {
  const { $, api, escapeHtml, fmtDt, toast } = window.SR;

  // ---------- 收件人 ----------
  async function loadRecipients() {
    let d;
    try { d = await api('/api/notifications/recipients/'); }
    catch (e) { return toast(e.message, 'error'); }

    const tb = $('#tblRecipientsBody');
    const cols = 'grid-template-columns: 28px 1.4fr 1.6fr 0.6fr 1.6fr 0.6fr 0.8fr;';
    tb.innerHTML = (d.items || []).map((r, idx) => `
      <div class="list-row${r.is_active ? '' : ' row-disabled'}" style="${cols}">
        <span class="idx">${String(idx + 1).padStart(2, '0')}</span>
        <div>
          <div><b>${escapeHtml(r.name)}</b></div>
          <div class="muted text-xxs">${escapeHtml(r.role || '')}</div>
        </div>
        <div>${r.email ? escapeHtml(r.email) : '<span class="muted">—</span>'}</div>
        <div>${r.feishu_webhook
          ? '<span class="verdict verdict-ok">已配</span>'
          : '<span class="verdict verdict-pending">未配</span>'}</div>
        <div>
          ${r.subscribe_high_impact ? '<span class="verdict verdict-fail">高</span> ' : ''}
          ${r.subscribe_opportunity ? '<span class="verdict verdict-ok">机</span> ' : ''}
          ${r.subscribe_daily ? '<span class="verdict verdict-info">日</span> ' : ''}
          ${r.subscribe_weekly ? '<span class="verdict verdict-warn">周</span>' : ''}
        </div>
        <div><span class="toggle-inline${r.is_active ? ' on' : ''}" data-act="toggle" data-id="${r.id}" title="${r.is_active ? '点击关闭推送' : '点击开启推送'}"></span></div>
        <div class="actions">
          <button class="btn btn-ghost btn-sm" data-act="send" data-id="${r.id}" title="发送测试消息">
            <i class="ri-send-plane-line"></i></button>
          <button class="btn btn-ghost btn-sm" data-act="edit" data-id="${r.id}" title="编辑">
            <i class="ri-edit-line"></i></button>
          <button class="btn btn-ghost btn-sm" data-act="delete" data-id="${r.id}" title="删除">
            <i class="ri-delete-bin-line" style="color:var(--info-red)"></i></button>
        </div>
      </div>
    `).join('') || '<div class="list-empty"><i class="ri-user-add-line"></i>暂无收件人 — 点击新建</div>';

    // toggle 开关点击
    tb.querySelectorAll('[data-act="toggle"]').forEach(el => {
      el.onclick = async () => {
        const id = el.dataset.id;
        const r = (d.items || []).find(x => x.id == id);
        const newState = !r.is_active;
        try {
          await api(`/api/notifications/recipients/${id}/`, {
            method: 'PATCH', body: JSON.stringify({ is_active: newState })
          });
          toast.success(newState ? '已开启' : '已关闭', `${r.name} 推送${newState ? '开启' : '关闭'}`);
          loadRecipients();
        } catch (e) { toast.error('操作失败', e.message); }
      };
    });

    tb.querySelectorAll('button').forEach(btn => {
      btn.onclick = async () => {
        const id = btn.dataset.id;
        const act = btn.dataset.act;
        if (act === 'send') {
          try {
            const res = await api('/api/notifications/test/', {
              method: 'POST', body: JSON.stringify({ recipient_id: parseInt(id) })
            });
            const results = res.results || {};
            const simulated = Object.values(results).some(v => v && v.simulated);
            if (simulated) {
              toast.warn('模拟发送', '总开关未开启，消息未真实送达。请在 Settings 将模式切换为 real');
            } else {
              toast.success('已发送', '测试消息已真实发送');
            }
            loadLogs();
          } catch (e) { toast.error('发送失败', e.message); }
        } else if (act === 'edit') {
          const r = (d.items || []).find(x => x.id == id);
          fillForm(r);
        } else if (act === 'delete') {
          const ok = await window.SR.confirm({
            caption: '删除收件人', title: '确认删除该收件人？',
            msg: '删除后该收件人将不再接收任何通知',
            danger: true, okText: '删除',
          });
          if (!ok) return;
          try {
            await api(`/api/notifications/recipients/${id}/`, { method: 'DELETE' });
            toast.success('已删除', '收件人已移除');
            loadRecipients();
          } catch (e) { toast.error('删除失败', e.message); }
        }
      };
    });
  }

  function clearForm() {
    $('#recipFormTitle').innerHTML = '<i class="ri-user-add-line"></i> 新建收件人';
    $('#btnCancelEdit').style.display = 'none';
    $('#rId').value = '';
    $('#rName').value = '';
    $('#rRole').value = '';
    $('#rEmail').value = '';
    $('#rWebhook').value = '';
    $('#rSubHigh').checked = true;
    $('#rSubOpportunity').checked = true;
    $('#rSubDaily').checked = true;
    $('#rSubWeekly').checked = true;
  }

  function fillForm(r) {
    $('#recipFormTitle').innerHTML = '<i class="ri-edit-line"></i> 编辑收件人';
    $('#btnCancelEdit').style.display = 'inline-flex';
    $('#rId').value = r.id;
    $('#rName').value = r.name || '';
    $('#rRole').value = r.role || '';
    $('#rEmail').value = r.email || '';
    $('#rWebhook').value = r.feishu_webhook || '';
    $('#rSubHigh').checked = r.subscribe_high_impact;
    $('#rSubOpportunity').checked = r.subscribe_opportunity;
    $('#rSubDaily').checked = r.subscribe_daily;
    $('#rSubWeekly').checked = r.subscribe_weekly;
  }

  $('#btnNewRecipient').onclick = clearForm;
  $('#btnCancelEdit').onclick = clearForm;

  $('#recipForm').onsubmit = async (e) => {
    e.preventDefault();
    const id = $('#rId').value;
    const body = JSON.stringify({
      name: $('#rName').value.trim(),
      role: $('#rRole').value.trim(),
      email: $('#rEmail').value.trim(),
      feishu_webhook: $('#rWebhook').value.trim(),
      subscribe_high_impact: $('#rSubHigh').checked,
      subscribe_opportunity: $('#rSubOpportunity').checked,
      subscribe_daily: $('#rSubDaily').checked,
      subscribe_weekly: $('#rSubWeekly').checked,
    });
    try {
      if (id) {
        await api(`/api/notifications/recipients/${id}/`, { method: 'PATCH', body });
        toast.success('已更新', `收件人 ${$('#rName').value}`);
      } else {
        await api('/api/notifications/recipients/create/', { method: 'POST', body });
        toast.success('已创建', `收件人 ${$('#rName').value}`);
      }
      clearForm();
      loadRecipients();
    } catch (err) { toast.error('保存失败', err.message); }
  };

  $('#btnTestSend').onclick = async () => {
    const id = $('#rId').value;
    if (!id) { return toast.warn('未选择', '请先保存或选择一个收件人'); }
    try {
      const r = await api('/api/notifications/test/', {
        method: 'POST', body: JSON.stringify({ recipient_id: parseInt(id) })
      });
      const results = r.results || {};
      const simulated = Object.values(results).some(v => v && v.simulated);
      if (simulated) {
        toast.warn('模拟发送', '总开关未开启，消息未真实送达。请在 Settings 将模式切换为 real');
      } else {
        toast.success('测试已发送', '消息已真实送达收件人');
      }
      loadLogs();
    } catch (e) { toast.error('发送失败', e.message); }
  };

  // ---------- 通知日志 ----------
  const LOG_DATA = [];   // 缓存当前日志数据

  // ---------- 右侧抽屉 (复用 .src-drawer 样式) ----------
  function ensureLogDrawer() {
    let dr = document.getElementById('logDrawer');
    if (dr) return dr;
    dr = document.createElement('aside');
    dr.id = 'logDrawer';
    dr.className = 'src-drawer';
    dr.hidden = true;
    dr.setAttribute('aria-hidden', 'true');
    dr.setAttribute('role', 'dialog');
    dr.innerHTML = `
      <div class="sd-head">
        <h4 id="logDrawerTitle">
          <i class="ri-mail-send-line"></i> 通知发送日志
          <span class="muted" id="logDrawerHint" style="font-weight:normal;font-size:var(--fz-xxs);margin-left:6px;"></span>
        </h4>
        <span class="sd-close" id="logDrawerClose" title="关闭 (Esc)">
          <i class="ri-close-line"></i>
        </span>
      </div>
      <div class="sd-body" id="logDrawerBody"></div>`;
    document.body.appendChild(dr);
    dr.querySelector('#logDrawerClose').addEventListener('click', closeLogDrawer);
    return dr;
  }
  function openLogDrawer() {
    const dr = ensureLogDrawer();
    dr.hidden = false;
    dr.setAttribute('aria-hidden', 'false');
    void dr.offsetWidth;
    dr.classList.add('open');
    document.addEventListener('keydown', onLogDrawerKey);
  }
  function closeLogDrawer() {
    const dr = document.getElementById('logDrawer');
    if (!dr) return;
    dr.classList.remove('open');
    dr.setAttribute('aria-hidden', 'true');
    setTimeout(() => { if (!dr.classList.contains('open')) dr.hidden = true; }, 260);
    document.removeEventListener('keydown', onLogDrawerKey);
  }
  function onLogDrawerKey(e) { if (e.key === 'Escape') closeLogDrawer(); }

  // 通道图标与中文映射 (列表 + 抽屉头部共用)
  const CH_META = {
    feishu:    { icon: 'ri-plane-line',      label: '飞书',     cls: 'c-blue'   },
    email:     { icon: 'ri-at-line',         label: '邮件',     cls: 'c-yellow' },
    websocket: { icon: 'ri-broadcast-line',  label: 'WebSocket', cls: 'c-green'  },
    sms:       { icon: 'ri-smartphone-line', label: '短信',     cls: 'c-purple' },
  };

  function showLogDetail(l) {
    const channelMap = { feishu: '飞书', email: '邮件', websocket: 'WebSocket', sms: '短信' };
    const statusMap = {
      sent: ['verdict-ok', '已发送'],
      failed: ['verdict-fail', '发送失败'],
      pending: ['verdict-warn', '待发送'],
      retrying: ['verdict-info', '重试中'],
    };
    const [stCls, stLabel] = statusMap[l.status] || ['verdict-pending', l.status];
    const ch = CH_META[l.channel] || { icon: 'ri-question-line', label: l.channel || '—', cls: '' };

    // 检测是否为模拟发送
    const rp = l.response_payload || {};
    const isSimulated = rp.simulated === true
      || (rp.msg && rp.msg.includes('simulated'))
      || (typeof rp === 'object' && JSON.stringify(rp).includes('simulated'));

    let bodyHtml = '';
    if (l.channel === 'email' && l.body) {
      bodyHtml = `<div class="log-detail-body log-detail-email">${l.body}</div>`;
    } else {
      bodyHtml = `<div class="log-detail-body"><pre>${escapeHtml(l.body || '无内容')}</pre></div>`;
    }

    const simulatedNotice = isSimulated
      ? `<div class="log-detail-warn">
           <i class="ri-information-line"></i>
           <span>本条消息为模拟发送，未真实送达收件人。原因：全链路真实化总开关未开启（当前模式非 "real"）。请前往 Settings → 降级与仿真切换 将模式设为 "real" 后再次发送。</span>
         </div>`
      : '';

    const html = `
      <div class="log-detail">
        ${simulatedNotice}
        <table class="kv-table">
          <tbody>
            <tr><th>ID</th>      <td>#${l.id}</td></tr>
            <tr><th>通道</th>    <td><i class="${ch.icon} ${ch.cls}" style="font-size:14px;margin-right:4px;"></i>${escapeHtml(ch.label)}</td></tr>
            <tr><th>事件</th>    <td>${escapeHtml(l.event_type || '—')}</td></tr>
            <tr><th>收件人</th>  <td>${escapeHtml(l.recipient || '—')}</td></tr>
            <tr><th>主题</th>    <td style="font-weight:600;color:var(--text-primary);">${escapeHtml(l.subject || '无主题')}</td></tr>
            <tr><th>状态</th>    <td><span class="verdict ${stCls}">${stLabel}</span>${l.retry_count ? `<span class="muted" style="margin-left:8px;">重试 ${l.retry_count} 次</span>` : ''}</td></tr>
            <tr><th>创建时间</th><td>${fmtDt(l.created_at)}</td></tr>
            <tr><th>发送时间</th><td>${l.sent_at ? fmtDt(l.sent_at) : '<span class="muted">—</span>'}</td></tr>
          </tbody>
        </table>
        ${bodyHtml}
        ${l.status === 'failed' && l.error_message
          ? `<div class="log-detail-error"><i class="ri-error-warning-line"></i> ${escapeHtml(l.error_message)}</div>`
          : ''}
      </div>`;

    ensureLogDrawer();
    document.getElementById('logDrawerBody').innerHTML = html;
    document.getElementById('logDrawerHint').textContent =
      `#${l.id} · ${l.subject ? l.subject.slice(0, 36) : ''}`;
    openLogDrawer();
  }

  async function loadLogs() {
    const qs = new URLSearchParams();
    if ($('#logChannel').value) qs.append('channel', $('#logChannel').value);
    if ($('#logStatus').value) qs.append('status', $('#logStatus').value);
    let d;
    try { d = await api('/api/notifications/logs/?' + qs.toString()); }
    catch (e) { return toast(e.message, 'error'); }
    const tb = $('#tblLogsBody');
    const cols = 'grid-template-columns: 50px 80px 110px 1fr 1.6fr 90px 60px 130px 70px;';
    const meta = $('#logMeta');
    if (meta) meta.textContent = `共 ${(d.items || []).length} 条`;
    const tag = $('#logTotalTag');
    if (tag) tag.textContent = `${(d.items || []).length} 条`;
    LOG_DATA.length = 0;
    (d.items || []).forEach(x => LOG_DATA.push(x));
    tb.innerHTML = (d.items || []).map(l => {
      const st = {
        sent:     '<span class="verdict verdict-ok">已发送</span>',
        failed:   '<span class="verdict verdict-fail">失败</span>',
        pending:  '<span class="verdict verdict-warn">待发送</span>',
        retrying: '<span class="verdict verdict-info">重试中</span>',
      }[l.status] || `<span class="verdict verdict-pending">${escapeHtml(l.status)}</span>`;
      const ch = CH_META[l.channel] || { icon: 'ri-question-line', label: l.channel || '—', cls: '' };
      return `<div class="list-row" style="${cols}" data-log-id="${l.id}">
        <div>${l.id}</div>
        <div class="log-ch-cell"><i class="${ch.icon} ${ch.cls}"></i> ${escapeHtml(ch.label)}</div>
        <div>${escapeHtml(l.event_type)}</div>
        <div title="${escapeHtml(l.recipient || '')}">${escapeHtml((l.recipient || '').slice(0, 32))}</div>
        <div title="${escapeHtml(l.subject || '')}">${escapeHtml((l.subject || '').slice(0, 40))}</div>
        <div>${st}</div>
        <div>${l.retry_count}</div>
        <div>${fmtDt(l.created_at)}</div>
        <div class="actions">${l.status !== 'sent'
          ? `<button class="btn btn-ghost btn-sm" data-id="${l.id}" title="重发"><i class="ri-refresh-line"></i></button>`
          : ''}</div>
      </div>`;
    }).join('') || '<div class="list-empty"><i class="ri-mail-line"></i>暂无日志</div>';

    // 行点击弹出详情
    tb.querySelectorAll('.list-row[data-log-id]').forEach(row => {
      row.style.cursor = 'pointer';
      row.onclick = (e) => {
        // 不拦截按钮点击
        if (e.target.closest('button')) return;
        const l = LOG_DATA.find(x => x.id == row.dataset.logId);
        if (l) showLogDetail(l);
      };
    });

    tb.querySelectorAll('button[data-id]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await api(`/api/notifications/logs/${btn.dataset.id}/resend/`, { method: 'POST' });
          toast.success('已加入重发队列');
        } catch (e) { toast.error('重发失败', e.message); }
      };
    });
  }

  $('#btnRefreshLogs').onclick = loadLogs;
  $('#logChannel').addEventListener('change', loadLogs);
  $('#logStatus').addEventListener('change', loadLogs);

  loadRecipients();
  loadLogs();
  setInterval(loadLogs, 15000);
})();
