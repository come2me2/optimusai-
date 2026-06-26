const { computeKpis } = require("./metrics.cjs");

const MIN_CLICKS = 25;
const SHIFT_PERCENT = 0.15;

function normalizeWeights(creatives) {
  const active = creatives.filter((c) => c.status === "active");
  const total = active.reduce((a, c) => a + c.traffic_weight, 0);
  if (total <= 0) {
    const w = active.length ? 1 / active.length : 1;
    active.forEach((c) => { c.traffic_weight = w; });
    return;
  }
  active.forEach((c) => { c.traffic_weight = Math.round((c.traffic_weight / total) * 10000) / 10000; });
}

class CreativeAbEngine {
  evaluate(campaignId, tick, creatives, cumulativeByCreative, windowKpis, currentBid) {
    const active = creatives.filter((c) => c.status === "active");
    if (active.length < 2) return { decision: null, updatedCreatives: creatives };

    const stats = [];
    for (const c of active) {
      const pm = cumulativeByCreative[c.id] || { impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0 };
      if (pm.clicks < MIN_CLICKS) return { decision: null, updatedCreatives: creatives };
      const kpis = computeKpis(pm);
      const score = kpis.ctr * Math.max(kpis.cr, 0.01) / Math.max(kpis.cpa, 1);
      stats.push({ creative: c, kpis, pm, score });
    }

    stats.sort((a, b) => b.score - a.score);
    const best = stats[0];
    const worst = stats[stats.length - 1];
    const updated = creatives.map((c) => ({ ...c }));

    if (worst.kpis.ctr < best.kpis.ctr * 0.55 && worst.pm.clicks >= MIN_CLICKS) {
      return this._pause(campaignId, tick, updated, worst, best, currentBid, windowKpis);
    }
    if (best.kpis.ctr > worst.kpis.ctr * 1.12 && (worst.kpis.cpa === 0 || best.kpis.cpa < worst.kpis.cpa * 0.95)) {
      return this._shift(campaignId, tick, updated, best, worst, currentBid, windowKpis);
    }
    return { decision: null, updatedCreatives: creatives };
  }

  _shift(campaignId, tick, creatives, winner, loser, bid, windowKpis) {
    for (const c of creatives) {
      if (c.id === winner.creative.id) c.traffic_weight = Math.min(0.95, c.traffic_weight + SHIFT_PERCENT);
      if (c.id === loser.creative.id) c.traffic_weight = Math.max(0.05, c.traffic_weight - SHIFT_PERCENT);
    }
    normalizeWeights(creatives);
    return {
      decision: {
        campaign_id: campaignId,
        tick,
        action: "shift_creative",
        bid_change_percent: 0,
        new_bid: bid,
        reason: `A/B: ${winner.creative.variant} CTR ${(winner.kpis.ctr * 100).toFixed(2)}% лучше ${loser.creative.variant} — +${SHIFT_PERCENT * 100}% трафика`,
        kpis_before: windowKpis,
        creative_id: winner.creative.id,
      },
      updatedCreatives: creatives,
    };
  }

  _pause(campaignId, tick, creatives, loser, winner, bid, windowKpis) {
    let freed = 0;
    let others = 0;
    for (const c of creatives) {
      if (c.id === loser.creative.id) {
        freed = c.traffic_weight;
        c.status = "paused";
        c.traffic_weight = 0;
      } else if (c.status === "active") others++;
    }
    if (others > 0) {
      const bonus = freed / others;
      creatives.forEach((c) => { if (c.status === "active") c.traffic_weight += bonus; });
    }
    normalizeWeights(creatives);
    return {
      decision: {
        campaign_id: campaignId,
        tick,
        action: "pause_creative",
        bid_change_percent: 0,
        new_bid: bid,
        reason: `A/B: пауза ${loser.creative.variant} (CTR ${(loser.kpis.ctr * 100).toFixed(2)}%) → трафик на ${winner.creative.variant}`,
        kpis_before: windowKpis,
        creative_id: loser.creative.id,
      },
      updatedCreatives: creatives,
    };
  }
}

module.exports = { CreativeAbEngine };
