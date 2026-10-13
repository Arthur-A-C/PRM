"""Snapshots analíticos paralelos; nenhuma FK altera ofertas legadas."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RefinedCatalogRun(Base):
    __tablename__ = "refined_catalog_runs"
    __table_args__ = (
        CheckConstraint("status IN ('validated','published','archived')", name="status_allowed"),
        Index("uq_refined_published_org", "organization_id", unique=True, postgresql_where=text("status = 'published'")),
    )
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    manifest: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefinedCatalogItem(Base):
    __tablename__ = "refined_catalog_items"
    __table_args__ = (
        UniqueConstraint("run_id", "source_id", "record_key", name="uq_refined_run_source_key"),
        Index("ix_refined_items_filter", "run_id", "source_id", "family_id", "public_catalog"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("refined_catalog_runs.id", ondelete="RESTRICT"), primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(20))
    record_key: Mapped[str] = mapped_column(Text)
    title_search: Mapped[str] = mapped_column(Text)
    family_id: Mapped[str] = mapped_column(String(100))
    public_catalog: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict] = mapped_column(JSONB)


class RefinedCatalogRaw(Base):
    __tablename__ = "refined_catalog_raw"
    run_id: Mapped[str] = mapped_column(ForeignKey("refined_catalog_runs.id", ondelete="RESTRICT"), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)
