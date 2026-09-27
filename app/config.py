import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("NIMO_DATA", ROOT / "runtime")).resolve()
DB = DATA / "data" / "hub.sqlite3"
MEDIA = DATA / "media"
SECRETS = DATA / "secrets"
BACKUPS = DATA / "backups"
ORIGIN = os.getenv("NIMO_ORIGIN", "https://192.168.178.91:8443").rstrip("/")
DEV = os.getenv("NIMO_DEV", "0") == "1"
QUOTA = int(os.getenv("NIMO_MEDIA_QUOTA", str(10 * 1024**3)))
RESERVE = int(os.getenv("NIMO_FREE_RESERVE", str(15 * 1024**3)))
IMAGE_LIMIT = 50 * 1024**2
VIDEO_LIMIT = 500 * 1024**2
API_VERSION = "v26.0"

def prepare():
    for path in (DB.parent, MEDIA / "originals", MEDIA / "previews", MEDIA / "tmp", SECRETS, BACKUPS):
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            path.chmod(0o700)
    # Multipart spooling must use disk, not the container's RAM-backed /tmp.
    import tempfile
    tempfile.tempdir = str(MEDIA / "tmp")
