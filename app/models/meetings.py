"""Single task/event store for Cards, Planner and Alerts; no parallel task registry."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Meeting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "meetings"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(240))
    partner: Mapped[str] = mapped_column(String(240), default="")
    opportunity: Mapped[str] = mapped_column(String(240), default="")
    meeting_date: Mapped[date | None] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    metadata_confirmed: Mapped[dict] = mapped_column(JSON, default=dict)
    participants: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TranscriptRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "meeting_revisions"
    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(20), default="text")
    original: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    segments: Mapped[list] = mapped_column(JSON)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)


class MeetingRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "meeting_runs"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_meeting_run_key"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id"), index=True)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meeting_revisions.id"))
    predecessor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meeting_runs.id"))
    stage: Mapped[str] = mapped_column(String(20))
    key: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_output: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(500))


class MeetingAudio(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "meeting_audio"
    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(240))
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)


class Activity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("organization_id", "analysis_run_id", "proposal_local_id", name="uq_activity_proposal"),
        CheckConstraint("due_date IS NULL OR due_at IS NULL", name="exclusive_deadline"),
        Index("ix_activity_planner", "organization_id", "assignee_user_id", "status", "due_date"),
        Index("ix_activity_instant", "organization_id", "due_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id"), index=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meeting_runs.id"))
    proposal_local_id: Mapped[str] = mapped_column(String(60))
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    approval: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    status: Mapped[str] = mapped_column(String(30), default="todo")
    due_date: Mapped[date | None] = mapped_column(Date)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    no_deadline_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    deadline_version: Mapped[int] = mapped_column(Integer, default=1)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityAudit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "activity_audits"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("activities.id"), index=True)
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meetings.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)


class ActivityAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "activity_alerts"
    __table_args__ = (UniqueConstraint("activity_id", "deadline_version", "kind", "recipient_id", name="uq_activity_alert_identity"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    deadline_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


MEETING_TABLES = [Meeting.__table__, TranscriptRevision.__table__, MeetingRun.__table__, MeetingAudio.__table__,
                  Activity.__table__, ActivityAudit.__table__, ActivityAlert.__table__]
