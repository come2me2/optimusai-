# Architecture

Optimus AI keeps the decision loop independent of any one ad platform. A CLI command or the dashboard calls the agent. The agent reads KPIs, asks the optimizer for an action, and sends that action through an adapter. The adapter either steps the mock market or, later, calls a live API. Metrics, decisions, creative stats, and bandit state are stored in SQLite.

```
CLI / Dashboard
        │
        ▼
    AgentLoop
        │
        ├── OptimizerEngine (rules + Thompson Sampling)
        ├── CreativeAbEngine (traffic split and pause)
        │
        ▼
 AdPlatformAdapter
        │
        ▼
 MockYandexAdapter → MarketSimulator
        │
        ▼
      SQLite
```

## Agent loop

Each simulated hour runs five steps:

1. **Observe.** The adapter returns impressions, clicks, conversions, spend, and revenue for the period.
2. **Diagnose.** The metrics layer computes CTR, CPC, conversion rate, CPA, and ROAS for the recent window and for the campaign to date.
3. **Decide.** The rule engine proposes bid changes that respect the CPA target, click volume, and daily budget. A Thompson Sampling bandit picks among the proposed steps: −20%, −10%, hold, +5%, and +10%. Reward is based on CPA, so the bandit remembers which steps have worked.
4. **Act.** The adapter applies the new bid. Bids stay inside a fixed floor and ceiling. In parallel, the creative test can move traffic or pause a variant.
5. **Learn.** The bandit updates from the outcome, and the store writes the snapshot and the decision.

Rules cover the cases a buyer would handle by hand: CPA well above target lowers the bid, a healthy CPA with weak delivery can raise it, and a spent budget throttles delivery. The bandit only chooses among actions the rules already allow.

## Mock market

`MarketSimulator` stands in for the auction:

| Factor | Effect |
| --- | --- |
| Bid | Better auction position and more impressions |
| Position | Higher positions raise CTR along an S-shaped curve |
| Hour of day | Peaks around 10–14 and 18–21; nights are quiet |
| Weekday | Weekends are weaker, as in a B2B account |
| Competition | A higher bid costs more per click |
| Shocks | About 4% of hours draw a competitor spike |
| Creative fatigue | CTR falls after the agent flags a tired creative |

The series is noisy, and the rules wait for a minimum number of clicks before they react.

## Creative test

A new campaign starts with two active creatives. After each variant has enough clicks, `CreativeAbEngine` scores them from CTR, conversion rate, and CPA. A modest winner receives more of the impression share. A variant whose CTR is far behind the leader is paused. Per-variant metrics are stored separately and shown on the dashboard.

## Adding a live platform

Implement `AdPlatformAdapter`:

- `get_period_metrics()` and `get_impression_share()` for the latest reporting window
- `set_bid()`, `pause()`, and `resume()` for writes
- `advance_tick()` to move to the next reporting period
- `apply_creative_fatigue()` if the platform can rotate or refresh ads

Register the adapter in `AgentLoop.get_adapter()` for the new `platform` value, and map the platform's report into `PeriodMetrics`. `AgentLoop`, `OptimizerEngine`, and `MetricsStore` stay as they are.

`YandexDirectAdapter` documents that path for Yandex Direct and does not call the network. The live integration needs an OAuth token with the Direct API scope, supplied at runtime. This repository does not contain a token.
