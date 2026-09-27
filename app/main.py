import calendar
import json
import math
import re
import time
import shutil
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from . import config, __version__
from .db import engine, transaction
from .models import Account, Idea, Draft, Publication, Media, Attachment, Task, Metric, Observation, Job, Setting, LoginSession, LoginAttempt
from .security import hasher, nonce, digest, vault
from .timeutil import local_time, display, BERLIN, week_bounds
from .metrics import comparable
from .media import store_upload, storage
from .jobs import enqueue
from .instagram import Instagram, PlatformError

STATUSES = {"idea":"Idee", "draft":"Entwurf", "ready":"Bereit", "published":"Veröffentlicht"}
FORMATS = {"image":"Bild", "carousel":"Karussell", "reel":"Reel", "video":"Video", "story":"Story"}
REASONS = {"unavailable":"Noch nicht verfügbar", "unsupported":"Nicht unterstützt / Berechtigung fehlt", "error":"Abruffehler", "missing":"Nicht erfasst"}
templates = Jinja2Templates(directory=str(config.ROOT / "app" / "templates"))
templates.env.filters.update(date=display, filesize=lambda n: f"{n/1024**2:.1f} MiB", number=lambda n: "—" if n is None else f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".").removesuffix(",00"))
templates.env.globals.update(statuses=STATUSES, formats=FORMATS, reasons=REASONS, version=__version__)

async def csrf(request: Request):
    if request.method != "POST":
        return
    if request.headers.get("origin") and request.headers["origin"].rstrip("/") != config.ORIGIN:
        raise HTTPException(403, "Die Anfrage stammt nicht vom Hub.")
    form = await request.form(max_files=1, max_fields=100, max_part_size=1024*1024)
    expected = request.cookies.get("nimo_login_csrf") if request.url.path == "/login" else getattr(request.state, "csrf", None)
    import secrets
    if not expected or not secrets.compare_digest(str(form.get("csrf", "")), expected):
        raise HTTPException(403, "Formular abgelaufen. Bitte Seite neu laden.")

@asynccontextmanager
async def lifespan(app):
    with engine.connect() as connection:
        from sqlalchemy import text
        try:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            raise RuntimeError("Datenbank fehlt. Zuerst: python -m app.cli init") from None
        if revision != "0001":
            raise RuntimeError("Datenbankversion passt nicht zur Anwendung.")
    yield

app = FastAPI(title="Nimo Social Hub", docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(csrf)], lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.ROOT / "app" / "static")), name="static")

class UploadLimit:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        maximum = config.VIDEO_LIMIT + 2*1024*1024 if scope["path"] == "/media/upload" else 2*1024*1024
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await HTMLResponse("Ungültige Dateigröße.", status_code=400)(scope, receive, send)
        if length > maximum:
            return await HTMLResponse("Upload zu groß.", status_code=413)(scope, receive, send)
        count = 0
        async def limited():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > maximum:
                raise HTTPException(413, "Upload zu groß.")
            if scope["path"] == "/media/upload" and shutil.disk_usage(config.DATA).free - len(message.get("body",b"")) < config.RESERVE:
                raise HTTPException(507, "Upload gestoppt: Speicherreserve erreicht.")
            return message
        await self.app(scope, limited, send)

@app.middleware("http")
async def authenticate(request, call_next):
    path = request.url.path
    public = path in ("/login", "/health") or path.startswith("/static/")
    request.state.csrf = ""
    if not public:
        with Session(engine) as session:
            row = session.get(LoginSession, digest(request.cookies.get("nimo_session", "")))
            if not row or row.expires < time.time():
                return RedirectResponse("/login", 303)
            request.state.csrf = row.csrf
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Preserve same-origin form Origin headers; suppress referrers to other sites.
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://*.cdninstagram.com https://*.fbcdn.net; media-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    if not path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response

app.add_middleware(UploadLimit)

def page(request, template, **context):
    return templates.TemplateResponse(request=request, name=template, context={"csrf":getattr(request.state, "csrf", ""), "now":time.time(), "path":request.url.path, **context})

