/* Service previews use text nodes and ignore replies from an earlier selection. */
(function () {
  'use strict';

  function createLoader(fetchInfo, render) {
    let sequence = 0;
    let controller;
    return async function load(url) {
      const current = ++sequence;
      if (controller) controller.abort();
      controller = new AbortController();
      const requestController = controller;
      const timer = setTimeout(() => requestController.abort(), 10000);
      render({ loading: true });
      try {
        const response = await fetchInfo(url, {
          credentials: 'same-origin',
          headers: { Accept: 'application/json' },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error('preview unavailable');
        const data = await response.json();
        if (current === sequence) render({ data });
      } catch (error) {
        if (current === sequence) {
          render({ error: 'دریافت پیش‌نمایش ناموفق بود. دوباره تلاش کنید.' });
        }
      } finally {
        clearTimeout(timer);
      }
    };
  }

  function renderPreview(modal, state) {
    modal.querySelector('[data-preview-loading]').hidden = !state.loading;
    modal.querySelector('[data-preview-content]').hidden = !state.data;
    const warning = state.error || (state.data && state.data.warning) || '';
    const error = modal.querySelector('[data-preview-error]');
    error.textContent = warning;
    error.hidden = !warning;
    modal.querySelector('[data-preview-retry]').disabled = !!state.loading;
    modal.setAttribute('aria-busy', state.loading ? 'true' : 'false');
    if (!state.data) return;
    modal.querySelectorAll('[data-preview-field]').forEach((field) => {
      field.textContent = state.data[field.dataset.previewField] || '—';
    });
    const status = modal.querySelector('[data-preview-field="status_title"]');
    const tone = state.data.status_tone;
    status.className = 'badge ' + (['active', 'warn', 'blocked', 'neutral'].includes(tone) ? tone : 'neutral');
  }

  function bind(document) {
    const modal = document.getElementById('modal-service-preview');
    if (!modal) return;
    let selectedUrl;
    const load = createLoader(window.fetch.bind(window), (state) => renderPreview(modal, state));
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-service-preview]');
      if (!button) return;
      selectedUrl = button.dataset.servicePreview;
      load(selectedUrl);
    });
    modal.querySelector('[data-preview-retry]').addEventListener('click', () => {
      if (selectedUrl) load(selectedUrl);
    });
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { createLoader, renderPreview, bind };
  } else {
    bind(document);
  }
})();
