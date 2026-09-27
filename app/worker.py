import json
import logging
import time
import portalocker
from . import config, backup, sync
from .db import transaction
from .jobs import claim, finish, schedule
from .media import make_preview

log = logging.getLogger("nimo.worker")

def step():
    job = claim()
    if not job:
        return False
    try:
        if job.kind == "preview":
            with transaction() as session:
                make_preview(session, json.loads(job.payload)["id"])
        elif job.kind == "db_backup":
            backup.daily()
        elif job.kind == "full_backup":
            backup.full()
        else:
            sync.run(job)
        finish(job)
    except Exception as exc:
        # Do not log exception representations: HTTP objects can contain tokens.
        log.warning("Auftrag %s (%s) fehlgeschlagen: %s", job.id, job.kind, type(exc).__name__)
        finish(job, exc)
    return True

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with portalocker.Lock(str(config.DATA / "worker.lock"), timeout=1):
        next_schedule = 0
        while True:
            if time.time() >= next_schedule:
                schedule()
                next_schedule = time.time() + 60
            if not step():
                time.sleep(3)

if __name__ == "__main__":
    main()
