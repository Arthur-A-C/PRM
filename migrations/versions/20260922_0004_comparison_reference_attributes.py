"""Referência de preço e atributos técnicos normalizados.

Revision ID: 20260922_0004
Revises: 20260922_0003
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260922_0004"
down_revision: str | None = "20260922_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("comparisons", sa.Column("reference_offer_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_comparisons_reference_offer_id_offers",
        "comparisons",
        "offers",
        ["reference_offer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_comparisons_reference_offer_id", "comparisons", ["reference_offer_id"]
    )

    op.create_table(
        "attribute_definitions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("canonical_unit", sa.String(50), nullable=True),
        sa.Column("comparable", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "data_type IN ('texto', 'numero', 'booleano')",
            name=op.f("ck_attribute_definitions_data_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_attribute_definitions_category_id_categories",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_attribute_definitions_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attribute_definitions"),
        sa.UniqueConstraint(
            "organization_id", "key", name="uq_attribute_definitions_org_key"
        ),
    )
    op.create_index(
        "ix_attribute_definitions_organization_id",
        "attribute_definitions",
        ["organization_id"],
    )
    op.create_index(
        "ix_attribute_definitions_category_id", "attribute_definitions", ["category_id"]
    )

    op.create_table(
        "offer_attributes",
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_numeric", sa.Numeric(20, 6), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "method IN ('importado', 'regra', 'ia', 'manual')",
            name=op.f("ck_offer_attributes_method_allowed"),
        ),
        sa.CheckConstraint(
            "review_status IN ('sugerido', 'revisado', 'rejeitado')",
            name=op.f("ck_offer_attributes_review_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["definition_id"],
            ["attribute_definitions.id"],
            name="fk_offer_attributes_definition_id_attribute_definitions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offers.id"],
            name="fk_offer_attributes_offer_id_offers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name="fk_offer_attributes_reviewed_by_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_offer_attributes"),
        sa.UniqueConstraint(
            "offer_id", "definition_id", name="uq_offer_attributes_offer_definition"
        ),
    )
    op.create_index("ix_offer_attributes_offer_id", "offer_attributes", ["offer_id"])
    op.create_index(
        "ix_offer_attributes_definition_id", "offer_attributes", ["definition_id"]
    )
    op.create_index(
        "ix_offer_attributes_reviewed_by_id", "offer_attributes", ["reviewed_by_id"]
    )


def downgrade() -> None:
    op.drop_table("offer_attributes")
    op.drop_table("attribute_definitions")
    op.drop_index("ix_comparisons_reference_offer_id", table_name="comparisons")
    op.drop_constraint(
        "fk_comparisons_reference_offer_id_offers", "comparisons", type_="foreignkey"
    )
    op.drop_column("comparisons", "reference_offer_id")
