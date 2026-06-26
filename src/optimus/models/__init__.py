from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CampaignStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"


class ActionType(str, Enum):
    INCREASE_BID = "increase_bid"
    DECREASE_BID = "decrease_bid"
    HOLD = "hold"
    PAUSE = "pause"
    THROTTLE = "throttle"
    CREATIVE_FATIGUE = "creative_fatigue"


class Campaign(BaseModel):
    id: str
    name: str
    platform: str = "yandex_mock"
    daily_budget: float = 5000.0
    target_cpa: float = 800.0
    conversion_value: float = 2500.0
    current_bid: float = 50.0
    status: CampaignStatus = CampaignStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PeriodMetrics(BaseModel):
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    spend: float = 0.0
    revenue: float = 0.0


class KPIs(BaseModel):
    ctr: float = 0.0
    cpc: float = 0.0
    cr: float = 0.0
    cpa: float = 0.0
    roas: float = 0.0
    impression_share: float = 0.0


class MetricsSnapshot(BaseModel):
    id: Optional[int] = None
    campaign_id: str
    tick: int
    simulated_hour: int
    metrics: PeriodMetrics
    kpis: KPIs
    bid: float
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Decision(BaseModel):
    id: Optional[int] = None
    campaign_id: str
    tick: int
    action: ActionType
    bid_change_percent: float = 0.0
    new_bid: float
    reason: str
    kpis_before: KPIs
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BidHistoryEntry(BaseModel):
    id: Optional[int] = None
    campaign_id: str
    tick: int
    old_bid: float
    new_bid: float
    action: ActionType
    created_at: datetime = Field(default_factory=datetime.utcnow)
