# Version: 0.2.1 - 2025-12-15
"""Config flow för Mail Agent integration."""

import imaplib
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    LOGGER,
    CONF_IMAP_SERVER,
    CONF_IMAP_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_FOLDER,
    DEFAULT_PORT,
    DEFAULT_FOLDER,
)

# Vi definierar schemat här
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IMAP_SERVER): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_IMAP_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_FOLDER, default=DEFAULT_FOLDER): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validera att användaren angivit korrekta uppgifter genom att testa anslutning."""

    # Kör IMAP-test i en tråd för att inte blockera
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

    # Returnera titel för integrationen
    return {"title": data[CONF_USERNAME]}


class MailAgentConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hantera en config flow för Mail Agent."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Hantera det inledande steget."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                # Kontrollera att vi inte redan har denna mail uppsatt
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

            except ValueError:
                errors["base"] = "invalid_auth"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Oväntat fel vid konfiguration")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
