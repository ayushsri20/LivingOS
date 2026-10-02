(() => {
  const analytics = document.getElementById('ro-analytics-link');
  if (!analytics) return;

  const formatMoney = value => new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(Number(value));

  const setText = (id, value) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  };

  const hour = new Date().getHours();
  setText('ro-greeting', hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening');

  async function refreshMetrics() {
    try {
      const response = await fetch(analytics.dataset.metricsUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || `Metrics request failed (${response.status})`);
      }

      const metrics = data.metrics;
      setText('m-expected', formatMoney(metrics.expected_yield));
      setText('m-collected', formatMoney(metrics.realized_revenue));
      setText('m-receivable', formatMoney(metrics.accounts_receivable));
      setText('m-efficiency', `${Number(metrics.collection_efficiency).toFixed(1)}%`);
      setText('m-occupancy-rate', `${Number(metrics.occupancy_rate).toFixed(0)}%`);
      setText('m-occupied', data.meta.occupied_rooms);
      setText('m-occupancy', `${Number(metrics.occupancy_rate).toFixed(1)}% occupancy`);
      setText('m-pending', formatMoney(metrics.accounts_receivable));
    } catch (error) {
      ['m-expected', 'm-collected', 'm-receivable', 'm-efficiency', 'm-occupancy-rate', 'm-pending']
        .forEach(id => setText(id, 'Unavailable'));
      console.error('Could not load authoritative rental metrics:', error);
    }
  }

  refreshMetrics();
  window.setInterval(() => {
    if (!document.hidden) refreshMetrics();
  }, 30000);
})();
