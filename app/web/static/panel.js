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
      /* Enforce on focus only — avoids getComputedStyle scan of every control on load */
      document.addEventListener('focusin', (e) => {
        const t = e.target;
        if (!t) return;
        if (t.matches && t.matches('input, select, textarea, [contenteditable="true"]')) enforce(t);
      }, true);
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
      /* Prefer «عملیات» whenever multiple action controls share a cell —
         prevents buttons stacking/overlapping (e.g. نقش + ویرایش + حذف). */
      document.querySelectorAll('.table-wrap').forEach(el => {
        el.classList.remove('force-kebab');
        let need = el.scrollWidth > el.clientWidth + 2;
        if (!need) {
          el.querySelectorAll('.row-actions-menu').forEach(menu => {
            if (need) return;
            const items = [...menu.children].filter((n) => n.nodeType === 1);
            if (items.length > 1) {
              need = true;
              return;
            }
            if (menu.querySelector('select, .ui-select')) {
              need = true;
              return;
            }
            if (menu.scrollWidth > menu.clientWidth + 2) need = true;
            else if (menu.offsetHeight > 44) need = true;
          });
        }
        el.classList.toggle('force-kebab', need);
      });
    }
    function refreshHScrollMarks(){
      document.querySelectorAll('.table-wrap, .section-tabs').forEach(markScrollable);
    }
    function refreshHScroll(){
      if (!document.querySelector('.table-wrap, .section-tabs')) return;
      refreshForceKebab();
      refreshHScrollMarks();
    }
    const _hScrollRoots = document.querySelectorAll('.table-wrap, .section-tabs');
    if (_hScrollRoots.length) {
      refreshHScroll();
      window.addEventListener('resize', refreshHScroll);
      if (window.ResizeObserver) {
        const ro = new ResizeObserver(refreshHScrollMarks);
        _hScrollRoots.forEach(el => ro.observe(el));
      }
    }

    /* Keep active settings/section tab visible in horizontal mobile scroll */
    function scrollActiveTabIntoView(){
      const tabs = document.querySelectorAll('.section-tabs');
      if (!tabs.length) return;
      tabs.forEach(nav => {
        const active = nav.querySelector('a.active');
        if (!active || typeof active.scrollIntoView !== 'function') return;
        try {
          active.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'instant' in window ? 'instant' : 'auto' });
        } catch (_) {
          try { active.scrollIntoView(false); } catch (e) {}
        }
      });
    }
    if (document.querySelector('.section-tabs')) {
      scrollActiveTabIntoView();
      requestAnimationFrame(scrollActiveTabIntoView);
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
        el.querySelectorAll('.row-actions-toggle').forEach(btn => {
          btn.setAttribute('aria-expanded', 'false');
        });
      });
      document.querySelectorAll('.row-actions-menu.is-ported').forEach(restoreRowMenu);
    }
    function placeRowMenu(wrap){
      if (!wrap) return;
      /* Prefer the visible toggle (label on desktop force-kebab, icon on mobile) */
      let anchor = null;
      wrap.querySelectorAll('.row-actions-toggle').forEach(t => {
        const st = window.getComputedStyle(t);
        if (st.display !== 'none' && st.visibility !== 'hidden') anchor = t;
      });
      if (!anchor) anchor = wrap.querySelector('.row-actions-toggle');
      let menu = wrap.querySelector('.row-actions-menu');
      if (!menu && wrap.dataset.raId) {
        menu = document.querySelector('.row-actions-menu.is-ported[data-owner="' + wrap.dataset.raId + '"]');
      }
      if (!anchor || !menu) return;
      if (!wrap.dataset.raId) {
        wrap.dataset.raId = 'ra-' + Math.random().toString(36).slice(2, 9);
      }
      if (!rowMenuHomes.has(menu)) {
        rowMenuHomes.set(menu, { parent: menu.parentNode, next: menu.nextSibling });
      }
      menu.dataset.owner = wrap.dataset.raId;
      document.body.appendChild(menu);
      menu.classList.add('is-ported');

      const gap = 8; /* --space-1 */
      const pad = 8;
      const rect = anchor.getBoundingClientRect();
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
      /* Prefer down when it fits; flip up only when below is short */
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

    /* Custom selects — replace native Windows/macOS popups with panel-styled menus */
    function closeUiSelects(except){
      document.querySelectorAll('.ui-select.open').forEach(wrap => {
        if (except && wrap === except) return;
        wrap.classList.remove('open');
        wrap.classList.remove('drop-up');
        const btn = wrap.querySelector('.ui-select-toggle');
        if (btn) btn.setAttribute('aria-expanded', 'false');
        const menu = wrap.querySelector('.ui-select-menu');
        if (menu) menu.hidden = true;
      });
    }
    function placeUiSelectMenu(wrap){
      if (!wrap) return;
      const toggle = wrap.querySelector('.ui-select-toggle');
      const menu = wrap.querySelector('.ui-select-menu');
      if (!toggle || !menu || menu.hidden) return;
      const gap = 8;
      const pad = 8;
      const rect = toggle.getBoundingClientRect();
      const mh = menu.offsetHeight || 120;
      const vh = window.innerHeight;
      const spaceBelow = vh - rect.bottom - gap - pad;
      const spaceAbove = rect.top - gap - pad;
      /* Ticket status only: always open up. Everywhere else: auto by available space. */
      let openUp;
      if (wrap.closest('.ticket-status-form, .ticket-status-actions')) {
        openUp = true;
      } else if (spaceBelow >= mh) {
        openUp = false;
      } else if (spaceAbove >= mh) {
        openUp = true;
      } else {
        openUp = spaceAbove > spaceBelow;
      }
      wrap.classList.toggle('drop-up', openUp);
    }
    function enhanceSelect(sel){
      if (!sel || sel.dataset.uiSelect === '1' || sel.multiple || sel.size > 1) return;
      if (sel.closest('.ui-select')) return;
      sel.dataset.uiSelect = '1';
      const wrap = document.createElement('div');
      wrap.className = 'ui-select' + (sel.classList.contains('select-sm') || (sel.closest('.actions') && !sel.classList.contains('select-block')) ? ' ui-select-sm' : '');
      if (sel.disabled) wrap.classList.add('is-disabled');
      sel.parentNode.insertBefore(wrap, sel);
      wrap.appendChild(sel);
      sel.classList.add('ui-select-native');
      sel.tabIndex = -1;
      sel.setAttribute('aria-hidden', 'true');

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'ui-select-toggle';
      toggle.setAttribute('aria-haspopup', 'listbox');
      toggle.setAttribute('aria-expanded', 'false');
      if (sel.disabled) toggle.disabled = true;
      const label = document.createElement('span');
      label.className = 'ui-select-label';
      toggle.appendChild(label);
      const caret = document.createElement('span');
      caret.innerHTML = '<svg class="ui-select-caret" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 6L8 3l3.5 3"/><path d="M4.5 10L8 13l3.5-3"/></svg>';
      toggle.appendChild(caret.firstChild);
      wrap.appendChild(toggle);

      const menu = document.createElement('div');
      menu.className = 'ui-select-menu';
      menu.setAttribute('role', 'listbox');
      menu.hidden = true;
      wrap.appendChild(menu);

      function syncLabel(){
        const opt = sel.options[sel.selectedIndex];
        label.textContent = opt ? opt.textContent : (sel.getAttribute('placeholder') || '—');
        menu.querySelectorAll('[role="option"]').forEach(btn => {
          btn.classList.toggle('active', btn.dataset.value === sel.value);
          btn.setAttribute('aria-selected', btn.dataset.value === sel.value ? 'true' : 'false');
        });
      }
      function rebuildOptions(){
        menu.innerHTML = '';
        Array.from(sel.options).forEach(opt => {
          if (opt.disabled && opt.value === '' && !opt.textContent.trim()) return;
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.setAttribute('role', 'option');
          btn.dataset.value = opt.value;
          btn.textContent = opt.textContent;
          if (opt.disabled) btn.disabled = true;
          if (opt.value === sel.value) {
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
          } else {
            btn.setAttribute('aria-selected', 'false');
          }
          btn.addEventListener('click', (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            if (opt.disabled) return;
            sel.value = opt.value;
            sel.dispatchEvent(new Event('input', { bubbles: true }));
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            syncLabel();
            closeUiSelects();
          });
          menu.appendChild(btn);
        });
        syncLabel();
      }
      rebuildOptions();
      toggle.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (sel.disabled) return;
        const open = wrap.classList.contains('open');
        closeUiSelects();
        /* Nested select inside kebab/عملیات must not dismiss the parent menu */
        const nestedInRowMenu = !!wrap.closest('.row-actions-menu, .row-actions');
        if (!nestedInRowMenu) {
          closeRowActions();
        }
        if (!open) {
          wrap.classList.add('open');
          toggle.setAttribute('aria-expanded', 'true');
          menu.hidden = false;
          placeUiSelectMenu(wrap);
          requestAnimationFrame(() => placeUiSelectMenu(wrap));
        }
      });
      sel.addEventListener('change', syncLabel);
      /* Always rebuild custom menu when <option> list is rewritten (e.g. plans modal
         audience → kind options). Previously only settings forms were watched, so
         dynamic selects kept showing stale labels/options. */
      const mo = new MutationObserver(() => rebuildOptions());
      mo.observe(sel, { childList: true, subtree: true, characterData: true });
    }
    function enhanceAllSelects(){
      document.querySelectorAll('select').forEach(enhanceSelect);
    }
    enhanceAllSelects();
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeUiSelects();
    });
    window.addEventListener('resize', () => closeUiSelects());
    window.addEventListener('scroll', (e) => {
      if (!document.querySelector('.ui-select.open')) return;
      if (e.target && e.target.closest && e.target.closest('.ui-select-menu')) return;
      closeUiSelects();
    }, true);

    document.addEventListener('click', (e) => {
      const toggle = e.target.closest('.row-actions-toggle');
      if (toggle) {
        e.preventDefault();
        e.stopPropagation();
        const wrap = toggle.closest('.row-actions');
        const open = wrap && wrap.classList.contains('open');
        closeRowActions();
        closeUiSelects();
        if (wrap && !open) {
          wrap.classList.add('open');
          wrap.querySelectorAll('.row-actions-toggle').forEach(btn => {
            btn.setAttribute('aria-expanded', 'true');
          });
          /* Port immediately so fixed menu is not trapped by .table-wrap overflow */
          placeRowMenu(wrap);
          requestAnimationFrame(() => placeRowMenu(wrap));
        }
        return;
      }
      const inRowMenu = !!(e.target.closest('.row-actions')
        || e.target.closest('.row-actions-menu')
        || e.target.closest('.ui-select-menu'));
      if (!inRowMenu) {
        closeRowActions();
      }
      if (!e.target.closest('.ui-select') && !e.target.closest('.ui-select-menu')) {
        closeUiSelects();
      }
    });
    window.addEventListener('resize', closeRowActions);
    window.addEventListener('scroll', (e) => {
      if (!document.querySelector('.row-actions.open')) return;
      /* ignore scrolls inside the open menu or a nested select popup */
      if (e.target && e.target.closest && (
        e.target.closest('.row-actions-menu') || e.target.closest('.ui-select-menu')
      )) return;
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
    function ensureModalPorted(el){
      if (!el) return;
      if (!modalHomes.has(el)) {
        modalHomes.set(el, { parent: el.parentNode, next: el.nextSibling });
      }
      if (el.parentNode !== document.body) {
        document.body.appendChild(el);
      }
    }
    function closeModal(el){
      if (!el) return;
      el.hidden = true;
      el.classList.remove('open');
      restoreModalHome(el);
      /* Drop sticky SSR form errors when closing (create/edit user modals) */
      el.querySelectorAll('.flash.err[id$="-form-err"]').forEach((err) => {
        err.hidden = true;
        err.textContent = '';
        delete err.dataset.keep;
      });
      if (typeof window.history !== 'undefined' && window.location.search.indexOf('form_err') >= 0) {
        try {
          const u = new URL(window.location.href);
          u.searchParams.delete('form_err');
          u.searchParams.delete('modal');
          u.searchParams.delete('uid');
          const next = u.pathname + (u.searchParams.toString() ? '?' + u.searchParams.toString() : '') + u.hash;
          window.history.replaceState({}, '', next);
        } catch (e) {}
      }
      if (!document.querySelector('.ui-modal.open')) {
        document.body.classList.remove('modal-open');
      }
    }
    function modalEscapeHref(el){
      if (!el) return null;
      const attr = el.getAttribute('data-modal-escape-href');
      if (attr) return attr;
      const nav = el.querySelector('[data-modal-close-nav]');
      if (!nav) return null;
      return nav.getAttribute('data-modal-close-nav') || '/tickets';
    }
    function openModal(id){
      const el = document.getElementById(id);
      if (!el) return;
      document.querySelectorAll('.ui-modal.open').forEach(closeModal);
      ensureModalPorted(el);
      /* Fresh open: clear prior form errors unless SSR keep flag is set */
      el.querySelectorAll('.flash.err[id$="-form-err"]').forEach((err) => {
        if (err.dataset.keep) return;
        err.hidden = true;
        err.textContent = '';
      });
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
    /* SSR-open modals (e.g. ticket view/create) — portal like button-opened modals */
    document.querySelectorAll('.ui-modal.open').forEach((el) => {
      ensureModalPorted(el);
      el.hidden = false;
      document.body.classList.add('modal-open');
      const thread = el.querySelector('.ticket-thread');
      if (thread) thread.scrollTop = thread.scrollHeight;
    });
    document.addEventListener('click', (e) => {
      const openBtn = e.target.closest('[data-modal-open]');
      if (openBtn) {
        e.preventDefault();
        openModal(openBtn.getAttribute('data-modal-open'));
        return;
      }
      const navClose = e.target.closest('[data-modal-close-nav]');
      if (navClose) {
        e.preventDefault();
        const href = navClose.getAttribute('data-modal-close-nav') || '/tickets';
        window.location.href = href;
        return;
      }
      const closer = e.target.closest('[data-modal-close]');
      if (closer) {
        closeModal(closer.closest('.ui-modal'));
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const open = document.querySelector('.ui-modal.open');
      if (!open) return;
      const href = modalEscapeHref(open);
      if (href) {
        window.location.href = href;
        return;
      }
      document.querySelectorAll('.ui-modal.open').forEach(closeModal);
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

    /* Multipart forms: progress bar inside upload boxes + success toast */
    (function initUploadProgress(){
      function ensureProgress(box){
        let barWrap = box.querySelector('.upload-box-progress');
        if (!barWrap) {
          barWrap = document.createElement('span');
          barWrap.className = 'upload-box-progress';
          barWrap.hidden = true;
          barWrap.setAttribute('aria-hidden', 'true');
          barWrap.innerHTML = '<i class="upload-box-progress-bar"></i>';
          box.appendChild(barWrap);
        }
        return barWrap;
      }
      function setProgress(box, pct){
        const wrap = ensureProgress(box);
        const bar = wrap.querySelector('.upload-box-progress-bar');
        wrap.hidden = false;
        if (bar) bar.style.width = Math.max(0, Math.min(100, pct)) + '%';
        box.classList.add('is-uploading');
      }
      function clearProgress(box){
        const wrap = box.querySelector('.upload-box-progress');
        const bar = wrap && wrap.querySelector('.upload-box-progress-bar');
        if (wrap) wrap.hidden = true;
        if (bar) bar.style.width = '0%';
        box.classList.remove('is-uploading');
      }
      function showToast(msg){
        document.querySelectorAll('.upload-toast').forEach((el) => el.remove());
        const toast = document.createElement('div');
        toast.className = 'upload-toast';
        toast.setAttribute('role', 'status');
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2800);
      }
      document.addEventListener('submit', (e) => {
        const form = e.target;
        if (!(form instanceof HTMLFormElement)) return;
        if ((form.getAttribute('enctype') || '').toLowerCase() !== 'multipart/form-data') return;
        if (form.dataset.uploadXhr === '1') return;
        const fileInputs = [...form.querySelectorAll('input[type="file"]')];
        const activeBoxes = [];
        fileInputs.forEach((inp) => {
          if (inp.files && inp.files.length) {
            const box = inp.closest('.upload-box');
            if (box) activeBoxes.push(box);
          }
        });
        if (!activeBoxes.length) return;
        e.preventDefault();
        form.dataset.uploadXhr = '1';
        activeBoxes.forEach((box) => setProgress(box, 4));
        const fd = new FormData(form);
        const submitter = e.submitter;
        if (submitter && submitter.name) {
          fd.append(submitter.name, submitter.value || '1');
        }
        const xhr = new XMLHttpRequest();
        xhr.open((form.method || 'POST').toUpperCase(), form.action || window.location.href, true);
        xhr.upload.onprogress = (ev) => {
          if (!ev.lengthComputable) return;
          const pct = Math.round((ev.loaded / ev.total) * 100);
          activeBoxes.forEach((box) => setProgress(box, pct));
        };
        xhr.onload = () => {
          activeBoxes.forEach((box) => setProgress(box, 100));
          const ok = xhr.status >= 200 && xhr.status < 400;
          if (ok) {
            showToast('آپلود با موفقیت انجام شد');
            const next = xhr.responseURL || form.action || window.location.href;
            setTimeout(() => { window.location.href = next; }, 450);
          } else {
            activeBoxes.forEach(clearProgress);
            delete form.dataset.uploadXhr;
            showToast('آپلود ناموفق بود — دوباره تلاش کنید');
          }
        };
        xhr.onerror = () => {
          activeBoxes.forEach(clearProgress);
          delete form.dataset.uploadXhr;
          showToast('خطا در ارسال فایل');
        };
        xhr.send(fd);
      }, true);
    })();

    /* Force-join channels: one row each + optional required toggle */
    (function initForceChannels(){
      function parseEntries(raw){
        const s = (raw || '').trim();
        if (!s) return [];
        if (s.charAt(0) === '[') {
          try {
            const data = JSON.parse(s);
            if (Array.isArray(data)) {
              const out = [];
              const seen = {};
              data.forEach((item) => {
                let id = '';
                let required = true;
                if (typeof item === 'string') id = item.trim();
                else if (item && typeof item === 'object') {
                  id = String(item.id || item.channel || '').trim();
                  required = item.required !== false && item.required !== 0 && item.required !== '0';
                }
                if (!id) return;
                const key = id.toLowerCase();
                if (seen[key]) return;
                seen[key] = 1;
                out.push({ id, required: !!required });
              });
              return out;
            }
          } catch (e) {}
        }
        return s.replace(/,/g, '\n').split('\n')
          .map((p) => p.trim())
          .filter(Boolean)
          .filter((ch, i, arr) => arr.findIndex((x) => x.toLowerCase() === ch.toLowerCase()) === i)
          .map((id) => ({ id, required: true }));
      }
      function rowHtml(entry){
        const id = entry && entry.id ? String(entry.id) : '';
        const req = !entry || entry.required !== false;
        return (
          '<div class="force-channel-row">' +
            '<label class="form-field force-channel-id-wrap">شناسه کانال' +
              '<input type="text" class="force-channel-id" dir="ltr" placeholder="@channel یا 123456789" value="' +
                id.replace(/"/g, '&quot;') + '" autocomplete="off" />' +
              '<small class="muted">@username یا آیدی عددی کانال/گروه</small>' +
            '</label>' +
            '<div class="force-channel-foot">' +
              '<label class="force-channel-req ui-switch-row">' +
                '<span class="ui-switch-copy"><strong>عضویت الزامی</strong></span>' +
                '<span class="ui-switch">' +
                  '<input type="checkbox" class="force-channel-required" value="1"' + (req ? ' checked' : '') + ' />' +
                  '<span class="ui-switch-track" aria-hidden="true"></span>' +
                '</span>' +
              '</label>' +
              '<div class="force-channel-actions">' +
                '<button type="button" class="btn btn-danger btn-sm force-channel-remove" aria-label="حذف کانال">حذف</button>' +
              '</div>' +
            '</div>' +
          '</div>'
        );
      }
      function addTileHtml(){
        return (
          '<button type="button" class="force-channel-add" data-force-channels-add aria-label="افزودن کانال">' +
            '<span class="force-channel-add-plus" aria-hidden="true">+</span>' +
            '<span>افزودن کانال</span>' +
          '</button>'
        );
      }
      function sync(root){
        const hidden = root.querySelector('[data-force-channels-json]');
        const list = root.querySelector('[data-force-channels-list]');
        if (!hidden || !list) return;
        const entries = [];
        const seen = {};
        list.querySelectorAll('.force-channel-row').forEach((row) => {
          const id = (row.querySelector('.force-channel-id') || {}).value || '';
          const ch = String(id).trim();
          if (!ch) return;
          const key = ch.toLowerCase();
          if (seen[key]) return;
          seen[key] = 1;
          const reqInput = row.querySelector('.force-channel-required');
          entries.push({ id: ch, required: !!(reqInput && reqInput.checked) });
        });
        hidden.value = JSON.stringify(entries);
      }
      function ensureRows(root, entries){
        const list = root.querySelector('[data-force-channels-list]');
        if (!list) return;
        const items = entries && entries.length ? entries : [];
        list.innerHTML = items.map(rowHtml).join('') + addTileHtml();
        sync(root);
      }
      document.querySelectorAll('[data-force-channels]').forEach((root) => {
        const hidden = root.querySelector('[data-force-channels-json]');
        ensureRows(root, parseEntries(hidden ? hidden.value : ''));
        root.addEventListener('click', (e) => {
          if (e.target.closest('[data-force-channels-add]')) {
            e.preventDefault();
            const list = root.querySelector('[data-force-channels-list]');
            if (!list) return;
            const add = list.querySelector('[data-force-channels-add]');
            if (add) add.insertAdjacentHTML('beforebegin', rowHtml({ id: '', required: true }));
            else list.insertAdjacentHTML('beforeend', rowHtml({ id: '', required: true }));
            const inputs = list.querySelectorAll('.force-channel-id');
            const last = inputs[inputs.length - 1];
            if (last) last.focus();
            sync(root);
            return;
          }
          const remove = e.target.closest('.force-channel-remove');
          if (remove) {
            e.preventDefault();
            const row = remove.closest('.force-channel-row');
            const list = root.querySelector('[data-force-channels-list]');
            if (row && list) {
              row.remove();
              if (!list.querySelector('[data-force-channels-add]')) {
                list.insertAdjacentHTML('beforeend', addTileHtml());
              }
              sync(root);
            }
          }
        });
        root.addEventListener('input', () => sync(root));
        root.addEventListener('change', () => sync(root));
        const form = root.closest('form');
        if (form) form.addEventListener('submit', () => sync(root));
      });
    })();

    /* Shared confirm modal — replaces native confirm()/prompt() for panel mutations */
    (function setupPanelConfirm(){
      const modal = document.getElementById('modal-confirm');
      if (!modal) return;
      const titleEl = document.getElementById('confirm-title');
      const msgEl = document.getElementById('confirm-message');
      const reasonWrap = document.getElementById('confirm-reason-wrap');
      const reasonInput = document.getElementById('confirm-reason');
      const reasonLabel = document.getElementById('confirm-reason-label');
      const submitBtn = document.getElementById('confirm-submit');
      const formEl = document.getElementById('confirm-form');
      let resolver = null;

      function finish(result){
        const r = resolver;
        resolver = null;
        if (modal.classList.contains('open')) closeModal(modal);
        if (r) r(result || { ok: false });
      }

      window.panelConfirm = function(opts){
        opts = opts || {};
        return new Promise((resolve) => {
          if (resolver) finish({ ok: false });
          resolver = resolve;
          try { closeRowActions(); } catch (_) {}
          try { closeUiSelects(); } catch (_) {}
          if (titleEl) titleEl.textContent = opts.title || 'تأیید';
          if (msgEl) msgEl.textContent = opts.message || 'ادامه می‌دهید؟';
          if (submitBtn) {
            submitBtn.textContent = opts.confirmLabel || 'تأیید';
            submitBtn.className = 'btn' + (opts.danger ? ' btn-danger' : (opts.warn ? ' btn-warn' : ''));
          }
          const needReason = !!opts.reason;
          if (reasonWrap) reasonWrap.hidden = !needReason;
          if (reasonInput) {
            reasonInput.required = needReason;
            reasonInput.value = '';
            reasonInput.minLength = opts.reasonMin || 3;
          }
          if (reasonLabel) reasonLabel.textContent = opts.reasonLabel || 'علت';
          openModal('modal-confirm');
          if (needReason && reasonInput) setTimeout(() => reasonInput.focus(), 40);
        });
      };

      if (formEl) {
        formEl.addEventListener('submit', (e) => {
          e.preventDefault();
          if (!resolver) return;
          if (reasonWrap && !reasonWrap.hidden) {
            const v = (reasonInput && reasonInput.value || '').trim();
            const min = (reasonInput && reasonInput.minLength) || 3;
            if (v.length < min) {
              if (reasonInput) reasonInput.focus();
              return;
            }
            finish({ ok: true, reason: v });
            return;
          }
          finish({ ok: true });
        });
      }

      modal.addEventListener('click', (e) => {
        if (!resolver) return;
        if (e.target.closest('[data-modal-close]') || e.target === modal.querySelector('.ui-modal-backdrop')) {
          /* closeModal runs via global handler; resolve cancel */
          const r = resolver;
          resolver = null;
          if (r) r({ ok: false });
        }
      });

      document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || !resolver) return;
        if (!modal.classList.contains('open')) return;
        finish({ ok: false });
      }, true);

      function readOpts(el, form){
        const src = el.hasAttribute('data-confirm') ? el : form;
        let needReason = src.hasAttribute('data-confirm-reason');
        const when = src.getAttribute('data-confirm-reason-when');
        const reasonName = src.getAttribute('data-confirm-reason-name') || 'reason';
        const reasonMin = parseInt(src.getAttribute('data-confirm-reason-min') || '3', 10) || 3;
        if (when && form) {
          const sel = form.querySelector('select[name="role"]');
          needReason = !!(sel && sel.value === when);
        }
        if (needReason && form) {
          const existing = form.querySelector(
            'textarea[name="' + reasonName + '"], input[name="' + reasonName + '"]'
          );
          const val = existing ? String(existing.value || '').trim() : '';
          if (val.length >= reasonMin) needReason = false;
        }
        return {
          title: src.getAttribute('data-confirm-title') || 'تأیید',
          message: src.getAttribute('data-confirm') || 'ادامه می‌دهید؟',
          danger: src.hasAttribute('data-confirm-danger'),
          warn: src.hasAttribute('data-confirm-warn'),
          reason: needReason,
          reasonMin: reasonMin,
          reasonLabel: src.getAttribute('data-confirm-reason-label') || 'علت',
          reasonName: reasonName,
          confirmLabel: src.getAttribute('data-confirm-label') || 'تأیید',
        };
      }

      function applyReason(form, opts, reason){
        if (!opts.reason || !reason) return;
        let hidden = form.querySelector(
          'input[name="' + opts.reasonName + '"], textarea[name="' + opts.reasonName + '"]'
        );
        if (!hidden) {
          hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = opts.reasonName;
          form.appendChild(hidden);
        }
        hidden.value = reason;
      }

      document.addEventListener('submit', (e) => {
        const form = e.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (form.id === 'confirm-form') return;
        if (form.dataset.confirmSkip === '1') {
          delete form.dataset.confirmSkip;
          return;
        }
        if (!form.hasAttribute('data-confirm')) return;
        e.preventDefault();
        e.stopPropagation();
        const opts = readOpts(form, form);
        window.panelConfirm(opts).then((result) => {
          if (!result || !result.ok) return;
          applyReason(form, opts, result.reason);
          form.dataset.confirmSkip = '1';
          if (typeof form.requestSubmit === 'function') form.requestSubmit();
          else form.submit();
        });
      }, true);

      document.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-confirm], input[type="submit"][data-confirm]');
        if (!btn) return;
        const form = btn.form || btn.closest('form');
        /* Form-level data-confirm is handled on submit */
        if (form && form.hasAttribute('data-confirm')) return;
        if (btn.dataset.confirmSkip === '1') {
          delete btn.dataset.confirmSkip;
          return;
        }
        e.preventDefault();
        e.stopPropagation();
        const opts = readOpts(btn, form);
        window.panelConfirm(opts).then((result) => {
          if (!result || !result.ok) return;
          if (!form) return;
          applyReason(form, opts, result.reason);
          form.dataset.confirmSkip = '1';
          btn.dataset.confirmSkip = '1';
          if (typeof form.requestSubmit === 'function') form.requestSubmit(btn);
          else {
            if (btn.name) {
              let h = document.createElement('input');
              h.type = 'hidden';
              h.name = btn.name;
              h.value = btn.value || '1';
              form.appendChild(h);
            }
            form.submit();
          }
        });
      }, true);
    })();
  })();
