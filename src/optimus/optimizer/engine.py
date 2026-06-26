import random
from dataclasses import dataclass

from optimus.models import ActionType, Campaign, Decision, KPIs
from optimus.optimizer.bandit import BidBandit
from optimus.optimizer.rules import BID_ACTIONS, RuleCandidate, RuleEngine


@dataclass
class OptimizerResult:
    decision: Decision
    action_key: str
    apply_creative_fatigue: bool = False


class OptimizerEngine:
    def __init__(self, rule_engine: RuleEngine | None = None) -> None:
        self.rule_engine = rule_engine or RuleEngine()

    def decide(
        self,
        campaign: Campaign,
        tick: int,
        window_kpis: KPIs,
        cumulative_kpis: KPIs,
        window_clicks: int,
        spend_today: float,
        simulated_hour: int,
        bandit: BidBandit,
        rng: random.Random | None = None,
    ) -> OptimizerResult:
        spend_rate = spend_today / campaign.daily_budget if campaign.daily_budget > 0 else 0.0

        candidates = self.rule_engine.evaluate(
            campaign=campaign,
            window_kpis=window_kpis,
            cumulative_kpis=cumulative_kpis,
            window_clicks=window_clicks,
            spend_rate=spend_rate,
            simulated_hour=simulated_hour,
        )

        candidate_keys = list(dict.fromkeys(c.action_key for c in candidates))
        chosen_key = bandit.select(candidate_keys, rng=rng)

        chosen_rule = next((c for c in candidates if c.action_key == chosen_key), candidates[0])
        action, bid_change = BID_ACTIONS.get(chosen_key, (ActionType.HOLD, 0.0))

        if chosen_rule.action == ActionType.CREATIVE_FATIGUE:
            new_bid = campaign.current_bid
            reason = chosen_rule.reason
            apply_fatigue = True
            action = ActionType.CREATIVE_FATIGUE
            bid_change = 0.0
        elif chosen_rule.action == ActionType.THROTTLE:
            new_bid = campaign.current_bid * (1.0 + bid_change / 100.0)
            reason = chosen_rule.reason
            apply_fatigue = False
            action = ActionType.THROTTLE
        else:
            new_bid = campaign.current_bid * (1.0 + bid_change / 100.0)
            reason = chosen_rule.reason + f" (bandit: {chosen_key})"
            apply_fatigue = False

        new_bid = max(5.0, min(round(new_bid, 2), 500.0))

        decision = Decision(
            campaign_id=campaign.id,
            tick=tick,
            action=action,
            bid_change_percent=bid_change,
            new_bid=new_bid,
            reason=reason,
            kpis_before=window_kpis,
        )

        return OptimizerResult(
            decision=decision,
            action_key=chosen_key,
            apply_creative_fatigue=apply_fatigue,
        )
