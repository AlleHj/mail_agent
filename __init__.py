# Version: 0.3.2 - 2025-12-15
"""Mail Agent - Initialisering och mail-loop via Config Entry."""

import imaplib
import email
from email.header import decode_header
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

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
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENABLE_DEBUG,
)

PLATFORMS = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sätt upp Mail Agent från en config entry (UI)."""

    # Hämta anslutningsdata
    config = entry.data
    server = config[CONF_IMAP_SERVER]
    port = config[CONF_IMAP_PORT]
    user = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    folder = config[CONF_FOLDER]

    # Hämta inställningar (options) med fallback till default
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    enable_debug = entry.options.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG)

    LOGGER.info(
        "Initierar Mail Agent för %s (Intervall: %ss, Debug: %s)",
        user,
        scan_interval,
        enable_debug,
    )

    scanner = MailAgentScanner(
        hass, server, port, user, password, folder, enable_debug
    )

    # Starta scanningen med det konfigurerade intervallet
    remove_listener = async_track_time_interval(
        hass, scanner.check_mail, timedelta(seconds=scan_interval)
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "scanner": scanner,
        "remove_listener": remove_listener,
    }

    # Lägg till lyssnare för uppdateringar av options
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Städa upp när integrationen tas bort."""
    if entry.entry_id in hass.data[DOMAIN]:
        data = hass.data[DOMAIN][entry.entry_id]
        data["remove_listener"]()
        hass.data[DOMAIN].pop(entry.entry_id)

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Hantera uppdateringar av options (körs när användaren ändrar inställningar)."""
    await hass.config_entries.async_reload(entry.entry_id)


class MailAgentScanner:
    """Klass för att hantera IMAP-scanning och processning."""

    def __init__(self, hass, server, port, user, password, folder, enable_debug):
        self.hass = hass
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.folder = folder
        self.enable_debug = enable_debug

    async def check_mail(self, now=None):
        """Asynkron wrapper."""
        await self.hass.async_add_executor_job(self._check_mail_sync)

    def _check_mail_sync(self):
        """Synkron metod som körs i tråd."""
        mail_con = None
        try:
            mail_con = imaplib.IMAP4_SSL(self.server, self.port)
            mail_con.login(self.user, self.password)
            mail_con.select(self.folder)

            status, messages = mail_con.search(None, "UNSEEN")

            if status != "OK":
                return

            mail_ids = messages[0].split()

            if not mail_ids:
                return

            if self.enable_debug:
                LOGGER.info("Hittade %s nya mail.", len(mail_ids))

            for mail_id in mail_ids:
                res, msg_data = mail_con.fetch(mail_id, "(RFC822)")

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])

                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8")

                        sender = msg.get("From")
                        body_text = self._get_mail_body(msg)

                        # Kontrollera bilagor
                        has_attachment = self._check_for_attachments(msg)
                        attachment_str = "TRUE" if has_attachment else "FALSE"

                        # KONTROLLERAD DEBUG-UTSKRIFT
                        if self.enable_debug:
                            LOGGER.info(
                                "\n--- MAIL AGENT DEBUG ---\nFrån: %s\nÄmne: %s\nBilaga: %s\nMeddelande:\n%s\n------------------------",
                                sender,
                                subject,
                                attachment_str,
                                body_text,
                            )

        except Exception as e:
            LOGGER.error("Fel vid mail-check: %s", e)
        finally:
            if mail_con:
                try:
                    mail_con.close()
                    mail_con.logout()
                except Exception:
                    pass

    def _check_for_attachments(self, msg):
        """Kontrollera om mailet innehåller bilagor."""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue

                disposition = part.get("Content-Disposition")
                if disposition and "attachment" in disposition:
                    return True
        return False

    def _get_mail_body(self, msg):
        """Extrahera textinnehållet från ett mail."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if (
                    content_type == "text/plain"
                    and "attachment" not in content_disposition
                ):
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset()
                        if payload:
                            body = payload.decode(
                                charset if charset else "utf-8", errors="replace"
                            )
                            break
                    except Exception as e:
                        if self.enable_debug:
                            LOGGER.warning("Kunde inte avkoda text-del: %s", e)
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset()
                if payload:
                    body = payload.decode(
                        charset if charset else "utf-8", errors="replace"
                    )
            except Exception as e:
                if self.enable_debug:
                    LOGGER.warning("Kunde inte avkoda body: %s", e)

        return body.strip()