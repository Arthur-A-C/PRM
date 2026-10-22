"""Add meeting pipeline and single activity/planner registry; no existing data touched."""
from alembic import op
from app.models.meetings import MEETING_TABLES

revision = "20261016_0009"
down_revision = "20261009_0008"
branch_labels = None
depends_on = None


def upgrade():
    for table in MEETING_TABLES:
        table.create(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError("Downgrade destrutivo bloqueado: arquive reuniões/atividades e planeje restauração antes de remover tabelas.")
