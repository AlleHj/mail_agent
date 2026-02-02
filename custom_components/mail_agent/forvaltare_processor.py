# Version: 0.19.0
"""Processor för att hantera fakturor och förvaltning via Google Drive."""

import json
from datetime import datetime
from pathlib import Path

from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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
        # Standardvärde "Fakturor" om inget anges
        self.drive_folder_path = config.get("drive_folder_path", "Fakturor")

    def process_email(self, sender, subject, body, attachment_paths):
        """
        Huvudmetod som anropas från MailAgentScanner.

        1. Analysera data med AI (PDF + Subject + Body).
        2. Ladda upp filen till Google Drive.
        3. Skicka Persistent Notification.
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

            if self.enable_debug:
                LOGGER.info("AI RESULTAT (Förvaltare):\n%s", json.dumps(ai_data, indent=2, ensure_ascii=False))

            # Fire event (kan vara bra för debugging/automatisering)
            self.hass.bus.fire("mail_agent.scanned_document", {
                "type": "forvaltare",
                "sender": sender,
                "subject": subject,
                "ai_data": ai_data,
                "attachments": [str(p) for p in attachment_paths]
            })

            # 2. Ladda upp filer till Drive
            uploaded_files = []
            if attachment_paths:
                # Vi försöker ladda upp även om AI inte är 100% säker, för att inte tappa bort dokument.
                # Om konfiguration saknas loggas ett fel.
                uploaded_files = self._upload_to_drive(ai_data, attachment_paths)

            # 3. Notifiera
            self._create_notification(ai_data, sender, uploaded_files)

            # Returnera data så att sensorn kan uppdateras
            return ai_data

        except Exception as e:
            LOGGER.error("Fel i ForvaltareProcessor: %s", e)
            return None

    def _call_gemini(self, file_paths, subject, body):
        client = genai.Client(api_key=self.gemini_api_key)
        uploaded_files = []

        # Ladda upp bilagor till Gemini
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

        Din uppgift är att analysera bifogade filer (om några), ämnesrad och brödtext för att hitta fakturainformation.
        Informationen kan finnas i mailets text även om det finns en PDF.

        LETA EFTER FÖLJANDE (Extremt noga):
        1. **Betalningsmottagare/Avsändare**: Vem ska ha betalt? (T.ex. Telia, Skatteverket, Hyresvärden).
        2. **Förfallodatum**: När ska det betalas? DETTA ÄR PRIO 1.
           - Om förfallodatum saknas, leta efter fakturadatum.
           - Format: YYYY-MM-DD.
           - Om du absolut inte hittar något datum (varken förfall eller faktura), lämna tomt (koden hanterar fallback).
        3. **Totalsumma**: Belopp att betala (inkl. valuta om möjligt).
        4. **Fakturanummer/OCR**: Referensnummer.
        5. **Unikt ID**: Skapa en kort, unik sträng baserat på innehållet (t.ex. OCR eller Fakturanr) för filnamnet.

        Svara strikt med JSON:
        {{
            "invoice_found": boolean,  // True om det verkar vara en faktura eller viktigt dokument
            "sender_name": "Namn",
            "due_date": "YYYY-MM-DD" eller null,
            "total_amount": "Belopp",
            "invoice_number": "OCR/Nr",
            "unique_id": "UnikID",
            "summary": "Kort sammanfattning (t.ex. 'Faktura Telia 499kr')",
            "description": "Mer detaljerad beskrivning"
        }}
        """

        contents = uploaded_files + [prompt]

        # Använd en säker metod för att kalla på modellen
        try:
            response = client.models.generate_content(
                model=self.gemini_model,
                contents=contents,
                config={'response_mime_type': 'application/json'}
            )

            # Städa upp uppladdade filer hos Google
            for f in uploaded_files:
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass

            return json.loads(response.text)

        except Exception as e:
            LOGGER.error(f"Fel vid AI-anrop: {e}")
            # Försök städa upp även vid fel
            for f in uploaded_files:
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass
            return {}

    def _get_drive_service(self):
        """Skapar och returnerar en autentiserad Google Drive Service."""
        if not all([self.google_client_id, self.google_client_secret, self.google_refresh_token]):
            LOGGER.error("Saknar inloggningsuppgifter för Google Drive (Client ID, Secret eller Refresh Token).")
            return None

        try:
            creds = Credentials(
                None, # Ingen access token från start
                refresh_token=self.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.google_client_id,
                client_secret=self.google_client_secret
            )
            service = build('drive', 'v3', credentials=creds)
            return service
        except Exception as e:
            LOGGER.error(f"Kunde inte skapa Google Drive-tjänst: {e}")
            return None

    def _get_or_create_nested_folder(self, service, folder_path):
        """
        Traverserar och skapar mappar enligt sökväg (t.ex. "Rot/Undermapp/Mapp").
        Returnerar ID för sista mappen i kedjan.
        """
        if not folder_path:
            return None

        parts = [p.strip() for p in folder_path.split("/") if p.strip()]
        if not parts:
            return None

        parent_id = None # Startar i root om None

        for part in parts:
            folder_id = self._get_or_create_folder(service, part, parent_id)
            if not folder_id:
                # Om vi misslyckas på någon nivå kan vi inte fortsätta
                LOGGER.error(f"Kunde inte hitta/skapa mapp '{part}' i sökvägen.")
                return None
            parent_id = folder_id

        return parent_id

    def _get_or_create_folder(self, service, folder_name, parent_id=None):
        """Hittar en mapp med givet namn (inom parent_id) eller skapar den."""
        try:
            query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            else:
                # Om inget parent_id, sök INTE i hela driven utan (oftast) i root om det inte specas.
                # Men om man vill hitta en mapp i "Mina filer" (root) så är 'root' in parents implicit om man inte anger något.
                # För säkerhets skull kan vi anta att om parent_id är None menar vi root eller så låter vi Drive söka överallt.
                # Men för att bygga struktur är det bäst att inte söka överallt om vi tror det är en undermapp.
                # I _get_or_create_nested_folder hanteras logiken. Första nivån är parent_id=None -> root?
                # Egentligen: Om parent_id är None, så söker vi bara på namn. Det kan hitta mappar var som helst.
                # Men om vi skapar, skapas den i root.
                pass

            results = service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])

            if files:
                # Mappen finns, returnera ID
                return files[0]['id']
            else:
                # Mappen finns inte, skapa den
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                if parent_id:
                    file_metadata['parents'] = [parent_id]

                folder = service.files().create(body=file_metadata, fields='id').execute()
                if self.enable_debug:
                    LOGGER.info(f"Skapade mapp på Drive: {folder_name} (ID: {folder.get('id')})")
                return folder.get('id')

        except Exception as e:
            LOGGER.error(f"Fel vid mapphantering ({folder_name}): {e}")
            return None

    def _upload_to_drive(self, ai_data, attachment_paths):
        """Laddar upp filer till Google Drive i strukturen Grundmapp/År/Månad."""
        service = self._get_drive_service()
        if not service:
            return []

        # Datumlogik för mappstruktur
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

        # 1. Hitta/Skapa hela sökvägen till Grundmappen (t.ex. "Nellie/Förvaltare")
        root_id = self._get_or_create_nested_folder(service, self.drive_folder_path)
        if not root_id:
            LOGGER.error(f"Kunde inte navigera till målmappen: {self.drive_folder_path}")
            return []

        # 2. Hitta/Skapa Årsmapp
        year_id = self._get_or_create_folder(service, year, parent_id=root_id)
        if not year_id:
            return []

        # 3. Hitta/Skapa Månadsmapp
        month_id = self._get_or_create_folder(service, month_name, parent_id=year_id)
        if not month_id:
            return []

        uploaded_files = []

        # Filnamnskomponenter
        sender = self._sanitize_filename(ai_data.get("sender_name", "Okänd"))
        due_date = date_obj.strftime("%Y-%m-%d")
        inv_no = self._sanitize_filename(ai_data.get("invoice_number", "Saknas"))
        amount = self._sanitize_filename(ai_data.get("total_amount", "0"))
        ai_unique_id = self._sanitize_filename(ai_data.get("unique_id", ""))

        for idx, src_path in enumerate(attachment_paths):
            try:
                src = Path(src_path)
                suffix = src.suffix

                # Unikt ID
                unique_part = ""
                if ai_unique_id:
                    unique_part += f"_{ai_unique_id}"

                if len(attachment_paths) > 1 or not ai_unique_id:
                     unique_part += f"_{idx+1}"

                new_filename = f"{sender}_{due_date}_{inv_no}_{amount}{unique_part}{suffix}"

                # Ladda upp filen
                file_metadata = {
                    'name': new_filename,
                    'parents': [month_id]
                }
                media = MediaFileUpload(src_path, mimetype='application/pdf') # Antag PDF, eller gissa typ

                file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

                if self.enable_debug:
                    LOGGER.info(f"Laddade upp fil till Drive: {new_filename} (ID: {file.get('id')})")

                uploaded_files.append(new_filename)

            except Exception as e:
                LOGGER.error(f"Kunde inte ladda upp fil {src_path} till Drive: {e}")

        return uploaded_files

    def _create_notification(self, ai_data, sender_email, uploaded_files):
        """Skapar en Persistent Notification i Home Assistant."""
        summary = ai_data.get("summary", "Okänd faktura")
        amount = ai_data.get("total_amount", "? kr")
        sender_name = ai_data.get("sender_name", sender_email)

        message = f"Faktura från {sender_name} hanterad.\nInfo: {summary}\nSumma: {amount}"

        if uploaded_files:
            message += f"\n\nLaddade upp {len(uploaded_files)} filer till Google Drive."
        else:
             message += "\n\nVARNING: Inga filer laddades upp (fel eller inga bilagor)."

        # Skicka persistent notification
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
        """Rensa sträng för att använda i filnamn."""
        if not text:
            return "Okand"
        # Byt ut ogiltiga tecken
        keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        cleaned = "".join(c if c in keep else "_" for c in text)
        return cleaned.strip("_")
