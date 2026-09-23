"""Catálogos, importações auditáveis, ofertas e preços.

Revision ID: 20260922_0002
Revises: 20260922_0001
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260922_0002"
down_revision: str | None = "20260922_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_brands_organization_id_organizations", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_brands"),
        sa.UniqueConstraint("organization_id", "normalized_name", name="uq_brands_org_normalized"),
    )
    op.create_index("ix_brands_organization_id", "brands", ["organization_id"])

    op.create_table(
        "categories",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("review_status IN ('sugerido', 'revisado')", name=op.f("ck_categories_review_status_allowed")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_categories_organization_id_organizations", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("organization_id", "normalized_name", name="uq_categories_org_normalized"),
    )
    op.create_index("ix_categories_organization_id", "categories", ["organization_id"])

    op.create_table(
        "catalog_imports",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("source_path", sa.String(500), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("header_row", sa.Integer(), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('processing', 'published', 'failed')", name=op.f("ck_catalog_imports_status_allowed")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_catalog_imports_company_id_companies", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_catalog_imports_created_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_catalog_imports_organization_id_organizations", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_imports"),
        sa.UniqueConstraint("company_id", "file_sha256", name="uq_catalog_import_company_hash"),
    )
    op.create_index("ix_catalog_imports_company_id", "catalog_imports", ["company_id"])
    op.create_index("ix_catalog_imports_created_by_id", "catalog_imports", ["created_by_id"])
    op.create_index("ix_catalog_imports_organization_id", "catalog_imports", ["organization_id"])
    op.create_index("ix_catalog_imports_org_status", "catalog_imports", ["organization_id", "status"])

    op.create_table(
        "offers",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("external_code", sa.String(255), nullable=False),
        sa.Column("manufacturer_code", sa.String(255), nullable=True),
        sa.Column("reference", sa.String(500), nullable=True),
        sa.Column("name_raw", sa.Text(), nullable=False),
        sa.Column("description_raw", sa.Text(), nullable=True),
        sa.Column("description_display", sa.Text(), nullable=True),
        sa.Column("application_raw", sa.Text(), nullable=True),
        sa.Column("brand_raw", sa.String(500), nullable=True),
        sa.Column("category_raw", sa.String(500), nullable=True),
        sa.Column("subcategory_raw", sa.String(500), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("unit_raw", sa.String(100), nullable=True),
        sa.Column("supplier_raw", sa.String(500), nullable=True),
        sa.Column("country_raw", sa.String(255), nullable=True),
        sa.Column("availability_raw", sa.String(500), nullable=True),
        sa.Column("availability_state", sa.String(30), nullable=False),
        sa.Column("stock_quantity", sa.Numeric(20, 6), nullable=True),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("excluded_from_analytics", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("availability_state IN ('em_estoque', 'fora_estoque', 'sob_encomenda', 'nao_informado')", name=op.f("ck_offers_availability_allowed")),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], name="fk_offers_brand_id_brands", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name="fk_offers_category_id_categories", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_offers_company_id_companies", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_offers_organization_id_organizations", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_offers"),
        sa.UniqueConstraint("company_id", "external_code", name="uq_offers_company_code"),
    )
    op.create_index("ix_offers_organization_id", "offers", ["organization_id"])
    op.create_index("ix_offers_brand_id", "offers", ["brand_id"])
    op.create_index("ix_offers_category_id", "offers", ["category_id"])
    op.create_index("ix_offers_company_active", "offers", ["company_id", "active"])

    op.create_table(
        "import_rows",
        sa.Column("catalog_import_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=True),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_row", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["catalog_import_id"], ["catalog_imports.id"], name="fk_import_rows_catalog_import_id_catalog_imports", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], name="fk_import_rows_offer_id_offers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_import_rows"),
        sa.UniqueConstraint("catalog_import_id", "row_number", name="uq_import_rows_batch_row"),
    )
    op.create_index("ix_import_rows_catalog_import_id", "import_rows", ["catalog_import_id"])
    op.create_index("ix_import_rows_offer_id", "import_rows", ["offer_id"])

    op.create_table(
        "offer_observations",
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_import_id", sa.Uuid(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("availability_raw", sa.String(500), nullable=True),
        sa.Column("availability_state", sa.String(30), nullable=False),
        sa.Column("stock_quantity", sa.Numeric(20, 6), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["catalog_import_id"], ["catalog_imports.id"], name="fk_offer_observations_catalog_import_id_catalog_imports", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], name="fk_offer_observations_offer_id_offers", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_offer_observations"),
        sa.UniqueConstraint("offer_id", "catalog_import_id", name="uq_observations_offer_import"),
    )
    op.create_index("ix_offer_observations_catalog_import_id", "offer_observations", ["catalog_import_id"])
    op.create_index("ix_offer_observations_offer_id", "offer_observations", ["offer_id"])
    op.create_index("ix_observations_offer_imported", "offer_observations", ["offer_id", "imported_at"])

    op.create_table(
        "offer_prices",
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("modality", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(20, 6), nullable=True),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("state IN ('valido', 'nao_informado', 'invalido')", name=op.f("ck_offer_prices_state_allowed")),
        sa.ForeignKeyConstraint(["observation_id"], ["offer_observations.id"], name="fk_offer_prices_observation_id_offer_observations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_offer_prices"),
        sa.UniqueConstraint("observation_id", "modality", name="uq_offer_prices_observation_modality"),
    )
    op.create_index("ix_offer_prices_observation_id", "offer_prices", ["observation_id"])
    op.create_index("ix_offer_prices_modality_amount", "offer_prices", ["modality", "amount"])


def downgrade() -> None:
    op.drop_table("offer_prices")
    op.drop_table("offer_observations")
    op.drop_table("import_rows")
    op.drop_table("offers")
    op.drop_table("catalog_imports")
    op.drop_table("categories")
    op.drop_table("brands")

