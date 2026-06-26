import pytest

from optimus.adapters.mock.simulator import MarketSimulator, SimulatorConfig
from optimus.metrics.calculator import compute_kpis
from optimus.models import Campaign, PeriodMetrics
from optimus.optimizer.bandit import BidBandit
from optimus.optimizer.engine import OptimizerEngine
from optimus.optimizer.rules import RuleEngine


def test_higher_bid_more_impressions():
    sim_low = MarketSimulator(config=SimulatorConfig(random_seed=1))
    sim_low.set_bid(30.0)
    sim_high = MarketSimulator(config=SimulatorConfig(random_seed=1))
    sim_high.set_bid(80.0)

    low = sim_low.simulate_hour(12, daily_budget=10000)
    high = sim_high.simulate_hour(12, daily_budget=10000)

    assert high.impressions >= low.impressions


def test_impression_share_increases_with_bid():
    sim = MarketSimulator()
    low_share = sim.impression_share(20.0)
    high_share = sim.impression_share(100.0)
    assert high_share > low_share


def test_compute_kpis():
    metrics = PeriodMetrics(impressions=1000, clicks=50, conversions=5, spend=2500, revenue=12500)
    kpis = compute_kpis(metrics)
    assert kpis.ctr == pytest.approx(0.05)
    assert kpis.cpc == pytest.approx(50.0)
    assert kpis.cpa == pytest.approx(500.0)
    assert kpis.roas == pytest.approx(5.0)


def test_rule_engine_decreases_bid_on_high_cpa():
    engine = RuleEngine()
    campaign = Campaign(id="1", name="t", target_cpa=800, current_bid=50)
    kpis = compute_kpis(PeriodMetrics(impressions=5000, clicks=100, conversions=5, spend=6000))
    kpis.impression_share = 0.5

    candidates = engine.evaluate(
        campaign=campaign,
        window_kpis=kpis,
        cumulative_kpis=kpis,
        window_clicks=100,
        spend_rate=0.5,
        simulated_hour=14,
    )
    actions = [c.action_key for c in candidates]
    assert "decrease_10" in actions or "decrease_20" in actions


def test_optimizer_decreases_bid_when_cpa_high():
    campaign = Campaign(id="1", name="t", target_cpa=800, current_bid=60)
    kpis = compute_kpis(PeriodMetrics(impressions=8000, clicks=120, conversions=6, spend=7200))
    kpis.impression_share = 0.55

    optimizer = OptimizerEngine()
    bandit = BidBandit()
    result = optimizer.decide(
        campaign=campaign,
        tick=10,
        window_kpis=kpis,
        cumulative_kpis=kpis,
        window_clicks=120,
        spend_today=3000,
        simulated_hour=14,
        bandit=bandit,
    )
    assert result.decision.new_bid <= campaign.current_bid or result.decision.action.value == "creative_fatigue"


def test_bandit_reward_lower_cpa_is_better():
    bandit = BidBandit()
    assert bandit.compute_reward(600, 800) > bandit.compute_reward(1200, 800)


def test_bandit_learns_from_updates():
    bandit = BidBandit()
    for _ in range(20):
        bandit.update("decrease_10", 0.9)
    for _ in range(20):
        bandit.update("increase_10", 0.1)

    chosen = bandit.select(["decrease_10", "increase_10"])
    assert chosen == "decrease_10"
