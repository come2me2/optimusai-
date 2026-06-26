import pytest

from optimus.adapters.mock.simulator import MarketSimulator, SimulatorConfig
from optimus.metrics.store import MetricsStore
from optimus.models import Creative, CreativeStatus, PeriodMetrics
from optimus.optimizer.creative_ab import CreativeAbEngine


def _creative(cid, variant, mult, weight=0.5):
    return Creative(
        id=cid,
        campaign_id="camp",
        variant=variant,
        name=f"Creative {variant}",
        headline=f"Headline {variant}",
        traffic_weight=weight,
        ctr_multiplier=mult,
        status=CreativeStatus.ACTIVE,
    )


def test_simulator_splits_traffic_by_weight():
    sim = MarketSimulator(config=SimulatorConfig(random_seed=7))
    sim.reset(50)
    creatives = [
        _creative("a", "A", 1.0, 0.7),
        _creative("b", "B", 1.2, 0.3),
    ]
    total, breakdown = sim.simulate_hour_with_creatives(12, 5000, 0, creatives)
    assert len(breakdown) == 2
    assert total.impressions == breakdown[0].metrics.impressions + breakdown[1].metrics.impressions
    assert breakdown[0].metrics.impressions >= breakdown[1].metrics.impressions


def test_creative_ab_shifts_traffic_to_winner():
    engine = CreativeAbEngine()
    creatives = [_creative("a", "A", 1.0), _creative("b", "B", 0.8)]
    cumulative = {
        "a": PeriodMetrics(impressions=5000, clicks=250, conversions=25, spend=5000, revenue=62500),
        "b": PeriodMetrics(impressions=5000, clicks=150, conversions=8, spend=15000, revenue=20000),
    }
    from optimus.models import KPIs
    result = engine.evaluate("camp", 10, creatives, cumulative, KPIs(), 50)
    assert result.decision is not None
    assert result.decision.action.value == "shift_creative"
    winner = next(c for c in result.updated_creatives if c.id == "a")
    loser = next(c for c in result.updated_creatives if c.id == "b")
    assert winner.traffic_weight > loser.traffic_weight


def test_campaign_seeds_default_creatives(tmp_path):
    store = MetricsStore(db_path=tmp_path / "t.db")
    campaign = store.create_campaign(name="AB test")
    creatives = store.get_creatives(campaign.id)
    assert len(creatives) == 2
    assert {c.variant for c in creatives} == {"A", "B"}


def test_agent_logs_creative_decisions(tmp_path):
    from optimus.agent.loop import AgentLoop

    store = MetricsStore(db_path=tmp_path / "t.db")
    campaign = store.create_campaign(name="AB loop")
    loop = AgentLoop(store=store)
    loop.run(campaign.id, ticks=40)
    decisions = store.get_decisions(campaign.id, limit=100)
    actions = {d.action.value for d in decisions}
    assert any(a in actions for a in ("shift_creative", "pause_creative", "hold", "decrease_bid", "increase_bid"))
