from dataclasses import dataclass
from typing import Optional

from optimus.models import ActionType, Campaign, KPIs


BID_ACTIONS: dict[str, tuple[ActionType, float]] = {
    "decrease_20": (ActionType.DECREASE_BID, -20.0),
    "decrease_10": (ActionType.DECREASE_BID, -10.0),
    "hold": (ActionType.HOLD, 0.0),
    "increase_5": (ActionType.INCREASE_BID, 5.0),
    "increase_10": (ActionType.INCREASE_BID, 10.0),
}


@dataclass
class RuleCandidate:
    action_key: str
    action: ActionType
    bid_change_percent: float
    reason: str
    priority: int = 0


class RuleEngine:
    """Marketing heuristics — proposes safe bid actions based on KPIs."""

    MIN_CLICKS = 15
    BENCHMARK_CTR = 0.03

    def evaluate(
        self,
        campaign: Campaign,
        window_kpis: KPIs,
        cumulative_kpis: KPIs,
        window_clicks: int,
        spend_rate: float,
        simulated_hour: int,
    ) -> list[RuleCandidate]:
        candidates: list[RuleCandidate] = []
        target = campaign.target_cpa
        cpa = window_kpis.cpa if window_kpis.cpa > 0 else cumulative_kpis.cpa
        ctr = window_kpis.ctr if window_kpis.ctr > 0 else cumulative_kpis.ctr
        hour_of_day = simulated_hour % 24

        if window_clicks >= self.MIN_CLICKS and cpa > 0:
            if cpa > target * 1.25:
                candidates.append(
                    RuleCandidate(
                        action_key="decrease_10",
                        action=ActionType.DECREASE_BID,
                        bid_change_percent=-10.0,
                        reason=f"CPA {cpa:.0f} > target {target:.0f} × 1.25 — снижаю ставку",
                        priority=10,
                    )
                )
                if cpa > target * 1.5:
                    candidates.append(
                        RuleCandidate(
                            action_key="decrease_20",
                            action=ActionType.DECREASE_BID,
                            bid_change_percent=-20.0,
                            reason=f"CPA {cpa:.0f} сильно выше target — агрессивное снижение",
                            priority=12,
                        )
                    )
            elif cpa < target * 0.85 and window_kpis.impression_share < 0.7:
                candidates.append(
                    RuleCandidate(
                        action_key="increase_5",
                        action=ActionType.INCREASE_BID,
                        bid_change_percent=5.0,
                        reason=(
                            f"CPA {cpa:.0f} ниже target, доля показов "
                            f"{window_kpis.impression_share:.0%} — наращиваю"
                        ),
                        priority=8,
                    )
                )
                candidates.append(
                    RuleCandidate(
                        action_key="increase_10",
                        action=ActionType.INCREASE_BID,
                        bid_change_percent=10.0,
                        reason=f"CPA {cpa:.0f} хороший, можно масштабировать",
                        priority=6,
                    )
                )

        if ctr > 0 and ctr < self.BENCHMARK_CTR * 0.6 and window_clicks >= 10:
            candidates.append(
                RuleCandidate(
                    action_key="hold",
                    action=ActionType.CREATIVE_FATIGUE,
                    bid_change_percent=0.0,
                    reason=f"CTR {ctr:.2%} низкий — усталость креатива, не трогаю ставку",
                    priority=9,
                )
            )

        if spend_rate > 0.9 and hour_of_day < 18:
            candidates.append(
                RuleCandidate(
                    action_key="decrease_10",
                    action=ActionType.THROTTLE,
                    bid_change_percent=-10.0,
                    reason=f"Расход {spend_rate:.0%} дневного бюджета до 18:00 — дросселирую",
                    priority=11,
                )
            )

        if not candidates:
            candidates.append(
                RuleCandidate(
                    action_key="hold",
                    action=ActionType.HOLD,
                    bid_change_percent=0.0,
                    reason="Метрики в норме или мало данных — удерживаю ставку",
                    priority=1,
                )
            )

        candidates.sort(key=lambda c: c.priority, reverse=True)
        return candidates
