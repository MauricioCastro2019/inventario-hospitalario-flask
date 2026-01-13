"""add paciente_nombre to cirugias

Revision ID: 6d44f14b1873
Revises: ade3cd18b4b3
Create Date: (lo que tengas)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6d44f14b1873"
down_revision = "ade3cd18b4b3"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ✅ Postgres (Railway): no fallar si ya existe
    if dialect == "postgresql":
        op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS paciente_nombre VARCHAR(160);")
    else:
        # ✅ SQLite (local): normal
        with op.batch_alter_table("cirugias", schema=None) as batch_op:
            batch_op.add_column(sa.Column("paciente_nombre", sa.String(length=160), nullable=True))


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS paciente_nombre;")
    else:
        with op.batch_alter_table("cirugias", schema=None) as batch_op:
            batch_op.drop_column("paciente_nombre")
