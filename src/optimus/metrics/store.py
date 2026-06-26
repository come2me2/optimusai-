import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from uuid import uuid4

from optimus.models import (
    ActionType,
    BidHistoryEntry,
    Campaign,
    CampaignStatus,
    Creative,
    CreativePeriodMetrics,
    CreativeStatus,
    Decision,
    KPIs,
    MetricsSnapshot,
    PeriodMetrics,
)

DEFAULT_CREATIVES = [
    {"variant": "A", "name": "Креатив A", "headline": "Скидка 20% — только сегодня", "ctr_multiplier": 1.0},
    {"variant": "B", "name": "Креатив B", "headline": "Бесплатная доставка за 2 часа", "ctr_multiplier": 1.15},
]

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "OPTIMUS_DB_PATH",
        str(Path(__file__).resolve().parents[3] / "data" / "optimus.db"),
    )
)


class MetricsStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    daily_budget REAL NOT NULL,
                    target_cpa REAL NOT NULL,
                    conversion_value REAL NOT NULL,
                    current_bid REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metrics_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    tick INTEGER NOT NULL,
                    simulated_hour INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL,
                    kpis_json TEXT NOT NULL,
                    bid REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    tick INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    bid_change_percent REAL NOT NULL,
                    new_bid REAL NOT NULL,
                    reason TEXT NOT NULL,
                    kpis_before_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
                );

                CREATE TABLE IF NOT EXISTS bid_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    tick INTEGER NOT NULL,
                    old_bid REAL NOT NULL,
                    new_bid REAL NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
                );

                CREATE TABLE IF NOT EXISTS agent_state (
                    campaign_id TEXT PRIMARY KEY,
                    current_tick INTEGER NOT NULL DEFAULT 0,
                    bandit_state_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
                );

                CREATE TABLE IF NOT EXISTS creatives (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    name TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    traffic_weight REAL NOT NULL DEFAULT 0.5,
                    ctr_multiplier REAL NOT NULL DEFAULT 1.0,
                    status TEXT NOT NULL DEFAULT 'active',
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
                );
                """
            )
            self._migrate_columns(conn)

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(metrics_snapshots)")}
        if "creative_breakdown_json" not in cols:
            conn.execute(
                "ALTER TABLE metrics_snapshots ADD COLUMN creative_breakdown_json TEXT DEFAULT '[]'"
            )
        dcols = {row[1] for row in conn.execute("PRAGMA table_info(decisions)")}
        if "creative_id" not in dcols:
            conn.execute("ALTER TABLE decisions ADD COLUMN creative_id TEXT")

    def create_campaign(
        self,
        name: str,
        daily_budget: float = 5000.0,
        target_cpa: float = 800.0,
        conversion_value: float = 2500.0,
        current_bid: float = 50.0,
        platform: str = "yandex_mock",
    ) -> Campaign:
        campaign = Campaign(
            id=str(uuid4()),
            name=name,
            platform=platform,
            daily_budget=daily_budget,
            target_cpa=target_cpa,
            conversion_value=conversion_value,
            current_bid=current_bid,
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO campaigns
                (id, name, platform, daily_budget, target_cpa, conversion_value,
                 current_bid, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign.id,
                    campaign.name,
                    campaign.platform,
                    campaign.daily_budget,
                    campaign.target_cpa,
                    campaign.conversion_value,
                    campaign.current_bid,
                    campaign.status.value,
                    campaign.created_at.isoformat(),
                ),
            )
            conn.execute(
                "INSERT INTO agent_state (campaign_id, current_tick, bandit_state_json) VALUES (?, 0, '{}')",
                (campaign.id,),
            )
        self._seed_default_creatives(campaign.id)
        return campaign

    def _seed_default_creatives(self, campaign_id: str) -> None:
        weight = 1.0 / len(DEFAULT_CREATIVES)
        with self._conn() as conn:
            for spec in DEFAULT_CREATIVES:
                conn.execute(
                    """
                    INSERT INTO creatives
                    (id, campaign_id, variant, name, headline, traffic_weight, ctr_multiplier, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (
                        str(uuid4()),
                        campaign_id,
                        spec["variant"],
                        spec["name"],
                        spec["headline"],
                        weight,
                        spec["ctr_multiplier"],
                    ),
                )

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
            ).fetchone()
        return self._row_to_campaign(row) if row else None

    def list_campaigns(self) -> list[Campaign]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        return [self._row_to_campaign(r) for r in rows]

    def get_active_campaign(self) -> Optional[Campaign]:
        campaigns = self.list_campaigns()
        return campaigns[0] if campaigns else None

    def update_campaign_bid(self, campaign_id: str, new_bid: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE campaigns SET current_bid = ? WHERE id = ?",
                (new_bid, campaign_id),
            )

    def update_campaign_status(self, campaign_id: str, status: CampaignStatus) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE campaigns SET status = ? WHERE id = ?",
                (status.value, campaign_id),
            )

    def update_target_cpa(self, campaign_id: str, target_cpa: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE campaigns SET target_cpa = ? WHERE id = ?",
                (target_cpa, campaign_id),
            )

    def get_creatives(self, campaign_id: str) -> list[Creative]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM creatives WHERE campaign_id = ? ORDER BY variant",
                (campaign_id,),
            ).fetchall()
        if not rows:
            self._seed_default_creatives(campaign_id)
            return self.get_creatives(campaign_id)
        return [self._row_to_creative(r) for r in rows]

    def save_creatives(self, creatives: list[Creative]) -> None:
        with self._conn() as conn:
            for c in creatives:
                conn.execute(
                    """
                    UPDATE creatives SET traffic_weight = ?, ctr_multiplier = ?, status = ?
                    WHERE id = ?
                    """,
                    (c.traffic_weight, c.ctr_multiplier, c.status.value, c.id),
                )

    def get_cumulative_creative_metrics(self, campaign_id: str) -> dict[str, PeriodMetrics]:
        totals: dict[str, PeriodMetrics] = {}
        for snap in self.get_snapshots(campaign_id, limit=10000):
            for item in snap.creative_breakdown:
                if item.creative_id not in totals:
                    totals[item.creative_id] = PeriodMetrics()
                t = totals[item.creative_id]
                t.impressions += item.metrics.impressions
                t.clicks += item.metrics.clicks
                t.conversions += item.metrics.conversions
                t.spend += item.metrics.spend
                t.revenue += item.metrics.revenue
        return totals

    def save_snapshot(self, snapshot: MetricsSnapshot) -> MetricsSnapshot:
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO metrics_snapshots
                (campaign_id, tick, simulated_hour, metrics_json, kpis_json, bid,
                 creative_breakdown_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.campaign_id,
                    snapshot.tick,
                    snapshot.simulated_hour,
                    snapshot.metrics.model_dump_json(),
                    snapshot.kpis.model_dump_json(),
                    snapshot.bid,
                    json.dumps([c.model_dump() for c in snapshot.creative_breakdown]),
                    snapshot.created_at.isoformat(),
                ),
            )
            snapshot.id = cursor.lastrowid
        return snapshot

    def get_snapshots(self, campaign_id: str, limit: int = 100) -> list[MetricsSnapshot]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM metrics_snapshots
                WHERE campaign_id = ?
                ORDER BY tick ASC
                LIMIT ?
                """,
                (campaign_id, limit),
            ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def get_latest_snapshot(self, campaign_id: str) -> Optional[MetricsSnapshot]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM metrics_snapshots
                WHERE campaign_id = ?
                ORDER BY tick DESC LIMIT 1
                """,
                (campaign_id,),
            ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def save_decision(self, decision: Decision) -> Decision:
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO decisions
                (campaign_id, tick, action, bid_change_percent, new_bid, reason, kpis_before_json, creative_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.campaign_id,
                    decision.tick,
                    decision.action.value,
                    decision.bid_change_percent,
                    decision.new_bid,
                    decision.reason,
                    decision.kpis_before.model_dump_json(),
                    decision.creative_id,
                    decision.created_at.isoformat(),
                ),
            )
            decision.id = cursor.lastrowid
        return decision

    def get_decisions(self, campaign_id: str, limit: int = 50) -> list[Decision]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM decisions
                WHERE campaign_id = ?
                ORDER BY tick DESC LIMIT ?
                """,
                (campaign_id, limit),
            ).fetchall()
        return [self._row_to_decision(r) for r in rows]

    def save_bid_history(self, entry: BidHistoryEntry) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO bid_history (campaign_id, tick, old_bid, new_bid, action, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.campaign_id,
                    entry.tick,
                    entry.old_bid,
                    entry.new_bid,
                    entry.action.value,
                    entry.created_at.isoformat(),
                ),
            )

    def get_tick(self, campaign_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT current_tick FROM agent_state WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        return row["current_tick"] if row else 0

    def set_tick(self, campaign_id: str, tick: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE agent_state SET current_tick = ? WHERE campaign_id = ?",
                (tick, campaign_id),
            )

    def get_bandit_state(self, campaign_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT bandit_state_json FROM agent_state WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        if not row:
            return {}
        return json.loads(row["bandit_state_json"])

    def set_bandit_state(self, campaign_id: str, state: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE agent_state SET bandit_state_json = ? WHERE campaign_id = ?",
                (json.dumps(state), campaign_id),
            )

    def get_cumulative_metrics(self, campaign_id: str) -> PeriodMetrics:
        snapshots = self.get_snapshots(campaign_id, limit=10000)
        total = PeriodMetrics()
        for s in snapshots:
            total.impressions += s.metrics.impressions
            total.clicks += s.metrics.clicks
            total.conversions += s.metrics.conversions
            total.spend += s.metrics.spend
            total.revenue += s.metrics.revenue
        return total

    def reset_campaign_data(self, campaign_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM metrics_snapshots WHERE campaign_id = ?", (campaign_id,))
            conn.execute("DELETE FROM decisions WHERE campaign_id = ?", (campaign_id,))
            conn.execute("DELETE FROM bid_history WHERE campaign_id = ?", (campaign_id,))
            conn.execute("DELETE FROM creatives WHERE campaign_id = ?", (campaign_id,))
            conn.execute(
                "UPDATE agent_state SET current_tick = 0, bandit_state_json = '{}' WHERE campaign_id = ?",
                (campaign_id,),
            )
        self._seed_default_creatives(campaign_id)

    def delete_all_campaigns(self) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM metrics_snapshots")
            conn.execute("DELETE FROM decisions")
            conn.execute("DELETE FROM bid_history")
            conn.execute("DELETE FROM creatives")
            conn.execute("DELETE FROM agent_state")
            conn.execute("DELETE FROM campaigns")

    @staticmethod
    def _row_to_campaign(row: sqlite3.Row) -> Campaign:
        return Campaign(
            id=row["id"],
            name=row["name"],
            platform=row["platform"],
            daily_budget=row["daily_budget"],
            target_cpa=row["target_cpa"],
            conversion_value=row["conversion_value"],
            current_bid=row["current_bid"],
            status=CampaignStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            )
        self._seed_default_creatives(campaign_id)

    @staticmethod
    def _row_to_creative(row: sqlite3.Row) -> Creative:
        return Creative(
            id=row["id"],
            campaign_id=row["campaign_id"],
            variant=row["variant"],
            name=row["name"],
            headline=row["headline"],
            traffic_weight=row["traffic_weight"],
            ctr_multiplier=row["ctr_multiplier"],
            status=CreativeStatus(row["status"]),
        )

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> MetricsSnapshot:
        breakdown_raw = row["creative_breakdown_json"] if "creative_breakdown_json" in row.keys() else "[]"
        if breakdown_raw is None:
            breakdown_raw = "[]"
        return MetricsSnapshot(
            id=row["id"],
            campaign_id=row["campaign_id"],
            tick=row["tick"],
            simulated_hour=row["simulated_hour"],
            metrics=PeriodMetrics.model_validate_json(row["metrics_json"]),
            kpis=KPIs.model_validate_json(row["kpis_json"]),
            bid=row["bid"],
            creative_breakdown=[
                CreativePeriodMetrics.model_validate(item) for item in json.loads(breakdown_raw)
            ],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_decision(row: sqlite3.Row) -> Decision:
        creative_id = row["creative_id"] if "creative_id" in row.keys() else None
        return Decision(
            id=row["id"],
            campaign_id=row["campaign_id"],
            tick=row["tick"],
            action=ActionType(row["action"]),
            bid_change_percent=row["bid_change_percent"],
            new_bid=row["new_bid"],
            reason=row["reason"],
            kpis_before=KPIs.model_validate_json(row["kpis_before_json"]),
            creative_id=creative_id,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
