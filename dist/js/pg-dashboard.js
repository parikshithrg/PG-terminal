(function initialisePGTerminalDashboard(global) {
  'use strict';

  let overviewRequest = null;

  function requestOverview(api, timeoutMs) {
    if (!overviewRequest) {
      overviewRequest = api.getJSON('/api/dashboard/overview', { timeoutMs })
        .finally(() => { overviewRequest = null; });
    }
    return overviewRequest;
  }

  async function loadOverview({
    api = global.PGTerminalApi,
    apply,
    fallback,
    timeoutMs = 90000,
  } = {}) {
    if (!api || typeof api.getJSON !== 'function') {
      throw new Error('dashboard_api_unavailable');
    }
    if (typeof apply !== 'function') {
      throw new Error('dashboard_apply_callback_required');
    }
    try {
      const payload = await requestOverview(api, timeoutMs);
      apply(payload);
      return true;
    } catch (_error) {
      if (typeof fallback === 'function') await fallback();
      return false;
    }
  }

  global.PGTerminalDashboard = Object.freeze({ loadOverview });
}(window));
