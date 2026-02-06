# Fil: custom_components/mail_agent/forvaltare_processor.py | Version: 0.24.0
"""Processor för att hantera fakturor och förvaltning via Google Drive."""

import json
import io
import re
import time
from datetime import datetime
from pathlib import Path

from google import genai
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

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
        self.drive_folder_path = config.get("drive_folder_path", "Fakturor")
        self.summary_filename = config.get("summary_filename", "fakturor_oversikt.json")

        # Cache for folder IDs to reduce API calls and prevent duplicates
        # Key: (parent_id, folder_name), Value: folder_id
        self.folder_cache = {}

    def process_email(self, sender, subject, body, attachment_paths, service=None):
        """
        Huvudmetod som anropas från MailAgentScanner.
        service: Ett autentiserat Google Drive Resource objekt.
        """

        if not self.gemini_api_key:
            if self.enable_debug:
                LOGGER.warning("Ingen API-nyckel för Gemini.")
            return None

        try:
            # 1. Anropa AI
            ai_data = self._call_gemini(attachment_paths, subject, body)

            if not ai_data:
                return None

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

            # 2. Ladda upp filer till Drive (eller förbered mappar för JSON)
            uploaded_files_info = [] # Lista med dicts {name, link}
            year_folder_id = None

            if service:
                # Vi kör alltid detta för att få year_folder_id till JSON, även utan bilagor
                uploaded_files_info, year_folder_id = self._upload_to_drive(service, ai_data, attachment_paths)
            else:
                LOGGER.warning("Ingen Drive-tjänst tillgänglig.")

            # 3. Uppdatera Översikts-JSON
            if service and year_folder_id:
                try:
                    self._process_summary_json(service, year_folder_id, ai_data, uploaded_files_info)
                except Exception as e:
                    LOGGER.error(f"Kunde inte uppdatera översiktsfilen: {e}")

            # 4. Notifiera
            self._create_notification(ai_data, sender, uploaded_files_info)

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

        Din uppgift är att analysera bifogade filer (om några), ämnesrad och brödtext i detalj.

        LETA EFTER FÖLJANDE:
        1. **Typ**: Är detta en "Faktura", "Kreditfaktura" eller annat (t.ex. "Tillgodokvitto")?
        2. **Avsändare**: Vem är det från? (T.ex. Comviq, Skatteverket).
        3. **Datum**:
           - **Fakturadatum**: När ställdes fakturan ut? (Detta styr sorteringen).
           - **Förfallodatum**: När ska den betalas?
           - Om datum saknas, använd dagens datum ({now_str}).
        4. **Belopp**: Totalsumma (inkludera valuta, t.ex. "399,00 kr"). Var noga med valören.
        5. **Referenser**:
           - **Fakturanummer**: Fakturans nummer.
           - **OCR**: OCR-numret för betalning. Ibland samma som fakturanummer.
           - **Kundnummer**: Kundnumret om det finns.
        6. **Betalning**:
           - **Betalsätt**: Plusgiro, Bankgiro eller annat.
        7. **Kontakt**:
           - **Telefon**: Telefonnummer till avsändaren om det finns.
        8. **Beskrivning**: En kortfattad text om vad det gäller.

        Om du inte hittar ett värde, sätt det till "okänt" (eller "0" för belopp).

        Svara strikt med JSON:
        {{
            "invoice_found": boolean,
            "type": "Faktura/Kreditfaktura/Annat",
            "sender_name": "Namn",
            "invoice_date": "YYYY-MM-DD",
            "due_date": "YYYY-MM-DD",
            "total_amount": "Belopp",
            "invoice_number": "Nummer/okänt",
            "ocr_number": "Nummer/okänt",
            "customer_number": "Nummer/okänt",
            "payment_method": "BG/PG/okänt",
            "phone_number": "Nummer/okänt",
            "summary": "Kort rubrik",
            "description": "Beskrivning"
        }}
        """

        contents = uploaded_files + [prompt]

        # Retry logic for 503 UNAVAILABLE
        max_retries = 3
        for attempt in range(max_retries):
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
                # Check for 503 or overload errors
                if "503" in str(e) or "overloaded" in str(e).lower():
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        LOGGER.warning(f"Gemini 503 Unavailable. Försök {attempt + 1}/{max_retries}. Väntar {wait_time}s...")
                        time.sleep(wait_time)
                        continue

                LOGGER.error(f"Fel vid AI-anrop (försök {attempt+1}): {e}")
                for f in uploaded_files:
                    try:
                        client.files.delete(name=f.name)
                    except Exception:
                        pass
                return None

        return None

    def _upload_to_drive(self, service, ai_data, attachment_paths):
        """Laddar upp filer och returnerar (lista_med_info, year_folder_id)."""
        # Datumlogik: Fakturadatum -> Förfallodatum -> Idag
        date_str = ai_data.get("invoice_date") or ai_data.get("due_date")
        if not date_str or date_str.lower() == "okänt":
            date_obj = dt_util.now()
        else:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except (ValueError, TypeError):
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
            return [], year_id

        uploaded_info = []

        # Hämta data för filnamn
        sender = self._sanitize_filename(ai_data.get("sender_name", "okänt"))

        inv_date_str = ai_data.get("invoice_date")
        if not inv_date_str or inv_date_str.lower() == "okänt":
            inv_date_str = dt_util.now().strftime("%Y-%m-%d")

        due_date_str = ai_data.get("due_date")
        if not due_date_str or due_date_str.lower() == "okänt":
            due_date_str = dt_util.now().strftime("%Y-%m-%d")

        inv_no = self._sanitize_filename(ai_data.get("invoice_number", "okänt"))
        ocr = self._sanitize_filename(ai_data.get("ocr_number", "okänt"))
        cust_no = self._sanitize_filename(ai_data.get("customer_number", "okänt"))
        amount = self._sanitize_filename(ai_data.get("total_amount", "0"))

        for idx, src_path in enumerate(attachment_paths):
            try:
                src = Path(src_path)
                suffix = src.suffix

                # Format: [avsändare]_Fakturadatum [datum1] Förfallodatum [datum2] Fakturnr [fakturanr] OCR [OCR] Kundnr [kundnr] Summa [Summa].pdf
                idx_part = ""
                if len(attachment_paths) > 1:
                    idx_part = f"_{idx+1}"

                new_filename = (
                    f"{sender}_Fakturadatum {inv_date_str} Förfallodatum {due_date_str} "
                    f"Fakturnr {inv_no} OCR {ocr} Kundnr {cust_no} Summa {amount}{idx_part}{suffix}"
                )

                # KONTROLLERA DUBBLETT
                query = f"name = '{new_filename}' and '{month_id}' in parents and trashed = false"
                existing = service.files().list(q=query, fields="files(id, webViewLink)").execute()
                if existing.get('files'):
                    LOGGER.info(f"Filen '{new_filename}' finns redan på Drive. Hoppar över uppladdning.")
                    # Lägg till existerande fil till info om vi vill länka den
                    f_obj = existing.get('files')[0]
                    uploaded_info.append({
                        "name": new_filename,
                        "link": f_obj.get("webViewLink", "")
                    })
                    continue

                file_metadata = {'name': new_filename, 'parents': [month_id]}
                media = MediaFileUpload(src_path, mimetype='application/pdf')

                file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
                if self.enable_debug:
                    LOGGER.info(f"Laddade upp fil till Drive: {new_filename} (ID: {file.get('id')})")

                uploaded_info.append({
                    "name": new_filename,
                    "link": file.get("webViewLink", "")
                })

            except Exception as e:
                LOGGER.error(f"Kunde inte ladda upp {src_path}: {e}")

        return uploaded_info, year_id

    def _process_summary_json(self, service, year_folder_id, ai_data, uploaded_files_info):
        """Hämtar, uppdaterar och sparar JSON-översikten i årsmappen med svenska nycklar och statistik."""
        if not self.summary_filename:
            return

        # 1. Hitta filen
        query = f"name='{self.summary_filename}' and '{year_folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        file_id = None
        # Initiera med nya strukturen
        current_data = {
            "år": "",
            "totalsumma_år": 0.0,
            "totalt_antal_fakturor": 0,
            "avsändare": {}
        }

        if files:
            file_id = files[0]['id']
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
        if "avsändare" not in current_data:
            current_data["avsändare"] = {}

        # Sätt år
        if not current_data.get("år"):
             d_str = ai_data.get("invoice_date") or ai_data.get("due_date")
             if d_str and d_str.lower() != "okänt":
                 try:
                     current_data["år"] = str(datetime.strptime(d_str, "%Y-%m-%d").year)
                 except (ValueError, TypeError):
                     pass
        if not current_data.get("år"):
             current_data["år"] = str(dt_util.now().year)

        sender = ai_data.get("sender_name", "Okänd")

        # Hantera migrering från lista till objekt för avsändare
        if sender in current_data["avsändare"] and isinstance(current_data["avsändare"][sender], list):
            old_list = current_data["avsändare"][sender]
            current_data["avsändare"][sender] = {
                "summa": 0.0,
                "antal": 0,
                "fakturor": old_list
            }
        elif sender not in current_data["avsändare"]:
            current_data["avsändare"][sender] = {
                "summa": 0.0,
                "antal": 0,
                "fakturor": []
            }

        fakturor_lista = current_data["avsändare"][sender]["fakturor"]

        # Dubblettkontroll
        new_inv = ai_data.get("invoice_number", "okänt")
        new_ocr = ai_data.get("ocr_number", "okänt")

        check_id = new_inv if new_inv != "okänt" else new_ocr
        if check_id == "okänt":
             raw = f"{ai_data.get('summary')}{ai_data.get('invoice_date')}"
             check_id = str(hash(raw))

        exists = False
        for item in fakturor_lista:
            existing_inv = item.get("fakturanummer", "okänt")
            existing_ocr = item.get("ocr", "okänt")

            if (existing_inv != "okänt" and existing_inv == new_inv) or \
               (existing_ocr != "okänt" and existing_ocr == new_ocr) or \
               (item.get("unikt_id") == check_id):
                 exists = True
                 break

        # Hämta länk från första filen om den finns
        file_link = ""
        if uploaded_files_info:
            file_link = uploaded_files_info[0].get("link", "")

        if not exists:
            entry = {
                "typ": ai_data.get("type", "Faktura"),
                "fakturanummer": ai_data.get("invoice_number", "okänt"),
                "ocr": ai_data.get("ocr_number", "okänt"),
                "fakturadatum": ai_data.get("invoice_date", dt_util.now().strftime("%Y-%m-%d")),
                "förfallodatum": ai_data.get("due_date", dt_util.now().strftime("%Y-%m-%d")),
                "belopp": self._parse_amount(ai_data.get("total_amount")),
                "kundnummer": ai_data.get("customer_number", "okänt"),
                "betalsätt": ai_data.get("payment_method", "okänt"),
                "telefon": ai_data.get("phone_number", "okänt"),
                "beskrivning": ai_data.get("description", ""),
                "unikt_id": check_id,
                "tillagd": dt_util.now().isoformat(),
                "länk": file_link
            }
            fakturor_lista.append(entry)
            fakturor_lista.sort(key=lambda x: x.get("fakturadatum") or "9999-99-99")

        else:
            if self.enable_debug:
                LOGGER.info("Fakturan finns redan i JSON-översikten (dubblett).")

        # 3. Räkna om totalsummor och statistik
        total_year = 0.0
        count_year = 0

        for s_name, s_data in current_data["avsändare"].items():
            # Migrering för andra avsändare om vi loopar igenom
            if isinstance(s_data, list):
                 s_data = {"summa": 0.0, "antal": 0, "fakturor": s_data}
                 current_data["avsändare"][s_name] = s_data

            sub_total = 0.0
            sub_count = len(s_data["fakturor"])

            for item in s_data["fakturor"]:
                val = item.get("belopp", 0)
                if "kredit" in str(item.get("typ", "")).lower():
                    sub_total -= val
                else:
                    sub_total += val

            s_data["summa"] = round(sub_total, 2)
            s_data["antal"] = sub_count

            total_year += sub_total
            count_year += sub_count

        current_data["totalsumma_år"] = round(total_year, 2)
        current_data["totalt_antal_fakturor"] = count_year

        # 4. Ladda upp
        json_content = json.dumps(current_data, indent=2, ensure_ascii=False)
        media_body = MediaIoBaseUpload(
            io.BytesIO(json_content.encode('utf-8')),
            mimetype='application/json',
            resumable=True
        )

        if file_id:
            service.files().update(
                fileId=file_id,
                media_body=media_body
            ).execute()
            if self.enable_debug:
                LOGGER.info(f"Uppdaterade JSON-fil: {self.summary_filename}")
        else:
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
        if not amount_str:
            return 0.0
        try:
            clean = re.sub(r"[^0-9,.-]", "", str(amount_str))
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
        # 1. Check local cache
        cache_key = (parent_id, folder_name)
        if cache_key in self.folder_cache:
            if self.enable_debug:
                LOGGER.debug(f"Using cached folder ID for '{folder_name}' (parent: {parent_id}): {self.folder_cache[cache_key]}")
            return self.folder_cache[cache_key]

        try:
            # 2. Check Drive
            query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"

            results = service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])

            if files:
                folder_id = files[0]['id']
                self.folder_cache[cache_key] = folder_id
                return folder_id
            else:
                # 3. Create Folder (with brief pause)
                if self.enable_debug:
                    LOGGER.debug(f"Creating folder '{folder_name}'...")

                # Small pause to help consistency/propagation
                time.sleep(2)

                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                if parent_id:
                    file_metadata['parents'] = [parent_id]
                folder = service.files().create(body=file_metadata, fields='id').execute()
                folder_id = folder.get('id')

                if folder_id:
                    self.folder_cache[cache_key] = folder_id
                    if self.enable_debug:
                        LOGGER.info(f"Created folder '{folder_name}' with ID: {folder_id}")

                return folder_id
        except Exception as e:
            LOGGER.error(f"Fel vid mapphantering ({folder_name}): {e}")
            return None

    def _create_notification(self, ai_data, sender_email, uploaded_files_info):
        summary = ai_data.get("summary", "Okänd faktura")
        amount = ai_data.get("total_amount", "? kr")
        sender_name = ai_data.get("sender_name", sender_email)

        message = f"Faktura från {sender_name} hanterad.\nInfo: {summary}\nSumma: {amount}"

        if uploaded_files_info:
            message += f"\n\nLaddade upp {len(uploaded_files_info)} filer till Google Drive."
        elif uploaded_files_info is not None and len(uploaded_files_info) == 0:
             message += "\n\nInga nya filer laddades upp (dubbletter eller fel)."

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
            "01. Januari", "02. Februari", "03. Mars", "04. April",
            "05. Maj", "06. Juni", "07. Juli", "08. Augusti",
            "09. September", "10. Oktober", "11. November", "12. December"
        ]
        return months[month_number - 1]

    def _sanitize_filename(self, text):
        if not text:
            return "Okand"
        # Tillåt mellanslag, komma, punkt, bokstäver, siffror
        keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_,."
        cleaned = "".join(c if c in keep else "_" for c in text)
        return cleaned.strip("_")