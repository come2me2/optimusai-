function computeKpis(metrics, impressionShare = 0) {
  const { impressions, clicks, conversions, spend, revenue } = metrics;
  return {
    ctr: impressions > 0 ? Math.round((clicks / impressions) * 1e6) / 1e6 : 0,
    cpc: clicks > 0 ? Math.round((spend / clicks) * 100) / 100 : 0,
    cr: clicks > 0 ? Math.round((conversions / clicks) * 1e6) / 1e6 : 0,
    cpa: conversions > 0 ? Math.round((spend / conversions) * 100) / 100 : 0,
    roas: spend > 0 ? Math.round((revenue / spend) * 10000) / 10000 : 0,
    impression_share: Math.round(impressionShare * 10000) / 10000,
  };
}

function aggregateMetrics(snapshots) {
  const total = { impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0 };
  for (const s of snapshots) {
    total.impressions += s.metrics.impressions;
    total.clicks += s.metrics.clicks;
    total.conversions += s.metrics.conversions;
    total.spend += s.metrics.spend;
    total.revenue += s.metrics.revenue;
  }
  return total;
}

function computeWindowKpis(snapshots, window = 6) {
  const recent = snapshots.slice(-window);
  const metrics = aggregateMetrics(recent);
  const avgShare = recent.length
    ? recent.reduce((a, s) => a + s.kpis.impression_share, 0) / recent.length
    : 0;
  return computeKpis(metrics, avgShare);
}

module.exports = { computeKpis, aggregateMetrics, computeWindowKpis };
