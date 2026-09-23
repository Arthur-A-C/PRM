"""Execuções e candidatos de correspondência entre catálogos.

Revision ID: 20260922_0005
Revises: 20260922_0004
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260922_0005"
down_revision: str | None = "20260922_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_match_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("competitor_company_id", sa.Uuid(), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("competitor_total", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("suggested_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name=op.f("ck_catalog_match_runs_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["competitor_company_id"], ["companies.id"],
            name="fk_catalog_match_runs_competitor_company_id_companies", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_catalog_match_runs_organization_id_organizations", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_match_runs"),
    )
    op.create_index("ix_catalog_match_runs_organization_id", "catalog_match_runs", ["organization_id"])
    op.create_index("ix_catalog_match_runs_competitor_company_id", "catalog_match_runs", ["competitor_company_id"])

    op.create_table(
        "catalog_matches",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("competitor_offer_id", sa.Uuid(), nullable=False),
        sa.Column("own_offer_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(7, 5), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('candidato', 'sugerido', 'confirmado', 'rejeitado')",
            name=op.f("ck_catalog_matches_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["competitor_offer_id"], ["offers.id"],
            name="fk_catalog_matches_competitor_offer_id_offers", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["own_offer_id"], ["offers.id"],
            name="fk_catalog_matches_own_offer_id_offers", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["users.id"],
            name="fk_catalog_matches_reviewed_by_id_users", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["catalog_match_runs.id"],
            name="fk_catalog_matches_run_id_catalog_match_runs", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_matches"),
        sa.UniqueConstraint(
            "run_id", "competitor_offer_id", "own_offer_id", name="uq_catalog_matches_pair"
        ),
        sa.UniqueConstraint(
            "run_id", "competitor_offer_id", "rank", name="uq_catalog_matches_rank"
        ),
    )
    op.create_index("ix_catalog_matches_run_id", "catalog_matches", ["run_id"])
    op.create_index("ix_catalog_matches_competitor_offer_id", "catalog_matches", ["competitor_offer_id"])
    op.create_index("ix_catalog_matches_own_offer_id", "catalog_matches", ["own_offer_id"])
    op.create_index("ix_catalog_matches_reviewed_by_id", "catalog_matches", ["reviewed_by_id"])


def downgrade() -> None:
    op.drop_table("catalog_matches")
    op.drop_table("catalog_match_runs")
