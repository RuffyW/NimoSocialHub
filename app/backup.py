import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from contextlib import closing
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import config, __version__
from .db import engine, write_lock, transaction
from .models import Media, Setting

def db_copy(destination):
    with closing(sqlite3.connect(config.DB)) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Datenbanksicherung ist nicht konsistent.")

def daily():
    destination = config.BACKUPS / f"database-{time.strftime('%Y%m%d', time.gmtime())}.sqlite3"
    with write_lock():
        db_copy(destination)
    for old in sorted(config.BACKUPS.glob("database-*.sqlite3"))[:-14]:
        old.unlink()
    with transaction() as session:
        session.merge(Setting(key="last_db_backup", value=str(time.time())))

def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()

def snapshot(destination):
    """Consistent metadata and immutable originals; no preview files needed."""
    destination.mkdir(parents=True, exist_ok=True)
    with write_lock(), Session(engine) as session:
        (destination / "data").mkdir()
        (destination / "media" / "originals").mkdir(parents=True)
        (destination / "secrets").mkdir()
        db_copy(destination / "data" / "hub.sqlite3")
        shutil.copy2(config.SECRETS / "vault.key", destination / "secrets" / "vault.key")
        for media in session.scalars(select(Media)):
            src, dst = config.MEDIA / media.path, destination / "media" / media.path
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
        (destination / "config.json").write_text(json.dumps({"version":__version__, "origin":config.ORIGIN, "quota":config.QUOTA, "reserve":config.RESERVE}), encoding="utf-8")
    files = {str(path.relative_to(destination)).replace("\\", "/"):checksum(path) for path in destination.rglob("*") if path.is_file()}
    (destination / "manifest.json").write_text(json.dumps({"version":__version__, "created":time.time(), "files":files}, indent=2), encoding="utf-8")

def full():
    if not shutil.which("age"):
        raise ValueError("Für verschlüsselte Vollsicherungen muss age installiert sein.")
    with Session(engine) as session:
        setting = session.get(Setting, "backup_recipient")
        recipient = setting.value if setting else ""
        used = sum(session.scalars(select(Media.size)))
    if not recipient.startswith("age1"):
        raise ValueError("Bitte zuerst den öffentlichen age-Empfänger in Einstellungen hinterlegen.")
    if shutil.disk_usage(config.DATA).free < used + config.RESERVE:
        raise ValueError("Nicht genügend Speicher für eine Vollsicherung zusätzlich zur Reserve.")
    filename = f"nimo-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{os.urandom(4).hex()}.tar.age"
    target = config.BACKUPS / filename
    temporary = target.with_suffix(".partial")
    try:
        with tempfile.TemporaryDirectory(dir=config.BACKUPS, prefix="snapshot-") as work:
            folder = Path(work) / "snapshot"
            snapshot(folder)
            with temporary.open("xb") as out:
                process = subprocess.Popen(["age", "-r", recipient], stdin=subprocess.PIPE, stdout=out, stderr=subprocess.DEVNULL)
                try:
                    with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
                        for path in folder.rglob("*"):
                            if path.is_file():
                                archive.add(path, arcname=str(path.relative_to(folder)), recursive=False)
                    process.stdin.close()
                    if process.wait(timeout=3600) != 0:
                        raise ValueError("Verschlüsselung der Sicherung fehlgeschlagen.")
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
        temporary.replace(target)
        for old in sorted(config.BACKUPS.glob("nimo-*.tar.age"))[:-2]:
            old.unlink()
        with transaction() as session:
            session.merge(Setting(key="last_full_backup", value=str(time.time())))
        return filename
    finally:
        temporary.unlink(missing_ok=True)

def restore(archive, identity, destination):
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Wiederherstellung nur in ein leeres Zielverzeichnis.")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as work:
        unpacked = Path(work) / "restore"
        unpacked.mkdir()
        plain = Path(work) / "snapshot.tar"
        with plain.open("wb") as out:
            subprocess.run(["age", "-d", "-i", str(identity), str(archive)], stdout=out, stderr=subprocess.DEVNULL, check=True)
        with tarfile.open(plain) as source:
            for member in source.getmembers():
                if not member.isfile() or member.name.startswith(("/", "\\")) or ".." in Path(member.name).parts or ":" in member.name:
                    raise ValueError("Ungültiger Pfad im Sicherungsarchiv.")
            source.extractall(unpacked, filter="data")
        manifest = json.loads((unpacked / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            path = (unpacked / name).resolve()
            if not path.is_relative_to(unpacked.resolve()) or checksum(path) != expected:
                raise ValueError("Prüfsumme der Sicherung stimmt nicht.")
        actual = {p.relative_to(unpacked).as_posix() for p in unpacked.rglob("*") if p.is_file()} - {"manifest.json"}
        if actual != set(manifest["files"]):
            raise ValueError("Dateibestand passt nicht zum Sicherungsmanifest.")
        with closing(sqlite3.connect(unpacked / "data" / "hub.sqlite3")) as database:
            if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Beschädigte Datenbank.")
            if database.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Beschädigte Datenbankbeziehungen.")
            database.execute("DELETE FROM sessions")
            database.execute("UPDATE jobs SET status='pending', lease_until=NULL, owner=NULL WHERE status='running'")
            database.execute("UPDATE media SET preview=NULL, preview_status='pending'")
            database.commit()
        for name in ("data", "secrets"):
            shutil.copytree(unpacked / name, destination / name)
        if (unpacked / "media").exists():
            shutil.copytree(unpacked / "media", destination / "media")
        for name in ("originals", "previews", "tmp"):
            (destination / "media" / name).mkdir(parents=True, exist_ok=True)
        shutil.copy2(unpacked / "config.json", destination / "config.json")
        if os.name != "nt":
            for directory in [destination, *[p for p in destination.rglob("*") if p.is_dir()]]:
                directory.chmod(0o700)
            (destination / "secrets" / "vault.key").chmod(0o600)
