# Fil: custom_components/mail_agent/config_flow.py | Version: 0.22.0
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

    def __init__(self):
        super().__init__()
        self._oauth_data = {}

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
        self._oauth_data = data
        return await self.async_step_config()

    async def async_step_config(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle the configuration step after OAuth."""
        if user_input is not None:
            # Merge OAuth data with user input options
            # Vi lagrar user_input i options för enkelhetens skull, eller i data om det är anslutningsrelaterat
            # Men i detta fall är det mest inställningar.
            # config_entries förväntar sig 'data' och 'options'.
            # AbstractOAuth2FlowHandler sparar auth-data i 'data'.

            title = self.flow_impl.name
            return self.async_create_entry(
                title=title,
                data=self._oauth_data,
                options=user_input
            )

        # Hämta schema (samma som OptionsFlow)
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

        # Default values
        options_schema = vol.Schema({
            # Logic Type
            vol.Optional(CONF_INTERPRETATION_TYPE, default=DEFAULT_INTERPRETATION_TYPE): type_selector,

            # Sender Name
            vol.Optional(CONF_SENDER_NAME, default=DEFAULT_SENDER_NAME): str,

            # Drive / Storage
            vol.Optional(CONF_DRIVE_FOLDER_PATH, default=DEFAULT_DRIVE_FOLDER_PATH): str,
            vol.Optional(CONF_SUMMARY_FILENAME, default=DEFAULT_SUMMARY_FILENAME): str,

            # Operation
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
            vol.Optional(CONF_ENABLE_DEBUG, default=DEFAULT_ENABLE_DEBUG): bool,

            # AI
            vol.Optional(CONF_GEMINI_API_KEY, default=""): str,
            vol.Optional(CONF_GEMINI_MODEL, default=DEFAULT_GEMINI_MODEL): str,

            # Calendar
            vol.Optional(CONF_CALENDAR_1): calendar_selector,
            vol.Optional(CONF_CALENDAR_2): calendar_selector,

            # Email Recipients
            vol.Optional(CONF_EMAIL_RECIPIENT_1): str,
            vol.Optional(CONF_EMAIL_RECIPIENT_2): str,

            # Notifications
            vol.Optional(CONF_NOTIFY_SERVICE_1): notify_selector,
            vol.Optional(CONF_NOTIFY_SERVICE_2): notify_selector,
        })

        return self.async_show_form(step_id="config", data_schema=options_schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MailAgentOptionsFlowHandler()


class MailAgentOptionsFlowHandler(OptionsFlow):
    # OBS: Vi tar bort __init__ helt eftersom OptionsFlow hanterar config_entry internt.
    # config_entry nås via self.config_entry (property).

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

            # Sender Name
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
