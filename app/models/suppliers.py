"""Supplier CRM, independent of meeting Activity until an explicit future integration."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

class Supplier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'suppliers'
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    responsible_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(50), default='base_ativa', index=True)
    score: Mapped[str] = mapped_column(String(30), default='morno')
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

class SupplierChild(UUIDPrimaryKeyMixin, TimestampMixin):
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('suppliers.id'), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    data: Mapped[dict] = mapped_column(JSON, default=dict)

class SupplierContact(SupplierChild, Base):
    __tablename__ = 'supplier_contacts'

class SupplierInteraction(SupplierChild, Base):
    __tablename__ = 'supplier_interactions'
    event: Mapped[str] = mapped_column(String(60))

class SupplierTask(SupplierChild, Base):
    __tablename__ = 'supplier_tasks'
    assignee_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), index=True)

class SupplierDocument(SupplierChild, Base):
    __tablename__ = 'supplier_documents'

MODELS = (Supplier, SupplierContact, SupplierInteraction, SupplierTask, SupplierDocument)

class SupplierAIRun(SupplierChild, Base):
    """AI extraction audit + preview + short cache. Never written to the supplier until a reviewed apply.
    supplier_id is empty while a new supplier is being created with AI, and linked when it is created."""
    __tablename__ = 'supplier_ai_runs'
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('suppliers.id'), index=True, nullable=True)
    source_type: Mapped[str] = mapped_column(String(30))
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))

AI_MODELS = (SupplierAIRun,)

class SupplierDeletionAudit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Minimal durable evidence retained after a supplier and its FK children are removed."""
    __tablename__ = 'supplier_deletion_audits'
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON, default=dict)

AUDIT_MODELS = (SupplierDeletionAudit,)
