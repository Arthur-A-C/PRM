"""Comparações persistidas e seus itens ordenados.

Revision ID: 20260922_0003
Revises: 20260922_0002
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260922_0003"
down_revision: str | None = "20260922_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comparisons",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("creator_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("equivalence_status", sa.String(30), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("filters_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mode IN ('exploratoria')", name=op.f("ck_comparisons_mode_allowed")),
        sa.CheckConstraint(
            "equivalence_status IN ('nao_avaliado', 'sugerido', 'confirmado', 'rejeitado')",
            name=op.f("ck_comparisons_equivalence_status_allowed"),
        ),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], name="fk_comparisons_creator_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_comparisons_organization_id_organizations", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_comparisons"),
    )
    op.create_index("ix_comparisons_creator_id", "comparisons", ["creator_id"])
    op.create_index("ix_comparisons_organization_id", "comparisons", ["organization_id"])

    op.create_table(
        "comparison_items",
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["comparison_id"], ["comparisons.id"], name="fk_comparison_items_comparison_id_comparisons", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], name="fk_comparison_items_offer_id_offers", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_comparison_items"),
        sa.UniqueConstraint("comparison_id", "offer_id", name="uq_comparison_items_offer"),
        sa.UniqueConstraint("comparison_id", "position", name="uq_comparison_items_position"),
    )
    op.create_index("ix_comparison_items_comparison_id", "comparison_items", ["comparison_id"])
    op.create_index("ix_comparison_items_offer_id", "comparison_items", ["offer_id"])


def downgrade() -> None:
    op.drop_table("comparison_items")
    op.drop_table("comparisons")

