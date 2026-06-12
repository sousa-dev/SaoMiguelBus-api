/* São Miguel Hub — static analytics dashboard.
 * Talks to the AUTH_KEY-protected /api/v3/analytics/reports/* endpoints.
 * No build step: plain ES2015+ for GitHub Pages. */
(function () {
  'use strict';

  var CONFIG_KEY = 'smb_analytics_config';
  var DEFAULTS = { apiBase: 'https://api.saomiguelbus.com', authKey: '', island: 'sao-miguel' };

  var SOURCES = {
    v3: {
      label: 'Hub (v3)',
      overview: '/api/v3/analytics/reports/overview',
      events: '/api/v3/analytics/reports/events',
      meta: '/api/v3/analytics/reports/meta',
      needsIsland: true,
      metrics: [
        { key: 'events', label: 'Events' },
        { key: 'sessions', label: 'Sessions' }
      ],
      series: [
        { key: 'events', label: 'Events', color: '#218732' },
        { key: 'sessions', label: 'Sessions', color: '#ffc107' }
      ],
      breakdowns: [
        { key: 'module', title: 'Modules' },
        { key: 'event_type', title: 'Event types' },
        { key: 'platform', title: 'Platforms' },
        { key: 'locale', title: 'Locales' }
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
    legacy: {
      label: 'Legacy',
      overview: '/api/v3/analytics/reports/legacy/overview',
      events: '/api/v3/analytics/reports/legacy/events',
      meta: '/api/v3/analytics/reports/legacy/meta',
      needsIsland: false,
      metrics: [
        { key: 'stats', label: 'Requests' },
        { key: 'routes', label: 'Route searches' }
      ],
      series: [{ key: 'count', label: 'Requests', color: '#218732' }],
      breakdowns: [
        { key: 'request', title: 'Request types' },
        { key: 'top_routes', title: 'Top routes' },
        { key: 'top_origins', title: 'Top origins' },
        { key: 'top_destinations', title: 'Top destinations' },
        { key: 'platform', title: 'Platforms' },
        { key: 'language', title: 'Languages' },
        { key: 'type_of_day', title: 'Day type' }
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

  var state = {
    config: loadConfig(),
    source: 'v3',
    rangeDays: 7,
    start: null,
    end: null,
    filters: {},
    page: 1,
    pageSize: 50,
    meta: {}
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
    els.refreshBtn = document.getElementById('refreshBtn');
    els.metricCards = document.getElementById('metricCards');
    els.seriesTitle = document.getElementById('seriesTitle');
    els.seriesInterval = document.getElementById('seriesInterval');
    els.seriesChart = document.getElementById('seriesChart');
    els.breakdownGrid = document.getElementById('breakdownGrid');
    els.eventsTable = document.getElementById('eventsTable');
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
        state.page = 1;
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

    els.settingsBtn.addEventListener('click', openSettings);
    els.settingsClose.addEventListener('click', closeSettings);
    els.settingsSave.addEventListener('click', saveSettings);
    els.settingsModal.addEventListener('click', function (e) {
      if (e.target === els.settingsModal) closeSettings();
    });
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
    loadMeta(src);
    Promise.all([
      api(src.overview, commonParams()),
      loadEvents()
    ]).then(function (results) {
      setConn('ok');
      renderOverview(src, results[0]);
    }).catch(function (err) {
      setConn('err');
      setError(err.message || String(err));
    });
  }

  function loadMeta(src) {
    api(src.meta, SOURCES[state.source].needsIsland ? {} : {}).then(function (meta) {
      state.meta = meta;
      renderFilters(src, meta);
    }).catch(function () { /* filters are optional */ });
  }

  function loadEvents() {
    var src = SOURCES[state.source];
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
    els.metricCards.innerHTML = src.metrics.map(function (m) {
      return '<div class="metric"><div class="metric__label">' + esc(m.label) +
        '</div><div class="metric__value">' + fmt(totals[m.key] || 0) + '</div></div>';
    }).join('') + extraMetric(src, data);

    renderSeries(src, data);
    renderBreakdowns(src, data.breakdowns || {});
    els.seriesInterval.textContent = data.range ? ('per ' + data.range.interval) : '';
  }

  function extraMetric(src, data) {
    var n = (data.series || []).length;
    if (!n) return '';
    var primary = src.metrics[0].key;
    var total = (data.totals && data.totals[primary]) || 0;
    var avg = Math.round(total / n);
    return '<div class="metric"><div class="metric__label">Avg / ' +
      (data.range ? data.range.interval : 'bucket') + '</div><div class="metric__value">' +
      fmt(avg) + '</div></div>';
  }

  function renderSeries(src, data) {
    var series = data.series || [];
    var interval = data.range ? data.range.interval : 'day';
    var labels = series.map(function (row) { return labelFor(row.bucket, interval); });
    var datasets = src.series.map(function (s) {
      return {
        label: s.label,
        data: series.map(function (row) { return row[s.key] || 0; }),
        backgroundColor: s.color,
        borderRadius: 4,
        maxBarThickness: 36
      };
    });
    if (chart) chart.destroy();
    chart = new Chart(els.seriesChart.getContext('2d'), {
      type: 'bar',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: datasets.length > 1, position: 'bottom' } },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#eef0f2' } }
        }
      }
    });
  }

  function renderBreakdowns(src, breakdowns) {
    els.breakdownGrid.innerHTML = src.breakdowns.map(function (b) {
      var rows = breakdowns[b.key] || [];
      var max = rows.reduce(function (m, r) { return Math.max(m, r.count); }, 0) || 1;
      var body = rows.length ? rows.map(function (r) {
        var pct = Math.round((r.count / max) * 100);
        return '<div class="bar-row"><span class="bar-row__fill" style="width:' + pct + '%"></span>' +
          '<span class="bar-row__key" title="' + esc(r.key) + '">' + esc(r.key || '—') + '</span>' +
          '<span class="bar-row__count">' + fmt(r.count) + '</span></div>';
      }).join('') : '<div class="panel__empty">No data in range.</div>';
      return '<div class="panel"><h3>' + esc(b.title) + '</h3><div class="panel__body">' + body + '</div></div>';
    }).join('');
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
        state.filters[sel.getAttribute('data-param')] = sel.value;
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
