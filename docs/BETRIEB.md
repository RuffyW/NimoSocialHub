# Installation und Betrieb

## 1. Bestand prüfen

Quellcode in ein **neues** Verzeichnis `/home/raphi/nimo-social-hub` übertragen, ohne `.venv`, `.tools`, `runtime`, `.env`, `test-results` oder Caches. Nicht über ein vorhandenes anderes Projekt kopieren. Das Skript `scripts/pi-preflight.sh` liest ausschließlich den Bestand. Auf dem Pi:

```sh
cd /home/raphi/nimo-social-hub
sh scripts/pi-preflight.sh
```

Fehlschlag von `sudo -n` bedeutet fehlende Berechtigung, nicht fehlende Container. Bei Bedarf die einzelnen Lesebefehle interaktiv mit `sudo` ausführen. Container, Images und Ports protokollieren; insbesondere 8443 muss frei sein. DHCP-Reservierung für `192.168.178.91` im Router prüfen. Keine Portfreigabe einrichten.

Für die folgenden Beispiele eine Funktion setzen, passend zum **erfolgreich geprüften** Aufruf:

```sh
# Docker-Snap, wenn docker.compose vorhanden ist:
dc() { sudo docker.compose "$@"; }
# Alternativ ausschließlich bei funktionierendem Compose-Plugin:
# dc() { sudo docker compose "$@"; }
```

Fehlt Compose in beiden Varianten: Installation hier unterbrechen und separat klären. Docker weder ersetzen noch neu starten; keine Änderungen am Docker-Datenverzeichnis und keine pauschale Freigabe des Docker-Sockets.

## 2. Isoliert vorbereiten und initialisieren

```sh
cp .env.example .env
chmod 600 .env
# Nur dieses neue Laufzeitverzeichnis, kein vorhandenes Projekt:
sudo install -d -m 700 -o 10001 -g 10001 /home/raphi/nimo-social-hub/runtime
dc config --quiet
dc build web
dc run --rm --no-deps web python -m app.cli init
```

`init` migriert und fragt das Passwort verdeckt ab (mindestens 12 Zeichen). Es wird weder in `.env` noch in der Shell-Historie gespeichert. Benutzer 10001 braucht Zugriff auf den Laufzeit-Mount. Bei Snap-/AppArmor-Zugriffsfehlern Pfad und `snap connections docker` prüfen, nicht die Sicherheitsmechanismen global abschalten.

```sh
dc up -d web worker proxy
dc ps
dc logs --tail=60 web worker proxy
```

Nur der Proxy veröffentlicht einen Port, gebunden an die konfigurierte LAN-IP. Web und Worker bleiben im eigenen Docker-Netz. RAM-Grenzen: 512/768/128 MiB; eine Medienaufgabe gleichzeitig. Starten die Dienste nicht, nur dieses Compose-Projekt stoppen: `dc stop`. Kein `docker system prune`, kein globaler Neustart.

## 3. HTTPS auf PC und Smartphone

Caddy erzeugt eine eigene lokale CA. Öffentliches Root-Zertifikat sicher vom Pi kopieren (niemals `root.key`):

```sh
dc cp proxy:/data/caddy/pki/authorities/local/root.crt ./nimo-hub-root.crt
openssl x509 -in nimo-hub-root.crt -noout -fingerprint -sha256
```

Zertifikat samt Fingerabdruck über den authentifizierten SSH-Weg beziehen. Windows: Zertifikat für den aktuellen Benutzer in „Vertrauenswürdige Stammzertifizierungsstellen“ importieren. iOS: Profil installieren und unter Zertifikatsvertrauenseinstellungen das Root-Vertrauen aktivieren. Android: CA-Zertifikat in den Sicherheitseinstellungen installieren; Browserunterstützung auf dem konkreten Gerät prüfen. Ein CA-Import ist eine bewusste Vertrauensentscheidung des Betreibers.

Danach `https://192.168.178.91:8443` öffnen. Keine Browserwarnung einfach wegklicken. Bei anderer IP `.env` anpassen; `NIMO_ORIGIN` wird aus IP und Port gebildet. Der Hub erwartet genau diesen Ursprung für Formulare.

## 4. Backups einrichten

