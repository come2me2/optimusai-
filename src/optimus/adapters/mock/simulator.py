import math
import random
from dataclasses import dataclass, field

from optimus.models import PeriodMetrics


def _sample_binomial(n: int, p: float, rng: random.Random) -> int:
    """Approximate binomial draw without numpy."""
    if n <= 0:
        return 0
    if n <= 50:
        return sum(1 for _ in range(n) if rng.random() < p)
    mean = n * p
    std = math.sqrt(mean * (1 - p))
    return max(0, min(n, int(round(rng.gauss(mean, max(std, 0.5))))))


@dataclass
class SimulatorConfig:
    base_market_volume: int = 12000
    market_cpc_floor: float = 15.0
    competition_level: float = 0.55
    base_ctr: float = 0.035
    base_cr: float = 0.08
    conversion_value: float = 2500.0
    random_seed: int = 42


@dataclass
class MarketSimulator:
    """
    Realistic mock ad auction market.

    Physics:
    - Higher bid -> better auction position -> more impressions
    - Position follows S-curve CTR
    - Hour-of-day and day-of-week demand multipliers
    - Competition inflates effective CPC at high bids
  - Random shocks (competitor entry, seasonality)
    """

    config: SimulatorConfig = field(default_factory=SimulatorConfig)
    current_bid: float = 50.0
    creative_fatigue: float = 0.0
    competitor_shock: float = 0.0
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.config.random_seed)

    def reset(self, bid: float = 50.0) -> None:
        self.current_bid = bid
        self.creative_fatigue = 0.0
        self.competitor_shock = 0.0
        self._rng = random.Random(self.config.random_seed)

    def set_bid(self, bid: float) -> float:
        self.current_bid = max(5.0, min(bid, 500.0))
        return self.current_bid

    def apply_creative_fatigue(self) -> None:
        self.creative_fatigue = min(0.5, self.creative_fatigue + 0.08)

    def _hour_multiplier(self, hour: int) -> float:
        # Peak hours 10-14 and 18-21
        if 10 <= hour <= 14:
            return 1.25
        if 18 <= hour <= 21:
            return 1.15
        if 0 <= hour <= 6:
            return 0.45
        return 0.85

    def _day_multiplier(self, day: int) -> float:
        # day 0=Mon, 6=Sun; weekends lower B2B demand
        if day >= 5:
            return 0.75
        return 1.0

    def _auction_position(self, bid: float) -> float:
        """Map bid to auction position score 0..1."""
        market_bid = 35.0 + self.competitor_shock * 20.0
        ratio = bid / max(market_bid, 1.0)
        return 1.0 / (1.0 + math.exp(-2.5 * (ratio - 1.0)))

    def impression_share(self, bid: float) -> float:
        position = self._auction_position(bid)
        share = 0.15 + 0.75 * position
        return min(0.98, max(0.05, share))

    def simulate_hour(
        self,
        simulated_hour: int,
        daily_budget: float,
        spend_so_far_today: float = 0.0,
    ) -> PeriodMetrics:
        hour_of_day = simulated_hour % 24
        day_of_week = (simulated_hour // 24) % 7

        # Occasional market shocks (~4% per hour)
        if self._rng.random() < 0.04:
            self.competitor_shock = self._rng.uniform(0.0, 1.0)

        demand = (
            self.config.base_market_volume
            * self._hour_multiplier(hour_of_day)
            * self._day_multiplier(day_of_week)
            * (1.0 - self.competitor_shock * 0.15)
        )

        share = self.impression_share(self.current_bid)
        noise = self._rng.uniform(0.85, 1.15)
        impressions = int(demand * share * noise / 24.0)
        impressions = max(0, impressions)

        position = self._auction_position(self.current_bid)
        ctr_base = self.config.base_ctr * (0.6 + 0.8 * position)
        ctr = ctr_base * (1.0 - self.creative_fatigue) * self._rng.uniform(0.9, 1.1)
        ctr = max(0.005, min(ctr, 0.12))

        clicks = _sample_binomial(impressions, ctr, self._rng) if impressions > 0 else 0

        # Competition inflates CPC when bid is high relative to market
        market_pressure = 1.0 + self.config.competition_level * position
        effective_cpc = self.current_bid * market_pressure * self._rng.uniform(0.92, 1.08)
        effective_cpc = max(self.config.market_cpc_floor, effective_cpc)

        spend = clicks * effective_cpc

        # Budget cap per hour slice
        hourly_budget = daily_budget / 24.0
        if spend > hourly_budget * 1.2:
            scale = (hourly_budget * 1.2) / spend
            clicks = int(clicks * scale)
            spend = clicks * effective_cpc

        if spend_so_far_today + spend > daily_budget:
            remaining = max(0.0, daily_budget - spend_so_far_today)
            if spend > 0:
                scale = remaining / spend
                clicks = int(clicks * scale)
                spend = clicks * effective_cpc

        cr = self.config.base_cr * self._rng.uniform(0.85, 1.15)
        cr = max(0.02, min(cr, 0.2))
        conversions = _sample_binomial(clicks, cr, self._rng) if clicks > 0 else 0
        revenue = conversions * self.config.conversion_value

        return PeriodMetrics(
            impressions=impressions,
            clicks=clicks,
            conversions=conversions,
            spend=round(spend, 2),
            revenue=round(revenue, 2),
        )
