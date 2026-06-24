"""Status sensor for the AlphaESS Modbus Controller."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AlphaessCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the status sensor."""
    coordinator: AlphaessCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AlphaessStatusSensor(coordinator, entry)])


class AlphaessStatusSensor(CoordinatorEntity, SensorEntity):
    """Reports what the controller is currently doing (normal / pv_off / zero_export)."""

    _attr_has_entity_name = True
    _attr_translation_key = "status"
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: AlphaessCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="AlphaESS",
            manufacturer="AlphaESS",
            model="Modbus Controller",
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get("mode")

    @property
    def extra_state_attributes(self):
        return self.coordinator.data or {}
