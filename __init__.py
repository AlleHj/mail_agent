# Version: 0.15.1 - 2025-12-17
"""Mail Agent - Huvudlogik med Global Låsning (Single Thread Lock)."""

import imaplib
import email
from email.header import decode_header
from pathlib import Path
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

# Importera den nya processorn (SVENSKA)
from .kallelse_processor import KallelseProcessor

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
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENABLE_DEBUG,
    DEFAULT_GEMINI_MODEL,
)

PLATFORMS = []

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup."""
    config = entry.data
    options = entry.options

    scanner = MailAgentScanner(
        hass,
        {**config, **options}
    )

    remove_listener = async_track_time_interval(
        hass, scanner.check_mail, timedelta(seconds=scanner.scan_interval)
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "scanner": scanner,
        "remove_listener": remove_listener,
    }

    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id]["remove_listener"]()
        hass.data[DOMAIN].pop(entry.entry_id)
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


class MailAgentScanner:
    def __init__(self, hass, config):
        self.hass = hass
        self.config = config

        self.server = config.get(CONF_IMAP_SERVER)
        self.port = config.get(CONF_IMAP_PORT)
        self.user = config.get(CONF_USERNAME)
        self.password = config.get(CONF_PASSWORD)
        self.folder = config.get(CONF_FOLDER)

        self.scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self.enable_debug = config.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG)

        self.interpretation_type = config.get(CONF_INTERPRETATION_TYPE, TYPE_KALLELSE)

        # Initiera Processor
        self.processor = None
        if self.interpretation_type == TYPE_KALLELSE:
            self.processor = KallelseProcessor(hass, config)
        else:
            LOGGER.warning("Okänd tolkningstyp: %s. Fallback till Kallelse.", self.interpretation_type)
            self.processor = KallelseProcessor(hass, config)

        self.storage_dir = Path(hass.config.path("www", "mail_agent_temp"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # GLOBAL LOCK: Förhindrar att flera scanningar körs samtidigt
        self._is_scanning = False

    async def check_mail(self, now=None):
        """Asynkron startpunkt som anropas av timer."""
        # OM vi redan scannar -> AVBRYT DIREKT
        if self._is_scanning:
            if self.enable_debug:
                LOGGER.debug("Sökning pågår redan. Hoppar över denna körning för att undvika dubbletter.")
            return

        # Lås dörren
        self._is_scanning = True

        try:
            # Kör den tunga synkrona logiken i en tråd
            await self.hass.async_add_executor_job(self._check_mail_sync)
        finally:
            # Lås upp dörren OAVSETT om det gick bra eller blev fel
            self._is_scanning = False

    def _check_mail_sync(self):
        """Synkron logik som körs i executor-tråden."""
        mail_con = None
        try:
            mail_con = imaplib.IMAP4_SSL(self.server, self.port)
            mail_con.login(self.user, self.password)
            mail_con.select(self.folder)

            status, messages = mail_con.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                return

            mail_ids = messages[0].split()

            if self.enable_debug:
                LOGGER.info("Hittade %s nya mail. Bearbetar sekventiellt...", len(mail_ids))

            for mail_id in mail_ids:
                try:
                    res, msg_data = mail_con.fetch(mail_id, "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            self._process_single_mail(msg)
                except Exception as e:
                    LOGGER.error("Fel vid bearbetning av mail ID %s: %s", mail_id, e)

        except Exception as e:
            LOGGER.error("Fel vid anslutning/sökning: %s", e)
        finally:
            if mail_con:
                try:
                    mail_con.close()
                    mail_con.logout()
                except Exception:
                    pass

    def _process_single_mail(self, msg):
        subject = self._decode_subject(msg["Subject"])
        sender = msg.get("From")
        body = self._get_mail_body(msg)
        attachment_paths = self._save_attachments(msg)

        if self.enable_debug:
            LOGGER.info(f"Hämtat mail från {sender}. Skickar till processor: {self.interpretation_type}")

        if self.processor:
            self.processor.process_email(sender, subject, body, attachment_paths)

    def _save_attachments(self, msg):
        saved_paths = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart': continue
                filename = part.get_filename()
                if not filename: continue
                if "pdf" in part.get_content_type():
                    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
                    filepath = self.storage_dir / filename
                    with open(filepath, "wb") as f: f.write(part.get_payload(decode=True))
                    saved_paths.append(filepath)
        return saved_paths

    def _get_mail_body(self, msg):
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try: body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace"); break
                    except: pass
        else:
            try: body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
            except: pass
        return body.strip()

    def _decode_subject(self, encoded_subject):
        if not encoded_subject: return "Okänt ämne"
        subject, encoding = decode_header(encoded_subject)[0]
        if isinstance(subject, bytes): return subject.decode(encoding if encoding else "utf-8")
        return subject