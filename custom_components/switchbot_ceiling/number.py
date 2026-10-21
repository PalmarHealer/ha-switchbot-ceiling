"""Effect speed of the SwitchBot RGBICWW Ceiling Light."""

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEFAULT_SPEED
from .coordinator import CeilingConfigEntry, CeilingCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CeilingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the effect speed."""
    async_add_entities([EffectSpeed(entry.runtime_data)])


class EffectSpeed(RestoreNumber):
    """Speed of segment effects; applied live to a running effect."""

    _attr_has_entity_name = True
    _attr_translation_key = "effect_speed"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_value = DEFAULT_SPEED

    def __init__(self, coordinator: CeilingCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.base_unique_id}_effect_speed"
        self._attr_device_info = device_info(coordinator)

    async def async_added_to_hass(self) -> None:
        if (data := await self.async_get_last_number_data()) and data.native_value:
            self._attr_native_value = data.native_value
            self._coordinator.effect_speed = int(data.native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self._coordinator.effect_speed = int(value)
        await self._coordinator.async_raw(f"570F490D03{int(value):02X}")
        self.async_write_ha_state()
