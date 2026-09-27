import argparse
import getpass
import json
import os
from pathlib import Path
from sqlalchemy import select
from alembic.config import Config
from alembic import command
from . import config, backup
from .db import transaction
from .models import Account, Setting, LoginSession, Media
from .metrics import seed
from .security import create_key, hasher
from .jobs import enqueue

def migrate():
    command.upgrade(Config(str(config.ROOT / "alembic.ini")), "head")

def initialize(password=None):
    migrate()
    create_key()
    with transaction() as session:
        if not session.get(Account,1):
            session.add(Account(id=1))
        seed(session)
        if not session.get(Setting,"password_hash"):
            password = password or getpass.getpass("Neues Betreiberpasswort (mindestens 12 Zeichen): ")
            if len(password)<12:
                raise ValueError("Mindestens 12 Zeichen erforderlich.")
            session.add(Setting(key="password_hash",value=hasher.hash(password)))

def main():
    parser=argparse.ArgumentParser(description="Nimo Social Hub verwalten")
    commands=parser.add_subparsers(dest="command",required=True)
    for name in ("init","migrate","password","backup-db","backup-full","rebuild-previews"):
        commands.add_parser(name)
    restore=commands.add_parser("restore")
    restore.add_argument("archive",type=Path); restore.add_argument("--identity",type=Path,required=True); restore.add_argument("--destination",type=Path,required=True)
    args=parser.parse_args()
    if args.command=="init":
        initialize()
        print("Hub initialisiert. Jetzt Webprozess und Worker starten.")
    elif args.command=="migrate":
        migrate()
    elif args.command=="password":
        password=getpass.getpass("Neues Passwort (mindestens 12 Zeichen): ")
        if len(password)<12:
            raise ValueError("Mindestens 12 Zeichen erforderlich.")
        with transaction() as session:
            session.merge(Setting(key="password_hash",value=hasher.hash(password)))
            from sqlalchemy import delete
            session.execute(delete(LoginSession))
    elif args.command=="backup-db":
        backup.daily()
        print("Datenbanksicherung erstellt.")
    elif args.command=="backup-full":
        print(backup.full())
    elif args.command=="restore":
        backup.restore(args.archive,args.identity,args.destination)
        print("Wiederhergestellt. Konfiguration prüfen, Webprozess zunächst ohne Worker starten.")
    elif args.command=="rebuild-previews":
        with transaction() as session:
            for media in session.scalars(select(Media)):
                enqueue(session,"preview",f"rebuild:{media.id}:{os.urandom(4).hex()}",{"id":media.id})

if __name__=="__main__":
    main()