def redirect(url):
    return RedirectResponse(url, 303)

def required(form, key, maximum=300):
    value = str(form.get(key, "")).strip()
    if not value or len(value) > maximum:
        raise ValueError(f"Feld {key}: Bitte einen Wert mit höchstens {maximum} Zeichen eingeben.")
    return value

def choose(value, choices):
    if value not in choices:
        raise ValueError("Ungültige Auswahl.")
    return value

def get_or_fail(session, model, identifier):
    value = session.get(model, identifier)
    if not value:
        raise HTTPException(404, "Eintrag nicht gefunden.")
    return value

def permalink(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in ("instagram.com", "www.instagram.com") or parsed.username or parsed.port or not re.fullmatch(r"/(p|reel|stories)/[A-Za-z0-9_./-]+/?", parsed.path):
        raise ValueError("Bitte einen gültigen HTTPS-Link zu einem Instagram-Beitrag eingeben.")
    return "https://www.instagram.com" + parsed.path.rstrip("/") + "/"

@app.exception_handler(ValueError)
async def invalid(request, exc):
    response = page(request, "error.html", message=str(exc))
    response.status_code = 400
    return response

@app.exception_handler(IntegrityError)
async def duplicate(request, exc):
    response = page(request, "error.html", message="Dieser Eintrag ist bereits vorhanden oder wird schon verwendet. Bitte den vorhandenen Beitrag zuordnen.")
    response.status_code = 409
    return response

@app.exception_handler(HTTPException)
async def http_error(request, exc):
    response = page(request, "error.html", message=exc.detail)
    response.status_code = exc.status_code
    return response

@app.get("/health")
def health():
    with Session(engine) as session:
        session.execute(select(1))
    return {"status":"ok", "version":__version__}

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    token = nonce()
    response = page(request, "login.html", csrf=token)
    response.set_cookie("nimo_login_csrf", token, httponly=True, secure=not config.DEV, samesite="strict", max_age=3600)
    return response

@app.post("/login")
async def login(request: Request):
    form = await request.form()
    address = request.client.host
    with transaction() as session:
        attempts = session.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.address == address, LoginAttempt.at > time.time()-900))
        if attempts >= 5:
            raise HTTPException(429, "Zu viele Anmeldeversuche. Bitte in 15 Minuten erneut versuchen.")
        setting = session.get(Setting, "password_hash")
        try:
            valid = setting and hasher.verify(setting.value, str(form.get("password", "")))
        except (VerifyMismatchError, InvalidHashError):
            valid = False
        if not valid:
            session.add(LoginAttempt(address=address))
        else:
            token = nonce()
            session.add(LoginSession(digest=digest(token), csrf=nonce(), expires=time.time()+7*86400))
    if not valid:
        raise HTTPException(401, "Anmeldung fehlgeschlagen.")
    response = redirect("/")
    response.set_cookie("nimo_session", token, httponly=True, secure=not config.DEV, samesite="strict", max_age=7*86400)
    response.delete_cookie("nimo_login_csrf")
    return response

@app.post("/logout")
def logout(request: Request):
    with transaction() as session:
        session.execute(delete(LoginSession).where(LoginSession.digest == digest(request.cookies.get("nimo_session", ""))))
    response = redirect("/login")
    response.delete_cookie("nimo_session")
    return response

