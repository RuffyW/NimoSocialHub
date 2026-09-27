# Nimo Social Hub

Privates, deutschsprachiges Marketingwerkzeug für einen Betreiber. Planung, Medien, Veröffentlichungen und Auswertung funktionieren ohne KI und ohne Plattformkonto. Ein Termin veröffentlicht nichts.

## Enthalten

- Dashboard, Kalender/Liste, Themen, wiederverwendbare Ideen, Aufgaben.
- Originalmedien, Tags, Zuordnung und Reihenfolge; Bildvorschauen und FFmpeg-Videoposter.
- Manuelle Veröffentlichungen und Messwerte mit Herkunft, Bezugszeitraum und Fehlgründen.
- Statistikverlauf, Wochenübersicht und Altersvergleiche nach 1/7/30 Tagen.
- Zuschaltbarer lesender Instagram-Adapter mit Pagination, Wiederholungen, Tokenverlängerung und Fehlerzuständen.
- Betreiberanmeldung, CSRF, verschlüsselte Tokens, SQLite-Migrationen, tägliche Datenbank- und wöchentliche verschlüsselte Vollsicherungen.
- Eigenes Compose-Projekt mit Web, Worker und Caddy; keine Änderungen an anderen Diensten.

Nicht enthalten: automatische Veröffentlichung, TikTok, Creator-Verwaltung, Nachrichtenversand, KI, Videotranscoding oder Vorlagengenerator.

## Aktueller Prüfstand

Die Anwendung wurde lokal unter Windows/Python 3.14 getestet. Die Produktion verwendet Python 3.13. ARM64-Wheels sämtlicher Laufzeitabhängigkeiten wurden erfolgreich aufgelöst und heruntergeladen. Die offiziellen Python-/Caddy-Imagekataloge führen ARM64 auf. Das ersetzt keinen ARM64-Containerlauf.

**Noch ausstehend:** Docker-/Snap-/Portprüfung und Containerstart auf dem Pi, echte Instagram-Abrufe mit @meinnimo, FFmpeg-Videoprüfung im Produktionsimage sowie Lastmessung und Zertifikatsvertrauen auf den tatsächlichen Endgeräten. Es wurden keine Pi-Dienste geändert. Der SSH-Zugang war mangels akzeptierter Anmeldedaten nicht möglich. Keine Kennzahlen aus dem realen Konto wurden erfunden.

[Installation, Betrieb und Wiederherstellung](docs/BETRIEB.md) · [Instagram-Einrichtung und Grenzen](docs/INSTAGRAM.md) · [Architektur](docs/ARCHITEKTUR.md) · [Prüfprotokoll](docs/PRUEFUNG.md)

## Lokale Entwicklung

Python 3.13 oder 3.14, FFmpeg/FFprobe und age bereitstellen. Unter Windows ist für den verschlüsselten Integrationstest alternativ `.tools/age/age.exe` und `age-keygen.exe` vorgesehen. Diese Testwerkzeuge werden nicht ausgeliefert.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
$env:NIMO_DATA = Join-Path $PWD 'runtime'
$env:NIMO_DEV = '1'
$env:NIMO_ORIGIN = 'http://127.0.0.1:8973'
.\.venv\Scripts\python -m app.cli init
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8973 --no-access-log
```

In einem zweiten Terminal mit denselben Umgebungsvariablen: `python -m app.worker` mit dem Python der virtuellen Umgebung. `NIMO_DEV=1` ist ausschließlich für lokalen HTTP-Zugriff vorgesehen; es wird in Compose nicht gesetzt. Kein Standardpasswort: `init` fragt das Betreiberpasswort verdeckt ab.

Tests: `.\.venv\Scripts\python -m pytest -q`. Sie verwenden ein eigenes temporäres Datenverzeichnis und simulierte API-Antworten. Die Vollsicherungsprüfung benötigt echtes age und schlägt bei fehlendem Werkzeug fehl.

## Gestaltung und Abhängigkeiten

Original-Maskottchen und lokal eingebundene Schriften aus `../repo-work/landing`, gemäß `../repo-work/marketing/README.md`. Keine Ersatzfigur. Schriftlizenzen liegen in `app/static/OFL-*.txt`.

HTMX 2.0.4 wird lokal ausgeliefert, Quelle: https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js, SHA256 `e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447`. Lizenz: Zero-Clause BSD, https://github.com/bigskysoftware/htmx/blob/v2.0.4/LICENSE.

`requirements.txt` enthält die direkten Abhängigkeiten, `requirements-lock.txt` den vollständigen für Linux ARM64/Python 3.13 aufgelösten Stand. Docker nutzt den Lock-Stand. Image-Tags sind festgelegt; Debian-Sicherheitspakete werden beim Build aktualisiert. Für identische Wiederherstellung das gebaute Image zusammen mit dem Release aufbewahren.
