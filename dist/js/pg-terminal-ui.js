(function terminalInterfaceSystem() {
  'use strict';

  const PAGE_LABELS = {
    dashboard: 'EXECUTIVE OVERVIEW',
    'market-sentiment': 'MARKET STATE',
    fando: 'DERIVATIVES POSITIONING',
    screener: 'CROSS-SECTION SCREEN',
    'seasonality-analysis': 'SEASONAL EVIDENCE',
    'earnings-analysis': 'EARNINGS EVIDENCE',
    'portfolio-analysis': 'LONG-TERM PORTFOLIO',
    'events-calendar': 'EVENT CALENDAR',
    'stock-data-ytd': 'STOCK DATA YTD',
    'historical-regimes': 'HISTORICAL REGIMES',
    backtests: 'REGISTERED TESTS',
    'alpha-research': 'TRADE RESEARCH',
    'home-loan-tracker': 'HOME LOAN TRACKER',
    'expense-tracker': 'PERSONAL EXPENSES'
  };

  const toneFromText = (text) => {
    const value = String(text || '').toLowerCase();
    if (/failed|blocked|negative|high-risk|declin|bearish|unavailable/.test(value)) return 'negative';
    if (/partial|pending|awaiting|mixed|checking|not loaded|required/.test(value)) return 'warning';
    if (/successful|complete|ready|connected|positive|bullish|operational/.test(value)) return 'positive';
    return '';
  };

  function syncPageLabel() {
    const page = document.body.dataset.activePage || 'dashboard';
    const label = document.getElementById('terminalRibbonPage');
    if (label) label.textContent = PAGE_LABELS[page] || page.replaceAll('-', ' ').toUpperCase();
  }

  function syncEodState() {
    const target = document.getElementById('terminalRibbonEod');
    const source = document.getElementById('eodUpdateState');
    if (!target || !source) return;
    const text = source.textContent.trim() || 'READY';
    target.textContent = text.toUpperCase();
    const cell = target.closest('.terminal-ribbon-cell');
    if (cell) cell.dataset.state = toneFromText(text);
  }

  function syncFeedState() {
    const target = document.getElementById('terminalRibbonFeed');
    const source = document.getElementById('kiteLoginButton');
    if (!target || !source) return;
    const connected = source.classList.contains('kite-authenticated');
    target.textContent = connected ? 'KITE CONNECTED' : 'LOCAL STORE';
    const cell = target.closest('.terminal-ribbon-cell');
    if (cell) cell.dataset.state = connected ? 'positive' : '';
  }

  function annotateEvidenceTone() {
    document.querySelectorAll('.summary-card').forEach((card) => {
      const nextTone = toneFromText(card.textContent);
      if ((card.dataset.tone || '') !== nextTone) card.dataset.tone = nextTone;
    });
  }

  function syncDashboardPulse() {
    const setText = (target, value) => {
      if (target && target.textContent !== value) target.textContent = value;
    };
    const copy = (sourceId, targetId, fallback = '—') => {
      const source = document.getElementById(sourceId);
      const target = document.getElementById(targetId);
      setText(target, source?.textContent.trim() || fallback);
    };

    copy('dashboardStoryRegime', 'dashboardPulseRegime', 'Loading');
    const scoreText = document.getElementById('dashboardStoryScore')?.textContent || '';
    const score = Number(scoreText.match(/-?\d+(?:\.\d+)?/)?.[0]);
    const scoreTarget = document.getElementById('dashboardPulseScore');
    const ring = document.getElementById('dashboardPulseRing');
    setText(scoreTarget, Number.isFinite(score) ? score.toFixed(0) : '—');
    if (ring) {
      const normalized = Number.isFinite(score) ? Math.max(0, Math.min(100, (score + 100) / 2)) : 8;
      ring.style.setProperty('--pulse-angle', `${normalized * 3.6}deg`);
    }

    copy('marketBreadthStrongestSector', 'dashboardPulseBreadth', 'Awaiting breadth');
    const breadthValue = document.getElementById('marketBreadthStrongest20')?.textContent.trim() || '—';
    const breadthMeta = document.getElementById('dashboardPulseBreadthMeta');
    setText(breadthMeta, `20DMA participation ${breadthValue}`);

    const bullishText = document.getElementById('dashboardFnoBullish')?.textContent.trim() || '—';
    const bearishText = document.getElementById('dashboardFnoBearish')?.textContent.trim() || '—';
    const bullish = Number(bullishText.replace(/[^\d.-]/g, ''));
    const bearish = Number(bearishText.replace(/[^\d.-]/g, ''));
    const futuresTarget = document.getElementById('dashboardPulseFutures');
    setText(futuresTarget, `${bullishText} / ${bearishText}`);
    const total = (Number.isFinite(bullish) ? bullish : 0) + (Number.isFinite(bearish) ? bearish : 0);
    const bullBar = document.getElementById('dashboardPulseBullBar');
    const bearBar = document.getElementById('dashboardPulseBearBar');
    if (bullBar) bullBar.style.width = `${total ? Math.max(8, bullish / total * 100) : 18}%`;
    if (bearBar) bearBar.style.width = `${total ? Math.max(8, bearish / total * 100) : 18}%`;

    copy('dashboardEventsNextDate', 'dashboardPulseEventDate');
    const eventStatus = document.getElementById('dashboardEventsStatus')?.textContent.trim();
    const eventCount = document.getElementById('dashboardEventsSevenDay')?.textContent.trim();
    const eventTarget = document.getElementById('dashboardPulseEvents');
    setText(eventTarget, eventCount && eventCount !== '—' ? `${eventCount} within 7 days` : (eventStatus || 'Loading calendar'));
  }

  function prepareTables() {
    document.querySelectorAll('table').forEach((table) => {
      table.dataset.density = 'institutional';
      if (!table.getAttribute('role')) table.setAttribute('role', 'table');
    });
  }

  function markChartFreeInterface() {
    const chartSelectors = [
      '.dashboard-analogue-chart',
      '.price-strength-chart',
      '.flow-chart-toolbar',
      '.flow-chart-grid',
      '.flow-chart-note',
      '.expense-visual-board',
      'canvas[id$="Chart"]'
    ];
    document.querySelectorAll(chartSelectors.join(',')).forEach((node) => {
      node.dataset.chartFreeHidden = 'true';
      node.setAttribute('aria-hidden', 'true');
    });
  }

  function start() {
    document.body.classList.add('institutional-terminal');
    syncPageLabel();
    syncEodState();
    syncFeedState();
    prepareTables();
    markChartFreeInterface();
    annotateEvidenceTone();
    syncDashboardPulse();

    const bodyObserver = new MutationObserver((mutations) => {
      if (mutations.some((mutation) => mutation.type === 'attributes' && mutation.attributeName === 'data-active-page')) {
        syncPageLabel();
      }
    });
    bodyObserver.observe(document.body, { attributes: true, attributeFilter: ['data-active-page'] });

    const eodState = document.getElementById('eodUpdateState');
    if (eodState) new MutationObserver(syncEodState).observe(eodState, { childList: true, subtree: true, characterData: true });

    const kiteButton = document.getElementById('kiteLoginButton');
    if (kiteButton) new MutationObserver(syncFeedState).observe(kiteButton, { attributes: true, childList: true, subtree: true });

    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        annotateEvidenceTone();
        prepareTables();
        syncDashboardPulse();
      });
    }).observe(document.getElementById('mainContent') || document.body, { childList: true, subtree: true, characterData: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
