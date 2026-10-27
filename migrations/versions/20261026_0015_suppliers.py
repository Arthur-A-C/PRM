"""Supplier CRM: additive tables only."""
from alembic import op
import sqlalchemy as sa
revision = '20261026_0015'
down_revision = '20261023_0014'
branch_labels = depends_on = None

def common():
    return [sa.Column('id',sa.Uuid(),primary_key=True),
            sa.Column('organization_id',sa.Uuid(),sa.ForeignKey('organizations.id'),nullable=False),
            sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
            sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
            sa.Column('data',sa.JSON(),nullable=False)]

def upgrade():
    op.create_table('suppliers',*common(),
        sa.Column('responsible_user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('name',sa.String(200),nullable=False),sa.Column('stage',sa.String(50),nullable=False),
        sa.Column('score',sa.String(30),nullable=False))
    for name in ('supplier_contacts','supplier_interactions','supplier_tasks','supplier_documents'):
        extra=[]
        if name=='supplier_interactions': extra=[sa.Column('event',sa.String(60),nullable=False)]
        if name=='supplier_tasks': extra=[sa.Column('assignee_user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False)]
        op.create_table(name,*common(),sa.Column('supplier_id',sa.Uuid(),sa.ForeignKey('suppliers.id'),nullable=False),
                        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),*extra)
        op.create_index('ix_'+name+'_supplier_id',name,['supplier_id'])
        op.create_index('ix_'+name+'_organization_id',name,['organization_id'])
    for field in ('organization_id','responsible_user_id','stage'):
        op.create_index('ix_suppliers_'+field,'suppliers',[field])
    op.create_index('ix_supplier_tasks_assignee_user_id','supplier_tasks',['assignee_user_id'])

def downgrade():
    for name in ('supplier_documents','supplier_tasks','supplier_interactions','supplier_contacts','suppliers'):
        op.drop_table(name)
