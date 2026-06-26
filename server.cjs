const express = require("express");
const path = require("path");
const { MetricsStore } = require("./lib/store.cjs");
const { computeKpis } = require("./lib/metrics.cjs");
const { AgentLoop } = require("./lib/agent.cjs");

const port = Number(process.env.PORT || 8000);
const host = process.env.HOST || "0.0.0.0";
const dataDir = process.env.OPTIMUS_DATA_DIR || path.join("/tmp", "optimus-data");
const dbPath = process.env.OPTIMUS_DB_PATH || path.join(dataDir, "optimus.db");
const staticDir = process.env.OPTIMUS_STATIC_DIR || path.join(__dirname, "static");

console.log(`[optimus] starting on ${host}:${port} (runtime: ${typeof Bun !== "undefined" ? "bun" : "node"})`);

const store = new MetricsStore(dbPath);
const loop = new AgentLoop(store);
const app = express();

app.use(express.json());
app.use("/static", express.static(staticDir));

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.get("/", (_req, res) => {
  res.sendFile(path.join(staticDir, "index.html"));
});

app.get("/campaigns", (_req, res) => res.json(store.listCampaigns()));

app.post("/campaigns", (req, res) => {
  const { name = "Тест CPA", daily_budget = 5000, target_cpa = 800, current_bid = 50 } = req.body || {};
  res.json(store.createCampaign({ name, daily_budget, target_cpa, current_bid }));
});

app.get("/campaigns/:id", (req, res) => {
  const campaign = store.getCampaign(req.params.id);
  if (!campaign) return res.status(404).json({ detail: "Campaign not found" });
  const cumulative = store.getCumulativeMetrics(req.params.id);
  res.json({
    campaign,
    tick: store.getTick(req.params.id),
    cumulative_metrics: cumulative,
    kpis: computeKpis(cumulative),
  });
});

app.patch("/campaigns/:id/target-cpa", (req, res) => {
  const campaign = store.getCampaign(req.params.id);
  if (!campaign) return res.status(404).json({ detail: "Campaign not found" });
  store.updateTargetCpa(req.params.id, req.body.target_cpa);
  res.json({ target_cpa: req.body.target_cpa });
});

app.post("/campaigns/:id/reset", (req, res) => {
  const campaign = store.getCampaign(req.params.id);
  if (!campaign) return res.status(404).json({ detail: "Campaign not found" });
  store.resetCampaign(req.params.id);
  loop.resetAdapter(req.params.id);
  res.json({ status: "reset" });
});

app.post("/agent/tick", (req, res) => {
  const campaignId = req.query.campaign_id;
  const campaign = campaignId ? store.getCampaign(campaignId) : store.getActiveCampaign();
  if (!campaign) return res.status(404).json({ detail: "No campaign found" });
  res.json(loop.tick(campaign.id));
});

app.post("/agent/run", (req, res) => {
  const campaignId = req.query.campaign_id;
  const campaign = campaignId ? store.getCampaign(campaignId) : store.getActiveCampaign();
  if (!campaign) return res.status(404).json({ detail: "No campaign found" });
  const ticks = req.body?.ticks ?? 1;
  const results = loop.run(campaign.id, ticks);
  res.json({ results, count: results.length });
});

app.get("/metrics/:id", (req, res) => {
  const limit = Number(req.query.limit || 100);
  res.json(store.getSnapshots(req.params.id, limit));
});

app.get("/decisions/:id", (req, res) => {
  const limit = Number(req.query.limit || 50);
  res.json(store.getDecisions(req.params.id, limit));
});

app.get("/creatives/:id", (req, res) => {
  const campaign = store.getCampaign(req.params.id);
  if (!campaign) return res.status(404).json({ detail: "Campaign not found" });
  const creatives = store.getCreatives(req.params.id);
  const cum = store.getCumulativeCreativeMetrics(req.params.id);
  res.json(creatives.map((c) => ({
    creative: c,
    metrics: cum[c.id] || { impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0 },
    kpis: computeKpis(cum[c.id] || {}),
  })));
});

app.listen(port, host, () => {
  console.log(`[optimus] ready http://${host}:${port} health=/health`);
});
