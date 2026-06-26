const { randomUUID } = require("crypto");
const { openDatabase } = require("./db.cjs");

const BID_ACTIONS = {
  decrease_20: { action: "decrease_bid", pct: -20 },
  decrease_10: { action: "decrease_bid", pct: -10 },
  hold: { action: "hold", pct: 0 },
  increase_5: { action: "increase_bid", pct: 5 },
  increase_10: { action: "increase_bid", pct: 10 },
};

const DEFAULT_CREATIVES = [
  { variant: "A", name: "Креатив A", headline: "Скидка 20% — только сегодня", ctr_multiplier: 1.0 },
  { variant: "B", name: "Креатив B", headline: "Бесплатная доставка за 2 часа", ctr_multiplier: 1.15 },
];

class MetricsStore {
  constructor(dbPath) {
    this.db = openDatabase(dbPath);
    this._init();
  }

  _init() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS campaigns (
        id TEXT PRIMARY KEY, name TEXT, platform TEXT, daily_budget REAL,
        target_cpa REAL, conversion_value REAL, current_bid REAL, status TEXT, created_at TEXT
      );
      CREATE TABLE IF NOT EXISTS metrics_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT, tick INTEGER,
        simulated_hour INTEGER, metrics_json TEXT, kpis_json TEXT, bid REAL,
        creative_breakdown_json TEXT DEFAULT '[]', created_at TEXT
      );
      CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT, tick INTEGER,
        action TEXT, bid_change_percent REAL, new_bid REAL, reason TEXT,
        kpis_before_json TEXT, creative_id TEXT, created_at TEXT
      );
      CREATE TABLE IF NOT EXISTS agent_state (
        campaign_id TEXT PRIMARY KEY, current_tick INTEGER DEFAULT 0, bandit_state_json TEXT DEFAULT '{}'
      );
      CREATE TABLE IF NOT EXISTS creatives (
        id TEXT PRIMARY KEY, campaign_id TEXT, variant TEXT, name TEXT, headline TEXT,
        traffic_weight REAL DEFAULT 0.5, ctr_multiplier REAL DEFAULT 1.0, status TEXT DEFAULT 'active'
      );
    `);
    this._migrate();
  }

  _migrate() {
    try { this.db.exec(`ALTER TABLE metrics_snapshots ADD COLUMN creative_breakdown_json TEXT DEFAULT '[]'`); } catch (_) {}
    try { this.db.exec(`ALTER TABLE decisions ADD COLUMN creative_id TEXT`); } catch (_) {}
  }

  _seedCreatives(campaignId) {
    const w = 1 / DEFAULT_CREATIVES.length;
    for (const spec of DEFAULT_CREATIVES) {
      this.db.prepare(
        `INSERT INTO creatives (id, campaign_id, variant, name, headline, traffic_weight, ctr_multiplier, status)
         VALUES (?, ?, ?, ?, ?, ?, ?, 'active')`
      ).run(randomUUID(), campaignId, spec.variant, spec.name, spec.headline, w, spec.ctr_multiplier);
    }
  }

  createCampaign({ name, daily_budget = 5000, target_cpa = 800, current_bid = 50 }) {
    const id = randomUUID();
    const now = new Date().toISOString();
    this.db.prepare(`INSERT INTO campaigns VALUES (?, ?, 'yandex_mock', ?, ?, 2500, ?, 'active', ?)`)
      .run(id, name, daily_budget, target_cpa, current_bid, now);
    this.db.prepare(`INSERT INTO agent_state (campaign_id) VALUES (?)`).run(id);
    this._seedCreatives(id);
    return this.getCampaign(id);
  }

  getCampaign(id) {
    const row = this.db.prepare(`SELECT * FROM campaigns WHERE id = ?`).get(id);
    if (!row) return null;
    return { id: row.id, name: row.name, platform: row.platform, daily_budget: row.daily_budget,
      target_cpa: row.target_cpa, conversion_value: row.conversion_value, current_bid: row.current_bid, status: row.status };
  }

  listCampaigns() {
    return this.db.prepare(`SELECT * FROM campaigns ORDER BY created_at DESC`).all()
      .map((row) => ({ id: row.id, name: row.name, platform: row.platform, daily_budget: row.daily_budget,
        target_cpa: row.target_cpa, conversion_value: row.conversion_value, current_bid: row.current_bid, status: row.status }));
  }

  getActiveCampaign() { return this.listCampaigns()[0] || null; }
  updateBid(id, bid) { this.db.prepare(`UPDATE campaigns SET current_bid = ? WHERE id = ?`).run(bid, id); }
  updateTargetCpa(id, target) { this.db.prepare(`UPDATE campaigns SET target_cpa = ? WHERE id = ?`).run(target, id); }
  getTick(id) { const r = this.db.prepare(`SELECT current_tick FROM agent_state WHERE campaign_id = ?`).get(id); return r ? r.current_tick : 0; }
  setTick(id, tick) { this.db.prepare(`UPDATE agent_state SET current_tick = ? WHERE campaign_id = ?`).run(tick, id); }
  getBanditState(id) { const r = this.db.prepare(`SELECT bandit_state_json FROM agent_state WHERE campaign_id = ?`).get(id); return r ? JSON.parse(r.bandit_state_json) : {}; }
  setBanditState(id, state) { this.db.prepare(`UPDATE agent_state SET bandit_state_json = ? WHERE campaign_id = ?`).run(JSON.stringify(state), id); }

  getCreatives(campaignId) {
    let rows = this.db.prepare(`SELECT * FROM creatives WHERE campaign_id = ? ORDER BY variant`).all(campaignId);
    if (!rows.length) { this._seedCreatives(campaignId); rows = this.db.prepare(`SELECT * FROM creatives WHERE campaign_id = ? ORDER BY variant`).all(campaignId); }
    return rows.map((r) => ({ id: r.id, campaign_id: r.campaign_id, variant: r.variant, name: r.name, headline: r.headline,
      traffic_weight: r.traffic_weight, ctr_multiplier: r.ctr_multiplier, status: r.status }));
  }

  saveCreatives(creatives) {
    const stmt = this.db.prepare(`UPDATE creatives SET traffic_weight = ?, ctr_multiplier = ?, status = ? WHERE id = ?`);
    for (const c of creatives) stmt.run(c.traffic_weight, c.ctr_multiplier, c.status, c.id);
  }

  saveSnapshot(snapshot) {
    this.db.prepare(
      `INSERT INTO metrics_snapshots (campaign_id, tick, simulated_hour, metrics_json, kpis_json, bid, creative_breakdown_json, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    ).run(snapshot.campaign_id, snapshot.tick, snapshot.simulated_hour, JSON.stringify(snapshot.metrics),
      JSON.stringify(snapshot.kpis), snapshot.bid, JSON.stringify(snapshot.creative_breakdown || []), new Date().toISOString());
  }

  getSnapshots(campaignId, limit = 100) {
    return this.db.prepare(`SELECT * FROM metrics_snapshots WHERE campaign_id = ? ORDER BY tick ASC LIMIT ?`).all(campaignId, limit)
      .map((row) => ({
        campaign_id: row.campaign_id, tick: row.tick, simulated_hour: row.simulated_hour,
        metrics: JSON.parse(row.metrics_json), kpis: JSON.parse(row.kpis_json), bid: row.bid,
        creative_breakdown: JSON.parse(row.creative_breakdown_json || "[]"),
      }));
  }

  saveDecision(d) {
    this.db.prepare(
      `INSERT INTO decisions (campaign_id, tick, action, bid_change_percent, new_bid, reason, kpis_before_json, creative_id, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).run(d.campaign_id, d.tick, d.action, d.bid_change_percent, d.new_bid, d.reason,
      JSON.stringify(d.kpis_before), d.creative_id || null, new Date().toISOString());
  }

  getDecisions(campaignId, limit = 50) {
    return this.db.prepare(`SELECT * FROM decisions WHERE campaign_id = ? ORDER BY tick DESC LIMIT ?`).all(campaignId, limit)
      .map((row) => ({ campaign_id: row.campaign_id, tick: row.tick, action: row.action,
        bid_change_percent: row.bid_change_percent, new_bid: row.new_bid, reason: row.reason,
        kpis_before: JSON.parse(row.kpis_before_json), creative_id: row.creative_id }));
  }

  getCumulativeMetrics(campaignId) {
    return this.getSnapshots(campaignId, 10000).reduce((t, s) => ({
      impressions: t.impressions + s.metrics.impressions, clicks: t.clicks + s.metrics.clicks,
      conversions: t.conversions + s.metrics.conversions, spend: t.spend + s.metrics.spend, revenue: t.revenue + s.metrics.revenue,
    }), { impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0 });
  }

  getCumulativeCreativeMetrics(campaignId) {
    const totals = {};
    for (const snap of this.getSnapshots(campaignId, 10000)) {
      for (const item of snap.creative_breakdown || []) {
        if (!totals[item.creative_id]) totals[item.creative_id] = { impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0 };
        const t = totals[item.creative_id];
        t.impressions += item.metrics.impressions; t.clicks += item.metrics.clicks;
        t.conversions += item.metrics.conversions; t.spend += item.metrics.spend; t.revenue += item.metrics.revenue;
      }
    }
    return totals;
  }

  resetCampaign(id) {
    this.db.prepare(`DELETE FROM metrics_snapshots WHERE campaign_id = ?`).run(id);
    this.db.prepare(`DELETE FROM decisions WHERE campaign_id = ?`).run(id);
    this.db.prepare(`DELETE FROM creatives WHERE campaign_id = ?`).run(id);
    this.db.prepare(`UPDATE agent_state SET current_tick = 0, bandit_state_json = '{}' WHERE campaign_id = ?`).run(id);
    this._seedCreatives(id);
  }
}

module.exports = { MetricsStore, BID_ACTIONS };
