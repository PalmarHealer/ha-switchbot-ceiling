"""Fade settings of the SwitchBot RGBICWW Ceiling Light."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import FADE_OPTIONS
from .coordinator import CeilingConfigEntry, CeilingCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CeilingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the fade selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        [FadeSelect(coordinator, "fade_on"), FadeSelect(coordinator, "fade_off")]
    )


class FadeSelect(SelectEntity, RestoreEntity):
    """Default fade for switching on or off (when no transition is given)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(FADE_OPTIONS)
    _attr_current_option = "default"

    def __init__(self, coordinator: CeilingCoordinator, key: str) -> None:
        self._coordinator = coordinator
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.base_unique_id}_{key}"
        self._attr_device_info = device_info(coordinator)

    async def async_added_to_hass(self) -> None:
        if (state := await self.async_get_last_state()) and state.state in FADE_OPTIONS:
            self._apply(state.state)

    def _apply(self, option: str) -> None:
        self._attr_current_option = option
        setattr(self._coordinator, self._key, FADE_OPTIONS[option])

    async def async_select_option(self, option: str) -> None:
        self._apply(option)
        self.async_write_ha_state()
