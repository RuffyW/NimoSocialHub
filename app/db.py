from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session
import portalocker
from . import config

class Base(DeclarativeBase):
    pass

config.prepare()
engine = create_engine(f"sqlite:///{config.DB.as_posix()}", connect_args={"check_same_thread": False, "timeout": 30})

@event.listens_for(engine, "connect")
def pragmas(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA busy_timeout=30000")

@contextmanager
def write_lock():
    # Shared by web, worker and backup: no half-uploaded backup snapshots.
    with portalocker.Lock(str(config.DATA / "write.lock"), timeout=60):
        yield

@contextmanager
def transaction():
    with write_lock(), Session(engine, expire_on_commit=False) as session:
        with session.begin():
            yield session
