"""Shared device info for SwitchBot ceiling light entities."""

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .const import MANUFACTURER, MODEL
from .coordinator import CeilingCoordinator


def device_info(coordinator: CeilingCoordinator) -> DeviceInfo:
    """Device info shared by all entities of one ceiling light."""
    address = coordinator.ble_device.address
    return DeviceInfo(
        connections={
            (dr.CONNECTION_BLUETOOTH, address),
            (dr.CONNECTION_NETWORK_MAC, address),
        },
        manufacturer=MANUFACTURER,
        model=MODEL,
        name=coordinator.device_name,
    )
