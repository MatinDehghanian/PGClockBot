/* Live figures of the bot and PasarGuard overviews: server meters, traffic rates, nodes.
   Text goes in through textContent only. The DOM is looked up on every tick, so the /pg/body
   swap and a missing card never break the poller. */
(function (root) {
  'use strict';
  var POLL_MS = 5000;
  var SAMPLES = 60;
  var SPARK_W = 300;
  var SPARK_H = 60;

  function clampPct(value) {
    if (typeof value !== 'number' || !isFinite(value)) return null;
    return Math.max(0, Math.min(100, value));
  }
  function fmtPct(value) {
    var p = clampPct(value);
    return p === null ? '—' : Math.round(p) + '٪';
  }
  function memHint(d) {
    if (d.memory_ratio_text) return d.memory_ratio_text;
    if (d.memory_used_text && d.memory_total_text) return d.memory_used_text + ' / ' + d.memory_total_text;
    return null;
  }
  function partsText(parts) {
    var p = parts || {};
    var num = p.num != null && p.num !== '' ? String(p.num) : '—';
    return p.unit ? num + ' ' + p.unit : num;
  }
  function pushSample(buffer, value, size) {
    var next = buffer.slice(-(size - 1));
    next.push(typeof value === 'number' && isFinite(value) && value > 0 ? value : 0);
    return next;
  }
  /* Polyline points of samples on a shared peak; the newest sample sits on the right edge. */
  function sparkPoints(values, peak, width, height) {
    if (!values.length || !(peak > 0)) return '';
    var step = values.length > 1 ? width / (SAMPLES - 1) : 0;
    var offset = width - step * (values.length - 1);
    return values.map(function (v, i) {
      var y = height - (Math.min(v, peak) / peak) * (height - 2) - 1;
      return (offset + step * i).toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');
  }
  function badgeClass(kind) {
    if (kind === 'ok') return 'badge connected';
    if (kind === 'warn') return 'badge connecting';
    if (kind === 'err') return 'badge danger';
    return 'badge neutral';
  }

  function setText(el, text) {
    if (el) el.textContent = text;
  }
  function applyMeter(box, pct, text, toneName, hint) {
    if (!box) return;
    var p = clampPct(pct);
    box.setAttribute('data-tone', toneName || 'neutral');
    setText(box.querySelector('[data-meter-val]'), text);
    var fill = box.querySelector('.ov-fill');
    if (fill) fill.style.setProperty('--p', String(p === null ? 0 : p));
    var track = box.querySelector('[role="meter"]');
    if (track) track.setAttribute('aria-valuenow', String(p === null ? 0 : Math.round(p)));
    if (hint) setText(box.querySelector('[data-meter-hint]'), hint);
  }
  function applyServer(card, d) {
    if (!card) return;
    applyMeter(card.querySelector('[data-meter="cpu"]'), d.cpu_percent, fmtPct(d.cpu_percent), d.cpu_tone,
      d.cpu_cores ? d.cpu_cores + ' هسته' : null);
    applyMeter(card.querySelector('[data-meter="mem"]'), d.memory_percent, fmtPct(d.memory_percent), d.mem_tone, memHint(d));
  }

  var series = { up: [], down: [] };
  function applyLive(card, live) {
    if (!card || !live) return;
    setText(card.querySelector('[data-live-up-num]'), live.rate_up_num || '—');
    setText(card.querySelector('[data-live-up-unit]'), live.rate_up_unit || '');
    setText(card.querySelector('[data-live-down-num]'), live.rate_down_num || '—');
    setText(card.querySelector('[data-live-down-unit]'), live.rate_down_unit || '');
    series.up = pushSample(series.up, live.rate_up, SAMPLES);
    series.down = pushSample(series.down, live.rate_down, SAMPLES);
    var peak = Math.max.apply(null, series.up.concat(series.down));
    var spark = card.querySelector('[data-live-spark]');
    if (spark) spark.classList.toggle('has-data', peak > 0);
    ['up', 'down'].forEach(function (dir) {
      var line = card.querySelector('[data-spark="' + dir + '"]');
      if (line) line.setAttribute('points', sparkPoints(series[dir], peak, SPARK_W, SPARK_H));
    });
  }
  function applyNode(row, n) {
    var st = row.querySelector('[data-node-status]');
    if (st) {
      st.textContent = n.status || '—';
      st.className = badgeClass(n.status_kind);
    }
    applyMeter(row.querySelector('[data-meter="cpu"]'), n.cpu_percent, n.cpu_text || '—', n.cpu_tone);
    applyMeter(row.querySelector('[data-meter="mem"]'), n.mem_percent, n.mem_text || '—', n.mem_tone);
    row.querySelectorAll('[data-node-f]').forEach(function (el) {
      el.textContent = partsText(n[el.getAttribute('data-node-f')]);
    });
  }
  function applyNodes(list, nodes) {
    if (!list || !Array.isArray(nodes)) return;
    var rows = {};
    list.querySelectorAll('[data-node-id]').forEach(function (row) {
      rows[row.getAttribute('data-node-id')] = row;
    });
    nodes.forEach(function (n) {
      if (n && n.id != null && rows[String(n.id)]) applyNode(rows[String(n.id)], n);
    });
  }

  function setStale(source, stale) {
    document.querySelectorAll('.ov-live').forEach(function (el) {
      el.classList.toggle('is-stale', stale);
    });
    var note = document.getElementById('ov-live-status');
    if (!stale) {
      if (note) note.remove();
      return;
    }
    if (note || !source || !source.parentNode) return;
    note = document.createElement('div');
    note.id = 'ov-live-status';
    note.className = 'flash warn';
    note.setAttribute('role', 'status');
    note.textContent = 'آمار زنده به‌روز نشد؛ آخرین اطلاعات نمایش داده می‌شود و دوباره تلاش می‌کنیم.';
    source.parentNode.insertBefore(note, source);
  }

  var pending = false;
  function source() {
    return document.querySelector('[data-pg-live][data-metrics-url]')
      || document.querySelector('[data-server-meters][data-metrics-url]');
  }
  function tick() {
    var src = source();
    if (document.hidden || pending || !src || !root.PGClockPanelWidgetRequest) return;
    var url = src.getAttribute('data-metrics-url');
    pending = true;
    root.PGClockPanelWidgetRequest.fetchJson(url + (url.indexOf('?') >= 0 ? '&' : '?') + '_=' + Date.now(), {
      cache: 'no-store',
      credentials: 'same-origin'
    }).then(function (d) {
      setStale(src, false);
      applyServer(document.querySelector('[data-server-meters]'), d || {});
      applyLive(document.querySelector('[data-pg-live]'), d && d.live);
      applyNodes(document.querySelector('[data-node-list]'), d && d.nodes);
    }).catch(function () {
      setStale(src, true);
    }).finally(function () {
      pending = false;
    });
  }

  var api = { clampPct: clampPct, fmtPct: fmtPct, memHint: memHint, partsText: partsText,
    pushSample: pushSample, sparkPoints: sparkPoints, badgeClass: badgeClass, SAMPLES: SAMPLES };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }
  setInterval(tick, POLL_MS);
  setTimeout(tick, 1500);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) tick(); });
  document.addEventListener('panel-widgets-ready', tick);
})(typeof window !== 'undefined' ? window : globalThis);
