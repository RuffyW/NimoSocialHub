import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import config
from .db import engine, transaction
from .models import Account, Publication, Observation, Job, Setting
from .jobs import enqueue
from .instagram import Instagram, PlatformError, safe_preview
from .security import vault

POST_METRICS = ["views", "reach", "likes", "comments", "saved", "shares", "total_interactions"]
ACCOUNT_METRICS = ["views", "reach", "likes", "comments", "saves", "shares", "total_interactions", "accounts_engaged"]

class ConnectionChanged(Exception):
    pass

@contextmanager
def connected_transaction(account_id, encrypted_token):
    with transaction() as session:
        account = session.get(Account, account_id)
        if not account or account.token != encrypted_token:
            raise ConnectionChanged()
        yield session

def heartbeat(job, connection=None):
    with transaction() as session:
        if connection and session.get(Account, connection[0]).token != connection[1]:
            raise ConnectionChanged()
        current = session.get(Job, job.id)
        if current and current.owner == job.owner:
            current.lease_until = time.time() + 300
        session.merge(Setting(key="worker_heartbeat", value=str(time.time())))

def observe(job, metric, value, reason=None, publication=None, start=None, end=None):
    key = f"{job.id}:{metric}:{publication or 'account'}:{start}"
    with transaction() as session:
        if not session.scalar(select(Observation.id).where(Observation.dedup_key == key)):
            session.add(Observation(dedup_key=key, metric=metric, value=value, reason=reason,
                publication_id=publication, observed_at=time.time(), period_start=start, period_end=end,
                source="api", api_version=config.API_VERSION))

def extract(data):
    rows = data.get("data", [])
    if not rows:
        return None
    row = rows[0]
    if "value" in row.get("total_value", {}):
        return row["total_value"]["value"]
    values = row.get("values", [])
    return values[-1].get("value") if values else None

