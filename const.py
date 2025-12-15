# Version: 0.2.0 - 2025-12-15
"""Konstanter för Mail Agent."""
import logging

DOMAIN = "mail_agent"

# Konfigurationsnycklar
CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_FOLDER = "folder"

# Default-värden
DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"

# Logger
LOGGER = logging.getLogger(__package__)