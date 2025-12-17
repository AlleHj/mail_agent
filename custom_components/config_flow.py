# Version: 0.16.0 - 2025-12-17
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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    DOMAIN,
    LOGGER,
    CONF_IMAP_SERVER,
    CONF_IMAP_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_FOLDER,
    CONF_SMTP_SERVER,
    CONF_SMTP_PORT,
    CONF_SMTP_SENDER_NAME, # Ny
    CONF_SCAN_INTERVAL,
    CONF_ENABLE_DEBUG,
    CONF_GEMINI_API_KEY,
    CONF_GEMINI_MODEL,
    CONF_CALENDAR_1,
    CONF_CALENDAR_2,
    CONF_EMAIL_RECIPIENT_1,
    CONF_EMAIL_RECIPIENT_2,
    CONF_NOTIFY_SERVICE_1,
    CONF_NOTIFY_SERVICE_2,
    CONF_INTERPRETATION_TYPE,
    TYPE_KALLELSE,
    DEFAULT_IMAP_PORT,
    DEFAULT_SMTP_PORT,
    DEFAULT_FOLDER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENABLE_DEBUG,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_INTERPRETATION_TYPE,
    DEFAULT_SMTP_SENDER_NAME, # Ny
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

        notify_services = []
        services = self.hass.services.async_services()
        if "notify" in services:
            for service in services["notify"]:
                notify_services.append(f"notify.{service}")
        notify_services.sort()

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                data_config = {
                    CONF_IMAP_SERVER: user_input[CONF_IMAP_SERVER],
                    CONF_IMAP_PORT: user_input[CONF_IMAP_PORT],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_FOLDER: user_input[CONF_FOLDER],
                }

                options_config = {
                    CONF_SMTP_SERVER: user_input.get(CONF_SMTP_SERVER),
                    CONF_SMTP_PORT: user_input.get(CONF_SMTP_PORT),
                    CONF_SMTP_SENDER_NAME: user_input.get(CONF_SMTP_SENDER_NAME), # Ny
                    CONF_INTERPRETATION_TYPE: user_input.get(CONF_INTERPRETATION_TYPE),
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL),
                    CONF_ENABLE_DEBUG: user_input.get(CONF_ENABLE_DEBUG),
                    CONF_GEMINI_API_KEY: user_input.get(CONF_GEMINI_API_KEY),
                    CONF_GEMINI_MODEL: user_input.get(CONF_GEMINI_MODEL),
                    CONF_CALENDAR_1: user_input.get(CONF_CALENDAR_1),
                    CONF_CALENDAR_2: user_input.get(CONF_CALENDAR_2),
                    CONF_EMAIL_RECIPIENT_1: user_input.get(CONF_EMAIL_RECIPIENT_1),
                    CONF_EMAIL_RECIPIENT_2: user_input.get(CONF_EMAIL_RECIPIENT_2),
                    CONF_NOTIFY_SERVICE_1: user_input.get(CONF_NOTIFY_SERVICE_1),
                    CONF_NOTIFY_SERVICE_2: user_input.get(CONF_NOTIFY_SERVICE_2),
                }

                return self.async_create_entry(
                    title=info["title"],
                    data=data_config,
                    options=options_config
                )
            except ValueError:
                errors["base"] = "invalid_auth"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                LOGGER.exception("Oväntat fel")
                errors["base"] = "unknown"

        notify_selector = SelectSelector(
            SelectSelectorConfig(
                options=notify_services,
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=True
            )
        )

        calendar_selector = EntitySelector(
            EntitySelectorConfig(domain="calendar", multiple=False)
        )

        type_selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"label": "Tolka kallelse", "value": TYPE_KALLELSE},
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="interpretation_type"
            )
        )

        schema = vol.Schema({
            # IMAP
            vol.Required(CONF_IMAP_SERVER): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_IMAP_PORT, default=DEFAULT_IMAP_PORT): int,
            vol.Optional(CONF_FOLDER, default=DEFAULT_FOLDER): str,

            # SMTP
            vol.Optional(CONF_SMTP_SERVER): str,
            vol.Optional(CONF_SMTP_PORT, default=DEFAULT_SMTP_PORT): int,
            # NYTT FÄLT FÖR AVSÄNDARNAMN
            vol.Optional(CONF_SMTP_SENDER_NAME, default=DEFAULT_SMTP_SENDER_NAME): str,

            # Logic Type
            vol.Optional(CONF_INTERPRETATION_TYPE, default=DEFAULT_INTERPRETATION_TYPE): type_selector,

            # AI
            vol.Required(CONF_GEMINI_API_KEY): str,
            vol.Optional(CONF_GEMINI_MODEL, default=DEFAULT_GEMINI_MODEL): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
            vol.Optional(CONF_ENABLE_DEBUG, default=DEFAULT_ENABLE_DEBUG): bool,

            # Integrations
            vol.Optional(CONF_CALENDAR_1): calendar_selector,
            vol.Optional(CONF_CALENDAR_2): calendar_selector,
            vol.Optional(CONF_NOTIFY_SERVICE_1): notify_selector,
            vol.Optional(CONF_NOTIFY_SERVICE_2): notify_selector,
            vol.Optional(CONF_EMAIL_RECIPIENT_1): str,
            vol.Optional(CONF_EMAIL_RECIPIENT_2): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class MailAgentOptionsFlowHandler(OptionsFlow):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            connection_data = {
                CONF_IMAP_SERVER: user_input[CONF_IMAP_SERVER],
                CONF_IMAP_PORT: user_input[CONF_IMAP_PORT],
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_FOLDER: user_input[CONF_FOLDER],
            }
            options_data = {
                CONF_SMTP_SERVER: user_input.get(CONF_SMTP_SERVER),
                CONF_SMTP_PORT: user_input.get(CONF_SMTP_PORT),
                CONF_SMTP_SENDER_NAME: user_input.get(CONF_SMTP_SENDER_NAME), # Ny
                CONF_INTERPRETATION_TYPE: user_input.get(CONF_INTERPRETATION_TYPE),
                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL),
                CONF_ENABLE_DEBUG: user_input.get(CONF_ENABLE_DEBUG),
                CONF_GEMINI_API_KEY: user_input.get(CONF_GEMINI_API_KEY),
                CONF_GEMINI_MODEL: user_input.get(CONF_GEMINI_MODEL),
                CONF_CALENDAR_1: user_input.get(CONF_CALENDAR_1),
                CONF_CALENDAR_2: user_input.get(CONF_CALENDAR_2),
                CONF_EMAIL_RECIPIENT_1: user_input.get(CONF_EMAIL_RECIPIENT_1),
                CONF_EMAIL_RECIPIENT_2: user_input.get(CONF_EMAIL_RECIPIENT_2),
                CONF_NOTIFY_SERVICE_1: user_input.get(CONF_NOTIFY_SERVICE_1),
                CONF_NOTIFY_SERVICE_2: user_input.get(CONF_NOTIFY_SERVICE_2),
            }

            self.hass.config_entries.async_update_entry(self.config_entry, data=connection_data)
            return self.async_create_entry(title="", data=options_data)

        config = self.config_entry.data
        options = self.config_entry.options

        notify_services = []
        services = self.hass.services.async_services()
        if "notify" in services:
            for service in services["notify"]:
                notify_services.append(f"notify.{service}")
        notify_services.sort()

        notify_selector = SelectSelector(
            SelectSelectorConfig(
                options=notify_services,
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=True
            )
        )

        calendar_selector = EntitySelector(
            EntitySelectorConfig(domain="calendar", multiple=False)
        )

        type_selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"label": "Tolka kallelse", "value": TYPE_KALLELSE},
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="interpretation_type"
            )
        )

        options_schema = vol.Schema({
            vol.Required(CONF_IMAP_SERVER, default=config.get(CONF_IMAP_SERVER)): str,
            vol.Required(CONF_USERNAME, default=config.get(CONF_USERNAME)): str,
            vol.Required(CONF_PASSWORD, default=config.get(CONF_PASSWORD)): str,
            vol.Optional(CONF_IMAP_PORT, default=config.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)): int,
            vol.Optional(CONF_FOLDER, default=config.get(CONF_FOLDER, DEFAULT_FOLDER)): str,

            vol.Optional(CONF_SMTP_SERVER, description={"suggested_value": options.get(CONF_SMTP_SERVER, "")}): str,
            vol.Optional(CONF_SMTP_PORT, default=options.get(CONF_SMTP_PORT, DEFAULT_SMTP_PORT)): int,
            # NYTT FÄLT FÖR OPTIONS
            vol.Optional(CONF_SMTP_SENDER_NAME, default=options.get(CONF_SMTP_SENDER_NAME, DEFAULT_SMTP_SENDER_NAME)): str,

            vol.Optional(CONF_INTERPRETATION_TYPE, default=options.get(CONF_INTERPRETATION_TYPE, DEFAULT_INTERPRETATION_TYPE)): type_selector,
            vol.Optional(CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): cv.positive_int,
            vol.Optional(CONF_ENABLE_DEBUG, default=options.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG)): bool,
            vol.Optional(CONF_GEMINI_API_KEY, default=options.get(CONF_GEMINI_API_KEY, "")): str,
            vol.Optional(CONF_GEMINI_MODEL, default=options.get(CONF_GEMINI_MODEL, DEFAULT_GEMINI_MODEL)): str,

            vol.Optional(CONF_CALENDAR_1, description={"suggested_value": options.get(CONF_CALENDAR_1)}): calendar_selector,
            vol.Optional(CONF_CALENDAR_2, description={"suggested_value": options.get(CONF_CALENDAR_2)}): calendar_selector,

            vol.Optional(CONF_EMAIL_RECIPIENT_1, description={"suggested_value": options.get(CONF_EMAIL_RECIPIENT_1)}): str,
            vol.Optional(CONF_EMAIL_RECIPIENT_2, description={"suggested_value": options.get(CONF_EMAIL_RECIPIENT_2)}): str,

            vol.Optional(CONF_NOTIFY_SERVICE_1, description={"suggested_value": options.get(CONF_NOTIFY_SERVICE_1)}): notify_selector,
            vol.Optional(CONF_NOTIFY_SERVICE_2, description={"suggested_value": options.get(CONF_NOTIFY_SERVICE_2)}): notify_selector,
        })

        return self.async_show_form(step_id="init", data_schema=options_schema)