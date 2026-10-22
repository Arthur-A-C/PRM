"""Per-store permissions for production file removal; new table only, no existing data touched."""
from alembic import op
from app.models.store_operations import STORE_OPERATION_TABLES

revision = "20261022_0012"
down_revision = "20261021_0011"
branch_labels = None
depends_on = None


def upgrade():
    for table in STORE_OPERATION_TABLES:
        table.create(op.get_bind(), checkfirst=False)


def downgrade():
    # Dropping permissions only removes authorizations; queues, journal and backups live elsewhere.
    for table in reversed(STORE_OPERATION_TABLES):
        table.drop(op.get_bind(), checkfirst=True)
