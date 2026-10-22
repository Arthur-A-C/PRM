"""Pauta Semanal de Desenvolvimento: new tables only, no existing data touched."""
from alembic import op
from app.models.weekly_agenda import WEEKLY_AGENDA_TABLES

revision = "20261023_0013"
down_revision = "20261021_0011"
branch_labels = None
depends_on = None


def upgrade():
    for table in WEEKLY_AGENDA_TABLES:
        table.create(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError("Downgrade destrutivo bloqueado: exporte/arquive as pautas antes de remover as tabelas.")
