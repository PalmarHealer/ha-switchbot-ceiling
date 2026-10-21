"""Segment effect colors of the SwitchBot RGBICWW Ceiling Light."""

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_SEGMENT_COLORS
from .coordinator import CeilingConfigEntry, CeilingCoordinator, parse_colors
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CeilingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the effect colors."""
    async_add_entities([SegmentColors(entry.runtime_data)])


class SegmentColors(TextEntity, RestoreEntity):
    """Comma separated hex colors used by the segment effects (1-10)."""

    _attr_has_entity_name = True
    _attr_translation_key = "segment_colors"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_max = 80
    _attr_native_value = DEFAULT_SEGMENT_COLORS

    def __init__(self, coordinator: CeilingCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.base_unique_id}_segment_colors"
        self._attr_device_info = device_info(coordinator)

    async def async_added_to_hass(self) -> None:
        if (state := await self.async_get_last_state()) and state.state not in (
            "unknown",
            "unavailable",
        ):
            self._attr_native_value = self._coordinator.segment_colors = state.state

    async def async_set_value(self, value: str) -> None:
        try:
            parse_colors(value)
        except ValueError as err:
            raise ServiceValidationError(
                f"Farben als Hex-Liste angeben, z. B. FF0000,00FF00 ({err})"
            ) from err
        self._attr_native_value = self._coordinator.segment_colors = value
        self.async_write_ha_state()
