# Mail Agent för Home Assistant

**Mail Agent** är en intelligent integration för Home Assistant som övervakar din e-post, analyserar innehållet med hjälp av Google Gemini AI och automatiskt agerar på viktig information. Den kan skapa kalenderhändelser, skicka notifieringar och vidarebefordra information via e-post.

## 🌟 Funktioner

*   **Smart E-postövervakning**: Ansluter till din e-post via IMAP och söker efter nya meddelanden.
*   **AI-Analys**: Använder Google Gemini (via `google-genai` SDK) för att förstå innehållet i e-postmeddelanden och bilagor.
*   **Automatisk Kalenderhantering**: Identifierar händelser, tider och platser i dina mail och lägger automatiskt till dem i dina Home Assistant-kalendrar.
*   **Notifieringar**: Skickar notiser till dina mobila enheter via Home Assistants notify-tjänster när en viktig händelse hittas.
*   **SMTP-stöd**: Kan skicka sammanfattande e-postmeddelanden med bilagor direkt via SMTP till konfigurerade mottagare.
*   **Händelsestyrd**: Publicerar händelsen `mail_agent.scanned_document` i Home Assistant, vilket gör det möjligt att skapa kraftfulla automationer baserade på inkommande post.

## 📋 Systemkrav

*   **Home Assistant**: Senaste versionen rekommenderas.
*   **Python-paket**: `google-genai` (installeras automatiskt).
*   **Google Gemini API-nyckel**: Krävs för AI-analysen.
*   **E-postkonto**: Tillgång till IMAP (för läsning) och SMTP (för utskick).

## 🚀 Installation

### Manuell Installation

1.  Ladda ner mappen `mail_agent` från detta repository.
2.  Kopiera mappen till `custom_components` i din Home Assistant-konfigurationsmapp.
3.  Starta om Home Assistant.

## ⚙️ Konfiguration

Integrationen konfigureras helt via användargränssnittet i Home Assistant.

1.  Gå till **Inställningar** > **Enheter & Tjänster**.
2.  Klicka på **Lägg till integration** och sök efter **Mail Agent**.
3.  Följ stegen för att ansluta till din e-postserver (IMAP).

### Inställningar (Options)

Efter installationen kan du klicka på **Konfigurera** på integrationen för att justera inställningar:

*   **Sökintervall**: Hur ofta (i sekunder) agenten ska leta efter nya mail.
*   **Gemini API**: Din API-nyckel och val av modell (t.ex. `gemini-3-pro-preview`).
*   **Kalendrar**: Välj vilka kalendrar i Home Assistant som ska uppdateras.
*   **Notifieringar**: Välj vilka notify-tjänster (t.ex. mobiltelefoner) som ska få notiser.
*   **E-postmottagare**: Ange e-postadresser som ska få vidarebefordrad information via SMTP.
*   **SMTP-inställningar**: Server och port för utgående e-post.

## 🛠️ Versionhantering

### v0.12.1 (2025-12-15)
*   Uppdaterad SDK-import för Google GenAI.
*   Förbättrad felhantering och loggning.

### v0.12.0 (2025-12-15)
*   Lagt till stöd för direkt SMTP-utskick.
*   Uppdaterat konfigurationsflöde för att inkludera SMTP-inställningar.

### v0.11.1
*   Initial release med grundläggande IMAP-stöd och Gemini-integration.

## 📝 Licens

Detta projekt är licensierat under MIT-licensen.
