![Version](https://img.shields.io/badge/version-0.19.0-blue.svg)
![Home Assistant](https://img.shields.io/badge/home%20assistant-component-orange.svg)

Mail Agent för Home Assistant
Version: 0.19.0
Uppdaterad: 2026-05-10

Mail Agent är en intelligent "Custom Component" för Home Assistant som automatiserar hanteringen av inkommande post. Genom att kombinera Google Gemini (Generativ AI) med traditionell e-posthantering (IMAP/SMTP), fungerar komponenten som en smart sekreterare eller förvaltare som läser dina mail, förstår innehållet (inklusive bilagor) och agerar därefter.

🚀 Nyheter i v0.19.0 (Förvaltare & Fakturor)
Denna version introducerar en helt ny typ av logik: "Förvaltare".
📁 Fakturahantering: Automatisk sortering och namngivning av inkommande fakturor.
☁️ Google Drive-uppladdning: Sparar filer direkt till din Google Drive med OAuth2 (Refresh Token).
💾 Arkivering: Skapar automatiskt mappar för År och Månad på din Drive.
🔔 Notifieringar: Få en diskret notifiering i Home Assistant när en faktura har behandlats och laddats upp.

🚀 Nyheter i v0.18.0 (Restore & Stabilitet)
Denna version fokuserar på dataintegritet och driftstabilitet:
💾 Restore-funktionalitet: Sensorerna (t.ex. "Emails Processed") nollställs inte längre när du ändrar inställningar eller startar om Home Assistant. De minns sitt senaste värde.
🛡️ Ökad Stabilitet: Fixar för "Thread Safety" och robustare hantering av IMAP-svar (förhindrar krascher vid oväntade mail-format).
👁️ Full Insyn: Nya sensorer ger dig kontroll över vad agenten gör i realtid.

📊 Nya Entiteter
Integrationen skapar nu följande entiteter för varje konfigurerat konto:
binary_sensor.mail_agent_scanning: Visar PÅ när agenten aktivt söker efter och bearbetar mail.
binary_sensor.mail_agent_connected: Visar status för anslutningen till IMAP-servern.
sensor.mail_agent_last_scan: Tidsstämpel för när inkorgen senast kontrollerades framgångsrikt.
sensor.mail_agent_last_event_summary: Visar sammanfattningen av det senast hittade eventet (t.ex. "Tandläkartid 14:00").
sensor.mail_agent_emails_processed: En räknare som visar totalt antal mail agenten har analyserat.

📋 Huvudfunktioner
🧠 AI-Driven Analys: Använder Google Gemini för att förstå naturligt språk i mail och bifogade PDF-kallelser.
📅 Automatisk Kalenderbokning (Typ: Kallelse): Extraherar tid, plats och sammanfattning och skapar händelser i din kalender.
💼 Fakturahantering (Typ: Förvaltare): Extraherar belopp, OCR och datum från fakturor och sparar dem strukturerat på Google Drive.
🔒 Trådsäkerhet: "Global Scanning Lock" förhindrar att samma mail bearbetas två gånger samtidigt.
📧 Robust SMTP: Skickar multipart-mail endast vid behov och hanterar bilagor korrekt.
🎨 Dashboard-ready: Bygg snygga statuspaneler i Lovelace med de nya sensorerna.

🔧 Installation
Ladda ner mappen mail_agent och placera den i /config/custom_components/.
Starta om Home Assistant.
Gå till Inställningar -> Enheter & Tjänster -> Lägg till integration.
Sök efter "Mail Agent" och följ guiden.

⚙️ Konfiguration (UI)
All konfiguration sker via gränssnittet. Inga YAML-filer behövs.
Anslutning: IMAP/SMTP server, port, användare, lösenord.
AI: Google Gemini API-nyckel och modellnamn.
Integrationer: Välj kalendrar och notifieringstjänster.
Logik: Anpassa sökintervall och debug-nivå.

För "Förvaltare"-läget krävs även:
Google Drive OAuth: Client ID, Client Secret och Refresh Token (för att ladda upp filer utan webbläsar-inloggning).
Målmapp: Namnet på den mapp i roten av din Drive där fakturor ska sparas (t.ex. "Fakturor").

🛠️ Felsökning
Sensorerna visar "Unknown"? Vänta till nästa sökintervall eller tvinga en omladdning av integrationen, så kommer de igång.
Inga mail hittas? Kontrollera att mailen är markerade som Olästa (Unseen) i din inkorg.

📄 Licens
Open Source för personligt bruk.
