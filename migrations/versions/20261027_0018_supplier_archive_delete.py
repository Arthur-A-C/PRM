"""Safe supplier archive and durable deletion audit."""
from alembic import op
import sqlalchemy as sa

revision = '20261027_0018'
down_revision = '20261027_0017'
branch_labels = depends_on = None

def upgrade():
    with op.batch_alter_table('suppliers') as table:
        table.add_column(sa.Column('archived_at',sa.DateTime(timezone=True),nullable=True))
        table.add_column(sa.Column('archived_by',sa.Uuid(),nullable=True))
        table.create_foreign_key('fk_suppliers_archived_by_users','users',['archived_by'],['id'],ondelete='SET NULL')
        table.create_index('ix_suppliers_archived_at',['archived_at'])
    op.create_table('supplier_deletion_audits',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('organization_id',sa.Uuid(),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('supplier_id',sa.Uuid(),nullable=False),
        sa.Column('supplier_name',sa.String(200),nullable=False),
        sa.Column('data',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index('ix_supplier_deletion_audits_organization_id','supplier_deletion_audits',['organization_id'])
    op.create_index('ix_supplier_deletion_audits_supplier_id','supplier_deletion_audits',['supplier_id'])

def downgrade():
    op.drop_table('supplier_deletion_audits')
    with op.batch_alter_table('suppliers') as table:
        table.drop_index('ix_suppliers_archived_at')
        table.drop_constraint('fk_suppliers_archived_by_users',type_='foreignkey')
        table.drop_column('archived_by')
        table.drop_column('archived_at')
