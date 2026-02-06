# Fil: custom_components/mail_agent/kallelse_processor.py | Version: 0.21.0
"""Processor för att tolka kallelser och bokningar."""

import json
import base64
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

from google import genai

from homeassistant.util import dt as dt_util
from .const import LOGGER, CONF_SENDER_NAME, DEFAULT_SENDER_NAME

class KallelseProcessor:
    """Hanterar logiken för 'Tolka kallelse'."""

    def __init__(self, hass, config):
        self.hass = hass
        self.gemini_api_key = config.get("gemini_api_key")
        self.gemini_model = config.get("gemini_model")
        self.enable_debug = config.get("enable_debug")

        self.cal1 = config.get("calendar_entity_1")
        self.cal2 = config.get("calendar_entity_2")

        # SMTP settings removed, using Gmail API + Sender Name
        self.sender_name = config.get(CONF_SENDER_NAME, DEFAULT_SENDER_NAME)

        self.email_recipients = [
            r for r in [config.get("email_recipient_1"), config.get("email_recipient_2")] if r
        ]
        self.notify_services = [
            s for s in [config.get("notify_service_1"), config.get("notify_service_2")] if s
        ]

    def process_email(self, sender, subject, body, attachment_paths, service=None):
        """
        Huvudmetod som anropas från MailAgentScanner.
        Returnerar ai_data (dict) om framgångsrik, annars None.
        """

        if not self.gemini_api_key:
            if self.enable_debug:
                LOGGER.warning("Ingen API-nyckel för Gemini.")
            return None

        try:
            # 1. Anropa AI
            ai_data = self._call_gemini(attachment_paths, subject, body)

            # Hantera lista från AI
            if isinstance(ai_data, list):
                if len(ai_data) > 0:
                    ai_data = ai_data[0]
                else:
                    ai_data = {}

            # Fire event
            self.hass.bus.fire("mail_agent.scanned_document", {
                "type": "kallelse",
                "sender": sender,
                "subject": subject,
                "ai_data": ai_data,
                "attachments": [str(p) for p in attachment_paths]
            })

            if self.enable_debug:
                LOGGER.info("AI RESULTAT (Kallelse):\n%s", json.dumps(ai_data, indent=2, ensure_ascii=False))

            # 2. Agera på resultatet
            if ai_data.get("event_found") is True:
                if ai_data.get("start_time"):
                    self._create_calendar_events(ai_data)

                self._send_notifications(ai_data, subject, attachment_paths, service)

            # Returnera data så att sensorn kan uppdateras
            return ai_data

        except Exception as e:
            LOGGER.error("Fel i KallelseProcessor: %s", e)
            return None

    def _call_gemini(self, file_paths, subject, body):
        client = genai.Client(api_key=self.gemini_api_key)
        uploaded_files = []
        for path in file_paths:
            uploaded_files.append(client.files.upload(file=path, config={'mime_type': 'application/pdf'}))

        now_str = dt_util.now().strftime('%Y-%m-%d %H:%M')

        prompt = f"""
        Du är en smart kalender-assistent.
        Idag är det: {now_str}

        Din uppgift är att hitta bokningar, kallelser eller möten i detta mail/bilaga.

        OM DET FINNS BILAGOR: Föreslå ett kort, beskrivande filnamn (slutar på .pdf) baserat på innehållet (t.ex. "Tandläkare_2025-05-10.pdf").

        Regler för datum och tid:
        1. Utgå ALLTID från dagens datum ({now_str}) vid relativa uttryck.
        2. Om år saknas, välj det år som gör datumet kommande.
        3. Gissa aldrig på dåtid.

        Ämne: {subject}
        Text: {body}

        Svara strikt med JSON:
        {{
            "event_found": boolean,
            "summary": "Kort beskrivning",
            "description": "Sammanfattning av detaljer",
            "start_time": "YYYY-MM-DD HH:MM:SS (eller null)",
            "location": "Plats",
            "type": "Typ",
            "suggested_filename": "Nytt_Filnamn.pdf"
        }}
        """

        contents = uploaded_files + [prompt]
        response = client.models.generate_content(
            model=self.gemini_model, contents=contents, config={'response_mime_type': 'application/json'}
        )

        for f in uploaded_files:
            try:
                client.files.delete(name=f.name)
            except Exception:
                pass

        return json.loads(response.text)

    def _create_calendar_events(self, ai_data):
        calendars = [c for c in [self.cal1, self.cal2] if c]
        if not calendars:
            return

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
            if self.enable_debug:
                LOGGER.info(f"Bokar i {calendar_entity}")
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

    def _send_notifications(self, ai_data, original_subject, attachment_paths, service):
        summary = ai_data.get("summary", "Okänd händelse")
        start_time = ai_data.get("start_time", "okänd tid")
        location = ai_data.get("location", "")
        description = ai_data.get("description", "")
        suggested_filename = ai_data.get("suggested_filename")

        if self.notify_services:
            mobile_message = f"Ny bokning: {summary}\nTid: {start_time}"
            for service_name_conf in self.notify_services:
                domain = "notify"
                s_name = service_name_conf.replace("notify.", "")
                self.hass.add_job(
                    self.hass.services.async_call(
                        domain, s_name,
                        {
                            "title": "Mail Agent",
                            "message": mobile_message,
                            "data": {"clickAction": "/calendar"}
                        }
                    )
                )

        if service and self.email_recipients:
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
            try:
                self._send_gmail_email(service, f"Ny kallelse: {summary}", email_body, attachment_paths, suggested_filename)
            except Exception as e:
                LOGGER.error(f"Kunde inte skicka Gmail: {e}")

    def _send_gmail_email(self, service, subject, html_body, files, suggested_filename=None):
        if not files:
            msg = MIMEText(html_body, 'html')
        else:
            msg = MIMEMultipart()
            msg.attach(MIMEText(html_body, 'html'))
            for file_path in files:
                try:
                    path = Path(file_path)
                    ctype, encoding = mimetypes.guess_type(path)
                    if ctype is None or encoding is not None:
                        ctype = 'application/octet-stream'
                    maintype, subtype = ctype.split('/', 1)
                    with open(path, 'rb') as f:
                        file_data = f.read()
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(file_data)
                    encoders.encode_base64(part)

                    if suggested_filename and len(files) == 1:
                        filename = suggested_filename
                    else:
                        filename = path.name

                    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                    msg.attach(part)
                except Exception as e:
                    LOGGER.error(f"Kunde inte bifoga fil {file_path}: {e}")

        # From: "Sender Name" <me>
        # Gmail API uses the authenticated user as default, but we can specify name.
        # We can't easily guess the email address unless we fetch profile, so we just set the name.
        # If we set From to "Name <email>", Gmail verifies the email.
        # It's safer to just let Gmail handle the address or use the one from profile if available.
        # But `formataddr` requires an address.
        # We can try just "Name" but standard RFC requires email.
        # We can use "me" but formataddr might not like it.
        # Let's try to just not set From header or set it to self.sender_name (which might be just "Mail Agent").
        # If we don't set 'From', Gmail uses account default.
        # If we want a display name, we need the email address.
        # We can't invoke API here easily to get profile just for this.
        # Let's assume the user is okay with default From, or we can fetch profile once in scanner.
        # But let's skip 'From' header manipulation for now to avoid complexity, or just set Subject/To.

        msg['To'] = ", ".join(self.email_recipients)
        msg['Subject'] = subject

        # Base64url encode
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        message = {'raw': raw}

        service.users().messages().send(userId='me', body=message).execute()

        if self.enable_debug:
            LOGGER.info("Gmail skickat framgångsrikt (Kallelse).")
