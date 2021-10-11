"""Amber Electric Coordinator."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from amberelectric import ApiException
from amberelectric.api import amber_api
from amberelectric.model.actual_interval import ActualInterval
from amberelectric.model.channel import ChannelType
from amberelectric.model.current_interval import CurrentInterval
from amberelectric.model.forecast_interval import ForecastInterval

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import LOGGER


def is_current(interval: ActualInterval | CurrentInterval | ForecastInterval) -> bool:
    """Return true if the supplied interval is a CurrentInterval."""
    return isinstance(interval, CurrentInterval)


def is_forecast(interval: ActualInterval | CurrentInterval | ForecastInterval) -> bool:
    """Return true if the supplied interval is a ForecastInterval."""
    return isinstance(interval, ForecastInterval)


def is_general(interval: ActualInterval | CurrentInterval | ForecastInterval) -> bool:
    """Return true if the supplied interval is on the general channel."""
    return interval.channel_type == ChannelType.GENERAL


def is_controlled_load(
    interval: ActualInterval | CurrentInterval | ForecastInterval,
) -> bool:
    """Return true if the supplied interval is on the controlled load channel."""
    return interval.channel_type == ChannelType.CONTROLLED_LOAD


def is_feed_in(interval: ActualInterval | CurrentInterval | ForecastInterval) -> bool:
    """Return true if the supplied interval is on the feed in channel."""
    return interval.channel_type == ChannelType.FEED_IN


class AmberUpdateCoordinator(DataUpdateCoordinator):
    """AmberUpdateCoordinator - In charge of downloading the data for a site, which all the sensors read."""

    def __init__(
        self, hass: HomeAssistant, api: amber_api.AmberApi, site_id: str
    ) -> None:
        """Initialise the data service."""
        super().__init__(
            hass,
            LOGGER,
            name="amberelectric",
            update_interval=timedelta(minutes=1),
        )
        self._api = api
        self.site_id = site_id

    def update_price_data(self) -> dict[str, dict[str, Any]]:
        """Update callback."""

        result: dict[str, dict[str, Any]] = {
            "current": {},
            "forecasts": {},
            "grid": {},
        }
        try:
            data = self._api.get_current_price(self.site_id, next=48)
        except ApiException as api_exception:
            raise UpdateFailed("Missing price data, skipping update") from api_exception

        current = [interval for interval in data if is_current(interval)]
        forecasts = [interval for interval in data if is_forecast(interval)]
        general = [interval for interval in current if is_general(interval)]

        if len(general) == 0:
            raise UpdateFailed("No general channel configured")

        result["current"]["general"] = general[0]
        result["forecasts"]["general"] = [
            interval for interval in forecasts if is_general(interval)
        ]
        result["grid"]["renewables"] = round(general[0].renewables)
        result["grid"]["price_spike"] = general[0].spike_status.value

        controlled_load = [
            interval for interval in current if is_controlled_load(interval)
        ]
        if controlled_load:
            result["current"]["controlled_load"] = controlled_load[0]
            result["forecasts"]["controlled_load"] = [
                interval for interval in forecasts if is_controlled_load(interval)
            ]

        feed_in = [interval for interval in current if is_feed_in(interval)]
        if feed_in:
            result["current"]["feed_in"] = feed_in[0]
            result["forecasts"]["feed_in"] = [
                interval for interval in forecasts if is_feed_in(interval)
            ]

        LOGGER.debug("Fetched new Amber data: %s", data)
        return result

    async def _async_update_data(self) -> dict[str, Any]:
        """Async update wrapper."""
        return await self.hass.async_add_executor_job(self.update_price_data)