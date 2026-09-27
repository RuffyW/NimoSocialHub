import io
import time
import sqlite3
from PIL import Image
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app import config, backup
from app.db import engine, transaction
from app.models import Draft, Publication, Media, Observation, Job, Account
from app.timeutil import local_time
from app.metrics import comparable
from app.security import vault
from app.sync import run

def post(client, url, **data):
    return client.post(url, data={"csrf":client.csrf, **data}, follow_redirects=False)

def test_complete_manual_workflow(client):
    result = post(client,"/drafts/save", title="Sicher entdecken",topic="Sicherheit",format="reel",status="draft",planned_at="2026-10-01T12:00")
    assert result.status_code == 303, result.text
    draft_id = result.headers["location"].split("/")[-1]
    picture = io.BytesIO()
    Image.new("RGB",(40,30),"purple").save(picture,"PNG")
    uploaded = client.post("/media/upload",data={"csrf":client.csrf,"tags":"Marke"},files={"file":("bild.png",picture.getvalue(),"image/png")},follow_redirects=False)
    assert uploaded.status_code == 303, uploaded.text
    with Session(engine) as session:
        media_id = session.scalar(select(Media.id))
    assert post(client,f"/drafts/{draft_id}/media",order=media_id).status_code == 303
    result = post(client,"/publications",draft_id=draft_id,permalink="https://www.instagram.com/reel/TEST/",published_at="2026-09-01T12:00")
    assert result.status_code == 303, result.text
    pub_id = result.headers["location"].split("/")[-1]
    result = post(client,"/observations",publication_id=pub_id,metric="reach",value="0",observed_at="2026-09-08T12:00",entry_id="first")
    assert result.status_code == 303, result.text
    for url in ("/","/planning","/planning?view=calendar","/drafts/new",f"/drafts/{draft_id}",f"/publications/{pub_id}","/media","/topics","/analytics?source=manual","/settings"):
        result = client.get(url)
        assert result.status_code == 200, (url,result.text)
    with Session(engine) as session:
        pub = session.get(Publication,pub_id)
        assert comparable(session,pub,"reach",7,"manual").value == 0
        assert comparable(session,pub,"reach",1,"manual") is None
        assert session.get(Draft,draft_id).status == "published"
    result = post(client,f"/drafts/{draft_id}/reuse")
    assert result.status_code == 303
    with Session(engine) as session:
        new = session.get(Draft,result.headers["location"].split("/")[-1])
        assert new.planned_at is None and new.status == "draft"
        assert session.scalar(select(func.count()).select_from(Publication)) == 1

def test_access_upload_and_csrf(client,monkeypatch):
    assert client.post("/tasks",data={"text":"x"}).status_code == 403
    bad = client.post("/media/upload",data={"csrf":client.csrf},files={"file":("bad.png",b"<html>bad</html>","image/png")})
    assert bad.status_code == 400
    monkeypatch.setattr(config,"VIDEO_LIMIT",10)
    assert client.post("/media/upload",content=b"a"*(2*1024*1024+11)).status_code == 413
    client.cookies.clear()
    assert client.get("/media/any/original",follow_redirects=False).status_code == 303

def test_berlin_time_changes():
    import pytest
    with pytest.raises(ValueError): local_time("2026-03-29T02:30")
    with pytest.raises(ValueError): local_time("2026-10-25T02:30")
    assert local_time("2026-10-25T02:30","1")-local_time("2026-10-25T02:30","0") == 3600

def test_sync_reconciles_and_repeats_without_duplicates(client):
    post(client,"/publications",permalink="https://www.instagram.com/reel/TEST/",published_at="2026-09-01T12:00",format="reel")
    with transaction() as session:
        account = session.get(Account,1)
        account.token = vault().encrypt(b"fake-token").decode()
        account.status = "connected"
        account.external_id = "123"
        job = Job(key="sync-test",kind="sync_posts",payload='{"account":1}')
        session.add(job)
    class API:
        def __init__(self,token): pass
        def publications(self,*args):
            return {"data":[{"id":"999","permalink":"https://www.instagram.com/reel/TEST/","timestamp":"2026-09-01T10:00:00Z","media_product_type":"REELS","caption":"Test"}]}
        def close(self): pass
    run(job,API); run(job,API)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Publication)) == 1
        assert session.scalar(select(Publication.external_id)) == "999"

