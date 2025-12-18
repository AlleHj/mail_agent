# Version: 0.19.0 - 2025-12-18
"""Mail Agent - Huvudlogik med Global Låsning, Sensorstöd och Restore."""

import imaplib
import email
from email.header import decode_header
from pathlib import Path
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from homeassistant.const import Platform

from .kallelse_processor import KallelseProcessor

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
    CONF_INTERPRETATION_TYPE,
    TYPE_KALLELSE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENABLE_DEBUG,
    SIGNAL_MAIL_AGENT_UPDATE,
)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup."""
    config = entry.data
    options = entry.options

    scanner = MailAgentScanner(
        hass,
        {**config, **options},
        entry.entry_id
    )

    remove_listener = async_track_time_interval(
        hass, scanner.check_mail, timedelta(seconds=scanner.scan_interval)
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "scanner": scanner,
        "remove_listener": remove_listener,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id]["remove_listener"]()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


class MailAgentScanner:
    def __init__(self, hass, config, entry_id):
        self.hass = hass
        self.config = config
        self.entry_id = entry_id

        self.server = config.get(CONF_IMAP_SERVER)
        self.port = config.get(CONF_IMAP_PORT)
        self.user = config.get(CONF_USERNAME)
        self.password = config.get(CONF_PASSWORD)
        self.folder = config.get(CONF_FOLDER)

        self.scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self.enable_debug = config.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG)
        self.interpretation_type = config.get(CONF_INTERPRETATION_TYPE, TYPE_KALLELSE)

        self.processor = None
        if self.interpretation_type == TYPE_KALLELSE:
            self.processor = KallelseProcessor(hass, config)
        else:
            LOGGER.warning("Okänd tolkningstyp: %s. Fallback till Kallelse.", self.interpretation_type)
            self.processor = KallelseProcessor(hass, config)

        self.storage_dir = Path(hass.config.path("www", "mail_agent_temp"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # STATE & LOCK
        self._is_scanning = False

        # SENSOR DATA
        self._is_connected = False
        self._last_scan_success = None  # datetime
        self._emails_processed_count = 0
        self._last_event_summary = "Ingen händelse än"

    @property
    def is_scanning(self):
        return self._is_scanning

    @property
    def is_connected(self):
        return self._is_connected

    @property
    def last_scan_success(self):
        return self._last_scan_success

    @property
    def emails_processed_count(self):
        return self._emails_processed_count

    @property
    def last_event_summary(self):
        return self._last_event_summary

    # --- RESTORE METODER (NYTT I v0.19.0) ---
    def restore_email_count(self, count):
        """Återställ räknaren från sensorns minne."""
        self._emails_processed_count = count
        if self.enable_debug:
            LOGGER.debug("Återställde email count till: %s", count)

    def restore_last_event(self, summary):
        """Återställ senaste händelse från sensorns minne."""
        self._last_event_summary = summary

    def restore_last_scan(self, last_scan_dt):
        """Återställ tid för senaste sökning."""
        self._last_scan_success = last_scan_dt
    # ----------------------------------------

    async def check_mail(self, now=None):
        """Asynkron startpunkt som anropas av timer."""
        if self._is_scanning:
            if self.enable_debug:
                LOGGER.debug("Sökning pågår redan.")
            return

        self._is_scanning = True
        self.hass.add_job(self._notify_update) # Uppdatera binary_sensor.scanning till On

        try:
            await self.hass.async_add_executor_job(self._check_mail_sync)
        finally:
            self._is_scanning = False
            self.hass.add_job(self._notify_update) # Uppdatera binary_sensor.scanning till Off

    @callback
    def _notify_update(self):
        """Skicka signal till sensorerna att data har ändrats."""
        async_dispatcher_send(self.hass, f"{SIGNAL_MAIL_AGENT_UPDATE}_{self.entry_id}")

    def _check_mail_sync(self):
        """Synkron logik i executor-tråden."""
        mail_con = None
        try:
            mail_con = imaplib.IMAP4_SSL(self.server, self.port)
            mail_con.login(self.user, self.password)
            mail_con.select(self.folder)

            # Anslutning lyckades
            if not self._is_connected:
                self._is_connected = True
                self.hass.add_job(self._notify_update)

            status, messages = mail_con.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                self._last_scan_success = dt_util.now()
                self.hass.add_job(self._notify_update)
                return

            mail_ids = messages[0].split()

            if self.enable_debug:
                LOGGER.info("Hittade %s nya mail.", len(mail_ids))

            for mail_id in mail_ids:
                try:
                    res, msg_data = mail_con.fetch(mail_id, "(RFC822)")

                    if not msg_data:
                        LOGGER.warning("Ingen data hämtades för mail ID %s", mail_id)
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            try:
                                # type: ignore undertrycker VS Code/Pylance-felet
                                msg = email.message_from_bytes(response_part[1]) # type: ignore
                                self._process_single_mail(msg)
                            except Exception as e:
                                LOGGER.error("Kunde inte parsa mail-innehåll (tuple): %s", e)

                        elif isinstance(response_part, (bytes, str)):
                            if self.enable_debug:
                                LOGGER.debug("Ignorerar IMAP-del av typ %s: %s", type(response_part), response_part)

                        else:
                            LOGGER.warning("Oväntad datatyp i IMAP-svar: %s. Hoppar över.", type(response_part))

                except Exception as e:
                    LOGGER.error("Fel vid bearbetning av mail ID %s: %s", mail_id, e)

            # Uppdatera timestamp för lyckad scan
            self._last_scan_success = dt_util.now()

        except Exception as e:
            LOGGER.error("Fel vid anslutning/sökning: %s", e)
            if self._is_connected:
                self._is_connected = False
                self.hass.add_job(self._notify_update)
        finally:
            if mail_con:
                try:
                    mail_con.close()
                    mail_con.logout()
                except Exception:
                    pass
            # Alltid skicka en sista uppdatering
            self.hass.add_job(self._notify_update)

    def _process_single_mail(self, msg):
        subject = self._decode_subject(msg["Subject"])
        sender = msg.get("From")
        body = self._get_mail_body(msg)
        attachment_paths = self._save_attachments(msg)

        if self.enable_debug:
            LOGGER.info(f"Hämtat mail från {sender}. Processar...")

        self._emails_processed_count += 1

        if self.processor:
            result = self.processor.process_email(sender, subject, body, attachment_paths)
            if result and result.get("summary"):
                self._last_event_summary = result.get("summary")
            elif result:
                self._last_event_summary = f"Analys klar (inget event): {subject}"

        self.hass.add_job(self._notify_update)

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