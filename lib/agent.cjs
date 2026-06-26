const { MarketSimulator } = require("./simulator.cjs");
const { computeKpis, computeWindowKpis } = require("./metrics.cjs");
const { BidBandit, decide } = require("./optimizer.cjs");
const { CreativeAbEngine } = require("./creative_ab.cjs");

class MockAdapter {
  constructor(campaign) {
    const seed = [...campaign.id].reduce((a, c) => a + c.charCodeAt(0), 0) % 10000;
    this.sim = new MarketSimulator(seed);
    this.sim.reset(campaign.current_bid);
    this.spendToday = 0;
    this.lastDay = -1;
    this.paused = false;
  }

  advance(campaign, simulatedHour, creatives) {
    const day = Math.floor(simulatedHour / 24);
    if (day !== this.lastDay) { this.spendToday = 0; this.lastDay = day; }
    if (this.paused || campaign.status === "paused") {
      return { total: { impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0 }, breakdown: [] };
    }
    let result;
    if (creatives && creatives.filter((c) => c.status === "active").length >= 2) {
      result = this.sim.simulateHourWithCreatives(simulatedHour, campaign.daily_budget, this.spendToday, creatives);
    } else {
      result = { total: this.sim.simulateHour(simulatedHour, campaign.daily_budget, this.spendToday), breakdown: [] };
    }
    this.spendToday += result.total.spend;
    return result;
  }

  impressionShare(bid) { return this.sim.impressionShare(bid); }
  setBid(bid) { return this.sim.setBid(bid); }
  applyFatigue() { this.sim.applyCreativeFatigue(); }
}

class AgentLoop {
  constructor(store) {
    this.store = store;
    this.adapters = new Map();
    this.creativeAb = new CreativeAbEngine();
  }

  getAdapter(campaign) {
    if (!this.adapters.has(campaign.id)) this.adapters.set(campaign.id, new MockAdapter(campaign));
    return this.adapters.get(campaign.id);
  }

  resetAdapter(campaignId) { this.adapters.delete(campaignId); }

  tick(campaignId) {
    const campaign = this.store.getCampaign(campaignId);
    if (!campaign) throw new Error("Campaign not found");

    const adapter = this.getAdapter(campaign);
    const tick = this.store.getTick(campaignId);
    const creatives = this.store.getCreatives(campaignId);
    const { total: period, breakdown } = adapter.advance(campaign, tick, creatives);
    const share = adapter.impressionShare(campaign.current_bid);
    const kpis = computeKpis(period, share);

    this.store.saveSnapshot({
      campaign_id: campaignId, tick, simulated_hour: tick, metrics: period, kpis,
      bid: campaign.current_bid, creative_breakdown: breakdown,
    });

    const snapshots = this.store.getSnapshots(campaignId);
    const windowKpis = computeWindowKpis(snapshots, 6);
    const cumulative = this.store.getCumulativeMetrics(campaignId);
    const cumulativeKpis = computeKpis(cumulative, windowKpis.impression_share);
    const windowClicks = snapshots.slice(-6).reduce((a, s) => a + s.metrics.clicks, 0);
    const spendToday = snapshots.filter((s) => Math.floor(s.simulated_hour / 24) === Math.floor(tick / 24))
      .reduce((a, s) => a + s.metrics.spend, 0);

    const bandit = new BidBandit(this.store.getBanditState(campaignId));
    const result = decide(campaign, tick, windowKpis, cumulativeKpis, windowClicks, spendToday, tick, bandit);

    if (result.applyFatigue) adapter.applyFatigue();
    else if (["increase_bid", "decrease_bid", "throttle"].includes(result.decision.action)) {
      adapter.setBid(result.decision.new_bid);
      this.store.updateBid(campaignId, result.decision.new_bid);
      campaign.current_bid = result.decision.new_bid;
    }

    this.store.saveDecision(result.decision);

    const abResult = this.creativeAb.evaluate(
      campaignId, tick, creatives, this.store.getCumulativeCreativeMetrics(campaignId),
      windowKpis, result.decision.new_bid
    );
    if (abResult.decision) {
      this.store.saveDecision(abResult.decision);
      this.store.saveCreatives(abResult.updatedCreatives);
    }

    const reward = bandit.computeReward(windowKpis.cpa > 0 ? windowKpis.cpa : cumulativeKpis.cpa, campaign.target_cpa);
    bandit.update(result.actionKey, reward);
    this.store.setBanditState(campaignId, bandit.toState());
    this.store.setTick(campaignId, tick + 1);

    return {
      tick, simulated_hour: tick, period_metrics: period, kpis, window_kpis: windowKpis,
      cumulative_kpis: cumulativeKpis, decision: result.decision,
      creative_decision: abResult.decision, creatives: abResult.updatedCreatives,
      bid: result.decision.new_bid,
    };
  }

  run(campaignId, ticks = 1) {
    const results = [];
    for (let i = 0; i < ticks; i++) results.push(this.tick(campaignId));
    return results;
  }
}

module.exports = { AgentLoop };
