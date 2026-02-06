# Version: 0.22.0
"""Konstanter för Mail Agent."""
import logging

DOMAIN = "mail_agent"

# Signals
SIGNAL_MAIL_AGENT_UPDATE = "mail_agent_update"

# Scopes
OAUTH2_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
]

# Labels
LABEL_AI_HANDLED = "AI-HANTERAD"

# Options / Logic Type
CONF_INTERPRETATION_TYPE = "interpretation_type"
TYPE_KALLELSE = "kallelse"
TYPE_FORVALTARE = "forvaltare"

# Options / Storage
CONF_DRIVE_FOLDER_PATH = "drive_folder_path"
CONF_SUMMARY_FILENAME = "summary_filename"

# Options / Gemini
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_DEBUG = "enable_debug"
CONF_GEMINI_API_KEY = "gemini_api_key"
CONF_GEMINI_MODEL = "gemini_model"

# Options / Calendar
CONF_CALENDAR_1 = "calendar_entity_1"
CONF_CALENDAR_2 = "calendar_entity_2"

# Options / Notifications
CONF_EMAIL_RECIPIENT_1 = "email_recipient_1"
CONF_EMAIL_RECIPIENT_2 = "email_recipient_2"
CONF_NOTIFY_SERVICE_1 = "notify_service_1"
CONF_NOTIFY_SERVICE_2 = "notify_service_2"
CONF_SENDER_NAME = "sender_name"
CONF_TARGET_EMAIL = "target_email"

# Defaults
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_ENABLE_DEBUG = False
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_INTERPRETATION_TYPE = TYPE_KALLELSE
DEFAULT_DRIVE_FOLDER_PATH = "Fakturor"
DEFAULT_SUMMARY_FILENAME = "fakturor_oversikt.json"
DEFAULT_SENDER_NAME = "Mail Agent"

LOGGER = logging.getLogger(__package__)
