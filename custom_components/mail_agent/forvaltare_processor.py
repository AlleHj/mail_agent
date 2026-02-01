# Version: 0.19.0
"""Processor för att hantera fakturor och förvaltning."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from google import genai

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
        self.storage_path = config.get("storage_path")

        # Vi behöver inte SMTP eller Kalender här enligt spec

    def process_email(self, sender, subject, body, attachment_paths):
        """
        Huvudmetod som anropas från MailAgentScanner.

        1. Analysera data med AI (PDF + Subject + Body).
        2. Spara filen strukturerat.
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

            # 2. Spara filer
            saved_files = []
            if ai_data.get("invoice_found") is True and attachment_paths:
                saved_files = self._save_files(ai_data, attachment_paths)
            elif attachment_paths:
                # Fallback: spara även om AI inte är 100% säker, men använd dagens datum?
                # Specifikationen sa: "Om AI:t absolut inte kan hitta något datum ... använd dagens datum".
                # Så vi sparar alltid om det finns bilagor och vi har kört analysen.
                saved_files = self._save_files(ai_data, attachment_paths)

            # 3. Notifiera
            self._create_notification(ai_data, sender, saved_files)

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

    def _save_files(self, ai_data, attachment_paths):
        """Sparar filer till konfigurerad mappstruktur."""
        if not self.storage_path:
            LOGGER.warning("Ingen lagringssökväg (storage_path) konfigurerad. Kan inte spara filer.")
            return []

        # Datumlogik för mappstruktur
        date_str = ai_data.get("due_date")

        # Fallback till dagens datum om inget hittades
        if not date_str:
            date_obj = dt_util.now()
        else:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                date_obj = dt_util.now()

        year = date_obj.strftime("%Y")
        month_name = self._get_swedish_month(date_obj.month)

        # Skapa sökväg: Grundmapp/ÅÅÅÅ/Månad/
        target_dir = Path(self.storage_path) / year / month_name

        saved_paths = []

        try:
            # Försök skapa mappar (motsvarar 'om Drive inte svarar' om detta misslyckas vid nätverksmount)
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            LOGGER.error(f"Kunde inte skapa mapp {target_dir}: {e}")
            return []

        # Konstruera filnamn
        # Format: Avsändare_Förfallodatum_Fakturanr_Summa_UniktID.pdf
        sender = self._sanitize_filename(ai_data.get("sender_name", "Okänd"))
        due_date = date_obj.strftime("%Y-%m-%d")
        inv_no = self._sanitize_filename(ai_data.get("invoice_number", "Saknas"))
        amount = self._sanitize_filename(ai_data.get("total_amount", "0"))
        ai_unique_id = self._sanitize_filename(ai_data.get("unique_id", ""))

        # Hantera flera bilagor genom att lägga till index om det behövs
        for idx, src_path in enumerate(attachment_paths):
            try:
                src = Path(src_path)
                suffix = src.suffix # Behåll ändelse (.pdf)

                # Konstruera unikt ID del
                # Om vi har flera filer lägger vi alltid till index för säkerhets skull
                # Om AI:t gav ett ID, använd det också

                unique_part = ""
                if ai_unique_id:
                    unique_part += f"_{ai_unique_id}"

                if len(attachment_paths) > 1 or not ai_unique_id:
                     unique_part += f"_{idx+1}"

                new_filename = f"{sender}_{due_date}_{inv_no}_{amount}{unique_part}{suffix}"
                dest_path = target_dir / new_filename

                shutil.copy2(src, dest_path)
                saved_paths.append(str(dest_path))

                if self.enable_debug:
                    LOGGER.info(f"Sparade fil till: {dest_path}")

            except Exception as e:
                LOGGER.error(f"Kunde inte spara fil {src_path} till {target_dir}: {e}")

        return saved_paths

    def _create_notification(self, ai_data, sender_email, saved_files):
        """Skapar en Persistent Notification i Home Assistant."""
        summary = ai_data.get("summary", "Okänd faktura")
        amount = ai_data.get("total_amount", "? kr")
        sender_name = ai_data.get("sender_name", sender_email)

        message = f"Faktura från {sender_name} hanterad.\nSumma: {amount}"

        if saved_files:
            message += f"\n\nSparade {len(saved_files)} filer."
            # Vi kan lägga till sökvägarna om vi vill, men det kanske blir kladdigt

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
