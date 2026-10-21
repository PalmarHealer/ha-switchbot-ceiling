"""Config flow for the SwitchBot RGBICWW Ceiling Light.

The SwitchBot account credentials are only used to fetch the BLE key and
are never stored; the entry keeps address, key_id and encryption_key.
"""

import logging
from typing import Any

from switchbot import (
    SwitchbotAccountConnectionError,
    SwitchBotAdvertisement,
    SwitchbotApiError,
    SwitchbotAuthenticationError,
    SwitchbotRgbicwwCeilingLight,
    parse_advertisement_data,
)
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ENCRYPTION_KEY, CONF_KEY_ID, DOMAIN, MODEL

_LOGGER = logging.getLogger(__name__)


def format_unique_id(address: str) -> str:
    """Format the unique ID."""
    return address.replace(":", "").lower()


def _name(adv: SwitchBotAdvertisement) -> str:
    return f"{adv.data['modelFriendlyName']} {adv.address.replace(':', '')[-4:]}"


def _parse(info: BluetoothServiceInfoBleak) -> SwitchBotAdvertisement | None:
    parsed = parse_advertisement_data(info.device, info.advertisement)
    if parsed and parsed.data.get("modelName") == MODEL:
        return parsed
    return None


class CeilingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._adv: SwitchBotAdvertisement | None = None
        self._discovered: dict[str, SwitchBotAdvertisement] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle bluetooth discovery."""
        await self.async_set_unique_id(format_unique_id(discovery_info.address))
        self._abort_if_unique_id_configured()
        if not (parsed := _parse(discovery_info)):
            return self.async_abort(reason="not_supported")
        self._adv = parsed
        self.context["title_placeholders"] = {"name": _name(parsed)}
        return await self.async_step_choose_method()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a discovered ceiling light."""
        if user_input is not None:
            self._adv = self._discovered[user_input[CONF_ADDRESS]]
            await self.async_set_unique_id(
                format_unique_id(self._adv.address), raise_on_progress=False
            )
            self._abort_if_unique_id_configured()
            return await self.async_step_choose_method()

        await bluetooth.async_request_active_scan(self.hass)
        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if format_unique_id(info.address) in current:
                continue
            if parsed := _parse(info):
                self._discovered[info.address] = parsed
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {addr: _name(adv) for addr, adv in self._discovered.items()}
                    )
                }
            ),
        )

    async def async_step_choose_method(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose between SwitchBot login and manual key."""
        assert self._adv is not None
        return self.async_show_menu(
            step_id="choose_method",
            menu_options=["auth", "key"],
            description_placeholders={"name": _name(self._adv)},
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fetch the key with the SwitchBot account (credentials not stored)."""
        assert self._adv is not None
        errors: dict[str, str] = {}
        placeholders = {"name": _name(self._adv), "error_detail": ""}
        if user_input is not None:
            try:
                key = await SwitchbotRgbicwwCeilingLight.async_retrieve_encryption_key(
                    async_get_clientsession(self.hass),
                    self._adv.address,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except SwitchbotAuthenticationError as err:
                errors["base"] = "auth_failed"
                placeholders["error_detail"] = str(err)
            except (SwitchbotApiError, SwitchbotAccountConnectionError) as err:
                errors["base"] = "api_error"
                placeholders["error_detail"] = str(err)
            except Exception:
                _LOGGER.exception("Unexpected error retrieving encryption key")
                errors["base"] = "unknown"
            else:
                return self._create(key[CONF_KEY_ID], key[CONF_ENCRYPTION_KEY])

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=(user_input or {}).get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter key_id and encryption_key manually."""
        assert self._adv is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            if await SwitchbotRgbicwwCeilingLight.verify_encryption_key(
                self._adv.device,
                user_input[CONF_KEY_ID],
                user_input[CONF_ENCRYPTION_KEY],
            ):
                return self._create(
                    user_input[CONF_KEY_ID], user_input[CONF_ENCRYPTION_KEY]
                )
            errors["base"] = "encryption_key_invalid"

        return self.async_show_form(
            step_id="key",
            data_schema=vol.Schema(
                {vol.Required(CONF_KEY_ID): str, vol.Required(CONF_ENCRYPTION_KEY): str}
            ),
            errors=errors,
            description_placeholders={"name": _name(self._adv)},
        )

    def _create(self, key_id: str, encryption_key: str) -> ConfigFlowResult:
        assert self._adv is not None
        return self.async_create_entry(
            title=_name(self._adv),
            data={
                CONF_ADDRESS: self._adv.address,
                CONF_KEY_ID: key_id,
                CONF_ENCRYPTION_KEY: encryption_key,
            },
        )
