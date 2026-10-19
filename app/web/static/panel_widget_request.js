/* Time-bound fragment reads, including response bodies and ignored aborts. */
(function (root) {
  'use strict';
  function fetchRead(url, options, kind) {
    var controller = new AbortController();
    var timer;
    var opts = Object.assign({}, options, { signal: controller.signal });
    var deadline = new Promise(function (_, reject) {
      timer = setTimeout(function () {
        controller.abort();
        reject(new Error('widget-timeout'));
      }, 8000);
    });
    var read = Promise.resolve().then(function () { return fetch(url, opts); }).then(function (response) {
      if (response.type === 'opaqueredirect' || response.status === 401 || response.status === 403
          || response.status >= 300 && response.status < 400) {
        throw new Error('widget-auth');
      }
      if (!response.ok) throw new Error('widget-response');
      if (kind === 'json' && response.headers && response.headers.get('x-pg-read-status')) {
        throw new Error('widget-unavailable');
      }
      return kind === 'json' ? response.json() : response.text();
    });
    return Promise.race([read, deadline]).finally(function () { clearTimeout(timer); });
  }
  var api = {
    fetchBody: function (url, options) { return fetchRead(url, options, 'text'); },
    fetchJson: function (url, options) {
      return fetchRead(url, Object.assign({ redirect: 'manual' }, options), 'json');
    }
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PGClockPanelWidgetRequest = api;
})(typeof window !== 'undefined' ? window : globalThis);
