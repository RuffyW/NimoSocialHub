import time
import uuid
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, ForeignKey, UniqueConstraint
from .db import Base

def uid():
    return uuid.uuid4().hex

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    platform = Column(String, nullable=False, default="instagram")
    external_id = Column(String)
    handle = Column(String, nullable=False, default="meinnimo")
    token = Column(Text)
    token_created = Column(Float)
    token_expires = Column(Float)
    permissions = Column(Text, default="")
    status = Column(String, default="manual")
    error = Column(Text, default="")
    last_success = Column(Float)
    last_attempt = Column(Float)

class Idea(Base):
    __tablename__ = "ideas"
    id = Column(String, primary_key=True, default=uid)
    title = Column(String, nullable=False)
    topic = Column(String, default="")
    audience = Column(String, default="Eltern")
    notes = Column(Text, default="")
    origin_id = Column(String, ForeignKey("ideas.id"))

class Draft(Base):
    __tablename__ = "drafts"
    id = Column(String, primary_key=True, default=uid)
    idea_id = Column(String, ForeignKey("ideas.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, default=1)
    format = Column(String, default="reel")
    caption = Column(Text, default="")
    status = Column(String, default="idea")
    planned_at = Column(Float)
    created_at = Column(Float, default=time.time)

class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("account_id", "external_id"), UniqueConstraint("account_id", "permalink"), UniqueConstraint("draft_id"))
    id = Column(String, primary_key=True, default=uid)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, default=1)
    draft_id = Column(String, ForeignKey("drafts.id"))
    external_id = Column(String)
    permalink = Column(String, nullable=False)
    published_at = Column(Float, nullable=False)
    format = Column(String, nullable=False)
    caption = Column(Text, default="")
    preview_url = Column(Text)
    media_id = Column(String, ForeignKey("media.id"))
    source = Column(String, default="manual")

class Media(Base):
    __tablename__ = "media"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True)
    sha256 = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    width = Column(Integer)
    height = Column(Integer)
    duration = Column(Float)
    tags = Column(String, default="")
    preview = Column(String)
    preview_status = Column(String, default="pending")
    created_at = Column(Float, default=time.time)

class Attachment(Base):
    __tablename__ = "attachments"
    draft_id = Column(String, ForeignKey("drafts.id"), primary_key=True)
    media_id = Column(String, ForeignKey("media.id"), primary_key=True)
    position = Column(Integer, nullable=False)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True, default=uid)
    draft_id = Column(String, ForeignKey("drafts.id"))
    text = Column(String, nullable=False)
    due_at = Column(Float)
    done = Column(Boolean, default=False)

class Metric(Base):
    __tablename__ = "metric_definitions"
    key = Column(String, primary_key=True)
    label = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    unit = Column(String, default="Anzahl")
    scope = Column(String, nullable=False)

class Observation(Base):
    __tablename__ = "observations"
    id = Column(String, primary_key=True, default=uid)
    dedup_key = Column(String, unique=True, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, default=1)
    publication_id = Column(String, ForeignKey("publications.id"))
    metric = Column(String, ForeignKey("metric_definitions.key"), nullable=False)
    value = Column(Float)
    reason = Column(String)
    observed_at = Column(Float, nullable=False)
    period_start = Column(Float)
    period_end = Column(Float)
    source = Column(String, nullable=False)
    api_version = Column(String)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=uid)
    key = Column(String, unique=True, nullable=False)
    kind = Column(String, nullable=False)
    payload = Column(Text, default="{}")
    status = Column(String, default="pending")
    due_at = Column(Float, default=time.time)
    attempts = Column(Integer, default=0)
    lease_until = Column(Float)
    owner = Column(String)
    error = Column(Text, default="")
    completed_at = Column(Float)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)

class LoginSession(Base):
    __tablename__ = "sessions"
    digest = Column(String, primary_key=True)
    csrf = Column(String, nullable=False)
    expires = Column(Float, nullable=False)

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id = Column(String, primary_key=True, default=uid)
    address = Column(String, nullable=False)
    at = Column(Float, default=time.time)
