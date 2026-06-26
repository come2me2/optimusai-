from optimus.adapters.base import AdPlatformAdapter
from optimus.adapters.mock.yandex import MockYandexAdapter
from optimus.metrics.calculator import compute_kpis, compute_window_kpis
from optimus.metrics.store import MetricsStore
from optimus.models import (
    ActionType,
    BidHistoryEntry,
    Campaign,
    CampaignStatus,
    MetricsSnapshot,
    PeriodMetrics,
)
from optimus.optimizer.bandit import BidBandit
from optimus.optimizer.creative_ab import CreativeAbEngine
from optimus.optimizer.engine import OptimizerEngine


class AgentLoop:
    """Observe → Diagnose → Decide → Act → Learn."""

    def __init__(
        self,
        store: MetricsStore | None = None,
        adapter: AdPlatformAdapter | None = None,
        optimizer: OptimizerEngine | None = None,
    ) -> None:
        self.store = store or MetricsStore()
        self.optimizer = optimizer or OptimizerEngine()
        self.creative_ab = CreativeAbEngine()
        self._adapters: dict[str, AdPlatformAdapter] = {}

    def get_adapter(self, campaign: Campaign) -> AdPlatformAdapter:
        if campaign.id not in self._adapters:
            if campaign.platform == "yandex_mock":
                adapter = MockYandexAdapter(
                    conversion_value=campaign.conversion_value,
                    random_seed=hash(campaign.id) % 10000,
                )
                adapter.reset(bid=campaign.current_bid)
            else:
                raise ValueError(f"Unknown platform: {campaign.platform}")
            self._adapters[campaign.id] = adapter
        return self._adapters[campaign.id]

    def reset_adapter(self, campaign: Campaign) -> None:
        if campaign.id in self._adapters:
            del self._adapters[campaign.id]

    def tick(self, campaign_id: str) -> dict:
        campaign = self.store.get_campaign(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign not found: {campaign_id}")

        adapter = self.get_adapter(campaign)
        tick = self.store.get_tick(campaign_id)
        simulated_hour = tick
        creatives = self.store.get_creatives(campaign_id)

        # --- Observe ---
        if isinstance(adapter, MockYandexAdapter):
            period, creative_breakdown = adapter.advance_tick_for_campaign(
                campaign, simulated_hour, creatives
            )
        else:
            adapter.advance_tick(simulated_hour)
            period = adapter.get_period_metrics(campaign)
            creative_breakdown = []

        impression_share = adapter.get_impression_share(campaign)
        kpis = compute_kpis(period, impression_share=impression_share)

        snapshot = MetricsSnapshot(
            campaign_id=campaign_id,
            tick=tick,
            simulated_hour=simulated_hour,
            metrics=period,
            kpis=kpis,
            bid=campaign.current_bid,
            creative_breakdown=creative_breakdown,
        )
        self.store.save_snapshot(snapshot)

        snapshots = self.store.get_snapshots(campaign_id)
        window_kpis = compute_window_kpis(snapshots, window=6)
        cumulative = self.store.get_cumulative_metrics(campaign_id)
        cumulative_kpis = compute_kpis(
            cumulative,
            impression_share=window_kpis.impression_share,
        )

        window_clicks = sum(s.metrics.clicks for s in snapshots[-6:])

        # Spend today for budget throttle
        spend_today = sum(
            s.metrics.spend
            for s in snapshots
            if s.simulated_hour // 24 == simulated_hour // 24
        )

        bandit = BidBandit.from_state(self.store.get_bandit_state(campaign_id))

        # --- Decide ---
        result = self.optimizer.decide(
            campaign=campaign,
            tick=tick,
            window_kpis=window_kpis,
            cumulative_kpis=cumulative_kpis,
            window_clicks=window_clicks,
            spend_today=spend_today,
            simulated_hour=simulated_hour,
            bandit=bandit,
        )

        old_bid = campaign.current_bid
        decision = result.decision

        # --- Act ---
        if result.apply_creative_fatigue:
            adapter.apply_creative_fatigue()
        elif decision.action in (
            ActionType.INCREASE_BID,
            ActionType.DECREASE_BID,
            ActionType.THROTTLE,
        ):
            adapter.set_bid(campaign, decision.new_bid)
            self.store.update_campaign_bid(campaign_id, decision.new_bid)
        elif decision.action == ActionType.PAUSE:
            adapter.pause(campaign)
            self.store.update_campaign_status(campaign_id, CampaignStatus.PAUSED)

        if decision.new_bid != old_bid:
            self.store.save_bid_history(
                BidHistoryEntry(
                    campaign_id=campaign_id,
                    tick=tick,
                    old_bid=old_bid,
                    new_bid=decision.new_bid,
                    action=decision.action,
                )
            )

        self.store.save_decision(decision)

        # --- Creative A/B ---
        cum_creative = self.store.get_cumulative_creative_metrics(campaign_id)
        ab_result = self.creative_ab.evaluate(
            campaign_id=campaign_id,
            tick=tick,
            creatives=creatives,
            cumulative_by_creative=cum_creative,
            window_kpis=window_kpis,
            current_bid=decision.new_bid,
        )
        if ab_result.decision:
            self.store.save_decision(ab_result.decision)
            self.store.save_creatives(ab_result.updated_creatives)

        # --- Learn ---
        reward = bandit.compute_reward(
            cpa=window_kpis.cpa if window_kpis.cpa > 0 else cumulative_kpis.cpa,
            target_cpa=campaign.target_cpa,
        )
        bandit.update(result.action_key, reward)
        self.store.set_bandit_state(campaign_id, bandit.to_state())

        self.store.set_tick(campaign_id, tick + 1)

        return {
            "tick": tick,
            "simulated_hour": simulated_hour,
            "period_metrics": period.model_dump(),
            "kpis": kpis.model_dump(),
            "window_kpis": window_kpis.model_dump(),
            "cumulative_kpis": cumulative_kpis.model_dump(),
            "decision": decision.model_dump(),
            "creative_decision": ab_result.decision.model_dump() if ab_result.decision else None,
            "creatives": [c.model_dump() for c in ab_result.updated_creatives],
            "bid": decision.new_bid,
        }

    def run(self, campaign_id: str, ticks: int = 1) -> list[dict]:
        results = []
        for _ in range(ticks):
            results.append(self.tick(campaign_id))
        return results
