import time
import uuid
from sqlalchemy import create_engine, String, Text, Float, Integer, BigInteger, Boolean, JSON, Index, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


def uid():
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    created: Mapped[float] = mapped_column(Float, default=time.time)


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Session(Identity, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[float] = mapped_column(Float)


class Case(Identity, Base):
    __tablename__ = "cases"
    owner_id: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(240))
    customer: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(30), default="Medium")
    status: Mapped[str] = mapped_column(String(40), default="Draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    components: Mapped[list] = mapped_column(JSON, default=list)
    incident_start: Mapped[str] = mapped_column(String(40), default="")
    incident_end: Mapped[str] = mapped_column(String(40), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")


class Membership(Identity, Base):
    __tablename__ = "memberships"
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    __table_args__ = (Index("member_unique", "case_id", "user_id", unique=True),)


class Upload(Identity, Base):
    __tablename__ = "uploads"
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(500))
    roles: Mapped[list] = mapped_column(JSON)
    size: Mapped[int] = mapped_column(BigInteger)
    offset: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(40), default="Uploading")
    error: Mapped[str] = mapped_column(Text, default="")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class File(Identity, Base):
    __tablename__ = "files"
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    upload_id: Mapped[str] = mapped_column(String(32), index=True)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    lines: Mapped[int] = mapped_column(Integer, default=0)
    roles: Mapped[list] = mapped_column(JSON)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    file_id: Mapped[str] = mapped_column(String(32), index=True)
    line: Mapped[int] = mapped_column(Integer)
    byte_start: Mapped[int] = mapped_column(BigInteger)
    byte_end: Mapped[int] = mapped_column(BigInteger)
    timestamp: Mapped[str] = mapped_column(String(40), default="", index=True)
    severity: Mapped[str] = mapped_column(String(12), default="INFO", index=True)
    message: Mapped[str] = mapped_column(Text)
    __table_args__ = (Index("file_line_unique", "file_id", "line", unique=True),)


class Job(Identity, Base):
    __tablename__ = "jobs"
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(30), default="Queued", index=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[str] = mapped_column(Text, default="Queued")
    error: Mapped[str] = mapped_column(Text, default="")


class Run(Identity, Base):
    __tablename__ = "runs"
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    evidence_ids: Mapped[list] = mapped_column(JSON)
    config: Mapped[dict] = mapped_column(JSON)
    components: Mapped[list] = mapped_column(JSON)
    question: Mapped[str] = mapped_column(Text, default="")
    partial: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="Queued")
    stages: Mapped[list] = mapped_column(JSON, default=list)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    summary: Mapped[str] = mapped_column(Text, default="")
    digest: Mapped[str] = mapped_column(String(64), default="")
    approved_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approved_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_hash: Mapped[str] = mapped_column(String(64), default="")


class Message(Identity, Base):
    __tablename__ = "messages"
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(String(32), default="")


class Knowledge(Identity, Base):
    __tablename__ = "knowledge"
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(80))
    content: Mapped[dict] = mapped_column(JSON)
    author_id: Mapped[str] = mapped_column(String(32))


class Audit(Identity, Base):
    __tablename__ = "audit"
    actor_id: Mapped[str] = mapped_column(String(32))
    case_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True,
                       connect_args={"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {})
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_settings(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
DB = sessionmaker(engine, expire_on_commit=False)


def audit(db, actor, case_id, action, detail=None):
    db.add(Audit(actor_id=actor, case_id=case_id, action=action, detail=detail or {}))


def serialize(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
