"""White and color sub-lights of the SwitchBot RGBICWW Ceiling Light.

Commands are sent raw (protocol from the SwitchBot app, woCeilingLight2.js)
instead of through the library helpers: those switch BOTH sub-lights or read
the full status back after every single command, which costs seconds over BLE.
The new state is shown optimistically until the advertisements catch up.
"""

from collections.abc import Callable, Coroutine
import logging
import time
from typing import Any, Concatenate

import switchbot
from switchbot import SwitchbotOperationError
import voluptuous as vol

from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothCoordinatorEntity,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    EFFECT_OFF,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ACTION_OFF,
    ACTION_ON,
    MAX_KELVIN,
    MAX_SEGMENT_COLORS,
    MIN_KELVIN,
    SEGMENT_EFFECT_PREFIX,
    SEGMENT_STYLES,
)
from .coordinator import CeilingConfigEntry, CeilingCoordinator
from .entity import device_info

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

# How long optimistic values win over (possibly stale) advertisements.
OPTIMISTIC_SECONDS = 10

CMD = "570F4901"
WHITE_ON, WHITE_OFF = f"{CMD}0181", f"{CMD}0182"
COLOR_ON, COLOR_OFF = f"{CMD}0184", f"{CMD}0188"

_RGB = vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple))


def _to_pct(brightness: int) -> int:
    """HA brightness 0-255 -> device 1-100."""
    return max(1, min(100, round(brightness / 255 * 100)))


def _to_ha(pct: int) -> int:
    return max(0, min(255, round(pct * 2.55)))


