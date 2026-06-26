const { BID_ACTIONS } = require("./store.cjs");

class BidBandit {
  constructor(state = {}) {
    this.arms = state.arms || {};
    this.explorationRate = state.exploration_rate ?? 0.15;
    for (const key of Object.keys(BID_ACTIONS)) {
      if (!this.arms[key]) this.arms[key] = { alpha: 1, beta: 1, pulls: 0 };
    }
  }

  toState() {
    return { exploration_rate: this.explorationRate, arms: this.arms };
  }

  select(candidateKeys) {
    const available = candidateKeys.filter((k) => BID_ACTIONS[k]);
    if (!available.length) return "hold";
    if (Math.random() < this.explorationRate) {
      return available[Math.floor(Math.random() * available.length)];
    }
    let best = available[0];
    let bestSample = -1;
    for (const key of available) {
      const arm = this.arms[key];
      const sample = this._betaSample(arm.alpha, arm.beta);
      if (sample > bestSample) {
        bestSample = sample;
        best = key;
      }
    }
    return best;
  }

  _betaSample(a, b) {
    const x = this._gammaSample(a);
    const y = this._gammaSample(b);
    return x / (x + y);
  }

  _gammaSample(k) {
    if (k < 1) return this._gammaSample(1 + k) * Math.pow(Math.random(), 1 / k);
    const d = k - 1 / 3;
    const c = 1 / Math.sqrt(9 * d);
    while (true) {
      let x, v;
      do {
        x = this._randn();
        v = 1 + c * x;
      } while (v <= 0);
      v = v * v * v;
      const u = Math.random();
      if (u < 1 - 0.0331 * (x * x) * (x * x)) return d * v;
      if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
    }
  }

  _randn() {
    const u = Math.random() || 1e-10;
    const v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  update(actionKey, reward) {
    if (!this.arms[actionKey]) return;
    const success = Math.max(0, Math.min(1, reward));
    this.arms[actionKey].alpha += success;
    this.arms[actionKey].beta += 1 - success;
    this.arms[actionKey].pulls += 1;
  }

  computeReward(cpa, targetCpa) {
    if (cpa <= 0 || targetCpa <= 0) return 0.5;
    const ratio = cpa / targetCpa;
    if (ratio <= 1) return Math.min(1, 0.7 + (1 - ratio) * 0.3);
    return Math.max(0, 1 - (ratio - 1) * 0.5);
  }
}

function evaluateRules(campaign, windowKpis, cumulativeKpis, windowClicks, spendRate, simulatedHour) {
  const candidates = [];
  const target = campaign.target_cpa;
  const cpa = windowKpis.cpa > 0 ? windowKpis.cpa : cumulativeKpis.cpa;
  const ctr = windowKpis.ctr > 0 ? windowKpis.ctr : cumulativeKpis.ctr;
  const hour = simulatedHour % 24;

  if (windowClicks >= 15 && cpa > 0) {
    if (cpa > target * 1.25) {
      candidates.push({
        action_key: "decrease_10",
        action: "decrease_bid",
        bid_change_percent: -10,
        reason: `CPA ${cpa.toFixed(0)} > target ${target.toFixed(0)} × 1.25 — снижаю ставку`,
        priority: 10,
      });
      if (cpa > target * 1.5) {
        candidates.push({
          action_key: "decrease_20",
          action: "decrease_bid",
          bid_change_percent: -20,
          reason: `CPA ${cpa.toFixed(0)} сильно выше target — агрессивное снижение`,
          priority: 12,
        });
      }
    } else if (cpa < target * 0.85 && windowKpis.impression_share < 0.7) {
      candidates.push({
        action_key: "increase_5",
        action: "increase_bid",
        bid_change_percent: 5,
        reason: `CPA ${cpa.toFixed(0)} ниже target, доля показов ${(windowKpis.impression_share * 100).toFixed(0)}% — наращиваю`,
        priority: 8,
      });
    }
  }

  if (ctr > 0 && ctr < 0.03 * 0.6 && windowClicks >= 10) {
    candidates.push({
      action_key: "hold",
      action: "creative_fatigue",
      bid_change_percent: 0,
      reason: `CTR ${(ctr * 100).toFixed(2)}% низкий — усталость креатива`,
      priority: 9,
    });
  }

  if (spendRate > 0.9 && hour < 18) {
    candidates.push({
      action_key: "decrease_10",
      action: "throttle",
      bid_change_percent: -10,
      reason: `Расход ${(spendRate * 100).toFixed(0)}% дневного бюджета до 18:00 — дросселирую`,
      priority: 11,
    });
  }

  if (!candidates.length) {
    candidates.push({
      action_key: "hold",
      action: "hold",
      bid_change_percent: 0,
      reason: "Метрики в норме или мало данных — удерживаю ставку",
      priority: 1,
    });
  }

  candidates.sort((a, b) => b.priority - a.priority);
  return candidates;
}

function decide(campaign, tick, windowKpis, cumulativeKpis, windowClicks, spendToday, simulatedHour, bandit) {
  const spendRate = campaign.daily_budget > 0 ? spendToday / campaign.daily_budget : 0;
  const candidates = evaluateRules(
    campaign,
    windowKpis,
    cumulativeKpis,
    windowClicks,
    spendRate,
    simulatedHour
  );
  const keys = [...new Set(candidates.map((c) => c.action_key))];
  const chosenKey = bandit.select(keys);
  const rule = candidates.find((c) => c.action_key === chosenKey) || candidates[0];
  const meta = BID_ACTIONS[chosenKey] || BID_ACTIONS.hold;

  let action = rule.action;
  let bidChange = meta.pct;
  let applyFatigue = false;
  let reason = rule.reason + ` (bandit: ${chosenKey})`;

  if (rule.action === "creative_fatigue") {
    action = "creative_fatigue";
    bidChange = 0;
    applyFatigue = true;
    reason = rule.reason;
  } else if (rule.action === "throttle") {
    action = "throttle";
  }

  const newBid = Math.max(5, Math.min(Math.round(campaign.current_bid * (1 + bidChange / 100) * 100) / 100, 500));

  return {
    decision: {
      campaign_id: campaign.id,
      tick,
      action,
      bid_change_percent: bidChange,
      new_bid: newBid,
      reason,
      kpis_before: windowKpis,
    },
    actionKey: chosenKey,
    applyFatigue,
  };
}

module.exports = { BidBandit, decide };
