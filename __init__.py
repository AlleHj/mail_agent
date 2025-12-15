# Version: 0.12.1 - 2025-12-15
"""Mail Agent - Huvudlogik med AI, Kalender och direkt SMTP-utskick."""

import imaplib
import smtplib
import email
import os
import json
import mimetypes
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# NY SDK IMPORT
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
        options,  # Skickar hela options-objektet
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
    def __init__(self, hass, server, port, user, password, folder, interval, debug, api_key, model, cal1, cal2, options):
        self.hass = hass
        # IMAP Settings
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.folder = folder

        # SMTP Settings
        self.smtp_server = options.get(CONF_SMTP_SERVER)
        self.smtp_port = options.get(CONF_SMTP_PORT, 587)

        self.scan_interval = interval
        self.enable_debug = debug
        self.gemini_api_key = api_key
        self.gemini_model = model
        self.cal1 = cal1
        self.cal2 = cal2

        # Notifieringsinställningar
        self.email_recipients = [
            r for r in [options.get(CONF_EMAIL_RECIPIENT_1), options.get(CONF_EMAIL_RECIPIENT_2)] if r
        ]
        self.notify_services = [
            s for s in [options.get(CONF_NOTIFY_SERVICE_1), options.get(CONF_NOTIFY_SERVICE_2)] if s
        ]

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
        subject = self._decode_subject(msg["Subject"])
        sender = msg.get("From")
        body = self._get_mail_body(msg)
        attachment_paths = self._save_attachments(msg)

        if self.enable_debug:
            LOGGER.info(f"Bearbetar mail från {sender}. Bilagor: {len(attachment_paths)}")

        if self.gemini_api_key:
            try:
                ai_data = self._call_gemini(attachment_paths, subject, body)

                self.hass.bus.fire("mail_agent.scanned_document", {
                    "sender": sender,
                    "subject": subject,
                    "ai_data": ai_data,
                    "attachments": [str(p) for p in attachment_paths]
                })

                if self.enable_debug:
                    LOGGER.info("AI RESULTAT:\n%s", json.dumps(ai_data, indent=2, ensure_ascii=False))

                if ai_data.get("event_found") is True:
                    # 1. Skapa kalenderbokning (om tid finns)
                    if ai_data.get("start_time"):
                        self._create_calendar_events(ai_data)

                    # 2. Skicka notifieringar (Mobil + E-post via SMTP)
                    self._send_notifications(ai_data, subject, attachment_paths)

            except Exception as e:
                LOGGER.error("Process-fel: %s", e)
        elif self.enable_debug:
            LOGGER.warning("Ingen API-nyckel.")

    def _send_notifications(self, ai_data, original_subject, attachment_paths):
        """Skickar mobilnotiser och direkta SMTP-mail."""

        summary = ai_data.get("summary", "Okänd händelse")
        start_time = ai_data.get("start_time", "okänd tid")
        location = ai_data.get("location", "")
        description = ai_data.get("description", "")

        # --- MOBILNOTISER (Async-anrop via add_job är ok här då det schemalägger på loopen) ---
        if self.notify_services:
            mobile_message = f"Ny bokning: {summary}\nTid: {start_time}"
            for service in self.notify_services:
                domain = "notify"
                service_name = service.replace("notify.", "")
                self.hass.add_job(
                    self.hass.services.async_call(
                        domain, service_name,
                        {
                            "title": "Mail Agent",
                            "message": mobile_message,
                            "data": {"clickAction": "/calendar"}
                        }
                    )
                )

        # --- E-POSTNOTISER (Direkt via SMTP) ---
        if self.smtp_server and self.email_recipients:
            if self.enable_debug:
                LOGGER.info("Förbereder direkt SMTP-utskick med %s bilagor", len(attachment_paths))

            email_body = f"""
            <h3>Mail Agent: Ny händelse</h3>
            <p><b>Händelse:</b> {summary}</p>
            <p><b>Tid:</b> {start_time}</p>
            <p><b>Plats:</b> {location}</p>
            <hr>
            <p><b>Detaljer:</b><br>{description}</p>
            <hr>
            <p><small>Originalämne: {original_subject}</small></p>
            """

            # ÄNDRING HÄR: Vi anropar funktionen direkt eftersom vi redan är i en tråd.
            # Ingen async_add_executor_job behövs eller ska användas här.
            try:
                self._send_smtp_email(
                    f"Ny kallelse: {summary}",
                    email_body,
                    attachment_paths
                )
            except Exception as e:
                LOGGER.error(f"Kunde inte skicka SMTP-mail: {e}")

    def _send_smtp_email(self, subject, html_body, files):
        """Skickar mail direkt via SMTP med bilagor."""
        msg = MIMEMultipart()
        msg['From'] = self.user
        msg['To'] = ", ".join(self.email_recipients)
        msg['Subject'] = subject

        msg.attach(MIMEText(html_body, 'html'))

        # Bifoga filer
        for file_path in files:
            try:
                path = Path(file_path)
                ctype, encoding = mimetypes.guess_type(path)
                if ctype is None or encoding is not None:
                    # No guess could be made, or the file is encoded (compressed), so
                    # use a generic bag-of-bits type.
                    ctype = 'application/octet-stream'

                maintype, subtype = ctype.split('/', 1)

                with open(path, 'rb') as f:
                    file_data = f.read()

                part = MIMEBase(maintype, subtype)
                part.set_payload(file_data)
                encoders.encode_base64(part)

                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{path.name}"'
                )
                msg.attach(part)
            except Exception as e:
                LOGGER.error(f"Kunde inte bifoga fil {file_path}: {e}")

        # Skicka
        if self.smtp_port == 465:
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
        else:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()

        server.login(self.user, self.password)
        server.sendmail(self.user, self.email_recipients, msg.as_string())
        server.quit()
        if self.enable_debug:
            LOGGER.info("SMTP mail skickat framgångsrikt.")

    def _create_calendar_events(self, ai_data):
        calendars = [c for c in [self.cal1, self.cal2] if c]
        if not calendars: return

        start_str = ai_data.get("start_time")
        try:
            dt_start = dt_util.as_local(datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S"))
            dt_end = dt_start + timedelta(hours=1)
        except (ValueError, TypeError):
            return

        summary = ai_data.get("summary", "Bokat Event")
        description = f"{ai_data.get('description', '')}\n\n[Auto-skapat av Mail Agent]"
        location = ai_data.get("location", "")

        for calendar_entity in calendars:
            if self.enable_debug: LOGGER.info(f"Bokar i {calendar_entity}")
            self.hass.add_job(
                self.hass.services.async_call(
                    "calendar", "create_event",
                    {
                        "entity_id": calendar_entity,
                        "summary": summary,
                        "description": description,
                        "start_date_time": dt_start.isoformat(),
                        "end_date_time": dt_end.isoformat(),
                        "location": location,
                    }
                )
            )

    def _call_gemini(self, file_paths, subject, body):
        client = genai.Client(api_key=self.gemini_api_key)
        uploaded_files = []
        for path in file_paths:
            uploaded_files.append(client.files.upload(file=path, config={'mime_type': 'application/pdf'}))

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        prompt = f"""
        Du är en smart kalender-assistent.
        Idag är det: {now_str}

        Regler för datum och tid:
        1. Utgå ALLTID från dagens datum ({now_str}) när du tolkar relativa tidsuttryck.
        2. Om ett datum anges utan år (t.ex. "16/12"), välj det år som gör datumet kommande (nära i framtiden).
        3. Gissa aldrig på dåtid.

        Ämne: {subject}
        Text: {body}

        Svara strikt med JSON:
        {{
            "event_found": boolean,
            "summary": "Kort beskrivning",
            "description": "Sammanfattning",
            "start_time": "YYYY-MM-DD HH:MM:SS (eller null)",
            "location": "Plats",
            "type": "Typ"
        }}
        """

        contents = uploaded_files + [prompt]
        response = client.models.generate_content(
            model=self.gemini_model, contents=contents, config={'response_mime_type': 'application/json'}
        )

        for f in uploaded_files:
            try: client.files.delete(name=f.name)
            except: pass

        return json.loads(response.text)

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