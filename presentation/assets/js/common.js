/* ======================================================
   VigilAI Presentation — 公共 JS
   键盘翻页 ← → / 进度条 / 章节标题
   ====================================================== */
(function () {
  'use strict';

  // 20 页 slide 文件名列表（按顺序）
  var SLIDES = [
    'slide-01-cover.html',
    'slide-02-pain-points.html',
    'slide-03-mission.html',
    'slide-04-personas.html',
    'slide-05-five-dimensions.html',
    'slide-06-solution.html',
    'slide-07-data-strategy.html',
    'slide-08-value-score.html',
    'slide-09-pest-framework.html',
    'slide-10-swot-matrix.html',
    'slide-11-briefings.html',
    'slide-12-alert-pipeline.html',
    'slide-13-human-loop.html',
    'slide-14-screenshot-dashboard.html',
    'slide-15-architecture.html',
    'slide-16-database.html',
    'slide-17-llm-mock.html',
    'slide-18-metrics.html',
    'slide-19-roadmap.html',
    'slide-20-team.html',
  ];

  var CHAPTERS = [
    '第一幕·痛点定义', '第一幕·痛点定义', '第一幕·痛点定义',
    '第一幕·痛点定义', '第一幕·痛点定义',
    '第二幕·解决方案', '第二幕·解决方案', '第二幕·解决方案',
    '第二幕·解决方案', '第二幕·解决方案', '第二幕·解决方案',
    '第二幕·解决方案', '第二幕·解决方案', '第二幕·解决方案',
    '第三幕·技术与未来', '第三幕·技术与未来', '第三幕·技术与未来',
    '第三幕·技术与未来', '第三幕·技术与未来', '第三幕·技术与未来',
  ];

  var TOTAL = SLIDES.length;

  // 当前页索引（0-based），从文件名推断
  function currentIndex() {
    var filename = location.pathname.split('/').pop();
    var idx = SLIDES.indexOf(filename);
    return idx >= 0 ? idx : 0;
  }

  function goToSlide(idx) {
    if (idx < 0) idx = 0;
    if (idx >= TOTAL) idx = TOTAL - 1;
    var target = SLIDES[idx];
    location.href = target;
  }

  function prev() { goToSlide(currentIndex() - 1); }
  function next() { goToSlide(currentIndex() + 1); }

  // 键盘翻页
  document.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') {
      e.preventDefault(); next();
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault(); prev();
    }
  });

  // 更新进度条 & 页码 & 章节
  window.addEventListener('load', function () {
    var idx = currentIndex();
    var pct = Math.round(((idx + 1) / TOTAL) * 100);

    // 进度条
    var fill = document.querySelector('.progress-bar-fill');
    if (fill) fill.style.width = pct + '%';

    // 页码
    var numEl = document.getElementById('slideNum');
    if (numEl) {
      numEl.innerHTML = '<b>' + (idx + 1) + '</b> / ' + TOTAL;
    }

    // 章节
    var chapEl = document.getElementById('slideChapter');
    if (chapEl) chapEl.textContent = CHAPTERS[idx] || '';

    // 上一页/下一页按钮
    var btnPrev = document.getElementById('btnPrev');
    var btnNext = document.getElementById('btnNext');
    if (btnPrev) {
      btnPrev.style.opacity = idx === 0 ? '0.3' : '1';
      btnPrev.onclick = prev;
    }
    if (btnNext) {
      btnNext.style.opacity = idx === TOTAL - 1 ? '0.3' : '1';
      btnNext.onclick = next;
    }
  });

  // 对外暴露
  window.SRPres = { prev: prev, next: next, goTo: goToSlide, total: TOTAL };
})();
