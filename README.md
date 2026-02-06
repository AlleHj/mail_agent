![Version](https://img.shields.io/badge/version-0.24.0-blue.svg)
![Home Assistant](https://img.shields.io/badge/home%20assistant-component-orange.svg)

# Mail Agent för Home Assistant

**Mail Agent** är en intelligent "Custom Component" för Home Assistant som automatiserar hanteringen av inkommande post via **Google Workspace/Gmail**. Genom att kombinera **Google Gemini (Generativ AI)** med Google APIs (Gmail & Drive), fungerar komponenten som en smart sekreterare som läser dina mail, förstår innehållet (inklusive bilagor) och agerar därefter.

---

## 🚀 Nyheter i v0.24.0 (OAuth2 & Modernisering)
Denna version är en total omskrivning av integrationslagret för att möta Googles moderna säkerhetskrav.
*   🔐 **OAuth2 Autentisering**: Inga fler app-lösenord eller manuella refresh tokens. Logga in säkert via Home Assistants inbyggda flöde.
*   📧 **Gmail API**: Ersätter gamla IMAP/SMTP för snabbare och säkrare hantering.
*   🎯 **Strikt Filtrering**: Integrationen lyssnar enbart på mail skickade till en specifik adress (t.ex. `faktura@din-doman.se`) och undviker loopar med smart etikett-hantering (`AI-HANTERAD`).
*   🔗 **Google Drive Integration**: Fakturor sparas med klickbara länkar direkt i översiktsfilen.

---

## 📋 Två Huvudlägen

### 1. 📅 Tolka Kallelse
Perfekt för familjekalendern.
*   **Funktion**: Läser kallelser (tandläkare, besiktning, frisör) och bokar in dem i din Home Assistant-kalender.
*   **Analys**: Extraherar tid, plats och beskrivning från mail och PDF-bilagor.
*   **Notifiering**: Skickar en notifiering till mobilen och ev. ett kvittensmail.

### 2. 💼 Förvaltare (Faktura & Admin)
Din digitala ekonomiavdelning.
*   **Funktion**: Hanterar inkommande fakturor och administrativa dokument.
*   **Struktur**: Sparar dokumentet på **Google Drive** i en mappstruktur baserad på År/Månad (t.ex. `Fakturor/2025/Februari/`).
*   **Översikt**: Uppdaterar en JSON-fil (`fakturor_oversikt.json`) med belopp, OCR, förfallodatum och **direktlänk till dokumentet**.
*   **Namngivning**: Döper om filen smart baserat på innehållet (t.ex. `Telia_Fakturadatum 2025-02-01 Summa 399kr.pdf`).

---

## ⚙️ Förberedelser (Google Cloud)

För att använda denna integration behöver du skapa ett projekt i Google Cloud Console.

1.  Gå till [Google Cloud Console](https://console.cloud.google.com/).
2.  Skapa ett nytt projekt.
3.  Aktivera följande API:er:
    *   **Gmail API**
    *   **Google Drive API**
4.  Gå till "APIs & Services" -> "Credentials".
5.  Konfigurera "OAuth consent screen" (Internal om du har Workspace, annars External/Test).
6.  Skapa "Credentials" -> "OAuth client ID" -> "Web application".
7.  Lägg till Home Assistants redirect URL (finns under Inställningar -> Enheter -> Autentiseringsuppgifter för applikationer i HA). Oftast: `https://my.home-assistant.io/redirect/oauth`.
8.  Spara **Client ID** och **Client Secret**.

---

## 🔧 Installation & Konfiguration

### Steg 1: Lägg till filer
Ladda ner mappen `mail_agent` och placera den i `/config/custom_components/`. Starta om Home Assistant.

### Steg 2: Lägg till Application Credentials
1.  Gå till **Inställningar** -> **Enheter & Tjänster** -> **... (Meny)** -> **Autentiseringsuppgifter för applikationer**.
2.  Klicka på "Lägg till autentiseringsuppgifter".
3.  Välj "Mail Agent".
4.  Klistra in ditt **Client ID** och **Client Secret** från Google Cloud.

### Steg 3: Lägg till Integrationen
1.  Gå till **Inställningar** -> **Enheter & Tjänster** -> **Lägg till integration**.
2.  Sök efter "Mail Agent".
3.  Logga in med ditt Google-konto när rutan poppar upp.
4.  Ge tillåtelse till mail- och filhantering.

### Steg 4: Konfigurera Parametrar
Du kommer nu till inställningssidan. Fyll i följande:

*   **E-postadress att bevaka**: (VIKTIGT!) Den adress integrationen ska lyssna på (t.ex. `kallelse@din-doman.se`).
*   **Avsändarnamn**: Namnet på denna "bot" (t.ex. "Faktura-Bot"). Detta styr också namnet på entiteterna i HA.
*   **Typ av tolkning**: Välj "Tolka kallelse" eller "Förvaltare".
*   **Google Gemini API-nyckel**: Din nyckel från [Google AI Studio](https://aistudio.google.com/).
*   **Google Drive Sökväg** (Förvaltare): Mappen där filer ska sparas (t.ex. `Fakturor`).
*   **Kalendrar & Notifieringar**: Välj var bokningar ska hamna och vem som ska notifieras.

---

## 📊 Entiteter

Integrationen skapar sensorer baserat på det **Avsändarnamn** du valt (t.ex. "Faktura-Bot"):

*   `binary_sensor.faktura_bot_scanning`: **PÅ** när agenten bearbetar mail.
*   `binary_sensor.faktura_bot_connected`: **PÅ** när anslutningen till Google fungerar.
*   `sensor.faktura_bot_last_scan`: Tidpunkt för senaste sökning.
*   `sensor.faktura_bot_emails_processed`: Antal hanterade mail totalt.
*   `sensor.faktura_bot_last_event_summary`: Senaste händelsen (t.ex. "Ny faktura från Telia hanterad").

---

## 🛠️ Felsökning

*   **Inga mail hämtas?**
    *   Kontrollera att mailet är skickat **TILL** den adress du angav i konfigurationen ("E-postadress att bevaka"). Integrationen filtrerar stenhårt på detta.
    *   Kontrollera att mailet **INTE** har etiketten `AI-HANTERAD` i Gmail. Ta bort etiketten manuellt om du vill att mailet ska läsas igen.
*   **Google Gemini Error 503?**
    *   Detta betyder att AI-modellen är överbelastad. Integrationen har inbyggd "retry"-logik och försöker igen automatiskt efter en stund.
*   **Kan inte autentisera?**
    *   Kontrollera att du lagt till rätt Redirect URI i Google Cloud Console.
    *   Se till att du har "Application Credentials" inlagda korrekt i HA.

---

## 📄 Licens
Open Source för personligt bruk.