@app.get("/")
def dashboard(request: Request):
    with Session(engine) as session:
        publications = session.scalars(select(Publication).order_by(Publication.published_at.desc()).limit(12)).all()
        upcoming = session.execute(select(Draft, Idea).join(Idea).where(Draft.status != "published", Draft.planned_at <= time.time()+7*86400).order_by(Draft.planned_at).limit(20)).all()
        tasks = session.scalars(select(Task).where(Task.done == False).order_by(Task.due_at).limit(12)).all()
        counts = {key:session.scalar(select(func.count()).select_from(Draft).where(Draft.status == key)) for key in STATUSES}
        post_stats = {}
        for publication in publications:
            recent = {}
            for observation in session.scalars(select(Observation).where(Observation.publication_id==publication.id,Observation.metric.in_(("views","reach","likes")),Observation.period_start.is_(None)).order_by(Observation.observed_at.desc())):
                recent.setdefault((observation.metric,observation.source),observation)
            post_stats[publication.id] = list(recent.values())
        observations = session.scalars(select(Observation).where(Observation.publication_id.is_(None)).order_by(func.coalesce(Observation.period_end,Observation.observed_at).desc(),Observation.observed_at.desc()).limit(100)).all()
        latest, seen = [], set()
        for row in observations:
            if row.metric not in seen:
                latest.append(row)
                seen.add(row.metric)
        return page(request, "dashboard.html", publications=publications, post_stats=post_stats, upcoming=upcoming, tasks=tasks, counts=counts, account=session.get(Account,1), metrics={m.key:m for m in session.scalars(select(Metric))}, observations=latest[:4], storage=storage(session))

@app.get("/planning")
def planning(request: Request, status: str="", topic: str="", format: str="", audience: str="", platform: str="", view: str="list", month: str=""):
    with Session(engine) as session:
        query = select(Draft, Idea).join(Idea).join(Account)
        for test, clause in [(status, Draft.status == status), (topic, Idea.topic == topic), (format, Draft.format == format), (audience, Idea.audience == audience), (platform, Account.platform == platform)]:
            if test:
                query = query.where(clause)
        rows = session.execute(query.order_by(Draft.planned_at.asc().nulls_last(), Draft.created_at.desc())).all()
        topics = session.scalars(select(Idea.topic).distinct().order_by(Idea.topic)).all()
        try:
            selected = datetime.strptime(month, "%Y-%m") if month else datetime.now(BERLIN)
        except ValueError:
            raise ValueError("Ungültiger Monat.") from None
        cells = []
        for week in calendar.Calendar(0).monthdatescalendar(selected.year, selected.month):
            cells.append([{"date":day, "rows":[(d,i) for d,i in rows if d.planned_at and datetime.fromtimestamp(d.planned_at,BERLIN).date()==day]} for day in week])
        return page(request, "planning.html", rows=rows, topics=topics, cells=cells, selected=selected, view=view, filters={"status":status,"topic":topic,"format":format,"audience":audience,"platform":platform})

@app.get("/drafts/new")
def new_draft(request: Request):
    return page(request, "draft.html", draft=None, idea=None, media=[], attached=[], tasks=[], publications=[], publication=None)

@app.get("/drafts/{identifier}")
def draft_detail(request: Request, identifier: str):
    with Session(engine) as session:
        draft = get_or_fail(session,Draft,identifier)
        return page(request,"draft.html",draft=draft,idea=session.get(Idea,draft.idea_id), media=session.scalars(select(Media).order_by(Media.created_at.desc())).all(),
            attached=session.scalars(select(Attachment).where(Attachment.draft_id==identifier).order_by(Attachment.position)).all(),
            tasks=session.scalars(select(Task).where(Task.draft_id==identifier)).all(),
            publications=session.scalars(select(Publication).where(Publication.draft_id.is_(None))).all(),
            publication=session.scalar(select(Publication).where(Publication.draft_id==identifier)))

