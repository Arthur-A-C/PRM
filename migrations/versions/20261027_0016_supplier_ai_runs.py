"""Supplier AI extraction runs: additive table only (audit, preview and short cache)."""
from alembic import op
import sqlalchemy as sa
revision = '20261027_0016'
down_revision = '20261026_0015'
branch_labels = depends_on = None

def upgrade():
    op.create_table('supplier_ai_runs',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('organization_id',sa.Uuid(),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('data',sa.JSON(),nullable=False),
        sa.Column('supplier_id',sa.Uuid(),sa.ForeignKey('suppliers.id'),nullable=False),
        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('source_type',sa.String(30),nullable=False),
        sa.Column('source_hash',sa.String(64),nullable=False),
        sa.Column('model',sa.String(120),nullable=False),
        sa.Column('status',sa.String(20),nullable=False))
    for field in ('supplier_id','organization_id','source_hash'):
        op.create_index('ix_supplier_ai_runs_'+field,'supplier_ai_runs',[field])

def downgrade():
    op.drop_table('supplier_ai_runs')
