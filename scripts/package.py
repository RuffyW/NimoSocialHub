"""Build a source release from an explicit allowlist, never from runtime data."""
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
files = []
for folder in ("app", "migrations", "scripts", "docs", "tests"):
    files.extend(path for path in (root/folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
for name in ("README.md", "Dockerfile", "Caddyfile", "compose.yaml", "alembic.ini", ".env.example", ".dockerignore", ".gitignore", "requirements.txt", "requirements-lock.txt", "requirements-dev.txt"):
    files.append(root/name)
destination = root/"dist"
destination.mkdir(exist_ok=True)
target = destination/"nimo-social-hub-0.1.0.zip"
manifest = []
with ZipFile(target,"w",ZIP_DEFLATED) as archive:
    for path in sorted(files):
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        archive.writestr("nimo-social-hub/"+name,data)
        manifest.append(hashlib.sha256(data).hexdigest()+"  "+name)
    archive.writestr("nimo-social-hub/RELEASE.sha256","\n".join(manifest)+"\n")
checksum = hashlib.sha256(target.read_bytes()).hexdigest()
target.with_suffix(".zip.sha256").write_text(checksum+"  "+target.name+"\n")
print(f"{target}: {len(files)} files, {target.stat().st_size} bytes")
