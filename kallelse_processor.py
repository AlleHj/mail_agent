# Version: 0.16.0 - 2025-12-17
"""Processor för att tolka kallelser och bokningar."""

import json
import smtplib
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

from google import genai
from google.genai import types

from homeassistant.util import dt as dt_util
from .const import LOGGER

class KallelseProcessor:
    """Hanterar logiken för 'Tolka kallelse'."""

    def __init__(self, hass, config):
        self.hass = hass
        self.gemini_api_key = config.get("gemini_api_key")
        self.gemini_model = config.get("gemini_model")
        self.enable_debug = config.get("enable_debug")

        self.cal1 = config.get("calendar_entity_1")
        self.cal2 = config.get("calendar_entity_2")

        self.smtp_server = config.get("smtp_server")
        self.smtp_port = config.get("smtp_port", 587)
        self.smtp_user = config.get("username")
        self.smtp_password = config.get("password")

        # HÄMTA AVSÄNDARNAMN FRÅN CONFIG (Eller fallback)
        self.smtp_sender_name = config.get("smtp_sender_name", "Mail Agent")

        self.email_recipients = [
            r for r in [config.get("email_recipient_1"), config.get("email_recipient_2")] if r
        ]
        self.notify_services = [
            s for s in [config.get("notify_service_1"), config.get("notify_service_2")] if s
        ]

    def process_email(self, sender, subject, body, attachment_paths):
        """Huvudmetod som anropas från MailAgentScanner."""

        if not self.gemini_api_key:
            if self.enable_debug: LOGGER.warning("Ingen API-nyckel för Gemini.")
            return

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

                self._send_notifications(ai_data, subject, attachment_paths)

        except Exception as e:
            LOGGER.error("Fel i KallelseProcessor: %s", e)

    def _call_gemini(self, file_paths, subject, body):
        client = genai.Client(api_key=self.gemini_api_key)
        uploaded_files = []
        for path in file_paths:
            uploaded_files.append(client.files.upload(file=path, config={'mime_type': 'application/pdf'}))

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        prompt = f"""
        Du är en smart kalender-assistent.
        Idag är det: {now_str}

        Din uppgift är att hitta bokningar, kallelser eller möten i detta mail/bilaga.

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

    def _send_notifications(self, ai_data, original_subject, attachment_paths):
        summary = ai_data.get("summary", "Okänd händelse")
        start_time = ai_data.get("start_time", "okänd tid")
        location = ai_data.get("location", "")
        description = ai_data.get("description", "")

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

        if self.smtp_server and self.email_recipients:
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
                self._send_smtp_email(f"Ny kallelse: {summary}", email_body, attachment_paths)
            except Exception as e:
                LOGGER.error(f"Kunde inte skicka SMTP-mail: {e}")

    def _send_smtp_email(self, subject, html_body, files):
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
                    part.add_header('Content-Disposition', f'attachment; filename="{path.name}"')
                    msg.attach(part)
                except Exception as e:
                    LOGGER.error(f"Kunde inte bifoga fil {file_path}: {e}")

        # HÄR ANVÄNDS DET NYA NAMNET FRÅN INSTÄLLNINGARNA
        msg['From'] = formataddr((self.smtp_sender_name, self.smtp_user))
        msg['To'] = ", ".join(self.email_recipients)
        msg['Subject'] = subject

        if self.smtp_port == 465:
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
        else:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()

        server.login(self.smtp_user, self.smtp_password)
        server.sendmail(self.smtp_user, self.email_recipients, msg.as_string())
        server.quit()
        if self.enable_debug: LOGGER.info("SMTP mail skickat framgångsrikt (Kallelse).")