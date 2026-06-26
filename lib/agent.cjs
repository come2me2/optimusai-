const { MarketSimulator } = require("./simulator.cjs");
const { computeKpis, computeWindowKpis } = require("./metrics.cjs");
const { BidBandit, decide } = require("./optimizer.cjs");

class MockAdapter {
  constructor(campaign) {
    const seed = [...campaign.id].reduce((a, c) => a + c.charCodeAt(0), 0) % 10000;
    this.sim = new MarketSimulator(seed);
    this.sim.reset(campaign.current_bid);
    this.spendToday = 0;
    this.lastDay = -1;
    this.paused = false;
  }

  advance(campaign, simulatedHour) {
    const day = Math.floor(simulatedHour / 24);
    if (day !== this.lastDay) {
      this.spendToday = 0;
      this.lastDay = day;
    }
    if (this.paused || campaign.status === "paused") {
      return { impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0 };
    }
    const period = this.sim.simulateHour(simulatedHour, campaign.daily_budget, this.spendToday);
    this.spendToday += period.spend;
    return period;
  }

  impressionShare(bid) {
    return this.sim.impressionShare(bid);
  }

  setBid(bid) {
    return this.sim.setBid(bid);
  }

  applyFatigue() {
    this.sim.applyCreativeFatigue();
  }
}

class AgentLoop {
  constructor(store) {
    this.store = store;
    this.adapters = new Map();
  }

  getAdapter(campaign) {
    if (!this.adapters.has(campaign.id)) {
      this.adapters.set(campaign.id, new MockAdapter(campaign));
    }
    return this.adapters.get(campaign.id);
  }

  resetAdapter(campaignId) {
    this.adapters.delete(campaignId);
  }

  tick(campaignId) {
    const campaign = this.store.getCampaign(campaignId);
    if (!campaign) throw new Error("Campaign not found");

    const adapter = this.getAdapter(campaign);
    const tick = this.store.getTick(campaignId);
    const period = adapter.advance(campaign, tick);
    const share = adapter.impressionShare(campaign.current_bid);
    const kpis = computeKpis(period, share);

    this.store.saveSnapshot({
      campaign_id: campaignId,
      tick,
      simulated_hour: tick,
      metrics: period,
      kpis,
      bid: campaign.current_bid,
    });

    const snapshots = this.store.getSnapshots(campaignId);
    const windowKpis = computeWindowKpis(snapshots, 6);
    const cumulative = this.store.getCumulativeMetrics(campaignId);
    const cumulativeKpis = computeKpis(cumulative, windowKpis.impression_share);
    const windowClicks = snapshots.slice(-6).reduce((a, s) => a + s.metrics.clicks, 0);
    const spendToday = snapshots
      .filter((s) => Math.floor(s.simulated_hour / 24) === Math.floor(tick / 24))
      .reduce((a, s) => a + s.metrics.spend, 0);

    const bandit = new BidBandit(this.store.getBanditState(campaignId));
    const result = decide(
      campaign,
      tick,
      windowKpis,
      cumulativeKpis,
      windowClicks,
      spendToday,
      tick,
      bandit
    );

    const oldBid = campaign.current_bid;
    if (result.applyFatigue) {
      adapter.applyFatigue();
    } else if (["increase_bid", "decrease_bid", "throttle"].includes(result.decision.action)) {
      adapter.setBid(result.decision.new_bid);
      this.store.updateBid(campaignId, result.decision.new_bid);
      campaign.current_bid = result.decision.new_bid;
    }

    this.store.saveDecision(result.decision);

    const reward = bandit.computeReward(
      windowKpis.cpa > 0 ? windowKpis.cpa : cumulativeKpis.cpa,
      campaign.target_cpa
    );
    bandit.update(result.actionKey, reward);
    this.store.setBanditState(campaignId, bandit.toState());
    this.store.setTick(campaignId, tick + 1);

    return {
      tick,
      simulated_hour: tick,
      period_metrics: period,
      kpis,
      window_kpis: windowKpis,
      cumulative_kpis: cumulativeKpis,
      decision: result.decision,
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