def test_consistent_snapshot(client,tmp_path):
    post(client,"/drafts/save",title="Sicherung",format="image",status="idea")
    backup.snapshot(tmp_path/"snapshot")
    db = sqlite3.connect(tmp_path/"snapshot/data/hub.sqlite3")
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("SELECT count(*) FROM drafts").fetchone()[0] == 1
    db.close()
    assert (tmp_path/"snapshot/secrets/vault.key").is_file()

def test_encrypted_restore(client,tmp_path,monkeypatch):
    import os, subprocess
    from pathlib import Path
    from app.models import Setting
    tool = config.ROOT/".tools/age"
    if tool.is_dir():
        monkeypatch.setenv("PATH",str(tool)+os.pathsep+os.environ["PATH"])
    identity = tmp_path/"identity.txt"
    subprocess.run(["age-keygen","-o",str(identity)],capture_output=True,check=True)
    recipient = subprocess.check_output(["age-keygen","-y",str(identity)],text=True).strip()
    post(client,"/drafts/save",title="Wiederherstellen",format="image",status="draft")
    image = io.BytesIO(); Image.new("RGB",(8,8)).save(image,"PNG")
    assert client.post("/media/upload",data={"csrf":client.csrf},files={"file":("test.png",image.getvalue(),"image/png")}).status_code == 200
    with transaction() as session:
        session.merge(Setting(key="backup_recipient",value=recipient))
    filename = backup.full()
    destination = tmp_path/"restored"
    backup.restore(config.BACKUPS/filename,identity,destination)
    db = sqlite3.connect(destination/"data/hub.sqlite3")
    assert db.execute("SELECT count(*) FROM drafts").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    for path,sha in db.execute("SELECT path,sha256 FROM media"):
        assert backup.checksum(destination/"media"/path) == sha
    db.close()
    assert (destination/"secrets/vault.key").read_bytes() == (config.SECRETS/"vault.key").read_bytes()

def test_restore_empty_media_archive(client,tmp_path,monkeypatch):
    import os,subprocess
    from app.models import Setting
    tool=config.ROOT/".tools/age"
    if tool.is_dir():
        monkeypatch.setenv("PATH",str(tool)+os.pathsep+os.environ["PATH"])
    identity=tmp_path/"identity.txt"
    subprocess.run(["age-keygen","-o",str(identity)],capture_output=True,check=True)
    recipient=subprocess.check_output(["age-keygen","-y",str(identity)],text=True).strip()
    with transaction() as session:
        session.merge(Setting(key="backup_recipient",value=recipient))
    destination=tmp_path/"restored"
    backup.restore(config.BACKUPS/backup.full(),identity,destination)
    assert (destination/"media/originals").is_dir()
    assert (destination/"media/previews").is_dir()
    assert (destination/"media/tmp").is_dir()

def test_leases_retries_and_api_errors(client):
    import httpx
    import pytest
    from app.jobs import claim,finish
    from app.instagram import Instagram,PlatformError
    with transaction() as session:
        session.add(Job(key="recover",kind="sync_posts",status="running",owner="old",lease_until=time.time()-1))
    job = claim()
    assert job.owner != "old" and job.attempts == 1
    finish(job,PlatformError("Rate limit",delay=900))
    with Session(engine) as session:
        assert session.get(Job,job.id).status == "pending"
        assert session.get(Job,job.id).due_at >= time.time()+890
    for code,payload,auth,retry in [(429,{"error":{"code":4}},False,True),(400,{"error":{"code":190}},True,False),(400,{"error":{"code":100}},False,False)]:
        api = Instagram("secret",httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(code,json=payload))))
        with pytest.raises(PlatformError) as caught: api.metric("123","reach")
        assert caught.value.auth == auth and caught.value.retry == retry
        assert "secret" not in str(caught.value)
        api.close()

