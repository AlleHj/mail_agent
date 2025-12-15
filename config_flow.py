# Version: 0.3.4 - 2025-12-15
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
    DEFAULT_PORT,
    DEFAULT_FOLDER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENABLE_DEBUG,
)

# Vi definierar ett gemensamt schema för att undvika kodupprepning,
# men i Options-flödet måste vi sätta default-värden dynamiskt.

async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validera att användaren angivit korrekta uppgifter genom att testa anslutning."""

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
    """Hantera en config flow för Mail Agent (första installationen)."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Skapa options flow handler."""
        return MailAgentOptionsFlowHandler()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Hantera det inledande steget."""
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
                LOGGER.exception("Oväntat fel vid konfiguration")
                errors["base"] = "unknown"

        # Schema för ny installation (tomma fält)
        schema = vol.Schema(
            {
                vol.Required(CONF_IMAP_SERVER): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_IMAP_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_FOLDER, default=DEFAULT_FOLDER): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )


class MailAgentOptionsFlowHandler(OptionsFlow):
    """Hantera ändringar av inställningar OCH anslutningsuppgifter."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Hantera konfigurationsformuläret."""
        errors = {}

        if user_input is not None:
            try:
                # 1. Validera de nya uppgifterna (även om vi bara ändrat intervallet,
                # vill vi veta att inloggningen fortfarande fungerar).
                await validate_input(self.hass, user_input)

                # 2. Separera data (anslutning) från options (inställningar)
                connection_data = {
                    CONF_IMAP_SERVER: user_input[CONF_IMAP_SERVER],
                    CONF_IMAP_PORT: user_input[CONF_IMAP_PORT],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_FOLDER: user_input[CONF_FOLDER],
                }

                options_data = {
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    CONF_ENABLE_DEBUG: user_input.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG),
                }

                # 3. Uppdatera själva Config Entryn med nya anslutningsuppgifter
                # Detta krävs för att 'data' inte uppdateras automatiskt av en OptionsFlow.
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=connection_data
                )

                # 4. Returnera options (detta uppdaterar entry.options automatiskt)
                return self.async_create_entry(title="", data=options_data)

            except ValueError:
                errors["base"] = "invalid_auth"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                LOGGER.exception("Oväntat fel vid uppdatering av konfiguration")
                errors["base"] = "unknown"

        # Hämta nuvarande värden
        config = self.config_entry.data
        options = self.config_entry.options

        # Bygg schema med förifyllda värden från nuvarande konfiguration
        options_schema = vol.Schema(
            {
                # Anslutningsuppgifter (från .data)
                vol.Required(CONF_IMAP_SERVER, default=config.get(CONF_IMAP_SERVER)): str,
                vol.Required(CONF_USERNAME, default=config.get(CONF_USERNAME)): str,
                vol.Required(CONF_PASSWORD, default=config.get(CONF_PASSWORD)): str,
                vol.Optional(CONF_IMAP_PORT, default=config.get(CONF_IMAP_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_FOLDER, default=config.get(CONF_FOLDER, DEFAULT_FOLDER)): str,

                # Inställningar (från .options)
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): cv.positive_int,
                vol.Optional(
                    CONF_ENABLE_DEBUG,
                    default=options.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG)
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema, errors=errors)