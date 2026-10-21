"""Three access levels, independent of the pending meeting schema migration."""
from alembic import op

revision = "20261021_0010"
down_revision = "20261009_0008"
branch_labels = ("access_levels",)
depends_on = None


def upgrade():
    op.drop_constraint(op.f("ck_users_role_allowed"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_role_allowed"), "users",
                               "role IN ('desenvolvedor', 'gestor', 'vendedor')")


def downgrade():
    raise RuntimeError("Downgrade bloqueado: reclassifique desenvolvedores explicitamente antes de restringir os níveis.")
