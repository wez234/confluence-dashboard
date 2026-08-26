/* ============================================================
   CONFLUENCE — dashboard logic
   Simulates the ingestion → detection pipeline client-side so the
   visualisation layer (this dashboard) can be demonstrated end-to-end.
   ============================================================ */

(function () {
  'use strict';

  /* ---------- helpers ---------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const fmt = (v, d = 2) => v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

  function gaussian() {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  function hourFraction(date) {
    return date.getHours() + date.getMinutes() / 60;
  }

  function gaussianCurve(x, mean, sigma) {
    return Math.exp(-((x - mean) ** 2) / (2 * sigma * sigma));
  }

  /* ---------- theme ---------- */
  (function initTheme() {
    const toggle = $('#theme-toggle');
    const root = document.documentElement;
    let mode = matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
    root.setAttribute('data-theme', mode);
    updateIcon();
    toggle.addEventListener('click', () => {
      mode = mode === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', mode);
      updateIcon();
      refreshAllChartColors();
    });
    function updateIcon() {
      toggle.setAttribute('aria-label', 'Switch to ' + (mode === 'dark' ? 'light' : 'dark') + ' mode');
      toggle.innerHTML =
        mode === 'dark'
          ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
          : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
  })();

  /* ---------- navigation ---------- */
  const VIEW_META = {
    overview: { title: 'Overview', subtitle: 'Live electricity, gas & water network monitoring' },
    utilities: { title: 'Utilities', subtitle: 'Per-network detail with historical comparison' },
    alerts: { title: 'Alerts & Explainability', subtitle: 'SHAP-style feature attribution for detected anomalies' },
    models: { title: 'Model Comparison', subtitle: 'Statistical vs. ML vs. deep-learning detection techniques' },
    architecture: { title: 'Platform Architecture', subtitle: 'Five-layer design from ingestion to visualisation' },
  };

  function showView(name) {
    $$('.view').forEach((v) => v.classList.remove('is-active'));
    $('#view-' + name).classList.add('is-active');
    $$('.nav-link').forEach((l) => l.removeAttribute('aria-current'));
    const link = $('.nav-link[data-view="' + name + '"]');
    if (link) link.setAttribute('aria-current', 'page');
    $('#page-title').textContent = VIEW_META[name].title;
    $('#page-subtitle').textContent = VIEW_META[name].subtitle;
    $('#main-scroll') && ($('#main-scroll').scrollTop = 0);
    document.querySelector('.main').scrollTop = 0;
  }

  $$('.nav-link').forEach((link) => link.addEventListener('click', () => showView(link.dataset.view)));
  $$('[data-goto]').forEach((el) => el.addEventListener('click', () => showView(el.dataset.goto)));

  /* ============================================================
     Data simulation
     ============================================================ */

  const UTILITIES = {
    electricity: {
      label: 'Electricity', unit: 'kWh', freqLabel: '15-min interval', colorVar: '--color-electricity',
      base: 3.4, noise: 0.22,
      peaks: [{ h: 8, sigma: 2.6, amp: 2.0 }, { h: 19, sigma: 2.8, amp: 2.7 }],
      stepMinutes: 15,
    },
    gas: {
      label: 'Gas', unit: 'm³', freqLabel: 'hourly interval', colorVar: '--color-gas',
      base: 1.1, noise: 0.11,
      peaks: [{ h: 7, sigma: 2.2, amp: 1.5 }, { h: 20, sigma: 2.6, amp: 1.2 }],
      stepMinutes: 60,
    },
    water: {
      label: 'Water', unit: 'L/min', freqLabel: 'variable interval', colorVar: '--color-water',
      base: 165, noise: 18,
      peaks: [{ h: 7, sigma: 1.8, amp: 85 }, { h: 19, sigma: 2.2, amp: 65 }],
      stepMinutes: 10,
    },
  };

  function baseline(cfg, date) {
    const hf = hourFraction(date);
    let v = cfg.base;
    cfg.peaks.forEach((p) => (v += p.amp * gaussianCurve(hf, p.h, p.sigma)));
    return v;
  }

  const FEATURE_NAMES = [
    'Consumption deviation', 'Rate of change', 'Time-of-day deviation',
    'Historical volatility', 'Cross-meter correlation',
  ];

  function featureContributions(zscore) {
    const magnitude = clamp(Math.abs(zscore) / 5, 0.3, 1);
    const raw = [
      0.32 + magnitude * 0.28 + Math.random() * 0.06,
      0.1 + Math.random() * 0.14,
      0.08 + Math.random() * 0.12,
      0.06 + Math.random() * 0.1,
      0.04 + Math.random() * 0.08,
    ];
    const sum = raw.reduce((a, b) => a + b, 0);
    return FEATURE_NAMES.map((name, i) => ({ name, value: raw[i] / sum }));
  }

  const state = {
    series: { electricity: [], gas: [], water: [] },
    clocks: { electricity: new Date(), gas: new Date(), water: new Date() },
    alerts: [],
    selectedAlertId: null,
    activeRange: 'live',
    alertSeq: 0,
    kpi: { precision: 0.912, recall: 0.887, throughput: 1180 },
  };

  function fmtTime(d) {
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }

  function tickUtility(key) {
    const cfg = UTILITIES[key];
    const arr = state.series[key];
    // advance virtual clock
    const stepMin = key === 'water' ? cfg.stepMinutes + Math.random() * 8 : cfg.stepMinutes;
    state.clocks[key] = new Date(state.clocks[key].getTime() + stepMin * 60000);
    const clock = state.clocks[key];

    const base = baseline(cfg, clock);

    // rolling stats of RESIDUALS (value minus expected diurnal baseline) —
    // this keeps the trend-following curve from being mistaken for drift.
    const window = arr.filter((p) => !p.anomaly).slice(-16).map((p) => p.residual);
    const meanR = window.length ? window.reduce((a, r) => a + r, 0) / window.length : 0;
    const varR = window.length ? window.reduce((a, r) => a + (r - meanR) ** 2, 0) / window.length : cfg.noise ** 2;
    const stdR = Math.sqrt(varR) || cfg.noise;

    let v = base + gaussian() * cfg.noise;

    const forced = Math.random() < 0.045;
    if (forced) {
      const sign = Math.random() < 0.78 ? 1 : -1;
      v += sign * (2.6 + Math.random() * 2.2) * stdR;
    }

    const residual = v - base;
    const z = (residual - meanR) / (stdR || 1);
    const anomaly = forced || Math.abs(z) > 3.2;

    const point = { t: fmtTime(clock), ts: clock.getTime(), v, anomaly, z, residual };
    arr.push(point);
    if (arr.length > 42) arr.shift();

    if (anomaly) registerAlert(key, point, z);
    return point;
  }

  function registerAlert(utilityKey, point, z) {
    const cfg = UTILITIES[utilityKey];
    const severity = Math.abs(z) >= 4.2 ? 'critical' : Math.abs(z) >= 3.6 ? 'warning' : 'info';
    const direction = z > 0 ? 'spike' : 'drop';
    const alert = {
      id: ++state.alertSeq,
      utility: utilityKey,
      label: cfg.label,
      unit: cfg.unit,
      severity,
      direction,
      value: point.v,
      z,
      time: point.t,
      ts: point.ts,
      features: featureContributions(z),
      latencyMs: 900 + Math.random() * 1400,
    };
    state.alerts.unshift(alert);
    if (state.alerts.length > 40) state.alerts.pop();
    if (state.selectedAlertId === null) state.selectedAlertId = alert.id;
    renderAlerts();
  }

  /* ============================================================
     Historical (static) datasets for 24H / 7D ranges
     ============================================================ */

  function buildHistorical(key, points, stepHours) {
    const cfg = UTILITIES[key];
    const arr = [];
    const now = new Date();
    const anomalyIdx = new Set();
    while (anomalyIdx.size < (points > 10 ? 3 : 1)) anomalyIdx.add(Math.floor(Math.random() * points));

    for (let i = points - 1; i >= 0; i--) {
      const d = new Date(now.getTime() - i * stepHours * 3600000);
      let v = baseline(cfg, d) + gaussian() * cfg.noise * 0.8;
      const idx = points - 1 - i;
      const isAnomaly = anomalyIdx.has(idx);
      if (isAnomaly) v += (Math.random() < 0.7 ? 1 : -1) * (2.8 + Math.random()) * cfg.noise;
      arr.push({
        t: stepHours >= 24
          ? d.toLocaleDateString(undefined, { weekday: 'short' })
          : d.toLocaleTimeString(undefined, { hour: '2-digit' }),
        v, anomaly: isAnomaly,
      });
    }
    return arr;
  }

  const historicalCache = { '24h': {}, '7d': {} };
  function getHistorical(range, key) {
    if (!historicalCache[range][key]) {
      historicalCache[range][key] = range === '24h' ? buildHistorical(key, 24, 1) : buildHistorical(key, 7, 24);
    }
    return historicalCache[range][key];
  }

  /* ============================================================
     Chart.js setup
     ============================================================ */

  if (window.Chart && window['chartjs-plugin-annotation']) {
    Chart.register(window['chartjs-plugin-annotation']);
  }

  Chart.defaults.font.family = "'Satoshi','Inter',sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.color = cssVar('--color-text-muted');

  const overviewCharts = {};
  const detailCharts = {};
  let modelAccuracyChart, modelLatencyChart;

  function lineChartOptions(unit) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500, easing: 'easeOutCubic' },
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 10 } } },
        y: {
          grid: { color: cssVar('--color-divider') },
          ticks: { font: { size: 10 }, callback: (v) => v.toLocaleString() },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: cssVar('--color-surface'),
          titleColor: cssVar('--color-text'),
          bodyColor: cssVar('--color-text-muted'),
          borderColor: cssVar('--color-border'),
          borderWidth: 1,
          padding: 10,
          callbacks: { label: (ctx) => `${fmt(ctx.parsed.y, 2)} ${unit}` },
        },
      },
      elements: { line: { tension: 0.35, borderWidth: 2 }, point: { hoverRadius: 6 } },
    };
  }

  function makeLineChart(canvasId, key) {
    const cfg = UTILITIES[key];
    const color = cssVar(cfg.colorVar);
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
      type: 'line',
      data: { labels: [], datasets: [{ data: [], borderColor: color, backgroundColor: color + '22', fill: true, pointBackgroundColor: [], pointRadius: [] }] },
      options: lineChartOptions(cfg.unit),
    });
  }

  function updateLineChart(chart, points, key) {
    const errColor = cssVar('--color-error');
    const color = cssVar(UTILITIES[key].colorVar);
    chart.data.labels = points.map((p) => p.t);
    chart.data.datasets[0].data = points.map((p) => p.v);
    chart.data.datasets[0].borderColor = color;
    chart.data.datasets[0].backgroundColor = color + '22';
    chart.data.datasets[0].pointBackgroundColor = points.map((p) => (p.anomaly ? errColor : color));
    chart.data.datasets[0].pointRadius = points.map((p) => (p.anomaly ? 5 : 0));
    chart.data.datasets[0].pointHoverRadius = 6;
    chart.update();
  }

  function initOverviewCharts() {
    const wrap = $('#overview-charts');
    wrap.innerHTML = Object.keys(UTILITIES).map((key) => {
      const cfg = UTILITIES[key];
      return `<div class="card chart-card">
        <div class="chart-card-head">
          <span class="chart-card-title"><span class="utility-dot ${key}"></span>${cfg.label}</span>
          <span class="chart-stat" id="stat-${key}">—</span>
        </div>
        <div class="chart-canvas-wrap"><canvas id="chart-${key}"></canvas></div>
      </div>`;
    }).join('');
    Object.keys(UTILITIES).forEach((key) => { overviewCharts[key] = makeLineChart('chart-' + key, key); });
  }

  function initDetailCharts() {
    const wrap = $('#utility-detail-cards');
    wrap.innerHTML = Object.keys(UTILITIES).map((key) => {
      const cfg = UTILITIES[key];
      return `<div class="card chart-card">
        <div class="chart-card-head">
          <span class="chart-card-title"><span class="utility-dot ${key}"></span>${cfg.label} <span class="badge ${key}" style="margin-left:6px;">${cfg.freqLabel}</span></span>
          <span class="chart-stat" id="detail-stat-${key}">—</span>
        </div>
        <div class="chart-canvas-wrap large"><canvas id="detail-chart-${key}"></canvas></div>
        <div class="detail-grid">
          <div class="stat-row"><span>Current</span><span id="detail-current-${key}">—</span></div>
          <div class="stat-row"><span id="detail-anom-label-${key}">Anomalies</span><span id="detail-anom-${key}">—</span></div>
          <div class="stat-row"><span>Unit</span><span>${cfg.unit}</span></div>
        </div>
      </div>`;
    }).join('');
    Object.keys(UTILITIES).forEach((key) => { detailCharts[key] = makeLineChart('detail-chart-' + key, key); });
  }

  function refreshAllChartColors() {
    Chart.defaults.color = cssVar('--color-text-muted');
    Object.keys(UTILITIES).forEach((key) => {
      updateLineChart(overviewCharts[key], state.series[key], key);
      updateLineChart(detailCharts[key], currentDetailData(key), key);
      overviewCharts[key].options.scales.y.grid.color = cssVar('--color-divider');
      detailCharts[key].options.scales.y.grid.color = cssVar('--color-divider');
      overviewCharts[key].update();
      detailCharts[key].update();
    });
    renderModelCharts();
  }

  function currentDetailData(key) {
    if (state.activeRange === 'live') return state.series[key];
    return getHistorical(state.activeRange, key);
  }

  function renderDetailCharts() {
    Object.keys(UTILITIES).forEach((key) => {
      const data = currentDetailData(key);
      updateLineChart(detailCharts[key], data, key);
      const last = data[data.length - 1];
      const cfg = UTILITIES[key];
      $('#detail-stat-' + key).textContent = state.activeRange === 'live' ? 'LIVE' : state.activeRange.toUpperCase();
      $('#detail-current-' + key).textContent = last ? `${fmt(last.v, 1)} ${cfg.unit}` : '—';
      $('#detail-anom-' + key).textContent = data.filter((p) => p.anomaly).length;
      const rangeLabel = state.activeRange === 'live' ? 'Live' : state.activeRange === '24h' ? '24h' : '7d';
      $('#detail-anom-label-' + key).textContent = rangeLabel + ' anomalies';
    });
  }

  $('#range-toggle').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    $$('#range-toggle button').forEach((b) => b.setAttribute('aria-pressed', 'false'));
    btn.setAttribute('aria-pressed', 'true');
    state.activeRange = btn.dataset.range;
    renderDetailCharts();
  });

  /* ============================================================
     KPI cards
     ============================================================ */

  const KPI_DEFS = [
    { id: 'active-alerts', label: 'Active alerts', icon: 'alert' },
    { id: 'avg-latency', label: 'Avg alert latency', icon: 'clock' },
    { id: 'precision', label: 'Precision (ensemble)', icon: 'target' },
    { id: 'recall', label: 'Recall (ensemble)', icon: 'target' },
    { id: 'throughput', label: 'Throughput', icon: 'pulse' },
    { id: 'uptime', label: 'Pipeline uptime', icon: 'check' },
  ];

  const ICONS = {
    alert: '<path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.5"/>',
    pulse: '<path d="M3 12h4l2-8 4 16 2-8h6"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
  };

  function initKpiGrid() {
    $('#kpi-grid').innerHTML = KPI_DEFS.map((k) => `
      <div class="card kpi-card">
        <span class="kpi-label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${ICONS[k.icon]}</svg>${k.label}</span>
        <span class="kpi-value" id="kpi-${k.id}">—</span>
        <span class="kpi-delta flat" id="kpi-${k.id}-delta"></span>
      </div>`).join('');
  }

  function renderKpis() {
    const now = Date.now();
    const activeAlerts = state.alerts.filter((a) => now - a.ts < 15 * 60000).length;
    const avgLatency = state.alerts.slice(0, 12).reduce((a, al) => a + al.latencyMs, 0) / Math.max(1, Math.min(12, state.alerts.length));
    const latencyS = state.alerts.length ? avgLatency / 1000 : 1.6;

    $('#kpi-active-alerts').textContent = activeAlerts;
    $('#kpi-avg-latency').textContent = fmt(latencyS, 2) + 's';
    $('#kpi-avg-latency-delta').innerHTML = latencyS < 2.5
      ? '<span class="kpi-delta down"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M12 19V5M5 12l7-7 7 7"/></svg>under 2.5s target</span>'
      : '<span class="kpi-delta up">above target</span>';

    state.kpi.precision = clamp(state.kpi.precision + (Math.random() - 0.5) * 0.004, 0.87, 0.94);
    state.kpi.recall = clamp(state.kpi.recall + (Math.random() - 0.5) * 0.004, 0.85, 0.92);
    state.kpi.throughput = clamp(state.kpi.throughput + (Math.random() - 0.5) * 24, 950, 1450);

    $('#kpi-precision').textContent = fmt(state.kpi.precision * 100, 1) + '%';
    $('#kpi-recall').textContent = fmt(state.kpi.recall * 100, 1) + '%';
    $('#kpi-throughput').textContent = Math.round(state.kpi.throughput).toLocaleString() + '/s';
    $('#kpi-uptime').textContent = '99.98%';

    $('#alert-nav-badge').textContent = state.alerts.length > 9 ? '9+' : state.alerts.length;
    $('#alert-nav-badge').style.display = state.alerts.length ? 'inline-flex' : 'none';
  }

  /* ============================================================
     Alerts rendering
     ============================================================ */

  const ALERT_ICON = {
    critical: '<path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>',
    warning: '<path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  };

  function alertItemHtml(a, selected) {
    const dirWord = a.direction === 'spike' ? 'spike' : 'drop';
    return `<button class="alert-item ${selected ? 'is-selected' : ''}" data-alert-id="${a.id}">
      <span class="alert-icon badge ${a.severity}" style="width:34px;height:34px;">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${ALERT_ICON[a.severity]}</svg>
      </span>
      <span class="alert-body">
        <span class="alert-top">
          <span class="alert-title">${a.label} ${dirWord}</span>
          <span class="badge ${a.utility}">${a.utility}</span>
          <span class="alert-time">${a.time}</span>
        </span>
        <span class="alert-meta">${fmt(a.value, 1)} ${a.unit} · z = ${a.z.toFixed(2)} · ${a.severity}</span>
      </span>
    </button>`;
  }

  function renderAlerts() {
    const overviewList = $('#overview-alert-list');
    const fullList = $('#full-alert-list');
    if (!state.alerts.length) {
      overviewList.innerHTML = '<div class="empty-alerts">No anomalies detected yet — monitoring streams…</div>';
      fullList.innerHTML = '<div class="empty-alerts">No anomalies detected yet — monitoring streams…</div>';
    } else {
      overviewList.innerHTML = state.alerts.slice(0, 6).map((a) => alertItemHtml(a, false)).join('');
      fullList.innerHTML = state.alerts.map((a) => alertItemHtml(a, a.id === state.selectedAlertId)).join('');
    }
    renderKpis();
    renderXaiPanel();
  }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.alert-item');
    if (!btn) return;
    state.selectedAlertId = Number(btn.dataset.alertId);
    renderAlerts();
    showView('alerts');
  });

  function renderXaiPanel() {
    const panel = $('#xai-panel');
    const alert = state.alerts.find((a) => a.id === state.selectedAlertId);
    if (!alert) {
      panel.innerHTML = '<div class="empty-alerts">Select an alert to see its explanation</div>';
      return;
    }
    const maxVal = Math.max(...alert.features.map((f) => f.value));
    panel.innerHTML = `
      <div class="xai-head">
        <span class="section-title" style="font-size:var(--text-base);">Explainability</span>
        <span class="xai-model-badge">SHAP · LSTM autoencoder</span>
      </div>
      <div class="xai-summary">
        <strong>${alert.label} ${alert.direction}</strong> detected at ${alert.time} — ${fmt(alert.value, 1)} ${alert.unit}
        (z = ${alert.z.toFixed(2)}, ${alert.severity} severity). The model attributes this mostly to
        <strong>${alert.features[0].name.toLowerCase()}</strong>, contributing ${fmt(alert.features[0].value * 100, 0)}% of the anomaly score.
      </div>
      <div style="display:flex; flex-direction:column; gap:10px;">
        ${alert.features.map((f) => `
          <div class="feature-bar-row">
            <span class="feature-bar-label">${f.name}</span>
            <span class="feature-bar-track"><span class="feature-bar-fill" style="width:${(f.value / maxVal) * 100}%"></span></span>
            <span class="feature-bar-value">${fmt(f.value * 100, 0)}%</span>
          </div>`).join('')}
      </div>
      <div class="stat-row"><span>Model latency</span><span>${fmt(alert.latencyMs / 1000, 2)}s</span></div>
      <div class="stat-row"><span>Alert ID</span><span>#${String(alert.id).padStart(4, '0')}</span></div>
    `;
  }

  /* ============================================================
     Model comparison
     ============================================================ */

  const MODELS = [
    { name: 'Z-score', color: '--color-water', precision: 0.81, recall: 0.74, f1: 0.77, rocauc: 0.83, latency: 0.6, interp: 'High' },
    { name: 'Isolation Forest', color: '--color-electricity', precision: 0.88, recall: 0.85, f1: 0.86, rocauc: 0.91, latency: 1.4, interp: 'Medium' },
    { name: 'LSTM Autoencoder + SHAP', color: '--color-primary', precision: 0.90, recall: 0.93, f1: 0.91, rocauc: 0.95, latency: 2.1, interp: 'Medium (via SHAP)' },
  ];

  function bestMark(metric, value) {
    const values = MODELS.map((m) => m[metric]);
    const best = metric === 'latency' ? Math.min(...values) : Math.max(...values);
    return value === best;
  }

  function renderModelTable() {
    $('#model-table-body').innerHTML = MODELS.map((m) => `
      <tr>
        <td><span class="model-swatch" style="background:${cssVar(m.color)}"></span>${m.name}</td>
        <td class="num ${bestMark('precision', m.precision) ? 'best' : ''}">${fmt(m.precision, 2)}</td>
        <td class="num ${bestMark('recall', m.recall) ? 'best' : ''}">${fmt(m.recall, 2)}</td>
        <td class="num ${bestMark('f1', m.f1) ? 'best' : ''}">${fmt(m.f1, 2)}</td>
        <td class="num ${bestMark('rocauc', m.rocauc) ? 'best' : ''}">${fmt(m.rocauc, 2)}</td>
        <td class="num ${bestMark('latency', m.latency) ? 'best' : ''}">${fmt(m.latency, 1)}s</td>
        <td>${m.interp}</td>
      </tr>`).join('');
  }

  function renderModelCharts() {
    const labels = ['Precision', 'Recall', 'F1-score', 'ROC-AUC'];
    const datasets = MODELS.map((m) => ({
      label: m.name,
      backgroundColor: cssVar(m.color),
      borderRadius: 4,
      data: [m.precision, m.recall, m.f1, m.rocauc],
    }));

    if (modelAccuracyChart) modelAccuracyChart.destroy();
    modelAccuracyChart = new Chart(document.getElementById('model-accuracy-chart').getContext('2d'), {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: { grid: { display: false } },
          y: { min: 0, max: 1, grid: { color: cssVar('--color-divider') } },
        },
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } },
      },
    });

    if (modelLatencyChart) modelLatencyChart.destroy();
    modelLatencyChart = new Chart(document.getElementById('model-latency-chart').getContext('2d'), {
      type: 'bar',
      data: {
        labels: MODELS.map((m) => m.name),
        datasets: [{
          label: 'Avg latency (s)',
          data: MODELS.map((m) => m.latency),
          backgroundColor: MODELS.map((m) => cssVar(m.color)),
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: { min: 0, max: 3, grid: { color: cssVar('--color-divider') } },
          y: { grid: { display: false } },
        },
        plugins: {
          legend: { display: false },
          annotation: {
            annotations: {
              targetLine: {
                type: 'line', xMin: 2.5, xMax: 2.5,
                borderColor: cssVar('--color-error'), borderWidth: 2, borderDash: [6, 4],
                label: { display: true, content: '2.5s target', position: 'end', color: cssVar('--color-error'), font: { size: 10 } },
              },
            },
          },
        },
      },
    });
  }

  /* ============================================================
     Architecture diagram
     ============================================================ */

  const LAYERS = [
    { title: 'Data Sources', desc: 'Electricity, gas & water smart meter streams — public/simulated, timestamp-normalised.', tech: ['SGCC benchmark', 'UK smart meter data', 'Simulated streams'] },
    { title: 'Ingestion Layer', desc: 'Streaming validation, cleansing & feature extraction across heterogeneous frequencies.', tech: ['Apache Kafka', 'Schema validation', 'Feature extraction'] },
    { title: 'Storage Layer', desc: 'Partitioned time-series storage for fast dashboard queries and historical analysis.', tech: ['TimescaleDB', 'PostgreSQL', 'Partitioning'] },
    { title: 'Detection Layer', desc: 'Multi-model anomaly detection compared across statistical, ML & deep-learning approaches.', tech: ['Z-score', 'Isolation Forest', 'LSTM AE', 'SHAP / LIME'] },
    { title: 'Visualisation Layer', desc: 'Live monitoring, historical analysis & explainable alert panels — this dashboard.', tech: ['Live charts', 'Alert panels', 'XAI panels'], active: true },
  ];

  function renderArchitecture() {
    $('#arch-flow').innerHTML = LAYERS.map((l, i) => `
      <div class="card arch-layer ${l.active ? 'active' : ''}">
        ${l.active ? '<span class="you-are-here">You are here</span>' : ''}
        <span class="arch-num">${String(i + 1).padStart(2, '0')}</span>
        <span class="arch-title">${l.title}</span>
        <span class="arch-desc">${l.desc}</span>
        <span class="tech-pill-row">${l.tech.map((t) => `<span class="tech-pill">${t}</span>`).join('')}</span>
        ${i < LAYERS.length - 1 ? '<span class="arch-arrow"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M13 6l6 6-6 6"/></svg></span>' : ''}
      </div>`).join('');
  }

  /* ============================================================
     Boot + tick loop
     ============================================================ */

  let lastUpdateTs = Date.now();
  function updateLastUpdatedChip() {
    const s = Math.round((Date.now() - lastUpdateTs) / 1000);
    $('#last-updated').textContent = s <= 1 ? 'updated just now' : `updated ${s}s ago`;
  }

  function seedHistory() {
    Object.keys(UTILITIES).forEach((key) => {
      state.clocks[key] = new Date(Date.now() - 30 * UTILITIES[key].stepMinutes * 60000);
      for (let i = 0; i < 26; i++) tickUtility(key);
    });
    // clear alerts generated purely for seeding so the feed starts clean-ish
    state.alerts = state.alerts.slice(0, 5);
    state.selectedAlertId = state.alerts.length ? state.alerts[0].id : null;
  }

  function tick() {
    Object.keys(UTILITIES).forEach(tickUtility);
    lastUpdateTs = Date.now();
    Object.keys(UTILITIES).forEach((key) => {
      updateLineChart(overviewCharts[key], state.series[key], key);
      const last = state.series[key][state.series[key].length - 1];
      $('#stat-' + key).textContent = last ? `${fmt(last.v, 1)} ${UTILITIES[key].unit}` : '—';
    });
    if (state.activeRange === 'live') renderDetailCharts();
    renderAlerts();
  }

  function boot() {
    initKpiGrid();
    initOverviewCharts();
    initDetailCharts();
    renderModelTable();
    renderArchitecture();
    seedHistory();
    renderDetailCharts();
    renderAlerts();
    renderModelCharts();
    tick();
    setInterval(tick, 3000);
    setInterval(updateLastUpdatedChip, 1000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
