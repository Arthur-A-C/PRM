"""Pauta Semanal de Desenvolvimento: one agenda per organization and week, its audit trail and settings."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WeeklyAgenda(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Collected evidence (sources), generated/edited items and human additions (manual) for one week."""

    __tablename__ = "weekly_agendas"
    __table_args__ = (UniqueConstraint("organization_id", "week_start", name="uq_weekly_agenda_week"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft | approved | archived
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(240))
    overview: Mapped[str] = mapped_column(Text, default="")
    items: Mapped[list] = mapped_column(JSON, default=list)
    manual: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[dict] = mapped_column(JSON, default=dict)
    generation: Mapped[dict] = mapped_column(JSON, default=dict)
    search_text: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class WeeklyAgendaRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only authorship trail: who generated, edited, approved, archived or exported what."""

    __tablename__ = "weekly_agenda_revisions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    agenda_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("weekly_agendas.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)  # None = scheduled worker
    action: Mapped[str] = mapped_column(String(40))
    changes: Mapped[dict] = mapped_column(JSON, default=dict)


class WeeklyAgendaSettings(TimestampMixin, Base):
    """Per-organization schedule and options; repository and token stay in backend configuration."""

    __tablename__ = "weekly_agenda_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    weekday: Mapped[int] = mapped_column(Integer, default=4)  # 0 = Monday ... 4 = Friday
    draft_time: Mapped[str] = mapped_column(String(5), default="08:00")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    planner_filter: Mapped[str] = mapped_column(String(120), default="")
    people: Mapped[dict] = mapped_column(JSON, default=dict)  # GitHub login -> display name
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


WEEKLY_AGENDA_TABLES = (WeeklyAgenda.__table__, WeeklyAgendaRevision.__table__, WeeklyAgendaSettings.__table__)
