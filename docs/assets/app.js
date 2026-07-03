/* São Miguel Hub — static analytics dashboard.
 * Talks to the AUTH_KEY-protected /api/v3/analytics/reports/* endpoints.
 * No build step: plain ES2015+ for GitHub Pages. */
(function () {
  'use strict';

  var CONFIG_KEY = 'smb_analytics_config';
  var DEFAULTS = { apiBase: 'https://api.saomiguelhub.com', authKey: '', island: 'sao-miguel' };

  var COLORS = { green: '#218732', amber: '#ffc107', gray: '#9aa3ab', teal: '#0e7490' };

  var SOURCES = {
    v3: {
      label: 'Overview',
      overview: '/api/v3/analytics/reports/overview',
      events: '/api/v3/analytics/reports/events',
      meta: '/api/v3/analytics/reports/meta',
      properties: '/api/v3/analytics/reports/properties',
      needsIsland: true,
      hasCompare: true,
      metrics: [
        { key: 'events', label: 'Events', delta: true },
        { key: 'sessions', label: 'Sessions', delta: true }
      ],
      series: [
        { key: 'events', label: 'Events', color: COLORS.green },
        { key: 'sessions', label: 'Sessions', color: COLORS.amber }
      ],
      breakdowns: [
        { key: 'module', title: 'Modules', filterParam: 'module' },
        { key: 'event_type', title: 'Event types', filterParam: 'event_type' },
        { key: 'platform', title: 'Platforms', filterParam: 'platform' },
        { key: 'locale', title: 'Locales', filterParam: 'locale' }
      ],
      filters: [
        { param: 'module', metaKey: 'modules', label: 'Module' },
        { param: 'event_type', metaKey: 'event_types', label: 'Event type' },
        { param: 'platform', metaKey: 'platforms', label: 'Platform' }
      ],
      columns: [
        { key: 'occurred_at', label: 'Time', time: true },
        { key: 'module', label: 'Module' },
        { key: 'event_type', label: 'Event' },
        { key: 'platform', label: 'Platform' },
        { key: 'locale', label: 'Locale' },
        { key: 'properties', label: 'Properties', json: true }
      ]
    },
    transit: {
      label: 'Transit',
      overview: '/api/v3/analytics/reports/transit/overview',
      needsIsland: true,
      hasCompare: true,
      metrics: [
        { key: 'searches', label: 'Route searches', delta: true },
        { key: 'legacy', label: 'Legacy source' },
        { key: 'v3', label: 'Hub (v3) source' }
      ],
      series: [
        { key: 'total', label: 'Total', color: COLORS.green },
        { key: 'legacy', label: 'Legacy', color: COLORS.gray },
        { key: 'v3', label: 'Hub v3', color: COLORS.amber }
      ],
      breakdowns: [
        { key: 'top_routes', title: 'Top routes', filterParams: { origin: 'origin', destination: 'destination' } },
        { key: 'top_origins', title: 'Top origins', filterParam: 'origin' },
        { key: 'top_destinations', title: 'Top destinations', filterParam: 'destination' },
        { key: 'platform', title: 'Platforms', filterParam: 'platform' }
      ],
      filters: []
    },
    ads: {
      label: 'Ads',
      overview: '/api/v3/analytics/reports/ads/overview',
      needsIsland: true,
      hasCompare: true,
      adsTable: true,
      metrics: [
        { key: 'impressions', label: 'Impressions', delta: true },
        { key: 'clicks', label: 'Clicks', delta: true },
        { key: 'ctr', label: 'CTR', delta: true, percent: true }
      ],
      series: [
        { key: 'impressions', label: 'Impressions', color: COLORS.green },
        { key: 'clicks', label: 'Clicks', color: COLORS.amber }
      ],
      breakdowns: [
        { key: 'platform', title: 'Platforms', filterParam: 'platform' },
        { key: 'kind', title: 'Event kinds' }
      ],
      filters: []
    },
    legacy: {
      label: 'Legacy',
      overview: '/api/v3/analytics/reports/legacy/overview',
      events: '/api/v3/analytics/reports/legacy/events',
      meta: '/api/v3/analytics/reports/legacy/meta',
      needsIsland: false,
      hasCompare: true,
      metrics: [
        { key: 'stats', label: 'Requests', delta: true },
        { key: 'routes', label: 'Route searches', delta: true }
      ],
      series: [{ key: 'count', label: 'Requests', color: COLORS.green }],
      breakdowns: [
        { key: 'request', title: 'Request types', filterParam: 'request' },
        { key: 'top_routes', title: 'Top routes', filterParams: { origin: 'origin', destination: 'destination' } },
        { key: 'top_origins', title: 'Top origins', filterParam: 'origin' },
        { key: 'top_destinations', title: 'Top destinations', filterParam: 'destination' },
        { key: 'platform', title: 'Platforms', filterParam: 'platform' },
        { key: 'language', title: 'Languages', filterParam: 'language' },
        { key: 'type_of_day', title: 'Day type' },
        { key: 'time', title: 'Time of day' }
      ],
      filters: [
        { param: 'request', metaKey: 'requests', label: 'Request' },
        { param: 'platform', metaKey: 'platforms', label: 'Platform' },
        { param: 'language', metaKey: 'languages', label: 'Language' }
      ],
      columns: [
        { key: 'timestamp', label: 'Time', time: true },
        { key: 'request', label: 'Request' },
        { key: 'origin', label: 'Origin' },
        { key: 'destination', label: 'Destination' },
        { key: 'platform', label: 'Platform' },
        { key: 'language', label: 'Lang' },
        { key: 'type_of_day', label: 'Day' }
      ]
    }
  };

  var ADS_COLUMNS = [
    { key: 'entity', label: 'Ad', text: true },
    { key: 'status', label: 'Status', text: true },
    { key: 'platform', label: 'Target', text: true },
    { key: 'impressions', label: 'Impressions' },
    { key: 'clicks', label: 'Clicks' },
    { key: 'ctr', label: 'CTR', percent: true },
    { key: 'lifetime_seen', label: 'Seen (lifetime)' },
    { key: 'lifetime_clicked', label: 'Clicked (lifetime)' }
  ];

  // Friendly titles for auto-discovered v3 property keys.
  var PROP_LABELS = {
    origin: 'Top origins',
    destination: 'Top destinations',
    day_type: 'Day type',
    start_time: 'Start time',
    results_count: 'Results count',
    source: 'News source',
    article_id: 'Top articles (id)',
    slug: 'Parish / slug',
    screen: 'Screen',
    trail_id: 'Top trails (id)',
    difficulty: 'Difficulty',
    kind: 'Kind',
    event_id: 'Event id',
    magnitude: 'Magnitude',
    window_hours: 'Window (hours)',
    radius_km: 'Radius (km)',
    date: 'Date',
    locale: 'Locale'
  };

  var state = {
    config: loadConfig(),
    source: 'v3',
    rangeDays: 7,
    start: null,
    end: null,
    filters: {},
    filterLabels: {},
    page: 1,
    pageSize: 50,
    meta: {},
    panelSort: {},
    adsSort: { key: 'impressions', dir: -1 },
    lastOverview: null,
    lastInsights: null
  };

  var els = {};
  var chart = null;

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    cache();
    bind();
    syncRangeInputs();
    els.footerApi.textContent = state.config.apiBase;
    if (!state.config.authKey) {
      openSettings();
    }
    refresh();
  }

  function cache() {
    els.tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'));
    els.rangePresets = document.getElementById('rangePresets');
    els.startDate = document.getElementById('startDate');
    els.endDate = document.getElementById('endDate');
    els.filterBar = document.getElementById('filterBar');
    els.activeFilters = document.getElementById('activeFilters');
    els.refreshBtn = document.getElementById('refreshBtn');
    els.metricCards = document.getElementById('metricCards');
    els.seriesTitle = document.getElementById('seriesTitle');
    els.seriesInterval = document.getElementById('seriesInterval');
    els.seriesChart = document.getElementById('seriesChart');
    els.breakdownGrid = document.getElementById('breakdownGrid');
    els.insightsGrid = document.getElementById('insightsGrid');
    els.insightsTitle = document.getElementById('insightsTitle');
    els.eventsCard = document.getElementById('eventsCard');
    els.eventsTable = document.getElementById('eventsTable');
    els.adsTableCard = document.getElementById('adsTableCard');
    els.adsTable = document.getElementById('adsTable');
    els.adsTableCaption = document.getElementById('adsTableCaption');
    els.pageLabel = document.getElementById('pageLabel');
    els.prevPage = document.getElementById('prevPage');
    els.nextPage = document.getElementById('nextPage');
    els.errorBanner = document.getElementById('errorBanner');
    els.connectionDot = document.getElementById('connectionDot');
    els.footerApi = document.getElementById('footerApi');
    // Settings
    els.settingsBtn = document.getElementById('settingsBtn');
    els.settingsModal = document.getElementById('settingsModal');
    els.settingsClose = document.getElementById('settingsClose');
    els.settingsSave = document.getElementById('settingsSave');
    els.apiBase = document.getElementById('apiBase');
    els.authKey = document.getElementById('authKey');
    els.islandKey = document.getElementById('islandKey');
  }

  function bind() {
    els.tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        if (tab.classList.contains('is-active')) return;
        els.tabs.forEach(function (t) { t.classList.remove('is-active'); });
        tab.classList.add('is-active');
        state.source = tab.getAttribute('data-source');
        state.filters = {};
        state.filterLabels = {};
        state.page = 1;
        state.panelSort = {};
        refresh();
      });
    });

    els.rangePresets.addEventListener('click', function (e) {
      var btn = e.target.closest('.chip');
      if (!btn) return;
      Array.prototype.forEach.call(els.rangePresets.children, function (c) { c.classList.remove('is-active'); });
      btn.classList.add('is-active');
      state.rangeDays = parseInt(btn.getAttribute('data-range'), 10);
      state.start = null;
      state.end = null;
      state.page = 1;
      syncRangeInputs();
      refresh();
    });

    function onDateChange() {
      state.start = els.startDate.value || null;
      state.end = els.endDate.value || null;
      if (state.start || state.end) {
        Array.prototype.forEach.call(els.rangePresets.children, function (c) { c.classList.remove('is-active'); });
      }
      state.page = 1;
      refresh();
    }
    els.startDate.addEventListener('change', onDateChange);
    els.endDate.addEventListener('change', onDateChange);

    els.refreshBtn.addEventListener('click', refresh);
    els.prevPage.addEventListener('click', function () { if (state.page > 1) { state.page--; loadEvents(); } });
    els.nextPage.addEventListener('click', function () { state.page++; loadEvents(); });

    // Click-to-filter: breakdown/insight rows carry a data-filters payload.
    [els.breakdownGrid, els.insightsGrid].forEach(function (grid) {
      grid.addEventListener('click', function (e) {
        var sortBtn = e.target.closest('[data-panel-sort]');
        if (sortBtn) { togglePanelSort(sortBtn.getAttribute('data-panel-sort')); return; }
        var row = e.target.closest('.bar-row[data-filters]');
        if (!row) return;
        applyRowFilters(row);
      });
    });

    els.activeFilters.addEventListener('click', function (e) {
      var clear = e.target.closest('[data-clear-all]');
      if (clear) {
        state.filters = {};
        state.filterLabels = {};
        state.page = 1;
        refresh();
        return;
      }
      var chip = e.target.closest('[data-remove-filter]');
      if (!chip) return;
      var param = chip.getAttribute('data-remove-filter');
      delete state.filters[param];
      delete state.filterLabels[param];
      state.page = 1;
      refresh();
    });

    els.adsTable.addEventListener('click', function (e) {
      var th = e.target.closest('th[data-sort-key]');
      if (!th) return;
      var key = th.getAttribute('data-sort-key');
      if (state.adsSort.key === key) {
        state.adsSort.dir = -state.adsSort.dir;
      } else {
        state.adsSort = { key: key, dir: -1 };
      }
      if (state.lastOverview) renderAdsTable(state.lastOverview);
    });

    els.settingsBtn.addEventListener('click', openSettings);
    els.settingsClose.addEventListener('click', closeSettings);
    els.settingsSave.addEventListener('click', saveSettings);
    els.settingsModal.addEventListener('click', function (e) {
      if (e.target === els.settingsModal) closeSettings();
    });
  }

  function applyRowFilters(row) {
    var filters;
    try { filters = JSON.parse(row.getAttribute('data-filters')); } catch (e) { return; }
    Object.keys(filters).forEach(function (param) {
      state.filters[param] = filters[param];
      state.filterLabels[param] = String(filters[param]);
    });
    state.page = 1;
    refresh();
  }

  function togglePanelSort(panelId) {
    state.panelSort[panelId] = state.panelSort[panelId] === 'alpha' ? 'count' : 'alpha';
    if (state.lastOverview) renderBreakdowns(SOURCES[state.source], state.lastOverview.breakdowns || {});
    if (state.lastInsights) renderInsights(state.lastInsights);
  }

  /* --- config --- */
  function loadConfig() {
    var cfg = {};
    try { cfg = JSON.parse(localStorage.getItem(CONFIG_KEY)) || {}; } catch (e) { cfg = {}; }
    return {
      apiBase: (cfg.apiBase || DEFAULTS.apiBase).replace(/\/+$/, ''),
      authKey: cfg.authKey || DEFAULTS.authKey,
      island: cfg.island || DEFAULTS.island
    };
  }

  function openSettings() {
    els.apiBase.value = state.config.apiBase;
    els.authKey.value = state.config.authKey;
    els.islandKey.value = state.config.island;
    els.settingsModal.hidden = false;
  }
  function closeSettings() { els.settingsModal.hidden = true; }
  function saveSettings() {
    state.config = {
      apiBase: (els.apiBase.value || DEFAULTS.apiBase).replace(/\/+$/, ''),
      authKey: els.authKey.value || '',
      island: els.islandKey.value || DEFAULTS.island
    };
    localStorage.setItem(CONFIG_KEY, JSON.stringify(state.config));
    els.footerApi.textContent = state.config.apiBase;
    closeSettings();
    refresh();
  }

  /* --- range helpers --- */
  function syncRangeInputs() {
    var range = computeRange();
    els.startDate.value = range.start;
    els.endDate.value = range.end;
  }
  function computeRange() {
    if (state.start || state.end) {
      var endC = state.end || isoDate(new Date());
      var startC = state.start || endC;
      return { start: startC, end: endC };
    }
    var end = new Date();
    var start = new Date();
    start.setDate(end.getDate() - (state.rangeDays - 1));
    return { start: isoDate(start), end: isoDate(end) };
  }
  function isoDate(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }

  /* --- API --- */
  function api(path, params) {
    var cfg = state.config;
    var url = cfg.apiBase + path;
    var qs = [];
    Object.keys(params || {}).forEach(function (k) {
      if (params[k] !== null && params[k] !== undefined && params[k] !== '') {
        qs.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
      }
    });
    if (qs.length) url += '?' + qs.join('&');
    var headers = { 'X-Auth-Key': cfg.authKey };
    if (SOURCES[state.source].needsIsland) headers['X-Island'] = cfg.island;
    return fetch(url, { headers: headers }).then(function (res) {
      if (res.status === 401) throw new Error('Unauthorized — check the AUTH key in Settings.');
      if (!res.ok) throw new Error('API error ' + res.status);
      return res.json();
    });
  }

  function commonParams() {
    var range = computeRange();
    var params = { start: range.start, end: range.end };
    Object.keys(state.filters).forEach(function (k) {
      if (state.filters[k]) params[k] = state.filters[k];
    });
    return params;
  }

  /* --- orchestration --- */
  function refresh() {
    var src = SOURCES[state.source];
    setError('');
    setLoading(true);
    renderActiveFilters();

    els.eventsCard.hidden = !src.events;
    els.adsTableCard.hidden = !src.adsTable;

    loadMeta(src);
    loadInsights(src);

    var params = commonParams();
    if (src.hasCompare) params.compare = 1;

    var jobs = [api(src.overview, params)];
    if (src.events) jobs.push(loadEvents());
    Promise.all(jobs).then(function (results) {
      setConn('ok');
      state.lastOverview = results[0];
      renderOverview(src, results[0]);
      if (src.adsTable) renderAdsTable(results[0]);
    }).catch(function (err) {
      setConn('err');
      setError(err.message || String(err));
    }).finally(function () {
      setLoading(false);
    });
  }

  function setLoading(on) {
    ['metricCards', 'breakdownGrid', 'insightsGrid'].forEach(function (id) {
      els[id].classList.toggle('is-loading', on);
    });
  }

  function loadInsights(src) {
    if (!src.properties) {
      state.lastInsights = null;
      els.insightsGrid.innerHTML = '';
      els.insightsTitle.hidden = true;
      return;
    }
    api(src.properties, commonParams()).then(function (data) {
      state.lastInsights = data;
      renderInsights(data);
    }).catch(function () {
      els.insightsGrid.innerHTML = '';
      els.insightsTitle.hidden = true;
    });
  }

  function loadMeta(src) {
    if (!src.meta) {
      els.filterBar.innerHTML = '';
      return;
    }
    api(src.meta, {}).then(function (meta) {
      state.meta = meta;
      renderFilters(src, meta);
    }).catch(function () { /* filters are optional */ });
  }

  function loadEvents() {
    var src = SOURCES[state.source];
    if (!src.events) return Promise.resolve(null);
    var params = commonParams();
    params.page = state.page;
    params.page_size = state.pageSize;
    return api(src.events, params).then(function (data) {
      renderTable(src, data);
      return data;
    });
  }

  /* --- rendering --- */
  function renderOverview(src, data) {
    var totals = data.totals || {};
    var prevTotals = (data.previous && data.previous.totals) || null;
    els.metricCards.innerHTML = src.metrics.map(function (m) {
      var value = totals[m.key] || 0;
      var display = m.percent ? formatPercent(value) : fmt(value);
      var deltaHtml = '';
      if (m.delta && prevTotals) {
        deltaHtml = deltaBadge(value, prevTotals[m.key] || 0);
      }
      return '<div class="metric"><div class="metric__label">' + esc(m.label) +
        '</div><div class="metric__value">' + display + '</div>' + deltaHtml + '</div>';
    }).join('') + extraMetric(src, data);

    renderSeries(src, data);
    renderBreakdowns(src, data.breakdowns || {});
    var intervalText = data.range ? ('per ' + data.range.interval) : '';
    if (data.previous) intervalText += ' · dashed = previous period';
    els.seriesInterval.textContent = intervalText;
  }

  function deltaBadge(current, previous) {
    if (!previous) {
      return '<div class="metric__delta metric__delta--flat">— vs previous period</div>';
    }
    var pct = (current - previous) / previous;
    var cls = pct > 0.001 ? 'up' : (pct < -0.001 ? 'down' : 'flat');
    var arrow = cls === 'up' ? '▲' : (cls === 'down' ? '▼' : '•');
    return '<div class="metric__delta metric__delta--' + cls + '">' + arrow + ' ' +
      Math.abs(pct * 100).toFixed(1) + '% vs previous period</div>';
  }

  function extraMetric(src, data) {
    var n = (data.series || []).length;
    if (!n) return '';
    var primary = src.metrics[0];
    if (primary.percent) return '';
    var total = (data.totals && data.totals[primary.key]) || 0;
    var avg = Math.round(total / n);
    return '<div class="metric"><div class="metric__label">Avg / ' +
      (data.range ? data.range.interval : 'bucket') + '</div><div class="metric__value">' +
      fmt(avg) + '</div></div>';
  }

  function renderSeries(src, data) {
    var series = data.series || [];
    var interval = data.range ? data.range.interval : 'day';
    var labels = series.map(function (row) { return labelFor(row.bucket, interval); });
    var single = src.series.length === 1;
    var datasets = src.series.map(function (s, i) {
      return {
        label: s.label,
        data: series.map(function (row) { return row[s.key] || 0; }),
        borderColor: s.color,
        backgroundColor: single || i === 0 ? hexAlpha(s.color, 0.12) : 'transparent',
        fill: single || i === 0,
        tension: 0.25,
        pointRadius: 0,
        pointHitRadius: 8,
        borderWidth: 2
      };
    });

    // Previous-period overlay: primary series only, aligned by bucket index.
    var prevSeries = (data.previous && data.previous.series) || null;
    if (prevSeries && prevSeries.length) {
      var primaryKey = src.series[0].key;
      var prevData = [];
      for (var i = 0; i < labels.length; i++) {
        prevData.push(prevSeries[i] ? (prevSeries[i][primaryKey] || 0) : null);
      }
      datasets.push({
        label: 'Previous period',
        data: prevData,
        borderColor: COLORS.gray,
        backgroundColor: 'transparent',
        borderDash: [5, 4],
        fill: false,
        tension: 0.25,
        pointRadius: 0,
        pointHitRadius: 8,
        borderWidth: 1.5
      });
    }

    if (chart) chart.destroy();
    chart = new Chart(els.seriesChart.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: datasets.length > 1, position: 'bottom' } },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#eef0f2' } }
        }
      }
    });
  }

  function hexAlpha(hex, alpha) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
  }

  function renderBreakdowns(src, breakdowns) {
    els.breakdownGrid.innerHTML = src.breakdowns.map(function (b) {
      return panelHtml(b.title, breakdowns[b.key] || [], {
        panelId: 'bd:' + b.key,
        filterParam: b.filterParam,
        filterParams: b.filterParams
      });
    }).join('');
  }

  function renderInsights(data) {
    var panels = [];
    if (data.routes && data.routes.length) {
      panels.push(panelHtml('Top routes (origin → destination)', data.routes, {
        panelId: 'ins:routes',
        filterParams: { origin: 'prop.origin', destination: 'prop.destination' }
      }));
    }
    var breakdowns = data.breakdowns || {};
    (data.keys || []).forEach(function (key) {
      panels.push(panelHtml(propLabel(key), breakdowns[key] || [], {
        panelId: 'ins:' + key,
        filterParam: 'prop.' + key
      }));
    });
    els.insightsGrid.innerHTML = panels.join('');
    els.insightsTitle.hidden = panels.length === 0;
  }

  function panelHtml(title, rows, opts) {
    opts = opts || {};
    var sortMode = state.panelSort[opts.panelId] || 'count';
    var sorted = rows.slice();
    if (sortMode === 'alpha') {
      sorted.sort(function (a, b) { return String(a.key).localeCompare(String(b.key)); });
    }
    var clickable = !!(opts.filterParam || opts.filterParams);
    var max = rows.reduce(function (m, r) { return Math.max(m, r.count); }, 0) || 1;
    var body = sorted.length ? sorted.map(function (r) {
      var pct = Math.round((r.count / max) * 100);
      var filters = rowFilters(r, opts);
      var attrs = filters ? ' data-filters="' + esc(JSON.stringify(filters)) + '" role="button" tabindex="0"' : '';
      var cls = 'bar-row' + (filters ? ' bar-row--clickable' : '');
      return '<div class="' + cls + '"' + attrs + '><span class="bar-row__fill" style="width:' + pct + '%"></span>' +
        '<span class="bar-row__key" title="' + esc(r.key) + '">' + esc(r.key || '—') + '</span>' +
        '<span class="bar-row__count">' + fmt(r.count) + '</span></div>';
    }).join('') : '<div class="panel__empty">No data in range.</div>';
    var sortBtn = sorted.length > 1
      ? '<button class="panel__sort" type="button" data-panel-sort="' + esc(opts.panelId || title) + '" ' +
        'title="Toggle sort">' + (sortMode === 'alpha' ? 'A–Z' : '#↓') + '</button>'
      : '';
    var hint = clickable ? '<span class="panel__hint">click to filter</span>' : '';
    return '<div class="panel"><h3>' + esc(title) + hint + sortBtn + '</h3><div class="panel__body">' + body + '</div></div>';
  }

  function rowFilters(row, opts) {
    if (opts.filterParams) {
      // Multi-param rows (routes): map each row field to its filter param.
      var filters = {};
      var ok = false;
      Object.keys(opts.filterParams).forEach(function (field) {
        if (row[field] !== undefined && row[field] !== null && row[field] !== '') {
          filters[opts.filterParams[field]] = row[field];
          ok = true;
        }
      });
      return ok ? filters : null;
    }
    if (opts.filterParam && row.key !== undefined && row.key !== null && row.key !== '') {
      var single = {};
      single[opts.filterParam] = row.key;
      return single;
    }
    return null;
  }

  function renderActiveFilters() {
    var params = Object.keys(state.filters).filter(function (k) { return state.filters[k]; });
    if (!params.length) {
      els.activeFilters.hidden = true;
      els.activeFilters.innerHTML = '';
      return;
    }
    var chips = params.map(function (param) {
      var label = state.filterLabels[param] || state.filters[param];
      var name = param.indexOf('prop.') === 0 ? param.slice(5) : param;
      return '<button class="chip chip--filter" type="button" data-remove-filter="' + esc(param) + '" ' +
        'title="Remove filter"><strong>' + esc(name) + ':</strong> ' + esc(label) + ' <span aria-hidden="true">×</span></button>';
    });
    chips.push('<button class="chip chip--clear" type="button" data-clear-all="1">Clear all</button>');
    els.activeFilters.innerHTML = chips.join('');
    els.activeFilters.hidden = false;
  }

  function renderAdsTable(data) {
    var rows = (data.ads || []).slice();
    var sort = state.adsSort;
    rows.sort(function (a, b) {
      var av = a[sort.key], bv = b[sort.key];
      if (typeof av === 'string' || typeof bv === 'string') {
        return String(av || '').localeCompare(String(bv || '')) * sort.dir;
      }
      return ((av || 0) - (bv || 0)) * sort.dir;
    });

    var thead = '<tr>' + ADS_COLUMNS.map(function (c) {
      var indicator = sort.key === c.key ? (sort.dir < 0 ? ' ▼' : ' ▲') : '';
      return '<th class="sortable" data-sort-key="' + esc(c.key) + '">' + esc(c.label) + indicator + '</th>';
    }).join('') + '</tr>';
    els.adsTable.querySelector('thead').innerHTML = thead;

    var body = rows.length ? rows.map(function (row) {
      return '<tr>' + ADS_COLUMNS.map(function (c) {
        var val = row[c.key];
        if (c.percent) val = formatPercent(val);
        else if (!c.text) val = fmt(val || 0);
        return '<td>' + esc(val == null || val === '' ? '—' : val) + '</td>';
      }).join('') + '</tr>';
    }).join('') : '<tr><td colspan="' + ADS_COLUMNS.length + '" class="panel__empty">No ads found.</td></tr>';
    els.adsTable.querySelector('tbody').innerHTML = body;

    els.adsTableCaption.textContent = data.first_event
      ? 'Range metrics tracked since ' + formatTime(data.first_event)
      : 'No timed ad events yet — lifetime counters only.';
  }

  function propLabel(key) {
    if (PROP_LABELS[key]) return PROP_LABELS[key];
    return key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
  }

  function renderFilters(src, meta) {
    var html = src.filters.map(function (f) {
      var opts = (meta[f.metaKey] || []).map(function (v) {
        var sel = state.filters[f.param] === v ? ' selected' : '';
        return '<option value="' + esc(v) + '"' + sel + '>' + esc(v) + '</option>';
      }).join('');
      return '<select data-param="' + f.param + '"><option value="">' + esc(f.label) + ': all</option>' + opts + '</select>';
    }).join('');
    els.filterBar.innerHTML = html;
    Array.prototype.forEach.call(els.filterBar.querySelectorAll('select'), function (sel) {
      sel.addEventListener('change', function () {
        var param = sel.getAttribute('data-param');
        if (sel.value) {
          state.filters[param] = sel.value;
          state.filterLabels[param] = sel.value;
        } else {
          delete state.filters[param];
          delete state.filterLabels[param];
        }
        state.page = 1;
        refresh();
      });
    });
  }

  function renderTable(src, data) {
    var thead = '<tr>' + src.columns.map(function (c) { return '<th>' + esc(c.label) + '</th>'; }).join('') + '</tr>';
    els.eventsTable.querySelector('thead').innerHTML = thead;
    var rows = data.results || [];
    var body = rows.length ? rows.map(function (row) {
      return '<tr>' + src.columns.map(function (c) {
        var val = row[c.key];
        if (c.time) val = formatTime(val);
        else if (c.json) return '<td class="props"><code>' + esc(JSON.stringify(val || {})) + '</code></td>';
        return '<td>' + esc(val == null || val === '' ? '—' : val) + '</td>';
      }).join('') + '</tr>';
    }).join('') : '<tr><td colspan="' + src.columns.length + '" class="panel__empty">No events in range.</td></tr>';
    els.eventsTable.querySelector('tbody').innerHTML = body;

    var totalPages = data.total_pages || 1;
    els.pageLabel.textContent = 'Page ' + (data.page || 1) + ' / ' + totalPages + ' · ' + fmt(data.count || 0) + ' rows';
    els.prevPage.disabled = (data.page || 1) <= 1;
    els.nextPage.disabled = (data.page || 1) >= totalPages;
  }

  /* --- formatting --- */
  function labelFor(iso, interval) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    if (interval === 'hour') return pad(d.getHours()) + ':00';
    if (interval === 'month') return d.toLocaleString(undefined, { month: 'short', year: '2-digit' });
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric' });
  }
  function formatTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  }
  function fmt(n) { return (n || 0).toLocaleString(); }
  function formatPercent(v) { return ((v || 0) * 100).toFixed(2) + '%'; }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function setError(msg) {
    els.errorBanner.hidden = !msg;
    els.errorBanner.textContent = msg || '';
  }
  function setConn(s) {
    els.connectionDot.className = 'conn conn--' + (s === 'ok' ? 'ok' : 'err');
  }
})();
