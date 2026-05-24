/* 驾驶舱 — KPI + 4 charts + 实时高影响告警 */
(async function () {
  const { $, api, fmtDt, escapeHtml, toast, PEST_LABEL, DIM_LABEL, LEVEL_LABEL } = window.SR;

  // 纯文本维度标签（Chart.js 不支持 HTML）
  const DIM_TEXT = {
    competition: '竞争',
    product: '产品',
    platform: '平台',
    social: '社媒',
    regulation: '法规',
    macro: '宏观',
    industry: '行业',
    other: '其他',
  };

  let alertCount = 0;

  async function loadKPI() {
    let data;
    try { data = await api('/api/intel/kpi/'); }
    catch (e) { toast('KPI 加载失败: ' + e.message, 'error'); return; }

    $('#kpiTotal').textContent = data.total;
    $('#kpiNew24').textContent = data.new_24h;
    $('#kpiHigh').textContent = data.high_impact;
    $('#kpiHigh24').textContent = data.high_impact_24h;

    const ot = data.ot_distribution || [];
    const o = (ot.find(x => x.opportunity_or_threat === 'O') || {}).cnt || 0;
    const t = (ot.find(x => x.opportunity_or_threat === 'T') || {}).cnt || 0;
    $('#kpiOT').innerHTML = `<span style="color:var(--info-green)">${o}</span> <span class="muted" style="font-size:var(--fz-xs);">/</span> <span style="color:var(--info-red)">${t}</span>`;

    drawPEST(data.pest_distribution || []);
    drawTrend(data.daily_trend || []);
    drawDim(data.dimension_distribution || []);
    fillMarkets(data.market_top10 || []);
  }

  function drawPEST(arr) {
    const map = { P: 0, E: 0, S: 0, T: 0 };
    arr.forEach(x => map[x.pest_type] = x.cnt);
    new Chart($('#chartPEST'), {
      type: 'doughnut',
      data: {
        labels: ['政治法律', '经济', '社会文化', '技术'],
        datasets: [{
          data: [map.P, map.E, map.S, map.T],
          backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#8b5cf6'],
          borderWidth: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { position: 'right', labels: { color: '#cbd5e1', font: { size: 11 } } } }
      }
    });
  }

  function drawTrend(arr) {
    new Chart($('#chartTrend'), {
      type: 'line',
      data: {
        labels: arr.map(x => x.date.slice(5)),
        datasets: [{
          label: '每日已分析情报',
          data: arr.map(x => x.count),
          borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,.18)',
          fill: true, tension: .35, pointRadius: 3,
        }]
      },
      options: {
        plugins: { legend: { labels: { color: '#cbd5e1' } } },
        scales: {
          x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e2a44' } },
          y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e2a44' }, beginAtZero: true },
        }
      }
    });
  }

  function drawDim(arr) {
    new Chart($('#chartDim'), {
      type: 'bar',
      data: {
        labels: arr.map(x => DIM_TEXT[x.strategic_dimension] || x.strategic_dimension),
        datasets: [{
          label: '条数',
          data: arr.map(x => x.cnt),
          backgroundColor: '#3b82f6',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e2a44' } },
          y: { ticks: { color: '#cbd5e1' }, grid: { color: 'transparent' } },
        }
      }
    });
  }

  function fillMarkets(arr) {
    const tb = $('#tblMarketBody');
    if (!tb) return;
    const cols = 'grid-template-columns: 2fr 1fr 1fr;';

    // 按均分降序排列：高分在前
    const sorted = (arr || []).slice().sort(
      (a, b) => (b.avg_score || 0) - (a.avg_score || 0)
    );
    const n = sorted.length;

    // 前三高 = 红 / 橙 / 黄；后三低 = 三档绿（最低最深绿）
    const TOP_COLORS = ['#ef4444', '#f59e0b', '#eab308'];
    const BOTTOM_COLORS = ['#86efac', '#22c55e', '#16a34a']; // 倒数第3 / 倒数第2 / 最低
    function scoreColor(idx) {
      if (idx < 3 && idx < n) return TOP_COLORS[idx];
      // 后三名（避免与前三重叠）
      const fromBottom = n - 1 - idx;
      if (fromBottom < 3 && idx >= 3) return BOTTOM_COLORS[2 - fromBottom];
      return '';
    }

    tb.innerHTML = sorted.map((x, i) => {
      const color = scoreColor(i);
      const style = color ? `color:${color};font-weight:700;` : '';
      const score = (x.avg_score || 0).toFixed(2);
      const marketEnc = encodeURIComponent(x.target_market);
      const href = `/dashboard/feed/?market=${marketEnc}&order=-impact_score`;
      return `
      <div class="list-row kpi-clickable" style="${cols}" data-href="${href}" title="查看 ${escapeHtml(x.target_market)} 全部情报">
        <div><b class="linklike">${escapeHtml(x.target_market)}</b></div>
        <div>${x.cnt}</div>
        <div style="${style}">${score}</div>
      </div>
    `;
    }).join('') || '<div class="list-empty"><i class="ri-inbox-line"></i>无数据</div>';

    // 绑定点击
    tb.querySelectorAll('.list-row[data-href]').forEach(el => {
      el.addEventListener('click', () => {
        window.location.href = el.getAttribute('data-href');
      });
    });

    // 绘制市场分值折线图（同样按降序展示）
    drawMarketLine(sorted);
  }

  function drawMarketLine(arr) {
    const canvas = $('#chartMarketLine');
    if (!canvas || !arr.length) return;
    // 指数增强：将 0-10 分值的微小差异放大，公式: (score^2.5) 用于拉开距离
    const rawScores = arr.map(x => parseFloat((x.avg_score || 0).toFixed(2)));
    const enhanced = rawScores.map(v => Math.pow(v, 2.5));
    const minVal = Math.min(...enhanced);
    const maxVal = Math.max(...enhanced);
    const margin = minVal / 10;
    new Chart(canvas, {
      type: 'line',
      data: {
        labels: arr.map(x => x.target_market),
        datasets: [{
          label: '平均影响分（指数增强）',
          data: enhanced,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,.15)',
          fill: true,
          tension: .3,
          pointRadius: 4,
          pointBackgroundColor: '#3b82f6',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                return '原始分: ' + rawScores[ctx.dataIndex] + ' / 10';
              }
            }
          }
        },
        scales: {
          x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#1e2a44' } },
          y: {
            ticks: { color: '#94a3b8' }, grid: { color: '#1e2a44' },
            min: Math.max(0, minVal - margin),
            max: maxVal + margin,
          },
        }
      }
    });
  }

  function renderAlert(p) {
    const ul = $('#alertList');
    if (alertCount === 0) ul.innerHTML = '';
    alertCount += 1;
    const cnt = $('#liveAlertCount');
    if (cnt) {
      const b = cnt.querySelector('b'); if (b) b.textContent = alertCount;
      else cnt.textContent = alertCount;
    }

    const item = document.createElement('div');
    item.className = 'alert-item';
    item.innerHTML = `
      <div class="a-score">${(p.impact_score || 0).toFixed(1)}</div>
      <div style="flex:1;">
        <div><b>${escapeHtml(p.title || '')}</b></div>
        <div class="a-meta">
          <span class="verdict verdict-info">${escapeHtml(p.market || '')}</span>
          <span class="muted">${escapeHtml(p.pest || '')}</span>
          <span>${LEVEL_LABEL[p.level] || ''}</span>
          <span class="muted">刚刚</span>
        </div>
      </div>
    `;
    ul.prepend(item);
    while (ul.children.length > 20) ul.removeChild(ul.lastChild);
  }

  document.addEventListener('sr:ws', (ev) => {
    const d = ev.detail || {};
    if (d.type === 'alert.high_impact') renderAlert(d);
  });

  // KPI 卡片点击 → 跳转情报流页并带上对应筛选参数
  document.querySelectorAll('.mini-stat.kpi-clickable[data-href]').forEach(el => {
    el.addEventListener('click', () => {
      const url = el.getAttribute('data-href');
      if (url) window.location.href = url;
    });
  });

  loadKPI();
  setInterval(loadKPI, 60000);
})();