def run(job, client_factory=Instagram):
    payload = json.loads(job.payload)
    with Session(engine) as session:
        account = session.get(Account, payload.get("account", 1))
        if not account or not account.token or account.status == "auth_required":
            return
        token = vault().decrypt(account.token.encode()).decode()
        encrypted_token = account.token
        account_id, external_id = account.id, account.external_id
        token_created, token_expires = account.token_created, account.token_expires
    api = client_factory(token)
    partial = False
    try:
        with connected_transaction(account_id, encrypted_token) as session:
            session.get(Account, account_id).last_attempt = time.time()
        if job.kind == "sync_posts":
            heartbeat(job, (account_id, encrypted_token))
            data = api.publications(external_id, payload.get("cursor"))
            with connected_transaction(account_id, encrypted_token) as session:
                for item in data.get("data", []):
                    fmt = "reel" if item.get("media_product_type") == "REELS" else "carousel" if item.get("media_type") == "CAROUSEL_ALBUM" else "video" if item.get("media_type") == "VIDEO" else "image"
                    if item.get("media_product_type") == "STORY":
                        continue
                    link = item.get("permalink")
                    if not link:
                        continue
                    row = session.scalar(select(Publication).where(Publication.account_id == account_id, Publication.external_id == str(item["id"])))
                    if not row:
                        # Exact permalink reconciliation only; never caption guessing.
                        row = session.scalar(select(Publication).where(Publication.account_id == account_id, Publication.permalink == link.rstrip("/") + "/"))
                    if not row:
                        row = Publication(account_id=account_id, permalink=link.rstrip("/") + "/")
                        session.add(row)
                    row.external_id = str(item["id"])
                    row.published_at = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")).timestamp()
                    row.format, row.caption, row.source = fmt, item.get("caption", ""), "api"
                    row.preview_url = safe_preview(item.get("thumbnail_url") or (item.get("media_url") if item.get("media_type") != "VIDEO" else None))
                paging = data.get("paging", {})
                cursor = paging.get("cursors", {}).get("after") if paging.get("next") else None
                if cursor and cursor != payload.get("cursor"):
                    root = payload.get("root", job.id)
                    enqueue(session, "sync_posts", f"page:{root}:{cursor}", {"account":account_id, "cursor":cursor, "root":root})
                else:
                    session.get(Account, account_id).last_success = time.time()
        elif job.kind == "post_metrics":
            with Session(engine) as session:
                publication = session.get(Publication, payload["publication"])
                if not publication or not publication.external_id:
                    return
                pid, xid, fmt = publication.id, publication.external_id, publication.format
            names = POST_METRICS + (["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"] if fmt == "reel" else [])
            for name in names:
                heartbeat(job, (account_id, encrypted_token))
                try:
                    value = extract(api.metric(xid, name))
                    observe(job, name, value, "unavailable" if value is None else None, pid)
                except PlatformError as exc:
                    if exc.retry or exc.auth:
                        raise
                    partial = True
                    observe(job, name, None, "unsupported", pid)
        elif job.kind == "account_metrics":
            # UTC periods are preserved and labelled; never relabel platform days as Berlin days.
            day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            for days in range(1, 8):
                start, end = (day-timedelta(days=days)).timestamp(), (day-timedelta(days=days-1)).timestamp()
                for name in ACCOUNT_METRICS:
                    heartbeat(job, (account_id, encrypted_token))
                    try:
                        value = extract(api.metric(external_id, name, {"period":"day", "metric_type":"total_value", "since":int(start), "until":int(end)-1}))
                        observe(job, name, value, "unavailable" if value is None else None, start=start, end=end)
                    except PlatformError as exc:
                        if exc.retry or exc.auth:
                            raise
                        partial = True
                        observe(job, name, None, "unsupported", start=start, end=end)
                heartbeat(job, (account_id, encrypted_token))
                try:
                    flow = api.metric(external_id,"follows_and_unfollows",{"period":"day","metric_type":"total_value","breakdown":"follow_type","since":int(start),"until":int(end)-1})
                    values = {}
                    for row in flow.get("data", []):
                        for breakdown in row.get("total_value", {}).get("breakdowns", []):
                            keys = breakdown.get("dimension_keys", [])
                            if "follow_type" not in keys:
                                continue
                            index = keys.index("follow_type")
                            for result in breakdown.get("results", []):
                                dimensions = result.get("dimension_values", [])
                                if len(dimensions) > index:
                                    values[str(dimensions[index]).lower()] = result.get("value")
                    for name, external in (("follows","follow"),("unfollows","unfollow")):
                        value = values.get(external)
                        observe(job,name,value,"unavailable" if value is None else None,start=start,end=end)
                except PlatformError as exc:
                    if exc.retry or exc.auth:
                        raise
                    partial = True
                    for name in ("follows","unfollows"):
                        observe(job,name,None,"unsupported",start=start,end=end)
            heartbeat(job, (account_id, encrypted_token))
            try:
                value = api.get(external_id, {"fields":"followers_count"}).get("followers_count")
                observe(job, "followers_count", value, "unavailable" if value is None else None)
            except PlatformError as exc:
                if exc.retry or exc.auth:
                    raise
                partial = True
                observe(job, "followers_count", None, "unsupported")
        elif job.kind == "refresh":
            if token_expires and token_expires <= time.time():
                raise PlatformError("Instagram-Token abgelaufen. Bitte neu verbinden.", retry=False, auth=True)
            if token_created and time.time()-token_created >= 30*86400:
                heartbeat(job, (account_id, encrypted_token))
                data = api.refresh()
                with connected_transaction(account_id, encrypted_token) as session:
                    account = session.get(Account, account_id)
                    account.token = vault().encrypt(data["access_token"].encode()).decode()
                    encrypted_token = account.token
                    account.token_created = time.time()
                    account.token_expires = time.time() + int(data["expires_in"])
        with connected_transaction(account_id, encrypted_token) as session:
            account = session.get(Account, account_id)
            if job.kind != "refresh":
                account.status = "partial" if partial else "connected"
                account.error = "Einige Kennzahlen sind für dieses Konto oder Format nicht verfügbar." if partial else ""
    except ConnectionChanged:
        return
    except PlatformError as exc:
        with transaction() as session:
            account = session.get(Account, account_id)
            if account.token == encrypted_token:
                account.status = "auth_required" if exc.auth else "error"
                account.error = str(exc)
        raise
    finally:
        api.close()
