# Version: 0.2.0 - 2025-12-15
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
)

PLATFORMS = []  # Vi har inga sensor/binary_sensor plattformar än, allt körs här.


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sätt upp Mail Agent från en config entry (UI)."""

    config = entry.data
    server = config[CONF_IMAP_SERVER]
    port = config[CONF_IMAP_PORT]
    user = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    folder = config[CONF_FOLDER]

    LOGGER.info("Initierar Mail Agent för %s", user)

    scanner = MailAgentScanner(hass, server, port, user, password, folder)

    # Starta scanningen direkt
    # Spara "unsubscribe" funktionen så vi kan stänga av den om integrationen tas bort
    remove_listener = async_track_time_interval(
        hass, scanner.check_mail, timedelta(seconds=60)
    )

    # Spara referenser i hass.data så vi kommer åt dem vid behov
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "scanner": scanner,
        "remove_listener": remove_listener,
    }

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Städa upp när integrationen tas bort."""
    if entry.entry_id in hass.data[DOMAIN]:
        data = hass.data[DOMAIN][entry.entry_id]
        # Stoppa timer-loopen
        data["remove_listener"]()
        hass.data[DOMAIN].pop(entry.entry_id)

    return True


class MailAgentScanner:
    """Klass för att hantera IMAP-scanning och processning."""

    def __init__(self, hass, server, port, user, password, folder):
        self.hass = hass
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.folder = folder

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

            LOGGER.info("Hittade %s nya mail.", len(mail_ids))

            for mail_id in mail_ids:
                res, msg_data = mail_con.fetch(mail_id, "(RFC822)")

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])

                        # Avkoda ämne
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8")

                        sender = msg.get("From")

                        # Extrahera brödtext (body)
                        body_text = self._get_mail_body(msg)

                        # DEBUG UTMATNING - NU MED BODY
                        LOGGER.warning(
                            "\n--- MAIL AGENT DEBUG ---\nFrån: %s\nÄmne: %s\nMeddelande:\n%s\n------------------------",
                            sender,
                            subject,
                            body_text,
                        )

                        # Här kommer vi senare lägga in logik för att skicka till Gemini

        except Exception as e:
            LOGGER.error("Fel vid mail-check: %s", e)
        finally:
            if mail_con:
                try:
                    mail_con.close()
                    mail_con.logout()
                except Exception:
                    pass

    def _get_mail_body(self, msg):
        """Extrahera textinnehållet från ett mail (multipart eller plain)."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # Vi letar efter text/plain primärt, och ignorerar bilagor
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
                            break  # Vi tar första text-delen vi hittar
                    except Exception as e:
                        LOGGER.warning("Kunde inte avkoda text-del: %s", e)
        else:
            # Inte multipart, vanligt textmail
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset()
                if payload:
                    body = payload.decode(
                        charset if charset else "utf-8", errors="replace"
                    )
            except Exception as e:
                LOGGER.warning("Kunde inte avkoda body: %s", e)

        return body.strip()
