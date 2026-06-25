"""Sensors for the AlphaESS Modbus Controller.

Exposes the controller status plus all measurements read locally over Modbus
(PV power per string + total, grid power per phase + total, battery power,
battery SOC, and derived house load). No cloud dependency.
"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AlphaessCoordinator


@dataclass(frozen=True, kw_only=True)
class AlphaessSensorDescription(SensorEntityDescription):
    """Describes an AlphaESS measurement sensor and where to read it from."""

    measurement_key: str = ""


def _power(key: str, name: str, icon: str) -> AlphaessSensorDescription:
    return AlphaessSensorDescription(
        key=key,
        name=name,
        icon=icon,
        measurement_key=key,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    )


MEASUREMENT_SENSORS: tuple[AlphaessSensorDescription, ...] = (
    _power("pv_total", "PV vermogen", "mdi:solar-power"),
    _power("pv1", "PV vermogen string 1", "mdi:solar-panel"),
    _power("pv2", "PV vermogen string 2", "mdi:solar-panel"),
    _power("pv3", "PV vermogen string 3", "mdi:solar-panel"),
    _power("pv4", "PV vermogen string 4", "mdi:solar-panel"),
    _power("grid_total", "Grid vermogen", "mdi:transmission-tower"),
    _power("grid_l1", "Grid vermogen L1", "mdi:transmission-tower"),
    _power("grid_l2", "Grid vermogen L2", "mdi:transmission-tower"),
    _power("grid_l3", "Grid vermogen L3", "mdi:transmission-tower"),
    _power("battery_power", "Accu vermogen", "mdi:battery-charging"),
    _power("load", "Huisverbruik", "mdi:home-lightning-bolt"),
    AlphaessSensorDescription(
        key="battery_soc",
        name="Accu SoC",
        icon="mdi:battery",
        measurement_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the status sensor plus the local Modbus measurement sensors."""
    coordinator: AlphaessCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [AlphaessStatusSensor(coordinator, entry)]
    entities.extend(
        AlphaessMeasurementSensor(coordinator, entry, desc)
        for desc in MEASUREMENT_SENSORS
    )
    async_add_entities(entities)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="AlphaESS",
        manufacturer="AlphaESS",
        model="Modbus Controller",
    )


class AlphaessStatusSensor(CoordinatorEntity, SensorEntity):
    """Reports what the controller is currently doing (normal / pv_off / zero_export)."""

    _attr_has_entity_name = True
    _attr_translation_key = "status"
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: AlphaessCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get("mode")

    @property
    def extra_state_attributes(self):
        data = dict(self.coordinator.data or {})
        # The raw measurements each have their own entity; don't duplicate the
        # whole block on the status sensor's attributes.
        data.pop("measurements", None)
        return data


class AlphaessMeasurementSensor(CoordinatorEntity, SensorEntity):
    """A single measurement read locally over Modbus."""

    _attr_has_entity_name = True
    entity_description: AlphaessSensorDescription

    def __init__(
        self,
        coordinator: AlphaessCoordinator,
        entry: ConfigEntry,
        description: AlphaessSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        measurements = data.get("measurements") or {}
        return measurements.get(self.entity_description.measurement_key)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        data = self.coordinator.data or {}
        return bool(data.get("measurements"))