def _handle_errors[_T: "CeilingEntity", **_P](
    func: Callable[Concatenate[_T, _P], Coroutine[Any, Any, None]],
) -> Callable[Concatenate[_T, _P], Coroutine[Any, Any, None]]:
    async def handler(self: _T, *args: _P.args, **kwargs: _P.kwargs) -> None:
        try:
            await func(self, *args, **kwargs)
        except SwitchbotOperationError as err:
            raise HomeAssistantError(f"SwitchBot command failed: {err}") from err

    return handler


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CeilingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up both sub-lights."""
    coordinator = entry.runtime_data
    async_add_entities(
        [CeilingWhiteLight(coordinator), CeilingColorLight(coordinator)]
    )
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "set_segment_effect",
        {
            vol.Required("effect"): vol.In(list(SEGMENT_STYLES)),
            vol.Required("colors"): vol.All(
                cv.ensure_list, [_RGB], vol.Length(min=1, max=MAX_SEGMENT_COLORS)
            ),
            vol.Optional("speed"): vol.All(vol.Coerce(int), vol.Range(0, 255)),
        },
        "async_set_segment_effect",
    )
    platform.async_register_entity_service(
        "send_command",
        {vol.Required("command"): vol.Match(r"^(?:[0-9a-fA-F]{2})+$")},
        "async_send_command",
    )


class CeilingEntity(PassiveBluetoothCoordinatorEntity[CeilingCoordinator], LightEntity):
    """Common base for both sub-lights."""

    _attr_has_entity_name = True
    _device: switchbot.SwitchbotRgbicwwCeilingLight

    def __init__(self, coordinator: CeilingCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._device = coordinator.device
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.base_unique_id}_{key}"
        self._attr_device_info = device_info(coordinator)
        self._optimistic: dict[str, Any] = {}
        self._optimistic_until = 0.0

    def _value(self, key: str, actual: Any) -> Any:
        if time.monotonic() < self._optimistic_until and key in self._optimistic:
            return self._optimistic[key]
        return actual

    async def _send(self, commands: list[str], **optimistic: Any) -> None:
        for command in commands:
            await self.coordinator.async_raw(command)
        self._optimistic = optimistic
        self._optimistic_until = time.monotonic() + OPTIMISTIC_SECONDS
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._device.subscribe(self._handle_coordinator_update))
        await super().async_added_to_hass()


class CeilingWhiteLight(CeilingEntity):
    """Main warm/cold white sub-light."""

    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_min_color_temp_kelvin = MIN_KELVIN
    _attr_max_color_temp_kelvin = MAX_KELVIN

    def __init__(self, coordinator: CeilingCoordinator) -> None:
        super().__init__(coordinator, "white")

    @property
    def is_on(self) -> bool | None:
        return self._value("on", self._device.is_main_on)

    @property
    def brightness(self) -> int | None:
        return self._value("brightness", _to_ha(self._device.main_brightness))

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._value("kelvin", self._device.color_temp)

    @_handle_errors
    async def async_turn_on(self, **kwargs: Any) -> None:
        commands: list[str] = []
        state: dict[str, Any] = {"on": True}
        pct = _to_pct(kwargs[ATTR_BRIGHTNESS]) if ATTR_BRIGHTNESS in kwargs else None
        kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        if kelvin is not None:
            kelvin = max(MIN_KELVIN, min(MAX_KELVIN, kelvin))
            state["kelvin"] = kelvin
        if pct is not None:
            state["brightness"] = kwargs[ATTR_BRIGHTNESS]
        if pct is not None and kelvin is not None:
            commands.append(f"{CMD}11{pct:02X}{kelvin:04X}")
        elif pct is not None:
            commands.append(f"{CMD}09{pct:02X}")
        elif kelvin is not None:
            commands.append(f"{CMD}10{kelvin:04X}")
        if not self.is_on:
            fade = _fade(kwargs, self.coordinator, self.coordinator.fade_on)
            if fade is None:
                commands.append(WHITE_ON)
            else:
                commands.append(self.coordinator.fade_command(main=(ACTION_ON, fade)))
        await self._send(commands, **state)

    @_handle_errors
    async def async_turn_off(self, **kwargs: Any) -> None:
        fade = _fade(kwargs, self.coordinator, self.coordinator.fade_off)
        if fade is None:
            command = WHITE_OFF
        else:
            command = self.coordinator.fade_command(main=(ACTION_OFF, fade))
        await self._send([command], on=False)


class CeilingColorLight(CeilingEntity):
    """RGBIC color sub-light (ring)."""

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature.EFFECT | LightEntityFeature.TRANSITION

    def __init__(self, coordinator: CeilingCoordinator) -> None:
        super().__init__(coordinator, "color")
        self._effect: str | None = None

    @property
    def is_on(self) -> bool | None:
        return self._value("on", self._device.is_on())

    @property
    def brightness(self) -> int | None:
        return self._value("brightness", _to_ha(self._device.brightness))

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self._value("rgb", self._device.rgb)

    @property
    def effect_list(self) -> list[str] | None:
        return [
            EFFECT_OFF,
            *(SEGMENT_EFFECT_PREFIX + style for style in SEGMENT_STYLES),
            *(self._device.get_effect_list or []),
        ]

    @property
    def effect(self) -> str | None:
        in_effect = self._value(
            "in_effect", self._device.color_mode is switchbot.ColorMode.EFFECT
        )
        if not in_effect:
            self._effect = None
        return self._effect or EFFECT_OFF

    @_handle_errors
    async def async_turn_on(self, **kwargs: Any) -> None:
        commands: list[str] = []
        state: dict[str, Any] = {"on": True}
        if kwargs.get(ATTR_EFFECT) == EFFECT_OFF and ATTR_RGB_COLOR not in kwargs:
            # Leave the effect by re-applying the last static color.
            kwargs[ATTR_RGB_COLOR] = self._device.rgb or (255, 255, 255)
            del kwargs[ATTR_EFFECT]
        if (effect := kwargs.get(ATTR_EFFECT)) is not None:
            if effect.startswith(SEGMENT_EFFECT_PREFIX):
                commands += self.coordinator.segment_effect_commands(
                    effect.removeprefix(SEGMENT_EFFECT_PREFIX)
                )
            elif effect in self._device.get_effect_list:
                commands += self._device._effect_dict[effect]  # noqa: SLF001
            else:
                raise HomeAssistantError(f"Unknown effect {effect}")
            self._effect = effect
            state["in_effect"] = True
        elif ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            brightness = kwargs.get(ATTR_BRIGHTNESS, self.brightness or 255)
            commands.append(f"{CMD}12{_to_pct(brightness):02X}{r:02X}{g:02X}{b:02X}00FF")
            state |= {"rgb": (r, g, b), "brightness": brightness, "in_effect": False}
            self._effect = None
        elif ATTR_BRIGHTNESS in kwargs:
            commands.append(f"{CMD}14{_to_pct(kwargs[ATTR_BRIGHTNESS]):02X}")
            state["brightness"] = kwargs[ATTR_BRIGHTNESS]
        if not self.is_on:
            fade = _fade(kwargs, self.coordinator, self.coordinator.fade_on)
            if fade is None:
                commands.append(COLOR_ON)
            else:
                commands.append(self.coordinator.fade_command(color=(ACTION_ON, fade)))
        await self._send(commands, **state)

    @_handle_errors
    async def async_turn_off(self, **kwargs: Any) -> None:
        fade = _fade(kwargs, self.coordinator, self.coordinator.fade_off)
        if fade is None:
            command = COLOR_OFF
        else:
            command = self.coordinator.fade_command(color=(ACTION_OFF, fade))
        await self._send([command], on=False)

    @_handle_errors
    async def async_set_segment_effect(
        self,
        effect: str,
        colors: list[tuple[int, int, int]],
        speed: int | None = None,
    ) -> None:
        """Run a segment effect with own colors."""
        self._effect = SEGMENT_EFFECT_PREFIX + effect
        await self._send(
            self.coordinator.segment_effect_commands(effect, colors, speed),
            on=True,
            in_effect=True,
        )

    @_handle_errors
    async def async_send_command(self, command: str) -> None:
        """Send a raw (encrypted) command, for protocol experiments."""
        result = await self.coordinator.async_raw(command)
        self.hass.bus.async_fire(
            "switchbot_ceiling_response",
            {"command": command, "response": result.hex()},
        )


def _fade(
    kwargs: dict[str, Any], coordinator: CeilingCoordinator, default: int
) -> int | None:
    """Transition of the call, else the configured fade (None = lamp default)."""
    if (transition := kwargs.get(ATTR_TRANSITION)) is not None:
        return round(transition)
    return default if coordinator.custom_fades else None
