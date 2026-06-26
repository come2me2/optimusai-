const { randomUUID } = require("crypto");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const BID_ACTIONS = {
  decrease_20: { action: "decrease_bid", pct: -20 },
  decrease_10: { action: "decrease_bid", pct: -10 },
  hold: { action: "hold", pct: 0 },
  increase_5: { action: "increase_bid", pct: 5 },
  increase_10: { action: "increase_bid", pct: 10 },
};

class MetricsStore {
  constructor(dbPath) {
    const dir = path.dirname(dbPath);
    require("fs").mkdirSync(dir, { recursive: true });
    this.db = new DatabaseSync(dbPath);
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
        simulated_hour INTEGER, metrics_json TEXT, kpis_json TEXT, bid REAL, created_at TEXT
      );
      CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT, tick INTEGER,
        action TEXT, bid_change_percent REAL, new_bid REAL, reason TEXT,
        kpis_before_json TEXT, created_at TEXT
      );
      CREATE TABLE IF NOT EXISTS agent_state (
        campaign_id TEXT PRIMARY KEY, current_tick INTEGER DEFAULT 0, bandit_state_json TEXT DEFAULT '{}'
      );
    `);
  }

  createCampaign({ name, daily_budget = 5000, target_cpa = 800, current_bid = 50 }) {
    const id = randomUUID();
    const now = new Date().toISOString();
    this.db
      .prepare(
        `INSERT INTO campaigns VALUES (?, ?, 'yandex_mock', ?, ?, 2500, ?, 'active', ?)`
      )
      .run(id, name, daily_budget, target_cpa, current_bid, now);
    this.db.prepare(`INSERT INTO agent_state (campaign_id) VALUES (?)`).run(id);
    return this.getCampaign(id);
  }

  getCampaign(id) {
    const row = this.db.prepare(`SELECT * FROM campaigns WHERE id = ?`).get(id);
    if (!row) return null;
    return {
      id: row.id,
      name: row.name,
      platform: row.platform,
      daily_budget: row.daily_budget,
      target_cpa: row.target_cpa,
      conversion_value: row.conversion_value,
      current_bid: row.current_bid,
      status: row.status,
    };
  }

  listCampaigns() {
    return this.db.prepare(`SELECT * FROM campaigns ORDER BY created_at DESC`).all().map((row) => ({
      id: row.id,
      name: row.name,
      platform: row.platform,
      daily_budget: row.daily_budget,
      target_cpa: row.target_cpa,
      conversion_value: row.conversion_value,
      current_bid: row.current_bid,
      status: row.status,
    }));
  }

  getActiveCampaign() {
    const list = this.listCampaigns();
    return list[0] || null;
  }

  updateBid(id, bid) {
    this.db.prepare(`UPDATE campaigns SET current_bid = ? WHERE id = ?`).run(bid, id);
  }

  updateTargetCpa(id, target) {
    this.db.prepare(`UPDATE campaigns SET target_cpa = ? WHERE id = ?`).run(target, id);
  }

  getTick(id) {
    const row = this.db.prepare(`SELECT current_tick FROM agent_state WHERE campaign_id = ?`).get(id);
    return row ? row.current_tick : 0;
  }

  setTick(id, tick) {
    this.db.prepare(`UPDATE agent_state SET current_tick = ? WHERE campaign_id = ?`).run(tick, id);
  }

  getBanditState(id) {
    const row = this.db.prepare(`SELECT bandit_state_json FROM agent_state WHERE campaign_id = ?`).get(id);
    return row ? JSON.parse(row.bandit_state_json) : {};
  }

  setBanditState(id, state) {
    this.db
      .prepare(`UPDATE agent_state SET bandit_state_json = ? WHERE campaign_id = ?`)
      .run(JSON.stringify(state), id);
  }

  saveSnapshot(snapshot) {
    this.db
      .prepare(
        `INSERT INTO metrics_snapshots
         (campaign_id, tick, simulated_hour, metrics_json, kpis_json, bid, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        snapshot.campaign_id,
        snapshot.tick,
        snapshot.simulated_hour,
        JSON.stringify(snapshot.metrics),
        JSON.stringify(snapshot.kpis),
        snapshot.bid,
        new Date().toISOString()
      );
  }

  getSnapshots(campaignId, limit = 100) {
    return this.db
      .prepare(`SELECT * FROM metrics_snapshots WHERE campaign_id = ? ORDER BY tick ASC LIMIT ?`)
      .all(campaignId, limit)
      .map((row) => ({
        campaign_id: row.campaign_id,
        tick: row.tick,
        simulated_hour: row.simulated_hour,
        metrics: JSON.parse(row.metrics_json),
        kpis: JSON.parse(row.kpis_json),
        bid: row.bid,
      }));
  }

  saveDecision(d) {
    this.db
      .prepare(
        `INSERT INTO decisions
         (campaign_id, tick, action, bid_change_percent, new_bid, reason, kpis_before_json, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        d.campaign_id,
        d.tick,
        d.action,
        d.bid_change_percent,
        d.new_bid,
        d.reason,
        JSON.stringify(d.kpis_before),
        new Date().toISOString()
      );
  }

  getDecisions(campaignId, limit = 50) {
    return this.db
      .prepare(`SELECT * FROM decisions WHERE campaign_id = ? ORDER BY tick DESC LIMIT ?`)
      .all(campaignId, limit)
      .map((row) => ({
        campaign_id: row.campaign_id,
        tick: row.tick,
        action: row.action,
        bid_change_percent: row.bid_change_percent,
        new_bid: row.new_bid,
        reason: row.reason,
        kpis_before: JSON.parse(row.kpis_before_json),
      }));
  }

  getCumulativeMetrics(campaignId) {
    const snaps = this.getSnapshots(campaignId, 10000);
    return snaps.reduce(
      (t, s) => ({
        impressions: t.impressions + s.metrics.impressions,
        clicks: t.clicks + s.metrics.clicks,
        conversions: t.conversions + s.metrics.conversions,
        spend: t.spend + s.metrics.spend,
        revenue: t.revenue + s.metrics.revenue,
      }),
      { impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0 }
    );
  }

  resetCampaign(id) {
    this.db.prepare(`DELETE FROM metrics_snapshots WHERE campaign_id = ?`).run(id);
    this.db.prepare(`DELETE FROM decisions WHERE campaign_id = ?`).run(id);
    this.db
      .prepare(`UPDATE agent_state SET current_tick = 0, bandit_state_json = '{}' WHERE campaign_id = ?`)
      .run(id);
  }
}

module.exports = { MetricsStore, BID_ACTIONS };
