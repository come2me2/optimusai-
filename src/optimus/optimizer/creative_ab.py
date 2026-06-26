from dataclasses import dataclass

from optimus.metrics.calculator import compute_kpis
from optimus.models import (
    ActionType,
    Creative,
    CreativeStatus,
    Decision,
    KPIs,
    PeriodMetrics,
)


@dataclass
class CreativeAbResult:
    decision: Decision | None
    updated_creatives: list[Creative]


class CreativeAbEngine:
    """A/B testing: compare creatives by CTR/CPA and shift traffic or pause losers."""

    MIN_CLICKS = 25
    SHIFT_PERCENT = 0.15

    def evaluate(
        self,
        campaign_id: str,
        tick: int,
        creatives: list[Creative],
        cumulative_by_creative: dict[str, PeriodMetrics],
        window_kpis: KPIs,
        current_bid: float,
    ) -> CreativeAbResult:
        active = [c for c in creatives if c.status == CreativeStatus.ACTIVE]
        if len(active) < 2:
            return CreativeAbResult(decision=None, updated_creatives=creatives)

        stats: list[tuple[Creative, KPIs, PeriodMetrics, float]] = []
        for c in active:
            pm = cumulative_by_creative.get(c.id, PeriodMetrics())
            if pm.clicks < self.MIN_CLICKS:
                return CreativeAbResult(decision=None, updated_creatives=creatives)
            kpis = compute_kpis(pm)
            score = kpis.ctr * max(kpis.cr, 0.01) / max(kpis.cpa, 1)
            stats.append((c, kpis, pm, score))

        stats.sort(key=lambda x: x[3], reverse=True)
        best_creative, best_kpis, _, _ = stats[0]
        worst_creative, worst_kpis, worst_pm, _ = stats[-1]

        updated = [c.model_copy() for c in creatives]

        if worst_kpis.ctr < best_kpis.ctr * 0.55 and worst_pm.clicks >= self.MIN_CLICKS:
            return self._pause_creative(
                campaign_id, tick, updated, worst_creative, best_creative,
                worst_kpis, best_kpis, current_bid, window_kpis,
            )

        if best_kpis.ctr > worst_kpis.ctr * 1.12 and (
            worst_kpis.cpa == 0 or best_kpis.cpa < worst_kpis.cpa * 0.95
        ):
            return self._shift_traffic(
                campaign_id, tick, updated, best_creative, worst_creative,
                best_kpis, worst_kpis, current_bid, window_kpis,
            )

        return CreativeAbResult(decision=None, updated_creatives=creatives)

    def _shift_traffic(
        self,
        campaign_id: str,
        tick: int,
        creatives: list[Creative],
        winner: Creative,
        loser: Creative,
        winner_kpis: KPIs,
        loser_kpis: KPIs,
        bid: float,
        window_kpis: KPIs,
    ) -> CreativeAbResult:
        shift = self.SHIFT_PERCENT
        for c in creatives:
            if c.id == winner.id:
                c.traffic_weight = min(0.95, c.traffic_weight + shift)
            elif c.id == loser.id:
                c.traffic_weight = max(0.05, c.traffic_weight - shift)
        self._normalize_weights(creatives)
        decision = Decision(
            campaign_id=campaign_id,
            tick=tick,
            action=ActionType.SHIFT_CREATIVE,
            new_bid=bid,
            reason=(
                f"A/B: {winner.variant} CTR {winner_kpis.ctr:.2%} / CPA {winner_kpis.cpa:.0f} лучше "
                f"{loser.variant} — переключаю +{shift:.0%} трафика на победителя"
            ),
            kpis_before=window_kpis,
            creative_id=winner.id,
        )
        return CreativeAbResult(decision=decision, updated_creatives=creatives)

    def _pause_creative(
        self,
        campaign_id: str,
        tick: int,
        creatives: list[Creative],
        loser: Creative,
        winner: Creative,
        loser_kpis: KPIs,
        winner_kpis: KPIs,
        bid: float,
        window_kpis: KPIs,
    ) -> CreativeAbResult:
        freed = 0.0
        active_others = 0
        for c in creatives:
            if c.id == loser.id:
                freed = c.traffic_weight
                c.status = CreativeStatus.PAUSED
                c.traffic_weight = 0.0
            elif c.status == CreativeStatus.ACTIVE:
                active_others += 1
        if active_others > 0:
            bonus = freed / active_others
            for c in creatives:
                if c.status == CreativeStatus.ACTIVE:
                    c.traffic_weight += bonus
        self._normalize_weights(creatives)
        decision = Decision(
            campaign_id=campaign_id,
            tick=tick,
            action=ActionType.PAUSE_CREATIVE,
            new_bid=bid,
            reason=(
                f"A/B: пауза {loser.variant} (CTR {loser_kpis.ctr:.2%}) — "
                f"трафик на {winner.variant} (CTR {winner_kpis.ctr:.2%})"
            ),
            kpis_before=window_kpis,
            creative_id=loser.id,
        )
        return CreativeAbResult(decision=decision, updated_creatives=creatives)

    @staticmethod
    def _normalize_weights(creatives: list[Creative]) -> None:
        active = [c for c in creatives if c.status == CreativeStatus.ACTIVE]
        total = sum(c.traffic_weight for c in active)
        if total <= 0:
            w = 1.0 / len(active) if active else 1.0
            for c in active:
                c.traffic_weight = w
            return
        for c in active:
            c.traffic_weight = round(c.traffic_weight / total, 4)
