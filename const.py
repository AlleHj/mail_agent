# Version: 0.3.0 - 2025-12-15
"""Konstanter för Mail Agent."""
import logging

DOMAIN = "mail_agent"

# Konfigurationsnycklar (Connection)
CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_FOLDER = "folder"

# Konfigurationsnycklar (Options)
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_DEBUG = "enable_debug"

# Default-värden
DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"
DEFAULT_SCAN_INTERVAL = 60  # Sekunder
DEFAULT_ENABLE_DEBUG = False

# Logger
LOGGER = logging.getLogger(__package__)