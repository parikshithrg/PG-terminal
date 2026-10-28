(function initialisePGTerminalCharts(global) {
  'use strict';

  const instances = new Map();
  const renderers = new Map();
  let resizeFrame = 0;

  function chartTheme() {
    const dark = document.documentElement.dataset.theme === 'dark';
    return {
      ink: dark ? '#edf5f7' : '#10273a',
      muted: dark ? '#8ba8b4' : '#667781',
      grid: dark ? '#284552' : '#cdd5d7',
      positive: dark ? '#36c58b' : '#278c6f',
      negative: dark ? '#ff617d' : '#b6203e',
      probability: dark ? '#62b4df' : '#367fa8',
      tooltip: dark ? '#071821' : '#fffdf7',
    };
  }

  function ensureInstance(element) {
    if (!element || !global.echarts) return null;
    let instance = instances.get(element);
    if (!instance || instance.isDisposed()) {
      instance = global.echarts.init(element, null, { renderer: 'canvas' });
      instances.set(element, instance);
    }
    return instance;
  }

  function renderAnalogueChart(element, horizons) {
    const rows = Array.isArray(horizons)
      ? horizons.filter((row) => Number.isFinite(Number(row.sessions)))
      : [];
    if (!element || !rows.length || !global.echarts) {
      if (element) element.hidden = true;
      return;
    }
    element.hidden = false;
    const colors = chartTheme();
    const instance = ensureInstance(element);
    if (!instance) return;
    instance.setOption({
      animationDuration: 320,
      aria: {
        enabled: true,
        description: 'Historical analogue mean forward returns and positive-observation probabilities. These outcomes overlap and are descriptive, not forecasts.',
      },
      grid: { left: 38, right: 38, top: 26, bottom: 34 },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 10,
        itemHeight: 7,
        textStyle: { color: colors.muted, fontFamily: 'Calibri, sans-serif', fontSize: 9 },
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: colors.tooltip,
        borderColor: colors.grid,
        textStyle: { color: colors.ink, fontFamily: 'Calibri, sans-serif', fontSize: 10 },
        formatter(params) {
          const row = rows[params[0]?.dataIndex] || {};
          return [
            `<strong>Next ${Number(row.sessions)} sessions</strong>`,
            `Mean return: ${Number(row.mean_return_pct || 0).toFixed(2)}%`,
            `Positive: ${Number(row.positive_rate_pct || 0).toFixed(1)}%`,
            `Worst: ${Number(row.worst_return_pct || 0).toFixed(2)}%`,
          ].join('<br>');
        },
      },
      xAxis: {
        type: 'category',
        data: rows.map((row) => `${Number(row.sessions)}D`),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: colors.grid } },
        axisLabel: { color: colors.muted, fontFamily: 'Calibri, sans-serif', fontSize: 9 },
      },
      yAxis: [
        {
          type: 'value',
          name: 'RETURN %',
          nameTextStyle: { color: colors.muted, fontSize: 8 },
          splitLine: { lineStyle: { color: colors.grid, type: 'dashed' } },
          axisLabel: { color: colors.muted, fontSize: 8, formatter: '{value}%' },
        },
        {
          type: 'value',
          min: 0,
          max: 100,
          name: 'POSITIVE %',
          nameTextStyle: { color: colors.muted, fontSize: 8 },
          splitLine: { show: false },
          axisLabel: { color: colors.muted, fontSize: 8, formatter: '{value}%' },
        },
      ],
      series: [
        {
          name: 'Mean return',
          type: 'bar',
          barMaxWidth: 28,
          data: rows.map((row) => ({
            value: Number(row.mean_return_pct || 0),
            itemStyle: { color: Number(row.mean_return_pct || 0) < 0 ? colors.negative : colors.positive },
          })),
        },
        {
          name: 'Positive observations',
          type: 'line',
          yAxisIndex: 1,
          symbolSize: 6,
          lineStyle: { width: 2, color: colors.probability },
          itemStyle: { color: colors.probability },
          data: rows.map((row) => Number(row.positive_rate_pct || 0)),
        },
      ],
    }, true);
  }

  function register(name, renderer) {
    renderers.set(name, renderer);
    renderer();
  }

  function refresh() {
    renderers.forEach((renderer) => renderer());
  }

  global.addEventListener('resize', () => {
    global.cancelAnimationFrame(resizeFrame);
    resizeFrame = global.requestAnimationFrame(() => instances.forEach((instance) => instance.resize()));
  });
  global.addEventListener('pgterminal:themechange', refresh);

  global.PGTerminalCharts = Object.freeze({ register, refresh, renderAnalogueChart });
}(window));
