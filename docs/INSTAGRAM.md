# Instagram einrichten

Manueller Betrieb ist sofort möglich. API-Funktionen werden erst nach einer echten Verbindung als funktionsfähig für @meinnimo betrachtet.

1. Eigene Meta-App mit Instagram API / Instagram Login anlegen. Professionelles Konto @meinnimo der App als eigenes Test-/verwaltetes Konto zuordnen, Einladung bestätigen.
2. `instagram_business_basic` und `instagram_business_manage_insights` bereitstellen. Kein Publishing-Scope erforderlich.
3. Im offiziellen Dashboard ein langlebiges Token erstellen. Token nicht in Chat, Shell-Historie oder Git einfügen.
4. Im privaten HTTPS-Hub unter Einstellungen Token sowie tatsächliches Ausstellungs-/Ablaufdatum eintragen. Der Hub prüft Handle, Konto-ID, Medienzugriff und Reichweitenzugriff und speichert das Token verschlüsselt.
5. „Jetzt synchronisieren“ starten. Erste Beitragsseite, weitere Pagination und verfügbare Einzelkennzahlen kontrollieren. Fehler und fehlende Berechtigungen sichtbar lassen; fehlende Werte sind nicht null.

Instagram Login setzt keine Facebook-Seite voraus. Standard Access ist für eigene zugeordnete Konten vorgesehen. Bei Zugang für fremde Konten können Advanced Access, App Review und Verifizierung nötig werden. Konkrete Anforderungen im Meta-Dashboard prüfen.

Der Adapter verwendet API v26.0, `graph.instagram.com`, offizielle Leseendpunkte und Tokenrefresh. Keine Scraping-Fallbacks, kein öffentlicher Callback im gewählten manuellen Einrichtungsweg. Langlebige Tokens werden täglich geprüft und ab Tag 30 verlängert; abgelaufene/widerrufene Tokens verlangen eine erneute Verbindung.

Eigene Feed-Bilder, Karussells, Videos und Reels: ID, Caption, Zeitpunkt, Format, Link und verfügbare CDN-Vorschau. Stories bleiben manuell. Beitragsmetriken einzeln je Format abfragen: Views, Reichweite, Likes, Kommentare, Speicherungen, Shares, Interaktionen; Reels zusätzlich Wiedergabedauern. Konto: verfügbare Tagesmetriken, aktueller Followerbestand und Zu-/Abgänge über `follow_type`-Aufschlüsselung. Jede Kennzahl kann fehlen oder für dieses Konto nicht unterstützt sein. Abrufbarkeit ist keine Garantie.

Postliste alle sechs Stunden; Kennzahlen bis 30 Tage alle sechs Stunden, bis 90 Tage täglich, danach wöchentlich bis zur dokumentierten Zweijahresgrenze. Kontowerte täglich für die letzten sieben abgeschlossenen UTC-Tage erneut erfassen; Zeitraum nicht zu Berliner Kalendertagen umetikettieren. Es gibt keinen automatischen kompletten 90-Tage-Konto-Rückimport. Das verfügbare 90-Tage-Fenster der Plattform und mögliche engere Grenzen bleiben unabhängig davon bestehen.

Bei Wiederholung desselben Auftrags keine doppelten Messungen. Spätere Aufträge speichern neue Beobachtungen, auch bei korrigierten Tageswerten. Historische Gesamtwerte können frühere 7-Tage-Leistung nicht rekonstruieren. Metriken können bis zu 48 Stunden nachlaufen; bestimmte Kontowerte fehlen unter Mindestgrößen. Karussell-Kinder erhalten keine eigenen erfundenen Insights. Reichweiten nicht summieren.

Vorschau-URLs werden nur für offizielle Instagram-/Facebook-CDN-Hosts verwendet. Sie können ablaufen und werden beim nächsten Beitragsabruf erneuert. API-Medien werden nicht automatisch als Originale heruntergeladen. Eigene hochgeladene Originale bleiben lokal erhalten.

Späteres Publishing benötigt zusätzliche Freigabe/Berechtigung, Formatprüfungen, Mediencontainer und eine getrennt abgesicherte Medienbereitstellung. TikTok ist zunächst Planung/Export und gegebenenfalls Display API; interne Direct-Post-Werkzeuge für eigene Konten werden nicht als zugesicherte Möglichkeit behandelt.

Offizielle Quellen, während der Planung geprüft:

- [Instagram-Plattform](https://developers.facebook.com/documentation/instagram-platform)
- [App einrichten](https://developers.facebook.com/documentation/instagram-platform/create-an-instagram-app)
- [Berechtigungen und Grenzen](https://developers.facebook.com/documentation/instagram-platform/insights)
- [Medien-Insights](https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media/insights)
- [Konto-Insights](https://developers.facebook.com/documentation/instagram-platform/api-reference/instagram-user/insights)
- [Tokenverwaltung](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Content Publishing](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
- [TikTok Display API](https://developers.tiktok.com/doc/display-api-overview/)
- [TikTok Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)
