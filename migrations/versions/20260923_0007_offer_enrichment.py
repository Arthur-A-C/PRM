"""Enriquecimento técnico rastreável por oferta.

Revision ID: 20260923_0007
Revises: 20260922_0006
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260923_0007"
down_revision: str | None = "20260922_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "offer_enrichments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("family", sa.String(255), nullable=True),
        sa.Column("family_group", sa.String(255), nullable=True),
        sa.Column("model_reference", sa.String(255), nullable=True),
        sa.Column("normalized_title", sa.Text(), nullable=True),
        sa.Column("search_codes", JSONB(), nullable=False),
        sa.Column("attributes", JSONB(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('regra', 'pipeline')", name=op.f("ck_offer_enrichments_source_allowed")),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], name="fk_offer_enrichments_offer_id_offers", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_offer_enrichments"),
        sa.UniqueConstraint("offer_id", name="uq_offer_enrichments_offer"),
    )
    op.create_index("ix_offer_enrichments_offer_id", "offer_enrichments", ["offer_id"])


def downgrade() -> None:
    op.drop_table("offer_enrichments")
