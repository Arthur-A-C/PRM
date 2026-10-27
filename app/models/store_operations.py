"""Legacy per-store permission records, retained for history and migration compatibility."""
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

STORE_COMPANIES = ("choice", "sag", "portwell")


class StoreOperationPermission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Historical assignments; removal role-v1 ignores these rows (including absent rows)."""

    __tablename__ = "store_operation_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "company", name="uq_store_operation_permissions_user_company"),
        CheckConstraint("company IN ('choice', 'sag', 'portwell')", name="company_allowed"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(20), nullable=False)
    can_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_execute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_restore: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Historical environment administration. Current removal privileges come from the active user's role.
    can_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


STORE_OPERATION_TABLES = (StoreOperationPermission.__table__,)
