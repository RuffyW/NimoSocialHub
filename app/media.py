import hashlib
import json
import os
import shutil
import subprocess
import uuid
import warnings
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, func
from . import config
from .models import Media, Job

Image.MAX_IMAGE_PIXELS = 40_000_000

def storage(session):
    used = session.scalar(select(func.coalesce(func.sum(Media.size), 0)))
    return {"used": used, "quota": config.QUOTA, "free": shutil.disk_usage(config.DATA).free,
            "percent": round(used / config.QUOTA * 100, 1), "reserve": config.RESERVE}

def check_space(session, incoming):
    state = storage(session)
    if state["used"] + incoming > config.QUOTA:
        raise ValueError("Das Medienbudget ist ausgeschöpft.")
    if state["free"] - incoming < config.RESERVE:
        raise ValueError("Zu wenig freier Speicher. Die Sicherheitsreserve beträgt 15 GiB.")

def probe(path):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as im:
                fmt, size = im.format, im.size
                im.verify()
        if fmt not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("Erlaubte Bilder: JPEG, PNG und WebP.")
        return {"mime": {"JPEG":"image/jpeg", "PNG":"image/png", "WEBP":"image/webp"}[fmt], "width":size[0], "height":size[1]}
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("Das Bild überschreitet die Grenze von 40 Megapixeln.") from None
    except (UnidentifiedImageError, OSError):
        pass
    if not shutil.which("ffprobe"):
        raise ValueError("Kein lesbares Bild. Für Videos muss FFprobe verfügbar sein.")
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, timeout=30, check=True)
        info = json.loads(result.stdout)
        stream = next(s for s in info["streams"] if s.get("codec_type") == "video")
        fmt = info["format"]["format_name"]
        if "mp4" not in fmt and "webm" not in fmt:
            raise ValueError("Erlaubte Videos: MP4, MOV und WebM.")
        return {"mime": "video/webm" if "webm" in fmt else "video/mp4", "width":stream.get("width"), "height":stream.get("height"), "duration":float(info["format"].get("duration", 0))}
    except (subprocess.SubprocessError, KeyError, StopIteration, json.JSONDecodeError):
        raise ValueError("Die Datei ist kein unterstütztes Bild oder Video.") from None

def store_upload(session, upload, tags=""):
    identifier = uuid.uuid4().hex
    temporary = config.MEDIA / "tmp" / identifier
    final = config.MEDIA / "originals" / identifier
    size, sha = 0, hashlib.sha256()
    try:
        check_space(session, 0)
        with temporary.open("xb") as out:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > config.VIDEO_LIMIT:
                    raise ValueError("Maximal 500 MiB pro Datei.")
                # Disk space already accounts for written temporary bytes.
                if size > config.QUOTA - storage(session)["used"] or shutil.disk_usage(config.DATA).free < config.RESERVE + len(chunk):
                    raise ValueError("Upload gestoppt: Speicherbudget oder Reserve erreicht.")
                out.write(chunk)
                sha.update(chunk)
            out.flush()
            os.fsync(out.fileno())
        info = probe(temporary)
        if info["mime"].startswith("image/") and size > config.IMAGE_LIMIT:
            raise ValueError("Maximal 50 MiB pro Bild.")
        temporary.replace(final)
        media = Media(id=identifier, name=Path(upload.filename or "Datei").name[:180], path=f"originals/{identifier}", sha256=sha.hexdigest(), size=size, tags=tags[:500], **info)
        session.add(media)
        session.add(Job(key=f"preview:{identifier}", kind="preview", payload=json.dumps({"id":identifier})))
        session.flush()
        return media
    except Exception:
        temporary.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        raise

def make_preview(session, identifier):
    media = session.get(Media, identifier)
    if not media:
        return
    original = config.MEDIA / media.path
    dest = config.MEDIA / "previews" / f"{identifier}.jpg"
    if media.mime.startswith("image/"):
        with Image.open(original) as source:
            im = ImageOps.exif_transpose(source).convert("RGB")
            im.thumbnail((960, 960))
            im.save(dest, "JPEG", quality=82)
    else:
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-threads", "1", "-protocol_whitelist", "file", "-i", str(original), "-frames:v", "1", "-vf", "scale=640:-2", "-threads", "1", "-y", str(dest)], timeout=60, check=True, capture_output=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            media.preview_status = "unavailable"
            return
    media.preview = f"previews/{identifier}.jpg"
    media.preview_status = "ready"
