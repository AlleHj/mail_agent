# Version: 0.10.0 - 2025-12-15
"""Mail Agent - Huvudlogik med Non-blocking Kalenderanrop."""

import imaplib
import email
import os
import json
import time
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path

# NY SDK IMPORT (v1.0+)
from google import genai
from google.genai import types

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

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
    CONF_GEMINI_API_KEY,
    CONF_GEMINI_MODEL,
    CONF_CALENDAR_1,
    CONF_CALENDAR_2,
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
        config[CONF_IMAP_SERVER],
        config[CONF_IMAP_PORT],
        config[CONF_USERNAME],
        config[CONF_PASSWORD],
        config[CONF_FOLDER],
        options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        options.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG),
        options.get(CONF_GEMINI_API_KEY),
        options.get(CONF_GEMINI_MODEL, DEFAULT_GEMINI_MODEL),
        options.get(CONF_CALENDAR_1),
        options.get(CONF_CALENDAR_2),
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
    def __init__(
        self,
        hass,
        server,
        port,
        user,
        password,
        folder,
        interval,
        debug,
        api_key,
        model,
        cal1,
        cal2,
    ):
        self.hass = hass
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.folder = folder
        self.scan_interval = interval
        self.enable_debug = debug
        self.gemini_api_key = api_key
        self.gemini_model = model
        self.cal1 = cal1
        self.cal2 = cal2

        self.storage_dir = Path(hass.config.path("www", "mail_agent_temp"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def check_mail(self, now=None):
        await self.hass.async_add_executor_job(self._check_mail_sync)

    def _check_mail_sync(self):
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
                LOGGER.info("Hittade %s nya mail.", len(mail_ids))

            for mail_id in mail_ids:
                res, msg_data = mail_con.fetch(mail_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        self._process_single_mail(msg)

        except Exception as e:
            LOGGER.error("Fel vid mail-check: %s", e)
        finally:
            if mail_con:
                try:
                    mail_con.close()
                    mail_con.logout()
                except Exception:
                    pass

    def _process_single_mail(self, msg):
        """Hanterar ett enskilt mail."""
        subject = self._decode_subject(msg["Subject"])
        sender = msg.get("From")
        body = self._get_mail_body(msg)
        attachment_paths = self._save_attachments(msg)

        if self.enable_debug:
            LOGGER.info(
                f"Bearbetar mail från {sender}. Ämne: {subject}. Antal bilagor: {len(attachment_paths)}"
            )

        if self.gemini_api_key:
            try:
                ai_data = self._call_gemini(attachment_paths, subject, body)

                self.hass.bus.fire(
                    "mail_agent.scanned_document",
                    {
                        "sender": sender,
                        "subject": subject,
                        "ai_data": ai_data,
                        "attachments": [str(p) for p in attachment_paths],
                    },
                )

                if self.enable_debug:
                    LOGGER.info(
                        "AI RESULTAT:\n%s",
                        json.dumps(ai_data, indent=2, ensure_ascii=False),
                    )

                if ai_data.get("event_found") is True and ai_data.get("start_time"):
                    self._create_calendar_events(ai_data)

            except Exception as e:
                LOGGER.error("Gemini/Kalender-fel: %s", e)

        elif not self.gemini_api_key and self.enable_debug:
            LOGGER.warning("Ingen API-nyckel angiven.")

    def _create_calendar_events(self, ai_data):
        """Skapar kalenderevent via add_job för att undvika deadlock."""

        calendars = [c for c in [self.cal1, self.cal2] if c]
        if not calendars:
            if self.enable_debug:
                LOGGER.info("Event hittat men inga kalendrar valda.")
            return

        start_str = ai_data.get("start_time")

        try:
            dt_start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            dt_start = dt_util.as_local(dt_start)
            dt_end = dt_start + timedelta(hours=1)

        except (ValueError, TypeError) as e:
            LOGGER.error("Kunde inte parsa datum '%s': %s", start_str, e)
            return

        summary = ai_data.get("summary", "Bokat Event")
        description = ai_data.get("description", "")
        location = ai_data.get("location", "")

        full_description = f"{description}\n\n[Auto-skapat av Mail Agent]"

        for calendar_entity in calendars:
            if self.enable_debug:
                LOGGER.info(
                    f"Schemalägger kalenderbokning i {calendar_entity}: {summary} @ {dt_start}"
                )

            # ÄNDRING: Vi använder add_job för att inte blockera SyncWorker.
            # Detta lägger anropet på Home Assistants huvudloop.
            self.hass.add_job(
                self.hass.services.async_call(
                    "calendar",
                    "create_event",
                    {
                        "entity_id": calendar_entity,
                        "summary": summary,
                        "description": full_description,
                        "start_date_time": dt_start.isoformat(),
                        "end_date_time": dt_end.isoformat(),
                        "location": location,
                    },
                )
            )

    def _call_gemini(self, file_paths, subject, body):
        """Anropar Google Gemini."""
        client = genai.Client(api_key=self.gemini_api_key)
        uploaded_files = []

        for path in file_paths:
            uploaded_file = client.files.upload(
                file=path, config={"mime_type": "application/pdf"}
            )
            uploaded_files.append(uploaded_file)

        prompt_text = f"""
        Du är en expert på dokumentanalys.

        MAILET:
        Ämne: {subject}
        Text: {body}

        UPPGIFT:
        Analysera innehållet.

        JSON SCHEMA:
        Svara ENDAST med ett JSON-objekt:
        {{
            "event_found": boolean,
            "summary": "Kort beskrivning",
            "description": "Detaljer",
            "start_time": "YYYY-MM-DD HH:MM:SS (eller null)",
            "location": "Plats (eller null)",
            "type": "Typ"
        }}
        """

        contents = uploaded_files + [prompt_text]

        # Vi lägger till en varningstext i loggen om "thought_signature" dyker upp,
        # men vi litar på att json.loads hanterar texten om den returneras korrekt.
        response = client.models.generate_content(
            model=self.gemini_model,
            contents=contents,
            config={"response_mime_type": "application/json"},
        )

        for f in uploaded_files:
            try:
                client.files.delete(name=f.name)
            except Exception:
                pass

        return json.loads(response.text)

    def _save_attachments(self, msg):
        """Sparar alla PDF-bilagor till disk."""
        saved_paths = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                filename = part.get_filename()
                if not filename:
                    continue
                content_type = part.get_content_type()
                if "pdf" in content_type:
                    filename = "".join(
                        c for c in filename if c.isalnum() or c in "._- "
                    )
                    filepath = self.storage_dir / filename
                    with open(filepath, "wb") as f:
                        f.write(part.get_payload(decode=True))
                    saved_paths.append(filepath)
        return saved_paths

    def _get_mail_body(self, msg):
        """Hämtar textinnehåll."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset()
                        if payload:
                            body = payload.decode(
                                charset if charset else "utf-8", errors="replace"
                            )
                            break
                    except Exception:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                body = payload.decode(
                    msg.get_content_charset() or "utf-8", errors="replace"
                )
            except Exception:
                pass
        return body.strip()

    def _decode_subject(self, encoded_subject):
        if not encoded_subject:
            return "Okänt ämne"
        subject, encoding = decode_header(encoded_subject)[0]
        if isinstance(subject, bytes):
            return subject.decode(encoding if encoding else "utf-8")
        return subject
