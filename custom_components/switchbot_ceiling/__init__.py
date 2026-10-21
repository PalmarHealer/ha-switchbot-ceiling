"""SwitchBot RGBICWW Ceiling Light (BLE) with separate white and color lights."""

import switchbot

from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_ENCRYPTION_KEY, CONF_KEY_ID
from .coordinator import CeilingConfigEntry, CeilingCoordinator, CeilingDevice

PLATFORMS = [Platform.LIGHT, Platform.NUMBER, Platform.SWITCH, Platform.TEXT]

async def async_setup_entry(hass: HomeAssistant, entry: CeilingConfigEntry) -> bool:
    """Set up the ceiling light from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    await switchbot.close_stale_connections_by_address(address)

    ble_device = bluetooth.async_ble_device_from_address(
        hass, address.upper(), connectable=True
    )
    if not ble_device:
        raise ConfigEntryNotReady(f"Could not find SwitchBot device {address}")

    try:
        device = CeilingDevice(
            device=ble_device,
            key_id=entry.data[CONF_KEY_ID],
            encryption_key=entry.data[CONF_ENCRYPTION_KEY],
        )
    except ValueError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = entry.runtime_data = CeilingCoordinator(
        hass, ble_device, device, entry.unique_id, entry.title, entry
    )
    entry.async_on_unload(coordinator.async_start())
    if not await coordinator.async_wait_ready():
        raise ConfigEntryNotReady(f"{address} is not advertising state")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(
        hass, coordinator.async_keep_connected(), "switchbot_ceiling keep-alive"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CeilingConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.device._execute_forced_disconnect()  # noqa: SLF001
    return unloaded
