import json
import time
import uuid
from sqlalchemy import select, or_, delete
from .db import transaction
from .models import Job, Setting, LoginAttempt, LoginSession

def enqueue(session, kind, key, payload=None, due=None):
    existing = session.scalar(select(Job).where(Job.key == key))
    if existing:
        return existing
    job = Job(kind=kind, key=key, payload=json.dumps(payload or {}), due_at=due or time.time())
    session.add(job)
    return job

def claim():
    now = time.time()
    with transaction() as session:
        job = session.scalar(select(Job).where(
            or_((Job.status == "pending") & (Job.due_at <= now), (Job.status == "running") & (Job.lease_until < now))
        ).order_by(Job.due_at).limit(1))
        if not job:
            return None
        job.status, job.owner, job.lease_until = "running", uuid.uuid4().hex, now + 300
        job.attempts += 1
        session.flush()
        return job

def finish(job, error=None):
    from .instagram import PlatformError
    with transaction() as session:
        current = session.get(Job, job.id)
        if not current or current.owner != job.owner:
            return
        if error:
            retry = not isinstance(error, PlatformError) or error.retry
            current.error = str(error) if isinstance(error, (PlatformError, ValueError)) else "Auftrag fehlgeschlagen. Betriebsprotokoll prüfen."
            current.status = "pending" if retry and current.attempts < 5 else "failed"
            current.due_at = time.time() + max(getattr(error, "delay", 0), min(60 * 2**current.attempts, 21600))
        else:
            current.status, current.completed_at = "done", time.time()
        current.lease_until = None

def schedule():
    from .models import Account, Publication
    now = time.time()
    with transaction() as session:
        session.merge(Setting(key="worker_heartbeat", value=str(now)))
        session.execute(delete(LoginAttempt).where(LoginAttempt.at < now-3600))
        session.execute(delete(LoginSession).where(LoginSession.expires < now))
        # Dedup rows kept >=14 days: longest scheduling bucket is one week.
        session.execute(delete(Job).where(Job.status == "done", Job.completed_at < now-14*86400))
        enqueue(session, "db_backup", f"db_backup:{int(now//86400)}")
        recipient = session.get(Setting, "backup_recipient")
        if recipient and recipient.value:
            enqueue(session, "full_backup", f"full_backup:{int(now//604800)}")
        for account in session.scalars(select(Account).where(Account.token.is_not(None), Account.status != "auth_required")):
            enqueue(session, "sync_posts", f"posts:{account.id}:{int(now//21600)}", {"account":account.id})
            enqueue(session, "account_metrics", f"account:{account.id}:{int(now//86400)}", {"account":account.id})
            enqueue(session, "refresh", f"refresh:{account.id}:{int(now//86400)}", {"account":account.id})
            for publication in session.scalars(select(Publication).where(Publication.account_id == account.id, Publication.external_id.is_not(None), Publication.format != "story")):
                age = now-publication.published_at
                if age > 730*86400:
                    continue
                interval = 21600 if age <= 30*86400 else 86400 if age <= 90*86400 else 604800
                enqueue(session, "post_metrics", f"metrics:{publication.id}:{int(now//interval)}", {"account":account.id, "publication":publication.id})
