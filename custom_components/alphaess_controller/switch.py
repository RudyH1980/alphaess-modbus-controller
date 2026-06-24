"""Control switches for the AlphaESS Modbus Controller."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    SWITCH_NEG_CHARGE,
    SWITCH_PV_SHUTDOWN,
    SWITCH_ZERO_EXPORT,
)
from .coordinator import AlphaessCoordinator

# key -> (friendly name, icon)
SWITCHES = {
    SWITCH_PV_SHUTDOWN: ("PV Shutdown", "mdi:solar-power-variant-outline"),
    SWITCH_NEG_CHARGE: ("Negative-price Charge", "mdi:battery-charging-high"),
    SWITCH_ZERO_EXPORT: ("Zero Export", "mdi:transmission-tower-off"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the control switches."""
    coordinator: AlphaessCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AlphaessSwitch(coordinator, entry, key, name, icon)
        for key, (name, icon) in SWITCHES.items()
    )


class AlphaessSwitch(SwitchEntity, RestoreEntity):
    """A switch that drives the controller's desired state (survives restarts)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, icon) -> None:
        self._coordinator = coordinator
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="AlphaESS Modbus Controller",
            manufacturer="AlphaESS",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._attr_is_on = last.state == "on"
        # seed the coordinator with the restored intent
        self._coordinator.switch_state[self._key] = self._attr_is_on

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        await self._coordinator.async_set_switch(self._key, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        await self._coordinator.async_set_switch(self._key, False)
        self.async_write_ha_state()
