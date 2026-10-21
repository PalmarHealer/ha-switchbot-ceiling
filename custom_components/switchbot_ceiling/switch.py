"""Switch between the lamp's own fades and the configured fade times."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import CeilingConfigEntry, CeilingCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CeilingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the fade switch."""
    async_add_entities([CustomFades(entry.runtime_data)])


class CustomFades(SwitchEntity, RestoreEntity):
    """On: use the fade time entities. Off: the lamp's built-in fades."""

    _attr_has_entity_name = True
    _attr_translation_key = "custom_fades"
    _attr_is_on = False

    def __init__(self, coordinator: CeilingCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.base_unique_id}_custom_fades"
        self._attr_device_info = device_info(coordinator)

    async def async_added_to_hass(self) -> None:
        if (state := await self.async_get_last_state()) and state.state in ("on", "off"):
            self._attr_is_on = state.state == "on"
        self._coordinator.custom_fades = self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set(False)

    def _set(self, value: bool) -> None:
        self._attr_is_on = self._coordinator.custom_fades = value
        self.async_write_ha_state()
