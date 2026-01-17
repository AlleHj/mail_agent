# 🛠️ Utveckling & Testning

Denna guide hjälper dig att sätta upp utvecklingsmiljön, länka integrationen korrekt i VS Code Dev Container och köra testfall.

## 1. Sätt upp utvecklingsmiljön

Vi följer Home Assistants officiella struktur för utveckling. För instruktioner om hur du sätter upp en Dev Container eller lokal miljö, se:
🔗 [Home Assistant Development Environment](https://developers.home-assistant.io/docs/development_environment/)

---

## 2. Installera testverktyg

För att kunna köra testerna krävs biblioteket `pytest-homeassistant-custom-component`.
Kör följande i terminalen:

```bash
pip install pytest-homeassistant-custom-component
```

Om filen `requirements_test.txt` finns i roten, kör även:

```bash
pip install -r requirements_test.txt
```

---

## 3. Länka integrationen (Symlink)

När du kör i en Dev Container (t.ex. `homeassistcore`) måste vi skapa en symbolisk länk så att Core hittar din custom component utan att du behöver kopiera filer manuellt.

**Namn på denna komponent:** `mail_agent`

### Skapa länk

Kör detta kommando för att länka in mappen:

```bash
ln -s /workspaces/homeassistcore/config/mail_agent/custom_components/mail_agent /workspaces/homeassistcore/config/custom_components/
```

### Ta bort länk (Avlänka)

Om du behöver ta bort kopplingen, använd `unlink`. Använd **INTE** `rm` på själva mappen, då det riskerar att radera källkoden.

```bash
unlink /workspaces/homeassistcore/config/custom_components/mail_agent
```

---

## 4. Köra tester med Pytest

Vi använder `pytest` för att verifiera koden. Här är guiden för hur du kör specifika tester och använder flaggor.

### 🎯 Köra specifika tester

| Mål | Kommando |
| :--- | :--- |
| **Kör allt** | `pytest` |
| **Kör en fil** | `pytest tests/test_config_flow.py` |
| **Kör ett specifikt testfall** | `pytest tests/test_config_flow.py::test_flow_init` <br> *(Lägg till `::` följt av funktionens namn)* |
| **Filtrera på ord/namn** | `pytest -k "sensor"` <br> *(Kör alla tester som innehåller ordet "sensor")* |

### 🚩 Flaggor & Parametrar

Här är de mest användbara flaggorna för felsökning:

| Flagga | Funktion | Användning |
| :--- | :--- | :--- |
| `-v` | **Verbose** (Visar testnamn) | Se exakt vilka tester som körs och deras status (PASSED/FAILED). |
| `-s` | **Show output** (Visar `print()`) | Nödvändigt när du debuggar med `print("Värde:", x)`. Utan denna döljs all output. |
| `-k "namn"` | **Keyword** (Filtrerar) | Kör t.ex. bara tester som heter något med "update_failed": `pytest -k "update_failed"` |
| `-x` | **Exit first** (Stanna vid fel) | Stoppar körningen direkt vid första misslyckade testet. Sparar tid när många tester går sönder. |
| `--lf` | **Last failed** (Kör om failade) | Kör enbart de tester som misslyckades vid förra körningen. |
| `--pdb` | **Debugger** (Starta PDB) | Pausar koden och startar en interaktiv debugger i terminalen precis där kraschen sker. |

### Exempel på kombinationer

Kör endast tester som handlar om sensorer, visa utskrifter och stanna vid första felet:

```bash
pytest -v -s -x -k "sensor"
```

---

## 5. Kvalitetskontroll (Linting)

Innan du skapar en Pull Request bör du köra `ruff` för att hitta stilfel och potentiella buggar:

```bash
pip install ruff
ruff check .
```
