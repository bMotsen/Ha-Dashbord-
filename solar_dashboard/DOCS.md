# Solar Dashboard i Home Assistant

Glas-dashboard med solceller, batteri, elpris, VW ID.3, Tuya-enheder og vejr.
Det vises som **Energi** i Home Assistants sidepanel og kan også åbnes direkte på en tablet.

## Konfiguration

Udfyld felterne under fanen **Konfiguration** og tryk **Gem** → **Genstart**.
Felter du lader stå tomme, vises med demo-data.

| Felt | Hvad skal stå der |
|---|---|
| Solplanet dongle IP | Lad feltet stå tomt, så findes donglen automatisk. Ellers donglens IP, fx `192.168.1.50` |
| Batteriets størrelse | fx `10` (kWh) |
| Prisområde | `DK1` (Jylland/Fyn) eller `DK2` (Sjælland/øerne) |
| Netselskab | Dit netselskab. Har du et andet, vælg `andet` (se nedenfor) |
| Elhandlerens tillæg | Tillæg pr. kWh ekskl. moms fra din elregning |
| VW e-mail / kodeord | Samme login som Volkswagen-appen |
| Tuya Access ID / Secret / enheds-ID | Fra dit cloud-projekt på iot.tuya.com |

**Vejret** bruger automatisk den placering, der er sat i Home Assistant (Indstillinger → System → Generelt).

## Tablet i fuld skærm

Åbn `http://<home-assistant-ip>:8765/?kiosk=1` på tabletten og tilføj den til hjemmeskærmen.
Siden kræver ikke login, så brug den kun på dit eget netværk.

## Avancerede indstillinger

Første gang app'en starter, laver den filen `config.yaml` i mappen `addon_configs/…_solar_dashboard` (navnet starter med `local_` eller et kort id).
Du kan redigere den med **File editor**, **Studio Code Server** eller **Samba share**. Her kan du fx:

* skjule, omdøbe og sortere Tuya-enheder
* skrive GLN og tarifkode for et netselskab, der ikke er på listen
* lægge `devices.json` fra `tinytuya wizard`, så enheder kan styres lokalt

Genstart app'en efter ændringer.

## Fejlfinding

Se fanen **Log**. Tryk på *Live/Demo*-feltet nederst på dashboardet for at se, hvilke dele der stadig er demo.
