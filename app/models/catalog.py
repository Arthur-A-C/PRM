import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_name", name="uq_brands_org_normalized"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)


class BrandAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brand_aliases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "normalized_alias", name="uq_brand_aliases_org_normalized"
        ),
        CheckConstraint("source IN ('importado', 'manual', 'seed')", name="source_allowed"),
        CheckConstraint(
            "review_status IN ('sugerido', 'revisado')", name="review_status_allowed"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_name", name="uq_categories_org_normalized"),
        CheckConstraint("review_status IN ('sugerido', 'revisado')", name="review_status_allowed"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="importado")
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="sugerido")


class CatalogImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_imports"
    __table_args__ = (
        UniqueConstraint("company_id", "file_sha256", name="uq_catalog_import_company_hash"),
        CheckConstraint(
            "status IN ('processing', 'published', 'failed')", name="status_allowed"
        ),
        Index("ix_catalog_imports_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    header_row: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)

    rows: Mapped[list["ImportRow"]] = relationship(back_populates="catalog_import")


class Offer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("company_id", "external_code", name="uq_offers_company_code"),
        CheckConstraint(
            "availability_state IN ('em_estoque', 'fora_estoque', 'sob_encomenda', 'nao_informado')",
            name="availability_allowed",
        ),
        Index("ix_offers_company_active", "company_id", "active"),
        Index("ix_offers_brand_id", "brand_id"),
        Index("ix_offers_category_id", "category_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL")
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    external_code: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer_code: Mapped[str | None] = mapped_column(String(255))
    reference: Mapped[str | None] = mapped_column(String(500))
    name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    description_raw: Mapped[str | None] = mapped_column(Text)
    description_display: Mapped[str | None] = mapped_column(Text)
    application_raw: Mapped[str | None] = mapped_column(Text)
    brand_raw: Mapped[str | None] = mapped_column(String(500))
    category_raw: Mapped[str | None] = mapped_column(String(500))
    subcategory_raw: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(Text)
    unit_raw: Mapped[str | None] = mapped_column(String(100))
    supplier_raw: Mapped[str | None] = mapped_column(String(500))
    country_raw: Mapped[str | None] = mapped_column(String(255))
    availability_raw: Mapped[str | None] = mapped_column(String(500))
    availability_state: Mapped[str] = mapped_column(String(30), nullable=False)
    stock_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    excluded_from_analytics: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    exclusion_reason: Mapped[str | None] = mapped_column(String(500))


class ImportRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        UniqueConstraint("catalog_import_id", "row_number", name="uq_import_rows_batch_row"),
    )

    catalog_import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("offers.id", ondelete="SET NULL"), index=True
    )
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    catalog_import: Mapped[CatalogImport] = relationship(back_populates="rows")


class OfferObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_observations"
    __table_args__ = (
        UniqueConstraint("offer_id", "catalog_import_id", name="uq_observations_offer_import"),
        Index("ix_observations_offer_imported", "offer_id", "imported_at"),
    )

    offer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    catalog_import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_imports.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    availability_raw: Mapped[str | None] = mapped_column(String(500))
    availability_state: Mapped[str] = mapped_column(String(30), nullable=False)
    stock_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OfferPrice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_prices"
    __table_args__ = (
        UniqueConstraint("observation_id", "modality", name="uq_offer_prices_observation_modality"),
        CheckConstraint("state IN ('valido', 'nao_informado', 'invalido')", name="state_allowed"),
        Index("ix_offer_prices_modality_amount", "modality", "amount"),
    )

    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offer_observations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    modality: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    raw_value: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), nullable=False)


class AttributeDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attribute_definitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_attribute_definitions_org_key"),
        CheckConstraint(
            "data_type IN ('texto', 'numero', 'booleano')", name="data_type_allowed"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    canonical_unit: Mapped[str | None] = mapped_column(String(50))
    comparable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class OfferAttribute(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_attributes"
    __table_args__ = (
        UniqueConstraint("offer_id", "definition_id", name="uq_offer_attributes_offer_definition"),
        CheckConstraint(
            "method IN ('importado', 'regra', 'ia', 'manual')", name="method_allowed"
        ),
        CheckConstraint(
            "review_status IN ('sugerido', 'revisado', 'rejeitado')",
            name="review_status_allowed",
        ),
    )

    offer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attribute_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    value_text: Mapped[str | None] = mapped_column(Text)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    unit: Mapped[str | None] = mapped_column(String(50))
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="sugerido"
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
