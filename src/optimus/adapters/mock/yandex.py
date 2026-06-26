from optimus.adapters.base import AdPlatformAdapter
from optimus.adapters.mock.simulator import MarketSimulator, SimulatorConfig
from optimus.models import Campaign, PeriodMetrics


class MockYandexAdapter(AdPlatformAdapter):
    """Mock Yandex Direct adapter backed by MarketSimulator."""

    def __init__(self, conversion_value: float = 2500.0, random_seed: int = 42) -> None:
        config = SimulatorConfig(
            conversion_value=conversion_value,
            random_seed=random_seed,
        )
        self.simulator = MarketSimulator(config=config)
        self._spend_today: float = 0.0
        self._last_day: int = -1
        self._paused: bool = False
        self._last_period_metrics = PeriodMetrics()

    def reset(self, bid: float = 50.0) -> None:
        self.simulator.reset(bid=bid)
        self._spend_today = 0.0
        self._last_day = -1
        self._paused = False

    def get_period_metrics(self, campaign: Campaign) -> PeriodMetrics:
        if self._paused or campaign.status.value == "paused":
            return PeriodMetrics()
        return self._last_period_metrics

    def get_impression_share(self, campaign: Campaign) -> float:
        return self.simulator.impression_share(campaign.current_bid)

    def set_bid(self, campaign: Campaign, new_bid: float) -> float:
        return self.simulator.set_bid(new_bid)

    def pause(self, campaign: Campaign) -> None:
        self._paused = True

    def resume(self, campaign: Campaign) -> None:
        self._paused = False

    def advance_tick(self, simulated_hour: int) -> None:
        day = simulated_hour // 24
        if day != self._last_day:
            self._spend_today = 0.0
            self._last_day = day

        if self._paused:
            self._last_period_metrics = PeriodMetrics()
            return

        self.simulator.config.conversion_value = 2500.0  # overridden per campaign in loop
        self._last_period_metrics = self.simulator.simulate_hour(
            simulated_hour=simulated_hour,
            daily_budget=5000.0,
            spend_so_far_today=self._spend_today,
        )
        self._spend_today += self._last_period_metrics.spend

    def advance_tick_for_campaign(self, campaign: Campaign, simulated_hour: int) -> PeriodMetrics:
        """Advance tick with campaign-specific budget and conversion value."""
        day = simulated_hour // 24
        if day != self._last_day:
            self._spend_today = 0.0
            self._last_day = day

        if self._paused or campaign.status.value == "paused":
            self._last_period_metrics = PeriodMetrics()
            return self._last_period_metrics

        self.simulator.config.conversion_value = campaign.conversion_value
        self._last_period_metrics = self.simulator.simulate_hour(
            simulated_hour=simulated_hour,
            daily_budget=campaign.daily_budget,
            spend_so_far_today=self._spend_today,
        )
        self._spend_today += self._last_period_metrics.spend
        return self._last_period_metrics

    def apply_creative_fatigue(self) -> None:
        self.simulator.apply_creative_fatigue()