@app.post("/drafts/save")
async def save_draft(request: Request):
    form = await request.form()
    with transaction() as session:
        identifier = str(form.get("id", ""))
        if identifier:
            draft = get_or_fail(session,Draft,identifier)
            idea = session.get(Idea,draft.idea_id)
        else:
            idea = Idea(title="")
            session.add(idea)
            session.flush()
            draft = Draft(idea_id=idea.id)
            session.add(draft)
        idea.title = required(form,"title")
        idea.topic = str(form.get("topic", ""))[:100]
        idea.audience = str(form.get("audience", "Eltern"))[:100]
        idea.notes = str(form.get("notes", ""))[:20000]
        draft.format = choose(str(form.get("format")), FORMATS)
        draft.caption = str(form.get("caption", ""))[:20000]
        status = choose(str(form.get("status", "idea")), STATUSES)
        linked = session.scalar(select(Publication).where(Publication.draft_id==draft.id)) if draft.id else None
        if status == "published" and not linked:
            raise ValueError("Bitte zuerst die tatsächliche Veröffentlichung erfassen oder zuordnen.")
        if linked and status != "published":
            raise ValueError("Für eine neue Variante bitte die Idee wiederverwenden.")
        draft.status = status
        draft.planned_at = local_time(str(form.get("planned_at", "")), str(form.get("fold", "")))
        session.flush()
        identifier = draft.id
    return redirect(f"/drafts/{identifier}")

@app.post("/drafts/{identifier}/reuse")
def reuse(request: Request, identifier: str):
    with transaction() as session:
        old = get_or_fail(session,Draft,identifier)
        idea = session.get(Idea,old.idea_id)
        new = Idea(title=idea.title+" · neue Idee", topic=idea.topic, audience=idea.audience, notes=idea.notes, origin_id=idea.id)
        session.add(new)
        session.flush()
        draft = Draft(idea_id=new.id,format=old.format,caption=old.caption,status="draft")
        session.add(draft)
        session.flush()
        identifier = draft.id
    return redirect(f"/drafts/{identifier}")

@app.post("/drafts/{identifier}/media")
async def attach(request: Request, identifier: str):
    form = await request.form()
    with transaction() as session:
        get_or_fail(session,Draft,identifier)
        ids = [x.strip() for x in str(form.get("order", "")).split(",") if x.strip()]
        if len(set(ids)) != len(ids) or len(ids)>30:
            raise ValueError("Bitte höchstens 30 unterschiedliche Medien zuordnen.")
        for mid in ids:
            get_or_fail(session,Media,mid)
        session.execute(delete(Attachment).where(Attachment.draft_id==identifier))
        for position, mid in enumerate(ids):
            session.add(Attachment(draft_id=identifier,media_id=mid,position=position))
    return redirect(f"/drafts/{identifier}")

@app.get("/publications/{identifier}")
def publication_detail(request: Request, identifier: str):
    with Session(engine) as session:
        publication = get_or_fail(session,Publication,identifier)
        return page(request,"publication.html", publication=publication,
            observations=session.scalars(select(Observation).where(Observation.publication_id==identifier).order_by(Observation.observed_at.desc())).all(),
            metrics={m.key:m for m in session.scalars(select(Metric))},
            drafts=session.execute(select(Draft,Idea).join(Idea).where(Draft.status!="published")).all())

@app.post("/publications")
async def publish_manual(request: Request):
    form = await request.form()
    with transaction() as session:
        draft_id = str(form.get("draft_id", "")) or None
        draft = get_or_fail(session,Draft,draft_id) if draft_id else None
        published = local_time(required(form,"published_at"),str(form.get("fold", "")))
        if published > time.time()+60:
            raise ValueError("Eine tatsächliche Veröffentlichung kann nicht in der Zukunft liegen.")
        media_id = str(form.get("media_id", "")) or None
        if media_id:
            get_or_fail(session,Media,media_id)
        if draft and not media_id:
            attachment = session.scalar(select(Attachment).where(Attachment.draft_id==draft.id).order_by(Attachment.position))
            media_id = attachment.media_id if attachment else None
        publication = Publication(draft_id=draft_id,permalink=permalink(required(form,"permalink",1000)),published_at=published,
            format=draft.format if draft else choose(str(form.get("format")),FORMATS),caption=draft.caption if draft else str(form.get("caption", ""))[:20000],media_id=media_id)
        session.add(publication)
        if draft:
            draft.status = "published"
        session.flush()
        identifier = publication.id
    return redirect(f"/publications/{identifier}")

