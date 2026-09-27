import hashlib
import secrets
import os
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from . import config

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def vault():
    path = config.SECRETS / "vault.key"
    if not path.exists():
        raise RuntimeError("Schlüssel fehlt. Zuerst den Hub initialisieren.")
    return Fernet(path.read_bytes())

def create_key():
    path = config.SECRETS / "vault.key"
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(Fernet.generate_key())

def nonce():
    return secrets.token_urlsafe(32)
