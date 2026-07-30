  (function(){
    const side = document.getElementById('sidebar');
    const btn = document.getElementById('menu-toggle');
    const back = document.getElementById('side-backdrop');
    function setOpen(v){
      if (!side) return;
      side.classList.toggle('open', v);
      if (back) {
        back.hidden = !v;
        back.classList.toggle('show', v);
        back.setAttribute('aria-hidden', v ? 'false' : 'true');
      }
      document.body.classList.toggle('nav-open', v);
      if (btn) btn.setAttribute('aria-expanded', v ? 'true' : 'false');
    }
    setOpen(false);
    if (btn) btn.addEventListener('click', () => setOpen(!side.classList.contains('open')));
    if (back) back.addEventListener('click', () => setOpen(false));
    side && side.querySelectorAll('a').forEach(a => a.addEventListener('click', () => setOpen(false)));

    /* Permanent no-zoom: keep focused text controls at ≥16px even if CSS regresses */
    (function () {
      const MIN = 16;
      const SKIP = new Set(['checkbox', 'radio', 'range', 'file', 'hidden', 'submit', 'button', 'reset', 'image']);
      function enforce(el) {
        if (!el || !el.style) return;
        const type = (el.getAttribute('type') || '').toLowerCase();
        if (SKIP.has(type)) return;
        const cs = window.getComputedStyle(el);
        const px = parseFloat(cs.fontSize) || 0;
        if (px > 0 && px < MIN) el.style.fontSize = MIN + 'px';
      }
      document.addEventListener('focusin', (e) => {
        const t = e.target;
        if (!t) return;
        if (t.matches && t.matches('input, select, textarea, [contenteditable="true"]')) enforce(t);
      }, true);
      document.querySelectorAll('input, select, textarea, [contenteditable="true"]').forEach(enforce);
    })();

    /* Theme: system | light | dark */
    (function(){
      const KEY = 'panel-theme';
      const root = document.documentElement;
      const wrap = document.getElementById('side-theme');
      const toggle = document.getElementById('theme-toggle');
      const menu = document.getElementById('theme-menu');
      const label = document.getElementById('theme-label');
      const ico = document.getElementById('theme-ico');
      const labels = { system: 'تم · سیستم', light: 'تم · روشن', dark: 'تم · تیره' };
      const icons = {
        system: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
        light: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
        dark: '<path d="M21 14.5A8.5 8.5 0 0 1 9.5 3 7 7 0 1 0 21 14.5z"/>'
      };
      function resolve(pref){
        if (pref === 'light' || pref === 'dark') return pref;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      function apply(pref){
        pref = pref || localStorage.getItem(KEY) || 'system';
        if (pref !== 'light' && pref !== 'dark') pref = 'system';
        localStorage.setItem(KEY, pref);
        root.setAttribute('data-theme', resolve(pref));
        if (label) label.textContent = labels[pref] || labels.system;
        if (ico) ico.innerHTML = icons[pref] || icons.system;
        if (menu) {
          menu.querySelectorAll('[data-theme-pref]').forEach(b => {
            b.classList.toggle('active', b.getAttribute('data-theme-pref') === pref);
          });
        }
        const dark = resolve(pref) === 'dark';
        document.querySelectorAll('meta[name="theme-color"]').forEach(m => {
          if (!m.media) m.setAttribute('content', dark ? '#09090b' : '#fafafa');
        });
      }
      function setMenu(open){
        if (!menu || !toggle) return;
        menu.hidden = !open;
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        wrap && wrap.classList.toggle('open', open);
      }
      apply();
      if (toggle) {
        toggle.addEventListener('click', (e) => {
          e.stopPropagation();
          setMenu(menu && menu.hidden);
        });
      }
      if (menu) {
        menu.addEventListener('click', (e) => {
          const b = e.target.closest('[data-theme-pref]');
          if (!b) return;
          e.preventDefault();
          apply(b.getAttribute('data-theme-pref'));
          setMenu(false);
        });
      }
      document.addEventListener('click', () => setMenu(false));
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') setMenu(false);
      });
      try {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
          if ((localStorage.getItem(KEY) || 'system') === 'system') apply('system');
        });
      } catch (e) {}
    })();

    function markScrollable(el){
      if (!el) return;
      const can = el.scrollWidth > el.clientWidth + 4;
      el.classList.toggle('is-scrollable', can);
    }
    function refreshForceKebab(){
      /* Measure with inline actions, then collapse when the table would overflow.
         Only called on load/resize — not from ResizeObserver (avoids toggle loops). */
      document.querySelectorAll('.table-wrap').forEach(el => {
        el.classList.remove('force-kebab');
        const need = el.scrollWidth > el.clientWidth + 2;
        el.classList.toggle('force-kebab', need);
      });
    }
    function refreshHScrollMarks(){
      document.querySelectorAll('.table-wrap, .section-tabs').forEach(markScrollable);
    }
    function refreshHScroll(){
      refreshForceKebab();
      refreshHScrollMarks();
    }
    refreshHScroll();
    window.addEventListener('resize', refreshHScroll);
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(refreshHScrollMarks);
      document.querySelectorAll('.table-wrap, .section-tabs').forEach(el => ro.observe(el));
    }

    /* Mobile row action menus (three-dot) — ported overlay, corner-aligned, inward */
    const rowMenuHomes = new WeakMap();
    function restoreRowMenu(menu){
      if (!menu) return;
      const home = rowMenuHomes.get(menu);
      menu.classList.remove('is-ported');
      menu.style.top = '';
      menu.style.left = '';
      menu.style.right = '';
      menu.style.bottom = '';
      menu.style.maxHeight = '';
      if (home && home.parent) {
        if (home.next && home.next.parentNode === home.parent) {
          home.parent.insertBefore(menu, home.next);
        } else {
          home.parent.appendChild(menu);
        }
      }
    }
    function closeRowActions(){
      document.querySelectorAll('.row-actions.open').forEach(el => {
        el.classList.remove('open');
        const btn = el.querySelector('.row-actions-toggle');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      });
      document.querySelectorAll('.row-actions-menu.is-ported').forEach(restoreRowMenu);
    }
    function placeRowMenu(wrap){
      if (!wrap) return;
      const btn = wrap.querySelector('.row-actions-toggle');
      let menu = wrap.querySelector('.row-actions-menu');
      if (!menu && wrap.dataset.raId) {
        menu = document.querySelector('.row-actions-menu.is-ported[data-owner="' + wrap.dataset.raId + '"]');
      }
      if (!btn || !menu) return;
      if (!wrap.dataset.raId) {
        wrap.dataset.raId = 'ra-' + Math.random().toString(36).slice(2, 9);
      }
      if (!rowMenuHomes.has(menu)) {
        rowMenuHomes.set(menu, { parent: menu.parentNode, next: menu.nextSibling });
      }
      menu.dataset.owner = wrap.dataset.raId;
      document.body.appendChild(menu);
      menu.classList.add('is-ported');

      const gap = 4;
      const pad = 8;
      const rect = btn.getBoundingClientRect();
      /* Full natural height — never scroll / clamp with max-height */
      menu.style.top = '0px';
      menu.style.left = '0px';
      menu.style.right = 'auto';
      menu.style.bottom = 'auto';
      menu.style.maxHeight = 'none';
      menu.style.height = 'auto';
      menu.style.overflow = 'visible';
      const mw = Math.max(menu.offsetWidth || 168, 168);
      const mh = menu.offsetHeight || 120;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      /* Inward: actions sit on the inline-end (physical left in RTL). Open toward table center (right). */
      let left = rect.left;
      if (left + mw > vw - pad) {
        left = rect.right - mw; /* flip if needed */
      }
      if (left < pad) left = pad;
      if (left + mw > vw - pad) left = Math.max(pad, vw - pad - mw);

      const spaceBelow = vh - rect.bottom - gap - pad;
      const spaceAbove = rect.top - gap - pad;
      /* Prefer the side that fits the full menu; flip up when below is short */
      let openDown;
      if (spaceBelow >= mh) openDown = true;
      else if (spaceAbove >= mh) openDown = false;
      else openDown = spaceBelow >= spaceAbove;

      let top;
      if (openDown) {
        top = rect.bottom + gap;
        if (top + mh > vh - pad) top = Math.max(pad, vh - pad - mh);
      } else {
        top = rect.top - gap - mh;
        if (top < pad) top = pad;
      }

      menu.style.top = Math.round(top) + 'px';
      menu.style.left = Math.round(left) + 'px';
      menu.style.right = 'auto';
      menu.style.bottom = 'auto';
      menu.style.maxHeight = 'none';
      menu.style.overflow = 'visible';
    }
    document.addEventListener('click', (e) => {
      const toggle = e.target.closest('.row-actions-toggle');
      if (toggle) {
        e.preventDefault();
        e.stopPropagation();
        const wrap = toggle.closest('.row-actions');
        const open = wrap && wrap.classList.contains('open');
        closeRowActions();
        if (wrap && !open) {
          wrap.classList.add('open');
          toggle.setAttribute('aria-expanded', 'true');
          requestAnimationFrame(() => placeRowMenu(wrap));
        }
        return;
      }
      if (!e.target.closest('.row-actions') && !e.target.closest('.row-actions-menu')) {
        closeRowActions();
      }
    });
    window.addEventListener('resize', closeRowActions);
    window.addEventListener('scroll', (e) => {
      if (!document.querySelector('.row-actions.open')) return;
      /* ignore scrolls inside the open menu itself */
      if (e.target && e.target.closest && e.target.closest('.row-actions-menu')) return;
      closeRowActions();
    }, true);

    /* Lightweight modals — always render on document.body above sidebar */
    const modalHomes = new WeakMap();
    function restoreModalHome(el){
      const home = modalHomes.get(el);
      if (!home || !home.parent) return;
      if (home.next && home.next.parentNode === home.parent) {
        home.parent.insertBefore(el, home.next);
      } else {
        home.parent.appendChild(el);
      }
    }
    function closeModal(el){
      if (!el) return;
      el.hidden = true;
      el.classList.remove('open');
      restoreModalHome(el);
      if (!document.querySelector('.ui-modal.open')) {
        document.body.classList.remove('modal-open');
      }
    }
    function openModal(id){
      const el = document.getElementById(id);
      if (!el) return;
      document.querySelectorAll('.ui-modal.open').forEach(closeModal);
      if (!modalHomes.has(el)) {
        modalHomes.set(el, { parent: el.parentNode, next: el.nextSibling });
      }
      document.body.appendChild(el);
      el.hidden = false;
      el.classList.add('open');
      document.body.classList.add('modal-open');
      /* Prefer a non-text control for initial focus to avoid mobile zoom side-effects */
      const panel = el.querySelector('.ui-modal-panel') || el;
      const focus =
        panel.querySelector('input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])') ||
        panel.querySelector('button:not([disabled]), [href]');
      if (focus) setTimeout(() => focus.focus(), 30);
    }
    document.addEventListener('click', (e) => {
      const openBtn = e.target.closest('[data-modal-open]');
      if (openBtn) {
        e.preventDefault();
        openModal(openBtn.getAttribute('data-modal-open'));
        return;
      }
      const closer = e.target.closest('[data-modal-close]');
      if (closer) {
        closeModal(closer.closest('.ui-modal'));
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.ui-modal.open').forEach(closeModal);
      }
    });

    /* Copy helpers (subscription links, etc.) */
    function markCopied(btn) {
      if (!btn) return;
      const prevText = btn.getAttribute('data-copy-label') || btn.textContent;
      btn.setAttribute('data-copy-label', prevText);
      btn.textContent = 'کپی شد';
      btn.classList.add('btn-ok', 'is-copied');
      setTimeout(() => {
        btn.textContent = prevText;
        btn.classList.remove('btn-ok', 'is-copied');
      }, 1200);
    }
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-copy]');
      if (!btn) return;
      e.preventDefault();
      const text = btn.getAttribute('data-copy') || '';
      if (!text) {
        alert('لینکی موجود نیست');
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => markCopied(btn)).catch(() => {
          window.prompt('کپی کنید:', text);
        });
      } else {
        window.prompt('کپی کنید:', text);
      }
    });

    /* Upload box file name preview */
    document.addEventListener('change', (e) => {
      const input = e.target;
      if (!input || input.type !== 'file') return;
      const box = input.closest('.upload-box');
      if (!box) return;
      const nameEl = box.querySelector('[data-upload-name]');
      const file = input.files && input.files[0];
      if (nameEl) nameEl.textContent = file ? file.name : 'فایلی انتخاب نشده';
      box.classList.toggle('has-file', !!file);
    });
  })();