Auf dem **PC** mit offiziellem [age](https://github.com/FiloSottile/age/releases):

```powershell
age-keygen -o nimo-backup-identity.txt
age-keygen -y nimo-backup-identity.txt
```

Den angezeigten öffentlichen `age1…`-Empfänger im Hub hinterlegen. Privaten Schlüssel auf dem PC und an einem unabhängigen sicheren Ort aufbewahren. Er gehört nicht auf den Pi. Der öffentliche Empfänger genügt dort zum Verschlüsseln.

- Worker: täglich SQLite-Onlinebackup, 14 Tagesstände.
- Worker: wöchentlich Vollsicherung, zwei lokale Pakete; zusätzlich über Einstellungen auslösbar.
- Wöchentlich das aktuelle `.tar.age` herunterladen; vier Wochenstände auf dem PC behalten.
- Nach Prüfung der externen Ablage diese im Hub bestätigen. Der Hub prüft nicht selbst den PC.
- Bei Ausfall der gesamten microSD können bis zu sieben Tage verloren gehen.

Vollsicherung umfasst SQLite, Originale, Token-Schlüssel, Versions-/Konfigurationsangaben und SHA256-Manifest. Die kurze Snapshot-Phase sperrt Schreibzugriffe. Medien werden über Hardlinks festgehalten und bleiben unverändert; die längere Verschlüsselung läuft danach. Die aktive Datenbank wird niemals ungeprüft kopiert. Backups und Originale werden nicht in Git eingecheckt.

Auch die **Anwendungsversion** auf dem PC aufbewahren: Release-Quellcode und nach erfolgreichem Pi-Build z. B. `sudo docker save nimo-social-hub:0.1.0 > nimo-social-hub-0.1.0-image.tar`. Das Image enthält keine Laufzeitdaten. So hängen Wiederherstellungen nicht von später veränderten Paketquellen ab.

## 5. Wiederherstellung tatsächlich durchführen

Die folgende Variante entschlüsselt auf dem PC; der private age-Schlüssel bleibt dort. In der passenden gesicherten Quellcodeversion mit installierten Python-Abhängigkeiten und age:

```powershell
.\.venv\Scripts\python -m app.cli restore C:\Backups\nimo-DATUM.tar.age --identity C:\Backups\nimo-backup-identity.txt --destination C:\Backups\nimo-wiederhergestellt
```

Das Ziel muss leer sein. Der Befehl prüft Pfade, vollständiges Manifest, Prüfsummen, SQLite-Integrität und Fremdschlüssel. Sitzungen werden entfernt; Vorschauen gelten als neu zu erzeugen. Fehlschläge werden nicht als erfolgreiche Wiederherstellung gemeldet.

Den wiederhergestellten Bestand **vertraulich** in ein neues Pi-Verzeichnis übertragen, z. B. `/home/raphi/nimo-social-hub-restore/runtime`. Dieses enthält Klartextdaten und den Token-Schlüssel. Zugriffsrechte nur dort setzen:

```sh
sudo chown -R 10001:10001 /home/raphi/nimo-social-hub-restore/runtime
sudo chmod -R go-rwx /home/raphi/nimo-social-hub-restore/runtime
```

Daneben den gesicherten Quellcode bereitstellen und dessen `.env` auf den neuen Datenpfad setzen. Falls das gesicherte Image noch fehlt, mit `sudo docker load -i nimo-social-hub-0.1.0-image.tar` laden. Für einen parallelen Test `NIMO_PORT=8444` wählen und zuvor prüfen. Compose mit **anderem** Namen ausführen:

```sh
dc -p nimo-social-hub-restore up -d web proxy
```

Zunächst **kein Worker**. Weil Caddys private CA nicht Teil des Anwendungspakets ist, erzeugt die Testinstanz eine neue CA; deren Zertifikat wie oben gesondert prüfen. `config.json` dokumentiert ursprüngliche Origin, Quote und Reserve; diese beim Wiederaufbau kontrollieren. Übernahme der Standardwerte nicht blind voraussetzen.

Mit bestehendem Betreiberpasswort anmelden. Beiträge, Zuordnungen, Messwerte und Originaldownloads stichprobenartig prüfen. Falls die Verbindung erst manuell kontrolliert werden soll: im Hub trennen. Dann:

```sh
dc -p nimo-social-hub-restore run --rm --no-deps web python -m app.cli rebuild-previews
dc -p nimo-social-hub-restore up -d worker
```

Erst nach erfolgreicher Prüfung regulären Zugriff umstellen; nie zwei Worker auf denselben Datenpfad ansetzen. Die alte Instanz und Sicherung bis zur bestätigten Abnahme behalten.

## 6. Updates und Rückweg

Vor Update Vollsicherung erstellen und auf PC prüfen. Alte Image-Version sichern, neue Version separat bauen. Nur den Hub anhalten, Migration mit neuer Anwendung explizit durchführen und anschließend starten:

```sh
dc stop web worker
dc run --rm --no-deps web python -m app.cli migrate
dc up -d web worker
```

Bei fehlgeschlagener Migration neue Version nicht starten. Alte Anwendung mit einem **passenden wiederhergestellten Backup** verwenden; keine beliebige ältere Anwendung auf eine neuere Datenbank richten. Keine unbeaufsichtigten Auto-Updates.

## 7. Betriebsabnahme auf dem Pi

Anmeldung am PC und Smartphone, Bild und kurzes eigenes Video hochladen, Poster und Originaldownload prüfen, eine manuelle Veröffentlichung samt Messwert erfassen. Worker nur im eigenen Projekt neu starten und ausstehende Aufträge prüfen. `sudo docker stats --no-stream` vor/während/nach Upload protokollieren. 10-GiB-Budget, 15-GiB-Reserve und Speichermeldung prüfen; keine echten Datenträger absichtlich füllen.

Abschließend `docker ps` und die relevanten bestehenden Dienste mit dem Preflight vergleichen. Ferner Anmeldung, Kennzahlen und Medien in einer getrennt wiederhergestellten Instanz prüfen. Erst diese Abnahme bestätigt den Pi-Betrieb.

Logs: `dc logs --tail=100 web worker`; Rotation 3 × 5 MiB je Dienst. Die Anwendung protokolliert weder Captions noch Tokens. Einstellungen zeigen Worker-Lebenszeichen, Aufträge, letzte Synchronisation und Sicherung. Bei „Erneute Anmeldung nötig“ Token neu verbinden; bei Speicherwarnung keine Uploads erzwingen. Medien werden in V1 bewusst nicht automatisch gelöscht. Eine SSD und automatisiertes externes Backup sind spätere Betriebsverbesserungen, keine Voraussetzung.
