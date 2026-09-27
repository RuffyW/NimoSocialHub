# Prüfprotokoll · 27.09.2026

## Lokal bestätigt

`python -m pytest -q`: **11 bestanden**. Eigenes temporäres Datenverzeichnis; kein Zugriff auf echte Instagram-Daten und keine Änderung an Pi-Diensten.

1. Vollständiger manueller Ablauf mit Bild-Upload, Medienzuordnung, Veröffentlichung, Kennzahl null, Altersvergleich, allen Hauptseiten und Wiederverwendung.
2. Zugangsschutz, CSRF, falscher Dateityp und Upload-Obergrenze.
3. Beide Berliner Zeitumstellungen einschließlich Auswahl der doppelten Uhrzeit.
4. Wiederholter Instagram-Import und Abgleich eines exakten manuell erfassten Links ohne Doppelbeitrag.
5. Konsistenter Snapshot mit SQLite-Integritätsprüfung.
6. Echte age-Verschlüsselung und Wiederherstellung in leeres Ziel; Medienprüfsummen, Schlüssel und entfernte Sitzungen geprüft.
7. Abgelaufene Worker-Lease, Wiederholung und API-Fehler für Rate Limit, ungültiges Token und fehlende Kennzahl.
8. Trennen während Tokenrefresh lässt die Verbindung getrennt.
9. Pagination-Unterbrechung, gespeicherter Cursor, fortgesetzter Abruf und wiederholte Folgeseite.
10. Null versus fehlend sowie ausgeschöpftes Medienbudget.
11. Vorübergehender Refresh-Ausfall bleibt wiederholbar; Token erscheint nicht im HTTP-Client-Protokoll.

Testumgebung: Windows, Python 3.14.2. Es gibt einen Deprecation-Hinweis des Starlette-Testclients zur zukünftigen httpx2-Nutzung; keine fehlgeschlagenen Tests. Produktion nutzt Python 3.13.15. Vollständige Laufzeitauflösung als ARM64/Python-3.13-Wheels erfolgreich; 30 Pakete festgeschrieben.

Chrome: reale Anmeldung, Entwurf speichern, mobile Ansicht bei 390 × 844 (375 CSS-Pixel Inhaltsbreite wegen Scrollbar), Aufgabe anlegen und per HTMX erledigen. Kein horizontaler Seitenüberlauf im geprüften Formular; keine Browserfehler im geprüften Ablauf. Lokale Fonts und Original-Maskottchen sichtbar. Testdaten liegen ausschließlich im ignorierten `test-results/preview`.

Der Browsercheck fand einen tatsächlichen Konflikt zwischen `Referrer-Policy: no-referrer` und der Origin-Prüfung von POST-Formularen. `same-origin` erhält notwendige Formularherkunft und unterdrückt Referrer zu fremden Seiten. Außerdem wurden mobile Kopfzeilen und die Scrollnavigation angepasst.

## Noch nicht bestätigt

- Start und Migration im Docker-Snap auf dem konkreten Pi; keine lokale Docker-Engine verfügbar.
- CPU/RAM und Verhalten großer Videouploads auf ARM64/microSD.
- FFprobe/FFmpeg im Produktionsimage und Gerätekompatibilität der Videovorschau.
- Caddy-CA-Vertrauen am realen PC/Smartphone und Zugriff über die LAN-IP.
- Reale Meta-App-Berechtigungen, Formatmetriken und Tokenrefresh von @meinnimo.

Diese Punkte sind Teil der Betriebsabnahme in BETRIEB.md. Quellcodefertigstellung und lokale Tests sind keine Behauptung einer erfolgreichen Pi-Auslieferung.