@app.post("/publications/{identifier}/link")
async def link_publication(request: Request, identifier: str):
    form = await request.form()
    with transaction() as session:
        publication = get_or_fail(session,Publication,identifier)
        if publication.draft_id:
            raise ValueError("Dieser Beitrag ist bereits zugeordnet.")
        draft = get_or_fail(session,Draft,required(form,"draft_id"))
        publication.draft_id, draft.status = draft.id, "published"
    return redirect(f"/drafts/{draft.id}")

@app.post("/observations")
async def manual_metric(request: Request):
    form = await request.form()
    with transaction() as session:
        publication_id = str(form.get("publication_id", "")) or None
        publication = get_or_fail(session,Publication,publication_id) if publication_id else None
        metric = get_or_fail(session,Metric,required(form,"metric"))
        if metric.scope != "both" and metric.scope != ("publication" if publication else "account"):
            raise ValueError("Diese Kennzahl gehört zu einem anderen Bezugsobjekt.")
        observed = local_time(required(form,"observed_at"),str(form.get("fold", "")))
        if observed > time.time()+60 or (publication and observed < publication.published_at):
            raise ValueError("Der Messzeitpunkt muss nach Veröffentlichung und spätestens jetzt liegen.")
        raw = str(form.get("value", "")).strip().replace(",", ".")
        value = float(raw) if raw else None
        if value is not None and (not math.isfinite(value) or value<0):
            raise ValueError("Bitte eine endliche, nicht negative Zahl eingeben.")
        reason = choose(str(form.get("reason", "missing")), REASONS) if value is None else None
        start = local_time(str(form.get("period_start", "")),str(form.get("fold", "")))
        end = local_time(str(form.get("period_end", "")),str(form.get("fold", "")))
        if bool(start) != bool(end) or (start is not None and (start>=end or end>observed)):
            raise ValueError("Bezugszeitraum vollständig und vor dem Messzeitpunkt angeben.")
        if not publication and metric.key != "followers_count" and start is None:
            raise ValueError("Für Konto-Kennzahlen bitte den Bezugszeitraum angeben.")
        session.add(Observation(dedup_key="manual:"+required(form,"entry_id"), publication_id=publication_id,metric=metric.key,value=value,reason=reason,observed_at=observed,period_start=start,period_end=end,source="manual"))
    return redirect(f"/publications/{publication_id}" if publication_id else "/analytics")

@app.post("/tasks")
async def add_task(request: Request):
    form = await request.form()
    with transaction() as session:
        draft_id = str(form.get("draft_id", "")) or None
        if draft_id:
            get_or_fail(session,Draft,draft_id)
        session.add(Task(text=required(form,"text",500),draft_id=draft_id,due_at=local_time(str(form.get("due_at", "")),str(form.get("fold", "")))))
    return redirect(f"/drafts/{draft_id}" if draft_id else "/")

@app.post("/tasks/{identifier}/toggle")
def toggle_task(request: Request, identifier: str):
    with transaction() as session:
        task = get_or_fail(session,Task,identifier)
        task.done = not task.done
    if request.headers.get("HX-Request"):
        return page(request,"task.html",task=task)
    return redirect(f"/drafts/{task.draft_id}" if task.draft_id else "/")

@app.get("/media")
def media_page(request: Request, tag: str=""):
    with Session(engine) as session:
        query = select(Media).order_by(Media.created_at.desc())
        if tag:
            query = query.where(Media.tags.contains(tag,autoescape=True))
        media = session.scalars(query).all()
        usages = {m.id:session.execute(select(Draft.id,Idea.title).join(Idea).join(Attachment,Attachment.draft_id==Draft.id).where(Attachment.media_id==m.id)).all() for m in media}
        return page(request,"media.html",media=media,usages=usages,storage=storage(session),tag=tag)

@app.post("/media/upload")
async def upload(request: Request):
    form = await request.form()
    item = form.get("file")
    if not hasattr(item,"file"):
        raise ValueError("Bitte eine Datei auswählen.")
    from starlette.concurrency import run_in_threadpool
    def save():
        with transaction() as session:
            store_upload(session,item,str(form.get("tags", "")))
    try:
        await run_in_threadpool(save)
    finally:
        await item.close()
    return redirect("/media")

