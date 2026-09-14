(function () {
  'use strict';

  var toggle = document.getElementById('guide-menu-toggle');
  var backdrop = document.getElementById('guide-backdrop');
  function setNav(open) {
    document.body.classList.toggle('guide-nav-open', !!open);
    if (backdrop) backdrop.hidden = !open;
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  if (toggle) toggle.addEventListener('click', function () {
    setNav(!document.body.classList.contains('guide-nav-open'));
  });
  if (backdrop) backdrop.addEventListener('click', function () { setNav(false); });

  /* Panel deep-links: on same host use path; on public docs site keep path as hint */
  document.querySelectorAll('[data-panel-path]').forEach(function (el) {
    var path = el.getAttribute('data-panel-path') || '';
    if (!path) return;
    var onPanel = /\/help(\/|$)/.test(location.pathname) && location.port === '9000';
    // If docs are served under the bot panel (/help), make chip a real in-app link.
    if (location.pathname.indexOf('/help') === 0 || location.pathname.indexOf('/static/guide') === 0) {
      el.setAttribute('href', path);
      el.addEventListener('click', function (e) {
        // allow normal navigation inside panel
      });
    } else {
      el.setAttribute('title', 'این مسیر را در وب‌پنل خودتان باز کنید');
      el.addEventListener('click', function (e) {
        e.preventDefault();
        try {
          navigator.clipboard.writeText(path);
          el.textContent = 'کپی شد: ' + path;
          setTimeout(function () { el.textContent = path; }, 1600);
        } catch (err) {
          window.prompt('مسیر صفحه در وب‌پنل:', path);
        }
      });
    }
  });

  var input = document.getElementById('guide-search-input');
  var panel = document.getElementById('guide-search-panel');
  if (!input || !panel) return;

  var indexPromise = null;
  function loadIndex() {
    if (!indexPromise) {
      var base = document.querySelector('script[src*="guide.js"]');
      var root = '';
      if (base && base.getAttribute('src')) {
        root = base.getAttribute('src').replace(/guide\.js.*$/, '');
      }
      indexPromise = fetch(root + 'search-index.json', { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .catch(function () { return []; });
    }
    return indexPromise;
  }

  function normalize(s) {
    return String(s || '')
      .toLowerCase()
      .replace(/ي/g, 'ی')
      .replace(/ك/g, 'ک')
      .replace(/[\u064B-\u065F]/g, '')
      .trim();
  }

  function scoreItem(q, item) {
    var nq = normalize(q);
    if (!nq) return 0;
    var title = normalize(item.title);
    var summary = normalize(item.summary);
    var body = normalize(item.body);
    var aliases = normalize((item.aliases || []).join(' '));
    var s = 0;
    if (title === nq) s += 100;
    if (title.indexOf(nq) === 0) s += 80;
    if (title.indexOf(nq) >= 0) s += 50;
    if (aliases.indexOf(nq) >= 0) s += 45;
    if (summary.indexOf(nq) >= 0) s += 25;
    nq.split(/\s+/).forEach(function (part) {
      if (part.length < 2) return;
      if (title.indexOf(part) >= 0) s += 12;
      if (aliases.indexOf(part) >= 0) s += 10;
      if (summary.indexOf(part) >= 0) s += 6;
      if (body.indexOf(part) >= 0) s += 3;
    });
    return s;
  }

  var active = -1;
  function render(hits) {
    panel.innerHTML = '';
    if (!hits.length) {
      panel.innerHTML = '<div class="guide-search-empty">نتیجه‌ای پیدا نشد. کلمه ساده‌تری مثل «رسید» یا «پلن» را امتحان کنید.</div>';
      panel.classList.add('open');
      return;
    }
    hits.slice(0, 8).forEach(function (h, i) {
      var a = document.createElement('a');
      a.className = 'guide-search-hit' + (i === active ? ' active' : '');
      a.href = h.href;
      a.setAttribute('role', 'option');
      a.innerHTML = '<strong></strong><span></span>';
      a.querySelector('strong').textContent = h.title;
      a.querySelector('span').textContent = h.summary || '';
      panel.appendChild(a);
    });
    panel.classList.add('open');
  }

  function runSearch() {
    var q = input.value.trim();
    active = -1;
    if (!q) {
      panel.classList.remove('open');
      panel.innerHTML = '';
      return;
    }
    loadIndex().then(function (items) {
      var ranked = items
        .map(function (it) { return { it: it, s: scoreItem(q, it) }; })
        .filter(function (x) { return x.s > 0; })
        .sort(function (a, b) { return b.s - a.s; })
        .map(function (x) { return x.it; });
      render(ranked);
    });
  }

  var timer = null;
  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(runSearch, 120);
  });
  input.addEventListener('keydown', function (e) {
    var hits = panel.querySelectorAll('.guide-search-hit');
    if (e.key === 'Escape') {
      panel.classList.remove('open');
      input.blur();
      return;
    }
    if (!hits.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      active = Math.min(hits.length - 1, active + 1);
      hits.forEach(function (h, i) { h.classList.toggle('active', i === active); });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      active = Math.max(0, active - 1);
      hits.forEach(function (h, i) { h.classList.toggle('active', i === active); });
    } else if (e.key === 'Enter' && active >= 0 && hits[active]) {
      e.preventDefault();
      location.href = hits[active].href;
    }
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.guide-search')) panel.classList.remove('open');
  });
})();
