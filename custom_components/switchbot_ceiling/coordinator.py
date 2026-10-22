"""Bluetooth coordinator for the SwitchBot RGBICWW Ceiling Light."""

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

import switchbot

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    ACTION_KEEP,
    DEFAULT_FADE,
    DEFAULT_SEGMENT_COLORS,
    DEFAULT_SPEED,
    MODEL,
    SEGMENT_STYLES,
)

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

DEVICE_STARTUP_TIMEOUT = 30
# Keep the BLE link up; the keep-alive re-opens it after a drop.
IDLE_DISCONNECT = 3600
KEEPALIVE_INTERVAL = 20
STATUS_COMMAND = "570F4A01"

type CeilingConfigEntry = ConfigEntry[CeilingCoordinator]


class CeilingCoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    """Track advertisements and poll the ceiling light when needed."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        device: switchbot.SwitchbotRgbicwwCeilingLight,
        base_unique_id: str,
        device_name: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            address=ble_device.address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_update,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=True,
        )
        self.ble_device = ble_device
        self.device = device
        self.device_name = device_name
        self.base_unique_id = base_unique_id
        self.config_entry = config_entry
        self._ready_event = asyncio.Event()
        self._was_unavailable = True
        # User settings, owned by the select/number/text entities.
        self.segment_colors: str = DEFAULT_SEGMENT_COLORS
        self.effect_speed: int = DEFAULT_SPEED
        self.custom_fades = False
        self.fade_on: int = DEFAULT_FADE
        self.fade_off: int = DEFAULT_FADE

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        return (
            self.hass.state is CoreState.running
            and self.device.poll_needed(seconds_since_last_poll)
            and bool(
                bluetooth.async_ble_device_from_address(
                    self.hass, service_info.device.address, connectable=True
                )
            )
        )

    async def _async_update(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Poll the device (reads RGB via GATT)."""
        await self.device.update()

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        super()._async_handle_unavailable(service_info)
        self._was_unavailable = True
        _LOGGER.info("Device %s is unavailable", self.device_name)

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        self.ble_device = service_info.device
        if not (
            adv := switchbot.parse_advertisement_data(
                service_info.device, service_info.advertisement, MODEL
            )
        ):
            return
        if "modelName" in adv.data:
            self._ready_event.set()
        if not self.device.advertisement_changed(adv) and not self._was_unavailable:
            return
        self._was_unavailable = False
        self.device.update_from_advertisement(adv)
        super()._async_handle_bluetooth_event(service_info, change)

    async def async_wait_ready(self) -> bool:
        """Wait until the first parsable advertisement arrived."""
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(DEVICE_STARTUP_TIMEOUT):
                await self._ready_event.wait()
                return True
        return False

    async def async_raw(self, command: str) -> bytes:
        """Send one encrypted command and require an OK response."""
        result = await self.device._send_command(command)  # noqa: SLF001
        _LOGGER.debug("%s -> %s", command, result.hex() if result else None)
        if not result or result[0] != 1:
            raise HomeAssistantError(
                f"Command {command} rejected: {result.hex() if result else None}"
            )
        return result

    async def async_keep_connected(self) -> None:
        """Reconnect in the background so commands never wait for a connect."""
        while True:
            client = self.device._client  # noqa: SLF001
            if not (client and client.is_connected):
                try:
                    await self.device._send_command(STATUS_COMMAND)  # noqa: SLF001
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Keep-alive connect failed: %s", err)
            await asyncio.sleep(KEEPALIVE_INTERVAL)

    def fade_command(
        self,
        color: tuple[int, int] = (ACTION_KEEP, 0),
        main: tuple[int, int] = (ACTION_KEEP, 0),
    ) -> str:
        """Switch sub-lights with a fade, via the device timer set to now."""
        due = int(time.time()) + 1
        return (
            f"570F4905{due:08X}{color[0]:02X}{color[1]:04X}"
            f"{main[0]:02X}{main[1]:04X}"
        )

    def segment_effect_commands(
        self,
        style: str,
        colors: list[tuple[int, int, int]] | None = None,
        speed: int | None = None,
    ) -> list[str]:
        """Commands for a segment effect of the color ring."""
        colors = colors or parse_colors(self.segment_colors)
        number = SEGMENT_STYLES[style]
        head = f"{number & 0xFF:02X}{((number >> 8) & 0x0F) << 4 | len(colors):02X}"
        commands = [
            f"570F490D01{head}{index // 3:02X}"
            + "".join(f"{r:02X}{g:02X}{b:02X}" for r, g, b in colors[index : index + 3])
            for index in range(0, len(colors), 3)
        ]
        commands.append(f"570F490D03{self.effect_speed if speed is None else speed:02X}")
        return commands


class CeilingDevice(switchbot.SwitchbotRgbicwwCeilingLight):
    """Library device that keeps its BLE connection instead of 8.5 s idle."""

    _release_tasks: set[asyncio.Task] = set()

    def _disconnected(self, client) -> None:
        """Release the D-Bus connection of a link the light dropped.

        bleak only closes a client's D-Bus connection in disconnect(), which
        the library never calls after an unexpected drop. With the keep-alive
        reconnecting every drop, the leaked connections reached the system
        bus limit (256 per user) and every new connect failed with EOFError.
        """
        super()._disconnected(client)
        if self._expected_disconnect:
            return
        task = asyncio.get_running_loop().create_task(self._release(client))
        self._release_tasks.add(task)
        task.add_done_callback(self._release_tasks.discard)

    @staticmethod
    async def _release(client) -> None:
        try:
            await client.disconnect()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Releasing dropped connection failed: %s", err)

    def _reset_disconnect_timer(self) -> None:
        self._cancel_disconnect_timer()
        self._expected_disconnect = False
        self._disconnect_timer = asyncio.get_running_loop().call_later(
            IDLE_DISCONNECT, self._disconnect_from_timer
        )


def parse_colors(value: str) -> list[tuple[int, int, int]]:
    """Parse "FF0000, #00ff00 ..." into RGB tuples (max 10)."""
    colors = []
    for part in value.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip().lstrip("#")
        if not part:
            continue
        if len(part) != 6:
            raise ValueError(f"invalid color {part!r}")
        colors.append((int(part[0:2], 16), int(part[2:4], 16), int(part[4:6], 16)))
    if not 1 <= len(colors) <= 10:
        raise ValueError("1-10 colors required")
    return colors