@app.post("/media/{identifier}/tags")
async def media_tags(request: Request, identifier: str):
    form = await request.form()
    with transaction() as session:
        get_or_fail(session,Media,identifier).tags = str(form.get("tags", ""))[:500]
    return redirect("/media")

@app.get("/media/{identifier}/{variant}")
def media_file(request: Request, identifier: str, variant: str):
    with Session(engine) as session:
        media = get_or_fail(session,Media,identifier)
        if variant == "preview":
            if not media.preview or not (config.MEDIA/media.preview).exists():
                return FileResponse(config.ROOT/"app/static/nimo-wave.png",media_type="image/png")
            return FileResponse(config.MEDIA/media.preview,media_type="image/jpeg")
        if variant not in ("original", "play"):
            raise HTTPException(404)
        return FileResponse(config.MEDIA/media.path,media_type=media.mime,filename=media.name if variant=="original" else None,content_disposition_type="attachment" if variant=="original" else "inline")

@app.get("/analytics")
def analytics(request: Request, days: int=7, metric: str="reach", source: str="api", format: str="reel", week: int=-1):
    choose(days,(1,7,30)); choose(source,("api","manual")); choose(format,FORMATS)
    if not -520 <= week <= 0:
        raise ValueError("Ungültige Kalenderwoche.")
    with Session(engine) as session:
        definition = get_or_fail(session,Metric,metric)
        publications = session.scalars(select(Publication).where(Publication.format==format).order_by(Publication.published_at.desc())).all()
        rows = [(p,comparable(session,p,metric,days,source)) for p in publications]
        start,end = week_bounds(week)
        weekly = session.scalars(select(Publication).where(Publication.published_at>=start,Publication.published_at<end).order_by(Publication.published_at)).all()
        weekly_results = {}
        for publication in weekly:
            latest = {}
            for observation in session.scalars(select(Observation).where(Observation.publication_id==publication.id,Observation.period_start.is_(None)).order_by(Observation.observed_at.desc())):
                latest.setdefault((observation.metric,observation.source),observation)
            weekly_results[publication.id] = list(latest.values())
        account_rows = session.scalars(select(Observation).where(Observation.publication_id.is_(None)).order_by(Observation.observed_at.desc()).limit(200)).all()
        return page(request,"analytics.html", rows=rows, coverage=sum(1 for _,o in rows if o and o.value is not None),days=days,metric=metric,definition=definition,source=source,format=format,week=week,start=start,end=end,weekly=weekly,weekly_results=weekly_results,provisional=time.time()<end+2*86400,
            tasks=session.scalars(select(Task).where(Task.done==False).order_by(Task.due_at)).all(),
            upcoming=session.execute(select(Draft,Idea).join(Idea).where(Draft.status!="published",Draft.planned_at.between(end,end+7*86400)).order_by(Draft.planned_at)).all(),
            metrics={m.key:m for m in session.scalars(select(Metric))},account_rows=account_rows,entry_id=nonce())

@app.get("/topics")
def topics(request: Request):
    with Session(engine) as session:
        rows = session.execute(select(Draft,Idea,Publication).join(Idea).outerjoin(Publication,Publication.draft_id==Draft.id).order_by(Idea.topic,Draft.created_at.desc())).all()
        groups = {}
        for draft,idea,publication in rows:
            groups.setdefault(idea.topic or "Ohne Thema",[]).append((draft,idea,publication))
        return page(request,"topics.html",groups=groups)

@app.get("/settings")
def settings(request: Request):
    with Session(engine) as session:
        return page(request,"settings.html",account=session.get(Account,1),settings={s.key:s.value for s in session.scalars(select(Setting).where(Setting.key!="password_hash"))},
            jobs=session.scalars(select(Job).where(Job.status!="done").order_by(Job.due_at.desc()).limit(30)).all(),storage=storage(session),backups=sorted(config.BACKUPS.glob("nimo-*.tar.age"),reverse=True))

