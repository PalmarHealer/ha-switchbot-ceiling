"""Effect speed and fade times of the SwitchBot RGBICWW Ceiling Light."""

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEFAULT_FADE, DEFAULT_SPEED, MAX_FADE
from .coordinator import CeilingConfigEntry, CeilingCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CeilingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            EffectSpeed(coordinator),
            FadeTime(coordinator, "fade_on"),
            FadeTime(coordinator, "fade_off"),
        ]
    )


class CeilingNumber(RestoreNumber):
    """Number stored on the coordinator and restored after restarts."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CeilingCoordinator, key: str) -> None:
        self._coordinator = coordinator
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.base_unique_id}_{key}_seconds"
        self._attr_device_info = device_info(coordinator)
        self._attr_native_value = getattr(coordinator, key)

    async def async_added_to_hass(self) -> None:
        if (data := await self.async_get_last_number_data()) and (
            data.native_value is not None
        ):
            self._attr_native_value = data.native_value
            setattr(self._coordinator, self._key, int(data.native_value))

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        setattr(self._coordinator, self._key, int(value))
        self.async_write_ha_state()


class EffectSpeed(CeilingNumber):
    """Speed of segment effects; applied live to a running effect."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: CeilingCoordinator) -> None:
        super().__init__(coordinator, "effect_speed")
        self._attr_unique_id = f"{coordinator.base_unique_id}_effect_speed"
        self._attr_native_value = DEFAULT_SPEED

    async def async_set_native_value(self, value: float) -> None:
        await self._coordinator.async_raw(f"570F490D03{int(value):02X}")
        await super().async_set_native_value(value)


class FadeTime(CeilingNumber):
    """Fade in seconds for switching on/off; 0 = instant."""

    _attr_native_min_value = 0
    _attr_native_max_value = MAX_FADE
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: CeilingCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_native_value = DEFAULT_FADE
