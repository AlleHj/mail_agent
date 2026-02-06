# Fil: custom_components/mail_agent/__init__.py | Version: 0.21.0
"""Mail Agent - Huvudlogik med Global Låsning, Sensorstöd och Restore."""

import base64
from pathlib import Path
from datetime import timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from homeassistant.const import Platform

from .kallelse_processor import KallelseProcessor
from .forvaltare_processor import ForvaltareProcessor

from .const import (
    DOMAIN,
    LOGGER,
    CONF_SCAN_INTERVAL,
    CONF_ENABLE_DEBUG,
    CONF_INTERPRETATION_TYPE,
    TYPE_KALLELSE,
    TYPE_FORVALTARE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENABLE_DEBUG,
    SIGNAL_MAIL_AGENT_UPDATE,
)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup."""
    config = entry.data
    options = entry.options

    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    try:
        await session.async_ensure_token_valid()
    except Exception as e:
        LOGGER.warning("Kunde inte validera token vid start: %s", e)

    scanner = MailAgentScanner(
        hass,
        {**config, **options},
        entry.entry_id,
        session
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
    def __init__(self, hass, config, entry_id, session):
        self.hass = hass
        self.config = config
        self.entry_id = entry_id
        self.session = session

        self.scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self.enable_debug = config.get(CONF_ENABLE_DEBUG, DEFAULT_ENABLE_DEBUG)
        self.interpretation_type = config.get(CONF_INTERPRETATION_TYPE, TYPE_KALLELSE)

        self.processor = None
        if self.interpretation_type == TYPE_KALLELSE:
            self.processor = KallelseProcessor(hass, config)
        elif self.interpretation_type == TYPE_FORVALTARE:
            self.processor = ForvaltareProcessor(hass, config)
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

        # Services (Initieras vid scan)
        self.gmail_service = None
        self.drive_service = None

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

    # --- RESTORE METODER ---
    def restore_email_count(self, count):
        self._emails_processed_count = count
        if self.enable_debug:
            LOGGER.debug("Återställde email count till: %s", count)

    def restore_last_event(self, summary):
        self._last_event_summary = summary

    def restore_last_scan(self, last_scan_dt):
        self._last_scan_success = last_scan_dt
    # -----------------------

    async def check_mail(self, now=None):
        """Asynkron startpunkt som anropas av timer."""
        if self._is_scanning:
            if self.enable_debug:
                LOGGER.debug("Sökning pågår redan.")
            return

        self._is_scanning = True
        self._notify_update()

        try:
            # Refresh token and build services
            await self.session.async_ensure_token_valid()
            creds = Credentials(token=self.session.token["access_token"])

            # Vi bygger services i executor för att undvika blockering vid discovery (om cache saknas)
            def _build_services():
                self.gmail_service = build("gmail", "v1", credentials=creds, cache_discovery=False)
                # Vi bygger alltid Drive-tjänsten om det är Förvaltare, eller om vi vill ha generellt stöd
                self.drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)

            await self.hass.async_add_executor_job(_build_services)

            await self.hass.async_add_executor_job(self._check_mail_sync)

        except Exception as e:
            LOGGER.error("Fel vid förberedelse av scan: %s", e)
            if self._is_connected:
                self._is_connected = False
                self._notify_update()
        finally:
            self._is_scanning = False
            self._notify_update()

    @callback
    def _notify_update(self):
        """Skicka signal till sensorerna att data har ändrats."""
        async_dispatcher_send(self.hass, f"{SIGNAL_MAIL_AGENT_UPDATE}_{self.entry_id}")

    def _check_mail_sync(self):
        """Synkron logik för att hämta mail via Gmail API."""
        if not self.gmail_service:
            LOGGER.error("Gmail-tjänst ej initierad.")
            return

        try:
            # Hämta olästa meddelanden
            # q='is:unread' hämtar alla olästa.
            results = self.gmail_service.users().messages().list(userId='me', q='is:unread').execute()
            messages = results.get('messages', [])

            if not self._is_connected:
                self._is_connected = True
                self.hass.add_job(self._notify_update)

            if not messages:
                self._last_scan_success = dt_util.now()
                self.hass.add_job(self._notify_update)
                return

            if self.enable_debug:
                LOGGER.info("Hittade %s nya mail.", len(messages))

            for msg_meta in messages:
                msg_id = msg_meta['id']
                try:
                    # Hämta hela mailet
                    msg_data = self.gmail_service.users().messages().get(userId='me', id=msg_id, format='full').execute()

                    self._process_single_gmail(msg_data)

                    # Markera som läst (ta bort UNREAD label)
                    self.gmail_service.users().messages().modify(
                        userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}
                    ).execute()

                except Exception as e:
                    LOGGER.error("Fel vid bearbetning av mail ID %s: %s", msg_id, e)

            self._last_scan_success = dt_util.now()

        except Exception as e:
            LOGGER.error("Fel vid sökning mot Gmail API: %s", e)
            if self._is_connected:
                self._is_connected = False
                self.hass.add_job(self._notify_update)
        finally:
             self.hass.add_job(self._notify_update)

    def _process_single_gmail(self, msg_resource):
        """Bearbeta ett Gmail-meddelande-objekt."""
        payload = msg_resource.get('payload', {})
        headers = payload.get('headers', [])

        subject = "Okänt ämne"
        sender = "Okänd avsändare"

        for h in headers:
            name = h.get('name', '').lower()
            if name == 'subject':
                subject = h.get('value')
            elif name == 'from':
                sender = h.get('value')

        if self.enable_debug:
            LOGGER.info(f"Hämtat mail från {sender} (Subject: {subject}). Processar...")

        body = self._get_gmail_body(payload)
        attachment_paths = self._save_gmail_attachments(msg_resource['id'], payload)

        self._emails_processed_count += 1

        if self.processor:
            # Skicka med relevanta tjänster
            service_arg = None
            if self.interpretation_type == TYPE_KALLELSE:
                service_arg = self.gmail_service
            elif self.interpretation_type == TYPE_FORVALTARE:
                service_arg = self.drive_service

            # Vi antar att processorerna uppdateras för att ta emot en extra parameter (service)
            # eller så passar vi den via kwargs om vi vill vara bakåtkompatibla (men vi skriver om dem nu).
            result = self.processor.process_email(sender, subject, body, attachment_paths, service=service_arg)

            if result and result.get("summary"):
                self._last_event_summary = result.get("summary")
            elif result:
                self._last_event_summary = f"Analys klar (inget event): {subject}"

        self.hass.add_job(self._notify_update)

    def _get_gmail_body(self, payload):
        """Rekursivt hämta body text."""
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType')
                if mime_type == 'text/plain':
                    data = part.get('body', {}).get('data')
                    if data:
                        padded_data = data + '=' * (-len(data) % 4)
                        body += base64.urlsafe_b64decode(padded_data).decode('utf-8', errors='replace')
                elif mime_type == 'multipart/alternative':
                    body += self._get_gmail_body(part)
        else:
            # Om ingen multipart, kolla direkt i body
            data = payload.get('body', {}).get('data')
            if data:
                 padded_data = data + '=' * (-len(data) % 4)
                 body += base64.urlsafe_b64decode(padded_data).decode('utf-8', errors='replace')

        return body.strip()

    def _save_gmail_attachments(self, msg_id, payload):
        """Spara bilagor från Gmail."""
        saved_paths = []

        def _walk_parts(parts):
            for part in parts:
                if 'parts' in part:
                    _walk_parts(part['parts'])

                filename = part.get('filename')
                body = part.get('body', {})
                attachment_id = body.get('attachmentId')

                if filename and attachment_id:
                    # Filter: Vi är mest intresserade av PDFer eller dokument
                    # Men vi tar allt som ser ut som en fil för processorn att avgöra
                    # Användaren kanske bara vill ha PDF för fakturor/kallelser.
                    # Vi behåller logiken "pdf" in checken?
                    mime_type = part.get('mimeType', '')
                    if "pdf" in mime_type.lower():
                        # Hämta attachment data
                        att = self.gmail_service.users().messages().attachments().get(
                            userId='me', messageId=msg_id, id=attachment_id
                        ).execute()
                        data = att.get('data')
                        if data:
                            padded_data = data + '=' * (-len(data) % 4)
                            file_data = base64.urlsafe_b64decode(padded_data)

                            safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
                            filepath = self.storage_dir / safe_filename
                            with open(filepath, "wb") as f:
                                f.write(file_data)
                            saved_paths.append(filepath)

        if 'parts' in payload:
            _walk_parts(payload['parts'])
        else:
            # Hantera fall där det finns bilagor men ingen multipart (ovanligt för bilagor men möjligt)
             _walk_parts([payload])

        return saved_paths