@app.post("/settings/instagram")
async def connect_instagram(request: Request):
    form = await request.form()
    token = required(form,"token",4096)
    from starlette.concurrency import run_in_threadpool
    def verify():
        api = Instagram(token)
        try:
            identity = api.identity()
            if identity.get("username", "").lower() != "meinnimo":
                raise ValueError("Das Token gehört nicht zu @meinnimo.")
            xid = str(identity.get("user_id") or identity.get("id") or "")
            if not xid:
                raise ValueError("Instagram hat keine Konto-ID geliefert.")
            # Verify basic access and insights separately. Empty metrics are legitimate.
            api.publications(xid)
            api.metric(xid,"reach",{"period":"day","metric_type":"total_value"})
            return xid
        except PlatformError as exc:
            raise ValueError(str(exc)) from None
        finally:
            api.close()
    xid = await run_in_threadpool(verify)
    created = local_time(required(form,"created_at"),str(form.get("fold", "")))
    expires = local_time(required(form,"expires_at"),str(form.get("fold", "")))
    if created>time.time() or expires<=time.time() or expires<=created:
        raise ValueError("Bitte gültiges Ausstellungs- und Ablaufdatum des langlebigen Tokens angeben.")
    with transaction() as session:
        account = session.get(Account,1)
        account.external_id=xid
        account.token=vault().encrypt(token.encode()).decode()
        account.token_created,account.token_expires=created,expires
        account.status,account.error="connected",""
        account.permissions="instagram_business_basic,instagram_business_manage_insights (lesend geprüft)"
        enqueue(session,"sync_posts",f"manual:{nonce()}",{"account":1})
    return redirect("/settings")

@app.post("/settings/disconnect")
def disconnect(request: Request):
    with transaction() as session:
        account=session.get(Account,1)
        account.token=None
        account.status,account.error="manual",""
    return redirect("/settings")

@app.post("/settings/sync")
def sync_now(request: Request):
    with transaction() as session:
        account=session.get(Account,1)
        if not account.token:
            raise ValueError("Zuerst Instagram verbinden oder manuell weiterarbeiten.")
        active=session.scalar(select(Job).where(Job.kind=="sync_posts",Job.status.in_(("pending","running"))))
        if not active:
            enqueue(session,"sync_posts",f"manual:{nonce()}",{"account":1})
    return redirect("/settings")

@app.post("/settings/retry/{identifier}")
def retry(request: Request,identifier: str):
    with transaction() as session:
        job=get_or_fail(session,Job,identifier)
        if job.status=="failed":
            job.status,job.attempts,job.due_at="pending",0,time.time()
    return redirect("/settings")

@app.post("/settings/backup")
async def backup_setting(request: Request):
    form=await request.form()
    recipient=required(form,"recipient",120)
    if not re.fullmatch(r"age1[023456789acdefghjklmnpqrstuvwxyz]{58}",recipient):
        raise ValueError("Bitte einen gültigen öffentlichen age1-Empfänger eingeben.")
    with transaction() as session:
        session.merge(Setting(key="backup_recipient",value=recipient))
        enqueue(session,"full_backup",f"backup:{nonce()}")
    return redirect("/settings")

@app.post("/settings/backup-confirm")
def confirm_backup(request: Request):
    with transaction() as session:
        session.merge(Setting(key="external_backup_confirmed",value=str(time.time())))
    return redirect("/settings")

@app.get("/backups/{filename}")
def download_backup(request: Request,filename: str):
    if not re.fullmatch(r"nimo-\d{8}-\d{6}\.tar\.age",filename) or not (config.BACKUPS/filename).is_file():
        raise HTTPException(404)
    return FileResponse(config.BACKUPS/filename,filename=filename,media_type="application/octet-stream")

templates.env.globals["nonce"] = nonce
