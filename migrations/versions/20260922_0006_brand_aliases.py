"""Aliases de marca e consolidação revisada de ELFIN.

Revision ID: 20260922_0006
Revises: 20260922_0005
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260922_0006"
down_revision: str | None = "20260922_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brand_aliases",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("normalized_alias", sa.String(255), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "source IN ('importado', 'manual', 'seed')",
            name=op.f("ck_brand_aliases_source_allowed"),
        ),
        sa.CheckConstraint(
            "review_status IN ('sugerido', 'revisado')",
            name=op.f("ck_brand_aliases_review_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"], ["brands.id"],
            name="fk_brand_aliases_brand_id_brands", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_brand_aliases_organization_id_organizations", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_brand_aliases"),
        sa.UniqueConstraint(
            "organization_id", "normalized_alias", name="uq_brand_aliases_org_normalized"
        ),
    )
    op.create_index("ix_brand_aliases_organization_id", "brand_aliases", ["organization_id"])
    op.create_index("ix_brand_aliases_brand_id", "brand_aliases", ["brand_id"])

    op.execute(
        """
        UPDATE offers AS offer
        SET brand_id = canonical.id, updated_at = now()
        FROM brands AS variant
        JOIN brands AS canonical
          ON canonical.organization_id = variant.organization_id
         AND canonical.normalized_name = 'elfin'
        WHERE offer.brand_id = variant.id
          AND variant.normalized_name = 'new elfin srl'
        """
    )
    op.execute(
        """
        DELETE FROM brands AS variant
        WHERE variant.normalized_name = 'new elfin srl'
          AND EXISTS (
            SELECT 1 FROM brands AS canonical
            WHERE canonical.organization_id = variant.organization_id
              AND canonical.normalized_name = 'elfin'
          )
        """
    )
    op.execute(
        """
        INSERT INTO brand_aliases
          (id, organization_id, brand_id, alias, normalized_alias, source, review_status)
        SELECT CAST(md5(organization_id::text || '-brand-alias-elfin') AS uuid),
               organization_id, id, 'ELFIN', 'elfin', 'seed', 'revisado'
        FROM brands WHERE normalized_name = 'elfin'
        """
    )
    op.execute(
        """
        INSERT INTO brand_aliases
          (id, organization_id, brand_id, alias, normalized_alias, source, review_status)
        SELECT CAST(md5(organization_id::text || '-brand-alias-new-elfin-srl') AS uuid),
               organization_id, id, 'NEW ELFIN SRL', 'new elfin srl', 'seed', 'revisado'
        FROM brands WHERE normalized_name = 'elfin'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO brands (id, organization_id, canonical_name, normalized_name)
        SELECT CAST(md5(organization_id::text || '-brand-restored-new-elfin-srl') AS uuid),
               organization_id, 'NEW ELFIN SRL', 'new elfin srl'
        FROM brands AS canonical
        WHERE normalized_name = 'elfin'
          AND NOT EXISTS (
            SELECT 1 FROM brands AS variant
            WHERE variant.organization_id = canonical.organization_id
              AND variant.normalized_name = 'new elfin srl'
          )
        """
    )
    op.execute(
        """
        UPDATE offers AS offer
        SET brand_id = variant.id, updated_at = now()
        FROM brands AS variant
        WHERE offer.organization_id = variant.organization_id
          AND variant.normalized_name = 'new elfin srl'
          AND lower(trim(offer.brand_raw)) = 'new elfin srl'
        """
    )
    op.drop_table("brand_aliases")
