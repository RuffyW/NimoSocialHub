# Prüfprotokoll · 27.09.2026

## Lokal bestätigt

`python -m pytest -q`: **12 bestanden**. Eigenes temporäres Datenverzeichnis; kein Zugriff auf echte Instagram-Daten und keine Änderung an Pi-Diensten.

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
12. Verschlüsselte Wiederherstellung eines frisch initialisierten Hubs ohne Medien. Fehlende leere Medienverzeichnisse werden korrekt angelegt.

Testumgebung: Windows, Python 3.14.2. Es gibt einen Deprecation-Hinweis des Starlette-Testclients zur zukünftigen httpx2-Nutzung; keine fehlgeschlagenen Tests. Produktion nutzt Python 3.13.15. Vollständige Laufzeitauflösung als ARM64/Python-3.13-Wheels erfolgreich; 30 Pakete festgeschrieben.

## Raspberry Pi 5 bestätigt

Ubuntu 26.04.1 ARM64; Docker-Snap mit `docker.compose` v5.5.1. Bestehende Container: Orivan Engine, Prometheus, Grafana. Die Hub-Container nutzen ein eigenes Compose-Projekt. Das gebaute Image ist ARM64, FFprobe 5.1.9 und age 1.1.1 sind verfügbar. Webprozess gesund, Worker und Proxy laufen. Port 8443 ist nur an `192.168.178.91` gebunden. TLS mit der eigenen lokalen CA geprüft; nach Ergänzung von `default_sni` funktioniert die IP-Adresse auch für Clients ohne TLS-SNI. Der PC hat die Login-Seite mit explizit geprüfter CA erreicht; ohne Anmeldung gab es 303, mit Anmeldung Dashboard und Einstellungen 200.

Eine verschlüsselte Vollsicherung wurde vom Pi auf den PC geladen und dort mit dem privaten age-Schlüssel erfolgreich wiederhergestellt. SQLite-Integrität `ok`, Sitzungen nach Restore null. In den ersten kurzen Stichproben lagen Proxy/Web/Worker bei etwa 12/64/44 MiB; das ist kein Lasttest. Die drei vorher vorhandenen Container liefen nach dem Hub-Start weiter.

Chrome: reale Anmeldung, Entwurf speichern, mobile Ansicht bei 390 × 844 (375 CSS-Pixel Inhaltsbreite wegen Scrollbar), Aufgabe anlegen und per HTMX erledigen. Kein horizontaler Seitenüberlauf im geprüften Formular; keine Browserfehler im geprüften Ablauf. Lokale Fonts und Original-Maskottchen sichtbar. Testdaten liegen ausschließlich im ignorierten `test-results/preview`.

Der Browsercheck fand einen tatsächlichen Konflikt zwischen `Referrer-Policy: no-referrer` und der Origin-Prüfung von POST-Formularen. `same-origin` erhält notwendige Formularherkunft und unterdrückt Referrer zu fremden Seiten. Außerdem wurden mobile Kopfzeilen und die Scrollnavigation angepasst.

## Noch nicht bestätigt

- CPU/RAM und Verhalten großer Videouploads auf ARM64/microSD.
- Video-Poster mit realer Videodatei und Gerätekompatibilität.
- Caddy-CA-Vertrauen im PC-Browser und Smartphone.
- Reale Meta-App-Berechtigungen, Formatmetriken und Tokenrefresh von @meinnimo.

Diese Punkte sind Teil der weiteren Betriebsabnahme in BETRIEB.md.
