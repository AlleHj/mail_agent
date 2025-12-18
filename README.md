Mail Agent för Home Assistant
Version: 0.76.0
Uppdaterad: 2025-12-18
Tillåter nu flera instanser.

Version: 0.16.0
Uppdaterad: 2025-12-17

Mail Agent är en intelligent "Custom Component" för Home Assistant som automatiserar hanteringen av inkommande post. Genom att kombinera Google Gemini (Generativ AI) med traditionell e-posthantering (IMAP/SMTP), fungerar komponenten som en smart sekreterare som läser dina mail, förstår innehållet (inklusive bilagor) och automatiskt bokar in möten i din kalender.

🚀 Huvudfunktioner i v0.16.0
  🧠 AI-Driven Analys: Använder Google Gemini (gemini-3-pro-preview) för att förstå naturligt språk i mail och bifogade PDF-kallelser.
  📅 Automatisk Kalenderbokning: Extraherar tid, plats och sammanfattning från ostrukturerad text och skapar händelser i din kalender.
  🛡️ Trådsäkerhet & Global Låsning: Inbyggd "Scanning Lock" som förhindrar att samma mail bearbetas två gånger.
  📧 Robust SMTP-motor:
  Dynamisk Bilagehantering: Skickar endast multipart-mail om bilagor faktiskt finns (eliminerar "spök-bilagor").
  Anpassat Avsändarnamn: Ställ in ett snyggt namn (t.ex. "Min Sekreterare") för utgående mail.
  🧩 Modulär Arkitektur: Byggd med "Strategy Pattern". Specifik logik (t.ex. för kallelser) ligger i separata filer, vilket gör systemet redo för framtida expansion (t.ex. fakturor).

📋 Krav
Home Assistant: Version 2024.x eller senare.
Google AI Studio API-nyckel: För tillgång till Gemini.
E-postkonto: IMAP (för att läsa) och SMTP (för att skicka) aktiverat.
Tips: Använd App-lösenord för Gmail.

🔧 Installation
Ladda ner mappen mail_agent och placera den i /config/custom_components/.
Starta om Home Assistant.
Gå till Inställningar -> Enheter & Tjänster -> Lägg till integration.
Sök efter "Mail Agent" och följ guiden.

⚙️ Konfiguration
Allt konfigureras direkt via UI (Config Flow). Inga YAML-filer behövs.
Anslutning
IMAP: Server, Port, Användare, Lösenord, Mapp.
SMTP: Server, Port, Avsändarnamn (Nytt!).

Logik & AI
Tolkningstyp: Välj vad integrationen ska göra (Just nu: "Tolka kallelse").
Gemini: API-nyckel och modellnamn.
Sökintervall: Hur ofta inkorgen ska kollas (sekunder).

Integrationer
Kalendrar: Välj upp till två kalendrar för bokningar.
Notifieringar: Välj vilka mobiler och e-postadresser som ska få notiser.

🛠️ Felsökning
Dubbla notiser? Kontrollera att du kör v0.15.1+ som har Global Låsning.
Import-fel på google.genai? Starta om Home Assistant helt för att ladda in nya bibliotek.
Inga mail hittas? Kontrollera att mailen är markerade som Olästa (Unseen).

📄 Licens
Detta projekt är utvecklat som en anpassad integration för personligt bruk (Open Source).
