# Architektur

FastAPI/Jinja2/HTMX liefert serverseitige Seiten. Ein Betreiber, ein Konto, deutsche Oberfläche. SQLite mit WAL, Fremdschlüsseln, FULL-Synchronisation und Dateischreibsperre liegt auf lokalem ext4. SQLAlchemy strukturiert Datenzugriffe; Alembic verwaltet die Schema-Version. Migration 0001 enthält eine eingefrorene Schema-Kopie, damit spätere Modelländerungen keine alte Migration verändern.

Web und Worker nutzen dasselbe Image und Datenmodell. Der Worker arbeitet sequenziell, wird durch eine eigene Prozesssperre geschützt und verwaltet persistente Aufträge in SQLite. Abgelaufene Auftrags-Leases werden nach Neustart übernommen. Netzwerkfehler werden begrenzt mit wachsendem Abstand wiederholt; Rate Limits beachten Retry-After. Dauerhafte Berechtigungsfehler erzeugen Handlungsbedarf. Weder Redis noch Celery erforderlich.

## Daten

`Account` hält Plattformidentität und verschlüsselten Zugang. `Idea` enthält Thema, Zielgruppe, Notizen und Wiederverwendungsherkunft. `Draft` hält Status, Format, Caption und Planzeitpunkt. `Publication` hält tatsächlichen Zeitpunkt, Link und optionale Zuordnung zu genau einem Entwurf. Externe IDs sind Zeichenketten; Konto/ID und Konto/Permalink sind eindeutig. Exakter Link kann eine manuelle Veröffentlichung mit API-Daten versöhnen; Captions werden niemals als Identität verwendet.

`Media` hält unveränderliches Original, SHA256, Metadaten, Tags und Vorschauzustand. `Attachment` ordnet Medien mehrfach und sortiert zu. `Task` enthält Fälligkeit und Erledigung. `Metric` erklärt Kennzahlen, Einheit und Geltungsbereich. `Observation` speichert Wert oder Fehlgrund, Messzeitpunkt, Zeitraum, Herkunft und API-Version. Wiederholungen desselben Auftrags sind idempotent; spätere Beobachtungen bleiben erhalten.

`Job` enthält Fälligkeit, Versuchszahl, Besitzer und Lease. `Setting` speichert Betriebsdaten. `LoginSession` speichert nur gehashte Sitzungstokens, `LoginAttempt` begrenzt Fehlversuche. Die Datenbank ist nur über die Anwendung zugänglich.

UTC-Zeitpunkte als Unixsekunden; Europe/Berlin für Darstellung und Wochen. Nicht existierende Ortszeiten werden abgewiesen, doppelte verlangen explizite Auswahl. Altersvergleich: ±6 Stunden bei 24 Stunden, ±12 Stunden bei 7/30 Tagen. Quellen und Formate getrennt. Keine Rekonstruktion historischer Messpunkte und keine Trendprognose.

## Grenzen und Erweiterungen

Originalbudgets und Reserve gelten unabhängig von Containergrenzen. Multipart-Dateien werden auf persistentem Datenträger gespult; kein 500-MiB-Upload in RAM. Dateityp wird geprüft, keine aktiven SVG-/HTML-Vorschauen. FFmpeg arbeitet mit lokalem Dateiprotokoll und begrenzter Laufzeit. Nicht abspielbare Videos erhalten Originaldownload und gegebenenfalls Poster.

Die aktuelle Medienbibliothek behält Originale dauerhaft; sie hat keine Löschfunktion. Beim Budgetlimit Bestand extern archivieren und Speicherentscheidung treffen, keine automatische Bereinigung von Originalen. Vorschauen können neu erstellt werden.

Plattformzugriff ist in `instagram.py` vom Ablauf in `sync.py` getrennt; neue Adapter können später ergänzt werden. TikTok, Creator und Publishing benötigen erst dann zusätzliche Routen und Datenmigrationen. Das jetzige UI bleibt bewusst auf @meinnimo begrenzt. Optionale KI würde nur Vorschläge liefern und ist keine Laufzeitabhängigkeit.

Caddy terminiert privates HTTPS. Keine öffentlichen Routerports. Fernzugriff separat per VPN. Zugangsdaten liegen verschlüsselt in SQLite; Schlüssel und Datenverzeichnis erhalten restriktive Rechte. Die Verschlüsselung schützt nicht gegen einen vollständig kompromittierten Pi mit Zugriff auf Schlüssel und Datenbank.

Kosten: keine kostenpflichtige API als Voraussetzung, kein Cloud-Abo. Strom, lokaler Speicher, unabhängige Backups und gelegentliche Wartung bleiben erforderlich.
