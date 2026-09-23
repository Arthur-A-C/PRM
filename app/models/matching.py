import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CatalogMatchRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_match_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'completed', 'failed')", name="status_allowed"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    competitor_company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    algorithm_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    competitor_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suggested_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)


class CatalogMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_matches"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "competitor_offer_id", "own_offer_id", name="uq_catalog_matches_pair"
        ),
        UniqueConstraint(
            "run_id", "competitor_offer_id", "rank", name="uq_catalog_matches_rank"
        ),
        CheckConstraint(
            "status IN ('candidato', 'sugerido', 'confirmado', 'rejeitado')",
            name="status_allowed",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_match_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competitor_offer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    own_offer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(7, 5), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    justification: Mapped[str | None] = mapped_column(Text)
