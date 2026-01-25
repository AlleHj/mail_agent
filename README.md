![Version](https://img.shields.io/badge/version-0.19.0-blue.svg)
![Home Assistant](https://img.shields.io/badge/home%20assistant-component-orange.svg)

Mail Agent för Home Assistant
Version: 0.19.0
Uppdaterad: 2026-01-25

Mail Agent är en intelligent "Custom Component" för Home Assistant som automatiserar hanteringen av inkommande post. Genom att kombinera Google Gemini (Generativ AI) med traditionell e-posthantering (IMAP/SMTP), fungerar komponenten som en smart sekreterare som läser dina mail, förstår innehållet (inklusive bilagor) och automatiskt bokar in möten i din kalender.

🚀 Nyheter i v0.19.0 (AI & Kompatibilitet)
Denna version introducerar smartare filhantering och framtidssäkrar integrationen:
📎 AI-Namngivning: Agenten analyserar nu innehållet i bifogade PDF:er och döper om dem till något logiskt (t.ex. "Tandläkare_2025-05-10.pdf") innan de skickas vidare.
🏗️ HA 2025.1+ Kompatibilitet: Uppdaterad kodbas för att fungera med kommande Home Assistant-versioner (fixat RestoreEntity och async-hantering).
🧹 Renare Kod: Omfattande genomgång och uppstädning av koden (Ruff-linting) för ökad kvalitet och färre varningar i loggen.

📊 Nya Entiteter
Integrationen skapar nu följande entiteter för varje konfigurerat konto:
binary_sensor.mail_agent_scanning: Visar PÅ när agenten aktivt söker efter och bearbetar mail.
binary_sensor.mail_agent_connected: Visar status för anslutningen till IMAP-servern.
sensor.mail_agent_last_scan: Tidsstämpel för när inkorgen senast kontrollerades framgångsrikt.
sensor.mail_agent_last_event_summary: Visar sammanfattningen av det senast hittade eventet (t.ex. "Tandläkartid 14:00").
sensor.mail_agent_emails_processed: En räknare som visar totalt antal mail agenten har analyserat.

📋 Huvudfunktioner
🧠 AI-Driven Analys: Använder Google Gemini för att förstå naturligt språk i mail och bifogade PDF-kallelser.
📅 Automatisk Kalenderbokning: Extraherar tid, plats och sammanfattning och skapar händelser i din kalender.
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

🛠️ Felsökning
Sensorerna visar "Unknown"? Vänta till nästa sökintervall eller tvinga en omladdning av integrationen, så kommer de igång.
Inga mail hittas? Kontrollera att mailen är markerade som Olästa (Unseen) i din inkorg.

📄 Licens
Open Source för personligt bruk.
