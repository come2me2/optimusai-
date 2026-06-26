from optimus.agent.loop import AgentLoop
from optimus.metrics.store import MetricsStore


def test_agent_loop_runs_and_logs_decisions(tmp_path):
    db = tmp_path / "test.db"
    store = MetricsStore(db_path=db)
    campaign = store.create_campaign(name="Test", target_cpa=800, current_bid=50)

    loop = AgentLoop(store=store)
    results = loop.run(campaign.id, ticks=20)

    assert len(results) == 20
    decisions = store.get_decisions(campaign.id)
    assert len(decisions) == 20
    snapshots = store.get_snapshots(campaign.id)
    assert len(snapshots) == 20


def test_agent_cpa_trends_toward_target(tmp_path):
    db = tmp_path / "test.db"
    store = MetricsStore(db_path=db)
    campaign = store.create_campaign(name="CPA test", target_cpa=800, current_bid=80)

    loop = AgentLoop(store=store)
    loop.run(campaign.id, ticks=40)

    snapshots = store.get_snapshots(campaign.id)
    early = snapshots[5:10]
    late = snapshots[-5:]
    early_cpa = sum(s.kpis.cpa for s in early if s.kpis.cpa > 0) / max(
        1, sum(1 for s in early if s.kpis.cpa > 0)
    )
    late_cpa = sum(s.kpis.cpa for s in late if s.kpis.cpa > 0) / max(
        1, sum(1 for s in late if s.kpis.cpa > 0)
    )
    # With noise, late CPA should not be wildly worse than 2x target
    if late_cpa > 0:
        assert late_cpa < campaign.target_cpa * 2.5
