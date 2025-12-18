# Version: 0.18.0 - 2025-12-18
"""Konstanter för Mail Agent."""
import logging

DOMAIN = "mail_agent"

# Signals
SIGNAL_MAIL_AGENT_UPDATE = "mail_agent_update"

# Connection
CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_FOLDER = "folder"

# SMTP
CONF_SMTP_SERVER = "smtp_server"
CONF_SMTP_PORT = "smtp_port"
CONF_SMTP_SENDER_NAME = "smtp_sender_name"

# Options / Logic Type
CONF_INTERPRETATION_TYPE = "interpretation_type"
TYPE_KALLELSE = "kallelse"

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

# Defaults
DEFAULT_IMAP_PORT = 993
DEFAULT_SMTP_PORT = 587
DEFAULT_FOLDER = "INBOX"
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_ENABLE_DEBUG = False
DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
DEFAULT_INTERPRETATION_TYPE = TYPE_KALLELSE
DEFAULT_SMTP_SENDER_NAME = "Mail Agent"

LOGGER = logging.getLogger(__package__)