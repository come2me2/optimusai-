from abc import ABC, abstractmethod

from optimus.models import Campaign, KPIs, PeriodMetrics


class AdPlatformAdapter(ABC):
    """Unified interface for any ad platform (Yandex, Google, Telegram, etc.)."""

    @abstractmethod
    def get_period_metrics(self, campaign: Campaign) -> PeriodMetrics:
        """Return metrics for the current simulation/API period."""

    @abstractmethod
    def get_impression_share(self, campaign: Campaign) -> float:
        """Return estimated impression share (0..1)."""

    @abstractmethod
    def set_bid(self, campaign: Campaign, new_bid: float) -> float:
        """Apply new bid and return the effective bid."""

    @abstractmethod
    def pause(self, campaign: Campaign) -> None:
        """Pause the campaign on the platform."""

    @abstractmethod
    def resume(self, campaign: Campaign) -> None:
        """Resume the campaign."""

    @abstractmethod
    def advance_tick(self, simulated_hour: int) -> None:
        """Advance time (mock) or sync period (live)."""

    @abstractmethod
    def apply_creative_fatigue(self) -> None:
        """Signal creative fatigue to the platform/simulator."""


class YandexDirectAdapter(AdPlatformAdapter):
    """
    Stub for live Yandex Direct API integration.

  To enable:
  1. Register app at https://oauth.yandex.ru/
  2. Obtain OAuth token with direct:api scope
  3. Implement API calls to Campaigns.get, Bids.set, Reports
  """

    def __init__(self, oauth_token: str) -> None:
        self.oauth_token = oauth_token

    def get_period_metrics(self, campaign: Campaign) -> PeriodMetrics:
        raise NotImplementedError("Connect Yandex Direct API — see class docstring")

    def get_impression_share(self, campaign: Campaign) -> float:
        raise NotImplementedError("Connect Yandex Direct API — see class docstring")

    def set_bid(self, campaign: Campaign, new_bid: float) -> float:
        raise NotImplementedError("Connect Yandex Direct API — see class docstring")

    def pause(self, campaign: Campaign) -> None:
        raise NotImplementedError("Connect Yandex Direct API — see class docstring")

    def resume(self, campaign: Campaign) -> None:
        raise NotImplementedError("Connect Yandex Direct API — see class docstring")

    def advance_tick(self, simulated_hour: int) -> None:
        raise NotImplementedError("Connect Yandex Direct API — see class docstring")

    def apply_creative_fatigue(self) -> None:
        raise NotImplementedError("Connect Yandex Direct API — see class docstring")
