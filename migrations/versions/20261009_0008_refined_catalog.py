"""Snapshots refinados preservando ofertas e importações legadas."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261009_0008"
down_revision = "20260923_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("refined_catalog_runs",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('validated','published','archived')", name="status_allowed"))
    op.create_index("ix_refined_catalog_runs_organization_id", "refined_catalog_runs", ["organization_id"])
    op.create_index("uq_refined_published_org", "refined_catalog_runs", ["organization_id"], unique=True, postgresql_where=sa.text("status = 'published'"))
    op.create_table("refined_catalog_items",
        sa.Column("run_id", sa.String(24), sa.ForeignKey("refined_catalog_runs.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("item_id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.String(20), nullable=False),
        sa.Column("record_key", sa.Text(), nullable=False),
        sa.Column("title_search", sa.Text(), nullable=False),
        sa.Column("family_id", sa.String(100), nullable=False),
        sa.Column("public_catalog", sa.Boolean(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.UniqueConstraint("run_id", "source_id", "record_key", name="uq_refined_run_source_key"))
    op.create_index("ix_refined_items_filter", "refined_catalog_items", ["run_id", "source_id", "family_id", "public_catalog"])
    op.create_table("refined_catalog_raw",
        sa.Column("run_id", sa.String(24), sa.ForeignKey("refined_catalog_runs.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("source_id", sa.String(20), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("payload", JSONB(), nullable=False))


def downgrade():
    # Snapshots são histórico, não dados descartáveis. Evita apagar por engano.
    raise RuntimeError("Rollback: republique a execução anterior; não remova histórico de snapshots")
