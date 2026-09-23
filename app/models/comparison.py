import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Comparison(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "comparisons"
    __table_args__ = (
        CheckConstraint("mode IN ('exploratoria')", name="mode_allowed"),
        CheckConstraint(
            "equivalence_status IN ('nao_avaliado', 'sugerido', 'confirmado', 'rejeitado')",
            name="equivalence_status_allowed",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reference_offer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("offers.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="exploratoria")
    equivalence_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="nao_avaliado"
    )
    conclusion: Mapped[str | None] = mapped_column(Text)
    filters_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    items: Mapped[list["ComparisonItem"]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan", order_by="ComparisonItem.position"
    )


class ComparisonItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "comparison_items"
    __table_args__ = (
        UniqueConstraint("comparison_id", "offer_id", name="uq_comparison_items_offer"),
        UniqueConstraint("comparison_id", "position", name="uq_comparison_items_position"),
    )

    comparison_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comparisons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    comparison: Mapped[Comparison] = relationship(back_populates="items")
