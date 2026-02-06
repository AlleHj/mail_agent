# Fil: custom_components/mail_agent/config_flow.py | Version: 0.21.0
"""Config flow för Mail Agent integration."""

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlowResult,
    OptionsFlow,
    ConfigEntry,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.config_entry_oauth2_flow import AbstractOAuth2FlowHandler
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
    CONF_DRIVE_FOLDER_PATH,
    CONF_SUMMARY_FILENAME,
    CONF_SENDER_NAME,
    TYPE_KALLELSE,
    TYPE_FORVALTARE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENABLE_DEBUG,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_INTERPRETATION_TYPE,
    DEFAULT_DRIVE_FOLDER_PATH,
    DEFAULT_SUMMARY_FILENAME,
    DEFAULT_SENDER_NAME,
    OAUTH2_SCOPES,
)

class MailAgentConfigFlow(AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Hantera en config flow för Mail Agent med OAuth2."""

    VERSION = 1
    DOMAIN = DOMAIN

    @property
    def logger(self):
        """Return logger."""
        return LOGGER

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": " ".join(OAUTH2_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }

    async def async_step_reauth(self, entry_data: dict) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                description_placeholders={"account": self._get_reauth_entry().data.get("auth_implementation")},
            )
        return await self.async_step_user()

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        """Create an entry for the flow."""
        # Unikt ID baserat på auth implementation title eller user ID om möjligt,
        # men för nu använder vi bara implementationen eller inget (låter HA hantera det).
        # Vi sätter title till implementationens namn eller "Mail Agent".
        title = self.flow_impl.name
        if "token" in data and "expires_at" in data["token"]:
             # Vi kan försöka hämta email här om vi vill ha en snygg titel,
             # men det kräver ett extra anrop. Vi nöjer oss med default.
             pass

        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MailAgentOptionsFlowHandler(config_entry)


class MailAgentOptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        # Bygg upp listor för options-flödet
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
                    {"label": "Förvaltare (Faktura/Admin)", "value": TYPE_FORVALTARE},
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="interpretation_type"
            )
        )

        options_schema = vol.Schema({
            # Logic Type
            vol.Optional(CONF_INTERPRETATION_TYPE, default=options.get(CONF_INTERPRETATION_TYPE, DEFAULT_INTERPRETATION_TYPE)): type_selector,

            # Sender Name (used for emails)
            vol.Optional(CONF_SENDER_NAME, default=options.get(CONF_SENDER_NAME, DEFAULT_SENDER_NAME)): str,

            # Drive / Storage
            vol.Optional(CONF_DRIVE_FOLDER_PATH, default=options.get(CONF_DRIVE_FOLDER_PATH, DEFAULT_DRIVE_FOLDER_PATH)): str,
            vol.Optional(CONF_SUMMARY_FILENAME, default=options.get(CONF_SUMMARY_FILENAME, DEFAULT_SUMMARY_FILENAME)): str,

            # Operation
            vol.Optional(CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): cv.positive_int,
            vol.Optional(CONF_ENABLE_DEBUG, default=options.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG)): bool,

            # AI
            vol.Optional(CONF_GEMINI_API_KEY, default=options.get(CONF_GEMINI_API_KEY, "")): str,
            vol.Optional(CONF_GEMINI_MODEL, default=options.get(CONF_GEMINI_MODEL, DEFAULT_GEMINI_MODEL)): str,

            # Calendar
            vol.Optional(CONF_CALENDAR_1, description={"suggested_value": options.get(CONF_CALENDAR_1)}): calendar_selector,
            vol.Optional(CONF_CALENDAR_2, description={"suggested_value": options.get(CONF_CALENDAR_2)}): calendar_selector,

            # Email Recipients
            vol.Optional(CONF_EMAIL_RECIPIENT_1, description={"suggested_value": options.get(CONF_EMAIL_RECIPIENT_1)}): str,
            vol.Optional(CONF_EMAIL_RECIPIENT_2, description={"suggested_value": options.get(CONF_EMAIL_RECIPIENT_2)}): str,

            # Notifications
            vol.Optional(CONF_NOTIFY_SERVICE_1, description={"suggested_value": options.get(CONF_NOTIFY_SERVICE_1)}): notify_selector,
            vol.Optional(CONF_NOTIFY_SERVICE_2, description={"suggested_value": options.get(CONF_NOTIFY_SERVICE_2)}): notify_selector,
        })

        return self.async_show_form(step_id="init", data_schema=options_schema)
