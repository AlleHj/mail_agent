# Version: 0.11.1 - 2025-12-15
"""Konstanter för Mail Agent."""
import logging

DOMAIN = "mail_agent"

# Connection
CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_FOLDER = "folder"

# Options / Gemini
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_DEBUG = "enable_debug"
CONF_GEMINI_API_KEY = "gemini_api_key"
CONF_GEMINI_MODEL = "gemini_model"

# Options / Calendar
CONF_CALENDAR_1 = "calendar_entity_1"
CONF_CALENDAR_2 = "calendar_entity_2"

# Options / Notifications
CONF_EMAIL_SERVICE = "email_service"         # T.ex. notify.skicka_epost
CONF_EMAIL_RECIPIENT_1 = "email_recipient_1" # T.ex. kalle@hjalmar.com
CONF_EMAIL_RECIPIENT_2 = "email_recipient_2"
CONF_NOTIFY_SERVICE_1 = "notify_service_1"   # T.ex. notify.mobile_app_iphone
CONF_NOTIFY_SERVICE_2 = "notify_service_2"

# Defaults
DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_ENABLE_DEBUG = False
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash-exp"

LOGGER = logging.getLogger(__package__)