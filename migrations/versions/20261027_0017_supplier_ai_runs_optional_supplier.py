"""Supplier AI runs may exist before the supplier (Novo fornecedor com IA): supplier_id becomes nullable. No data change."""
from alembic import op
import sqlalchemy as sa
revision = '20261027_0017'
down_revision = '20261027_0016'
branch_labels = depends_on = None

def upgrade():
    with op.batch_alter_table('supplier_ai_runs') as table:
        table.alter_column('supplier_id', existing_type=sa.Uuid(), nullable=True)

def downgrade():
    # Analyses of suppliers never created have no supplier to point to; they are dropped before restoring NOT NULL.
    op.execute('DELETE FROM supplier_ai_runs WHERE supplier_id IS NULL')
    with op.batch_alter_table('supplier_ai_runs') as table:
        table.alter_column('supplier_id', existing_type=sa.Uuid(), nullable=False)
