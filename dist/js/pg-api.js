(function initialisePGTerminalApi(global) {
  'use strict';

  class PGTerminalApiError extends Error {
    constructor(message, details = {}) {
      super(message);
      this.name = 'PGTerminalApiError';
      this.status = details.status || 0;
      this.endpoint = details.endpoint || '';
      this.payload = details.payload || null;
    }
  }

  async function requestJSON(endpoint, options = {}) {
    const timeoutMs = Number(options.timeoutMs || 30000);
    const controller = new AbortController();
    const timer = global.setTimeout(() => controller.abort(), timeoutMs);
    const requestOptions = { cache: 'no-store', ...options, signal: controller.signal };
    delete requestOptions.timeoutMs;
    try {
      const response = await global.fetch(endpoint, requestOptions);
      let payload = null;
      try {
        payload = await response.json();
      } catch (_error) {
        throw new PGTerminalApiError('The local API returned invalid JSON.', {
          status: response.status,
          endpoint,
        });
      }
      if (!response.ok || payload?.ok === false) {
        throw new PGTerminalApiError(payload?.reason || `Request failed with status ${response.status}.`, {
          status: response.status,
          endpoint,
          payload,
        });
      }
      return payload;
    } catch (error) {
      if (error instanceof PGTerminalApiError) throw error;
      const message = error?.name === 'AbortError'
        ? `The local API did not respond within ${timeoutMs}ms.`
        : 'The local API is unavailable.';
      throw new PGTerminalApiError(message, { endpoint });
    } finally {
      global.clearTimeout(timer);
    }
  }

  global.PGTerminalApi = Object.freeze({
    Error: PGTerminalApiError,
    getJSON(endpoint, options = {}) {
      return requestJSON(endpoint, { ...options, method: 'GET' });
    },
    requestJSON,
  });
}(window));
