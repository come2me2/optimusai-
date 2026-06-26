function mulberry32(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function sampleBinomial(n, p, rand) {
  if (n <= 0) return 0;
  if (n <= 50) {
    let hits = 0;
    for (let i = 0; i < n; i++) if (rand() < p) hits++;
    return hits;
  }
  const mean = n * p;
  const std = Math.sqrt(mean * (1 - p));
  const z = rand() * 2 - 1;
  return Math.max(0, Math.min(n, Math.round(mean + z * Math.max(std, 0.5))));
}

class MarketSimulator {
  constructor(seed = 42) {
    this.seed = seed;
    this.reset(50);
  }

  reset(bid = 50) {
    this.currentBid = bid;
    this.creativeFatigue = 0;
    this.competitorShock = 0;
    this.rand = mulberry32(this.seed);
    this.conversionValue = 2500;
    this.baseMarketVolume = 12000;
    this.marketCpcFloor = 15;
    this.competitionLevel = 0.55;
    this.baseCtr = 0.035;
    this.baseCr = 0.08;
  }

  setBid(bid) {
    this.currentBid = Math.max(5, Math.min(bid, 500));
    return this.currentBid;
  }

  applyCreativeFatigue() {
    this.creativeFatigue = Math.min(0.5, this.creativeFatigue + 0.08);
  }

  hourMultiplier(hour) {
    if (hour >= 10 && hour <= 14) return 1.25;
    if (hour >= 18 && hour <= 21) return 1.15;
    if (hour >= 0 && hour <= 6) return 0.45;
    return 0.85;
  }

  dayMultiplier(day) {
    return day >= 5 ? 0.75 : 1;
  }

  auctionPosition(bid) {
    const marketBid = 35 + this.competitorShock * 20;
    const ratio = bid / Math.max(marketBid, 1);
    return 1 / (1 + Math.exp(-2.5 * (ratio - 1)));
  }

  impressionShare(bid) {
    const position = this.auctionPosition(bid);
    return Math.min(0.98, Math.max(0.05, 0.15 + 0.75 * position));
  }

  simulateHour(simulatedHour, dailyBudget, spendSoFarToday = 0) {
    const hour = simulatedHour % 24;
    const day = Math.floor(simulatedHour / 24) % 7;
    const rand = this.rand;

    if (rand() < 0.04) this.competitorShock = rand();

    const demand =
      this.baseMarketVolume *
      this.hourMultiplier(hour) *
      this.dayMultiplier(day) *
      (1 - this.competitorShock * 0.15);

    const share = this.impressionShare(this.currentBid);
    const noise = 0.85 + rand() * 0.3;
    let impressions = Math.max(0, Math.floor((demand * share * noise) / 24));

    const position = this.auctionPosition(this.currentBid);
    let ctr = this.baseCtr * (0.6 + 0.8 * position);
    ctr *= 1 - this.creativeFatigue;
    ctr *= 0.9 + rand() * 0.2;
    ctr = Math.max(0.005, Math.min(ctr, 0.12));

    let clicks = impressions > 0 ? sampleBinomial(impressions, ctr, rand) : 0;

    const marketPressure = 1 + this.competitionLevel * position;
    let effectiveCpc = this.currentBid * marketPressure * (0.92 + rand() * 0.16);
    effectiveCpc = Math.max(this.marketCpcFloor, effectiveCpc);

    let spend = clicks * effectiveCpc;
    const hourlyBudget = dailyBudget / 24;

    if (spend > hourlyBudget * 1.2) {
      const scale = (hourlyBudget * 1.2) / spend;
      clicks = Math.floor(clicks * scale);
      spend = clicks * effectiveCpc;
    }

    if (spendSoFarToday + spend > dailyBudget) {
      const remaining = Math.max(0, dailyBudget - spendSoFarToday);
      if (spend > 0) {
        const scale = remaining / spend;
        clicks = Math.floor(clicks * scale);
        spend = clicks * effectiveCpc;
      }
    }

    let cr = this.baseCr * (0.85 + rand() * 0.3);
    cr = Math.max(0.02, Math.min(cr, 0.2));
    const conversions = clicks > 0 ? sampleBinomial(clicks, cr, rand) : 0;
    const revenue = conversions * this.conversionValue;

    return {
      impressions,
      clicks,
      conversions,
      spend: Math.round(spend * 100) / 100,
      revenue: Math.round(revenue * 100) / 100,
    };
  }
}

module.exports = { MarketSimulator };
