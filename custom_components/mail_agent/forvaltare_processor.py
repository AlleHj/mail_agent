# Version: 0.20.0
"""Processor för att hantera fakturor och förvaltning via Google Drive."""

import json
import io
import re
from datetime import datetime
from pathlib import Path

from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from homeassistant.util import dt as dt_util
from .const import LOGGER

class ForvaltareProcessor:
    """Hanterar logiken för 'Förvaltare' (Fakturor/Admin)."""

    def __init__(self, hass, config):
        self.hass = hass
        self.config = config

        # Konfiguration
        self.gemini_api_key = config.get("gemini_api_key")
        self.gemini_model = config.get("gemini_model")
        self.enable_debug = config.get("enable_debug")

        # Google Drive Konfiguration
        self.google_client_id = config.get("google_client_id")
        self.google_client_secret = config.get("google_client_secret")
        self.google_refresh_token = config.get("google_refresh_token")
        self.drive_folder_path = config.get("drive_folder_path", "Fakturor")
        self.summary_filename = config.get("summary_filename", "fakturor_oversikt.json")

    def process_email(self, sender, subject, body, attachment_paths):
        """
        Huvudmetod som anropas från MailAgentScanner.
        """

        if not self.gemini_api_key:
            if self.enable_debug:
                LOGGER.warning("Ingen API-nyckel för Gemini.")
            return None

        try:
            # 1. Anropa AI
            ai_data = self._call_gemini(attachment_paths, subject, body)

            if isinstance(ai_data, list):
                if len(ai_data) > 0:
                    ai_data = ai_data[0]
                else:
                    ai_data = {}

            if self.enable_debug:
                LOGGER.info("AI RESULTAT (Förvaltare):\n%s", json.dumps(ai_data, indent=2, ensure_ascii=False))

            self.hass.bus.fire("mail_agent.scanned_document", {
                "type": "forvaltare",
                "sender": sender,
                "subject": subject,
                "ai_data": ai_data,
                "attachments": [str(p) for p in attachment_paths]
            })

            # 2. Ladda upp filer till Drive
            uploaded_files = []
            year_folder_id = None

            # Vi behöver Drive Service för både uppladdning och JSON-hantering
            service = self._get_drive_service()

            if service and attachment_paths:
                uploaded_files, year_folder_id = self._upload_to_drive(service, ai_data, attachment_paths)

            # 3. Uppdatera Översikts-JSON
            if service and year_folder_id:
                try:
                    self._process_summary_json(service, year_folder_id, ai_data)
                except Exception as e:
                    LOGGER.error(f"Kunde inte uppdatera översiktsfilen: {e}")

            # 4. Notifiera
            self._create_notification(ai_data, sender, uploaded_files)

            return ai_data

        except Exception as e:
            LOGGER.error("Fel i ForvaltareProcessor: %s", e)
            return None

    def _call_gemini(self, file_paths, subject, body):
        client = genai.Client(api_key=self.gemini_api_key)
        uploaded_files = []

        for path in file_paths:
            try:
                uploaded_files.append(client.files.upload(file=path, config={'mime_type': 'application/pdf'}))
            except Exception as e:
                LOGGER.warning(f"Kunde inte ladda upp fil {path} till Gemini: {e}")

        now_str = dt_util.now().strftime('%Y-%m-%d')

        prompt = f"""
        Du är en expert på att extrahera data från fakturor och administrativa dokument.
        Dagens datum är: {now_str}

        Ämne: {subject}
        Text: {body}

        Din uppgift är att analysera bifogade filer (om några), ämnesrad och brödtext.

        LETA EFTER FÖLJANDE:
        1. **Typ**: Är detta en "Faktura" eller "Kreditfaktura"?
        2. **Avsändare**: Vem är det från? (T.ex. Comviq, Skatteverket).
        3. **Datum**:
           - **Fakturadatum**: När ställdes fakturan ut?
           - **Förfallodatum**: När ska den betalas?
           - Om datum saknas, använd dagens datum ({now_str}).
        4. **Belopp**: Totalsumma (inkludera valuta, t.ex. "399 kr").
        5. **Referenser**: Fakturanummer, OCR eller kundnummer.
        6. **Unikt ID**: Identifiera ett unikt nummer (helst fakturanummer/OCR).
        7. **Beskrivning**: En kortfattad text om vad det gäller (t.ex. "Mobilfaktura Jan").

        Svara strikt med JSON:
        {{
            "invoice_found": boolean,
            "type": "Faktura" eller "Kreditfaktura",
            "sender_name": "Namn",
            "invoice_date": "YYYY-MM-DD",
            "due_date": "YYYY-MM-DD",
            "total_amount": "Belopp kr",
            "invoice_number": "Nummer",
            "unique_id": "UniktID",
            "summary": "Kort rubrik",
            "description": "Beskrivning"
        }}
        """

        contents = uploaded_files + [prompt]

        try:
            response = client.models.generate_content(
                model=self.gemini_model,
                contents=contents,
                config={'response_mime_type': 'application/json'}
            )

            for f in uploaded_files:
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass

            return json.loads(response.text)

        except Exception as e:
            LOGGER.error(f"Fel vid AI-anrop: {e}")
            for f in uploaded_files:
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass
            return {}

    def _get_drive_service(self):
        if not all([self.google_client_id, self.google_client_secret, self.google_refresh_token]):
            LOGGER.error("Saknar inloggningsuppgifter för Google Drive.")
            return None

        try:
            creds = Credentials(
                None,
                refresh_token=self.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.google_client_id,
                client_secret=self.google_client_secret
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            LOGGER.error(f"Kunde inte skapa Google Drive-tjänst: {e}")
            return None

    def _upload_to_drive(self, service, ai_data, attachment_paths):
        """Laddar upp filer och returnerar (lista_på_filer, year_folder_id)."""
        date_str = ai_data.get("due_date")
        if not date_str:
            date_obj = dt_util.now()
        else:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                date_obj = dt_util.now()

        year = date_obj.strftime("%Y")
        month_name = self._get_swedish_month(date_obj.month)

        root_id = self._get_or_create_nested_folder(service, self.drive_folder_path)
        if not root_id:
            LOGGER.error(f"Kunde inte hitta/skapa: {self.drive_folder_path}")
            return [], None

        year_id = self._get_or_create_folder(service, year, parent_id=root_id)
        if not year_id:
            return [], None

        month_id = self._get_or_create_folder(service, month_name, parent_id=year_id)
        if not month_id:
            return [], year_id # Returnera year_id så vi kan spara JSON där ändå?

        uploaded_files = []

        sender = self._sanitize_filename(ai_data.get("sender_name", "Okänd"))
        due_date = date_obj.strftime("%Y-%m-%d")
        inv_no = self._sanitize_filename(ai_data.get("invoice_number", "Saknas"))
        amount = self._sanitize_filename(ai_data.get("total_amount", "0"))
        ai_unique_id = self._sanitize_filename(ai_data.get("unique_id", ""))

        for idx, src_path in enumerate(attachment_paths):
            try:
                src = Path(src_path)
                suffix = src.suffix

                unique_part = ""
                if ai_unique_id:
                    unique_part += f"_{ai_unique_id}"

                if len(attachment_paths) > 1 or not ai_unique_id:
                     unique_part += f"_{idx+1}"

                new_filename = f"{sender}_{due_date}_{inv_no}_{amount}{unique_part}{suffix}"

                file_metadata = {'name': new_filename, 'parents': [month_id]}
                media = MediaFileUpload(src_path, mimetype='application/pdf')

                file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                uploaded_files.append(new_filename)

            except Exception as e:
                LOGGER.error(f"Kunde inte ladda upp {src_path}: {e}")

        return uploaded_files, year_id

    def _process_summary_json(self, service, year_folder_id, ai_data):
        """Hämtar, uppdaterar och sparar JSON-översikten i årsmappen."""
        if not self.summary_filename:
            return

        # 1. Hitta filen
        query = f"name='{self.summary_filename}' and '{year_folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        file_id = None
        current_data = {"year": "", "total_sum_year": 0.0, "senders": {}}

        if files:
            file_id = files[0]['id']
            # Ladda ner innehåll
            try:
                request = service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()

                fh.seek(0)
                content = fh.read().decode('utf-8')
                current_data = json.loads(content)
            except Exception as e:
                LOGGER.warning(f"Kunde inte läsa existerande JSON, skapar ny: {e}")

        # 2. Uppdatera data
        # Säkerställ struktur
        if "senders" not in current_data:
            current_data["senders"] = {}

        # Sätt år om det saknas (baserat på fakturan vi behandlar nu)
        if not current_data.get("year"):
             # Försök ta år från invoice_date eller due_date
             d_str = ai_data.get("invoice_date") or ai_data.get("due_date")
             if d_str:
                 try:
                     current_data["year"] = str(datetime.strptime(d_str, "%Y-%m-%d").year)
                 except:
                     pass

        sender = ai_data.get("sender_name", "Okänd")
        if sender not in current_data["senders"]:
            current_data["senders"][sender] = []

        # Kolla dubbletter (baserat på unique_id eller invoice_number)
        new_id = ai_data.get("unique_id") or ai_data.get("invoice_number")
        exists = False
        if new_id:
            for item in current_data["senders"][sender]:
                existing_id = item.get("unique_id") or item.get("invoice_number")
                if existing_id and existing_id == new_id:
                    exists = True
                    break

        if not exists:
            # Lägg till posten
            entry = {
                "type": ai_data.get("type", "Faktura"),
                "invoice_number": ai_data.get("invoice_number"),
                "invoice_date": ai_data.get("invoice_date"),
                "due_date": ai_data.get("due_date"),
                "amount_str": ai_data.get("total_amount"),
                "amount": self._parse_amount(ai_data.get("total_amount")),
                "unique_id": new_id,
                "summary": ai_data.get("summary"),
                "description": ai_data.get("description"),
                "added_at": dt_util.now().isoformat()
            }
            current_data["senders"][sender].append(entry)

            # Sortera listan på förfallodatum
            current_data["senders"][sender].sort(key=lambda x: x.get("due_date") or "9999-99-99")

            # 3. Räkna om totalsumma
            total = 0.0
            for s_list in current_data["senders"].values():
                for item in s_list:
                    # Dra av om det är kredit?
                    val = item.get("amount", 0)
                    if item.get("type", "").lower() == "kreditfaktura":
                        total -= val
                    else:
                        total += val
            current_data["total_sum_year"] = round(total, 2)

            # 4. Ladda upp igen
            json_content = json.dumps(current_data, indent=2, ensure_ascii=False)
            media_body = MediaFileUpload(
                io.BytesIO(json_content.encode('utf-8')),
                mimetype='application/json',
                resumable=True
            )

            if file_id:
                # Uppdatera
                service.files().update(
                    fileId=file_id,
                    media_body=media_body
                ).execute()
                if self.enable_debug:
                    LOGGER.info(f"Uppdaterade JSON-fil: {self.summary_filename}")
            else:
                # Skapa ny
                file_metadata = {
                    'name': self.summary_filename,
                    'parents': [year_folder_id],
                    'mimeType': 'application/json'
                }
                service.files().create(
                    body=file_metadata,
                    media_body=media_body
                ).execute()
                if self.enable_debug:
                    LOGGER.info(f"Skapade ny JSON-fil: {self.summary_filename}")

    def _parse_amount(self, amount_str):
        """Försöker extrahera ett tal från en sträng (t.ex. '399 kr' -> 399.0)."""
        if not amount_str:
            return 0.0
        try:
            # Rensa bort allt utom siffror, komma, punkt och minus
            clean = re.sub(r"[^0-9,.-]", "", str(amount_str))
            # Byt komma mot punkt
            clean = clean.replace(",", ".")
            return float(clean)
        except Exception:
            return 0.0

    def _get_or_create_nested_folder(self, service, folder_path):
        if not folder_path:
            return None
        parts = [p.strip() for p in folder_path.split("/") if p.strip()]
        if not parts:
            return None
        parent_id = None
        for part in parts:
            folder_id = self._get_or_create_folder(service, part, parent_id)
            if not folder_id:
                return None
            parent_id = folder_id
        return parent_id

    def _get_or_create_folder(self, service, folder_name, parent_id=None):
        try:
            query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"

            results = service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])

            if files:
                return files[0]['id']
            else:
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                if parent_id:
                    file_metadata['parents'] = [parent_id]
                folder = service.files().create(body=file_metadata, fields='id').execute()
                return folder.get('id')
        except Exception as e:
            LOGGER.error(f"Fel vid mapphantering ({folder_name}): {e}")
            return None

    def _create_notification(self, ai_data, sender_email, uploaded_files):
        summary = ai_data.get("summary", "Okänd faktura")
        amount = ai_data.get("total_amount", "? kr")
        sender_name = ai_data.get("sender_name", sender_email)

        message = f"Faktura från {sender_name} hanterad.\nInfo: {summary}\nSumma: {amount}"

        if uploaded_files:
            message += f"\n\nLaddade upp {len(uploaded_files)} filer till Google Drive."

        self.hass.add_job(
            self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "Ny Faktura Hanterad",
                    "message": message,
                    "notification_id": f"mail_agent_invoice_{int(dt_util.now().timestamp())}"
                }
            )
        )

    def _get_swedish_month(self, month_number):
        months = [
            "Januari", "Februari", "Mars", "April", "Maj", "Juni",
            "Juli", "Augusti", "September", "Oktober", "November", "December"
        ]
        return months[month_number - 1]

    def _sanitize_filename(self, text):
        if not text:
            return "Okand"
        keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        cleaned = "".join(c if c in keep else "_" for c in text)
        return cleaned.strip("_")