def test_disconnect_during_refresh_does_not_restore_token(client):
    with transaction() as session:
        account = session.get(Account,1)
        account.token = vault().encrypt(b"old-token").decode()
        account.status = "connected"
        account.token_created = time.time()-31*86400
        account.token_expires = time.time()+29*86400
        job = Job(key="refresh-test",kind="refresh")
        session.add(job)
    class API:
        def __init__(self,token): pass
        def refresh(self):
            post(client,"/settings/disconnect")
            return {"access_token":"new-token","expires_in":60*86400}
        def close(self): pass
    run(job,API)
    with Session(engine) as session:
        account = session.get(Account,1)
        assert account.token is None and account.status == "manual"

def test_pagination_checkpoint_survives_interruption(client):
    import json
    from app.jobs import claim,finish
    from app.instagram import PlatformError
    with transaction() as session:
        account = session.get(Account,1)
        account.token = vault().encrypt(b"fake").decode()
        account.status = "connected"
        session.add(Job(key="firstpage",kind="sync_posts"))
    class API:
        fail = True
        def __init__(self,token): pass
        def close(self): pass
        def publications(self,xid,cursor):
            if cursor and self.fail: raise PlatformError("temporär")
            return {"data":[{"id":"2" if cursor else "1","permalink":"https://www.instagram.com/p/B/" if cursor else "https://www.instagram.com/p/A/","timestamp":"2026-09-01T10:00:00Z","media_type":"IMAGE"}],"paging":{} if cursor else {"next":"https://graph.instagram.com/example","cursors":{"after":"cursor-2"}}}
    first = claim(); run(first,API); finish(first)
    second = claim()
    assert json.loads(second.payload)["cursor"] == "cursor-2"
    import pytest
    with pytest.raises(PlatformError): run(second,API)
    with Session(engine) as session:
        assert session.get(Account,1).last_success is None
        assert session.scalar(select(func.count()).select_from(Publication)) == 1
    API.fail = False
    run(second,API); run(second,API); finish(second)
    with Session(engine) as session:
        assert session.get(Account,1).last_success is not None
        assert session.scalar(select(func.count()).select_from(Publication)) == 2

def test_missing_values_and_quota(client,monkeypatch):
    result = post(client,"/publications",permalink="https://www.instagram.com/p/MISSING/",published_at="2026-09-01T12:00",format="image")
    pid = result.headers["location"].split("/")[-1]
    for entry,value in (("zero","0"),("missing","")):
        assert post(client,"/observations",publication_id=pid,metric="reach",value=value,reason="unavailable",observed_at="2026-09-08T12:00",entry_id=entry).status_code == 303
    with Session(engine) as session:
        rows = {o.dedup_key:o for o in session.scalars(select(Observation))}
        assert rows["manual:zero"].value == 0 and rows["manual:zero"].reason is None
        assert rows["manual:missing"].value is None and rows["manual:missing"].reason == "unavailable"
    monkeypatch.setattr(config,"QUOTA",1)
    picture=io.BytesIO(); Image.new("RGB",(8,8)).save(picture,"PNG")
    response=client.post("/media/upload",data={"csrf":client.csrf},files={"file":("quota.png",picture.getvalue(),"image/png")})
    assert response.status_code == 400
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Media)) == 0

def test_refresh_outage_is_retryable_without_token_logs(caplog):
    import httpx,pytest,logging
    from app.instagram import Instagram,PlatformError
    caplog.set_level(logging.INFO)
    api=Instagram("do-not-log-this",httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(503,json={"error":{}}))))
    with pytest.raises(PlatformError) as caught: api.refresh()
    assert caught.value.retry and not caught.value.auth
    assert "do-not-log-this" not in caplog.text
    api.close()
