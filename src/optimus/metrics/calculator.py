from optimus.models import KPIs, PeriodMetrics


def compute_kpis(
    metrics: PeriodMetrics,
    impression_share: float = 0.0,
) -> KPIs:
    impressions = metrics.impressions
    clicks = metrics.clicks
    conversions = metrics.conversions
    spend = metrics.spend
    revenue = metrics.revenue

    ctr = clicks / impressions if impressions > 0 else 0.0
    cpc = spend / clicks if clicks > 0 else 0.0
    cr = conversions / clicks if clicks > 0 else 0.0
    cpa = spend / conversions if conversions > 0 else 0.0
    roas = revenue / spend if spend > 0 else 0.0

    return KPIs(
        ctr=round(ctr, 6),
        cpc=round(cpc, 2),
        cr=round(cr, 6),
        cpa=round(cpa, 2),
        roas=round(roas, 4),
        impression_share=round(impression_share, 4),
    )


def aggregate_metrics(snapshots: list) -> PeriodMetrics:
    total = PeriodMetrics()
    for s in snapshots:
        total.impressions += s.metrics.impressions
        total.clicks += s.metrics.clicks
        total.conversions += s.metrics.conversions
        total.spend += s.metrics.spend
        total.revenue += s.metrics.revenue
    return total


def compute_window_kpis(snapshots: list, window: int = 6) -> KPIs:
    recent = snapshots[-window:] if snapshots else []
    metrics = aggregate_metrics(recent)
    avg_share = (
        sum(s.kpis.impression_share for s in recent) / len(recent) if recent else 0.0
    )
    return compute_kpis(metrics, impression_share=avg_share)
