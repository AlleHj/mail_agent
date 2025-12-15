# Version: 0.9.0 - 2025-12-15
"""Config flow för Mail Agent integration."""

import imaplib
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    ConfigEntry,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
)

from .const import (
    DOMAIN,
    LOGGER,
    CONF_IMAP_SERVER,
    CONF_IMAP_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_FOLDER,
    CONF_SCAN_INTERVAL,
    CONF_ENABLE_DEBUG,
    CONF_GEMINI_API_KEY,
    CONF_GEMINI_MODEL,
    CONF_CALENDAR_1,
    CONF_CALENDAR_2,
    DEFAULT_PORT,
    DEFAULT_FOLDER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENABLE_DEBUG,
    DEFAULT_GEMINI_MODEL,
)


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validera IMAP-anslutning."""

    def _test_imap_login():
        try:
            connection = imaplib.IMAP4_SSL(data[CONF_IMAP_SERVER], data[CONF_IMAP_PORT])
            connection.login(data[CONF_USERNAME], data[CONF_PASSWORD])
            connection.select(data[CONF_FOLDER])
            connection.logout()
            return True
        except imaplib.IMAP4.error:
            raise ValueError("invalid_auth")
        except Exception as e:
            LOGGER.error("Anslutningsfel: %s", e)
            raise ConnectionError("cannot_connect")

    await hass.async_add_executor_job(_test_imap_login)
    return {"title": data[CONF_USERNAME]}


class MailAgentConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hantera en config flow för Mail Agent."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MailAgentOptionsFlowHandler()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)
            except ValueError:
                errors["base"] = "invalid_auth"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                LOGGER.exception("Oväntat fel")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_IMAP_SERVER): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_IMAP_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_FOLDER, default=DEFAULT_FOLDER): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class MailAgentOptionsFlowHandler(OptionsFlow):
    """Hantera inställningar inklusive Gemini och Kalendrar."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            # Uppdatera Connection Data
            connection_data = {
                CONF_IMAP_SERVER: user_input[CONF_IMAP_SERVER],
                CONF_IMAP_PORT: user_input[CONF_IMAP_PORT],
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_FOLDER: user_input[CONF_FOLDER],
            }
            # Uppdatera Options
            options_data = {
                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL),
                CONF_ENABLE_DEBUG: user_input.get(CONF_ENABLE_DEBUG),
                CONF_GEMINI_API_KEY: user_input.get(CONF_GEMINI_API_KEY),
                CONF_GEMINI_MODEL: user_input.get(CONF_GEMINI_MODEL),
                CONF_CALENDAR_1: user_input.get(CONF_CALENDAR_1),
                CONF_CALENDAR_2: user_input.get(CONF_CALENDAR_2),
            }

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=connection_data
            )
            return self.async_create_entry(title="", data=options_data)

        config = self.config_entry.data
        options = self.config_entry.options

        # Selector: Visar bara entiteter som är kalendrar
        calendar_selector = EntitySelector(
            EntitySelectorConfig(domain="calendar", multiple=False)
        )

        options_schema = vol.Schema(
            {
                # IMAP
                vol.Required(
                    CONF_IMAP_SERVER, default=config.get(CONF_IMAP_SERVER)
                ): str,
                vol.Required(CONF_USERNAME, default=config.get(CONF_USERNAME)): str,
                vol.Required(CONF_PASSWORD, default=config.get(CONF_PASSWORD)): str,
                vol.Optional(
                    CONF_IMAP_PORT, default=config.get(CONF_IMAP_PORT, DEFAULT_PORT)
                ): int,
                vol.Optional(
                    CONF_FOLDER, default=config.get(CONF_FOLDER, DEFAULT_FOLDER)
                ): str,
                # Settings
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): cv.positive_int,
                vol.Optional(
                    CONF_ENABLE_DEBUG,
                    default=options.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG),
                ): bool,
                # Gemini AI
                vol.Optional(
                    CONF_GEMINI_API_KEY, default=options.get(CONF_GEMINI_API_KEY, "")
                ): str,
                vol.Optional(
                    CONF_GEMINI_MODEL,
                    default=options.get(CONF_GEMINI_MODEL, DEFAULT_GEMINI_MODEL),
                ): str,
                # Kalendrar (Optional)
                vol.Optional(
                    CONF_CALENDAR_1,
                    description={"suggested_value": options.get(CONF_CALENDAR_1)},
                ): calendar_selector,
                vol.Optional(
                    CONF_CALENDAR_2,
                    description={"suggested_value": options.get(CONF_CALENDAR_2)},
                ): calendar_selector,
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
