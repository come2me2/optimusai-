import random
from dataclasses import dataclass, field

from optimus.optimizer.rules import BID_ACTIONS


@dataclass
class ArmState:
    alpha: float = 1.0
    beta: float = 1.0
    pulls: int = 0


@dataclass
class BidBandit:
    """
    Thompson Sampling over discrete bid actions.
    Learns which bid adjustments work for this mock market.
    """

    arms: dict[str, ArmState] = field(default_factory=dict)
    exploration_rate: float = 0.15

    def _ensure_arms(self) -> None:
        for key in BID_ACTIONS:
            if key not in self.arms:
                self.arms[key] = ArmState()

    @classmethod
    def from_state(cls, state: dict) -> "BidBandit":
        bandit = cls()
        for key, vals in state.get("arms", {}).items():
            bandit.arms[key] = ArmState(
                alpha=vals.get("alpha", 1.0),
                beta=vals.get("beta", 1.0),
                pulls=vals.get("pulls", 0),
            )
        bandit.exploration_rate = state.get("exploration_rate", 0.15)
        return bandit

    def to_state(self) -> dict:
        return {
            "exploration_rate": self.exploration_rate,
            "arms": {
                k: {"alpha": v.alpha, "beta": v.beta, "pulls": v.pulls}
                for k, v in self.arms.items()
            },
        }

    def select(self, candidate_keys: list[str], rng: random.Random | None = None) -> str:
        self._ensure_arms()
        rng = rng or random.Random()

        available = [k for k in candidate_keys if k in BID_ACTIONS]
        if not available:
            return "hold"

        if rng.random() < self.exploration_rate:
            return rng.choice(available)

        best_key = available[0]
        best_sample = -1.0
        for key in available:
            arm = self.arms[key]
            sample = rng.betavariate(arm.alpha, arm.beta)
            if sample > best_sample:
                best_sample = sample
                best_key = key
        return best_key

    def update(self, action_key: str, reward: float) -> None:
        self._ensure_arms()
        if action_key not in self.arms:
            return
        arm = self.arms[action_key]
        # reward in [0, 1]
        success = max(0.0, min(1.0, reward))
        arm.alpha += success
        arm.beta += 1.0 - success
        arm.pulls += 1

    def compute_reward(self, cpa: float, target_cpa: float) -> float:
        """Higher reward when CPA is closer to or below target."""
        if cpa <= 0 or target_cpa <= 0:
            return 0.5
        ratio = cpa / target_cpa
        if ratio <= 1.0:
            return min(1.0, 0.7 + (1.0 - ratio) * 0.3)
        return max(0.0, 1.0 - (ratio - 1.0) * 0.5)
