from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260109_add_cirugias_cols"
down_revision = None
branch_labels = None
depends_on = None


def _col_exists(conn, table_name: str, col_name: str) -> bool:
    insp = inspect(conn)
    try:
        cols = insp.get_columns(table_name)
    except Exception:
        return False
    return any(c["name"] == col_name for c in cols)


def _add_col_if_missing(table_name: str, column: sa.Column):
    conn = op.get_bind()
    if not _col_exists(conn, table_name, column.name):
        op.add_column(table_name, column)


def upgrade():
    # ✅ Cross-DB (SQLite/Postgres): agrega SOLO si falta
    table = "cirugias"

    _add_col_if_missing(table, sa.Column("paciente", sa.String(length=160), nullable=True))
    _add_col_if_missing(table, sa.Column("edad", sa.Integer(), nullable=True))
    _add_col_if_missing(table, sa.Column("sexo", sa.String(length=10), nullable=True))
    _add_col_if_missing(table, sa.Column("telefono", sa.String(length=30), nullable=True))

    _add_col_if_missing(table, sa.Column("folio_expediente", sa.String(length=80), nullable=True))
    _add_col_if_missing(table, sa.Column("especialidad", sa.String(length=120), nullable=True))
    _add_col_if_missing(table, sa.Column("procedimiento", sa.String(length=200), nullable=True))

    _add_col_if_missing(table, sa.Column("cirujano", sa.String(length=160), nullable=True))
    _add_col_if_missing(table, sa.Column("anestesiologo", sa.String(length=160), nullable=True))
    _add_col_if_missing(table, sa.Column("ayudantes", sa.Text(), nullable=True))
    _add_col_if_missing(table, sa.Column("instrumentista", sa.String(length=160), nullable=True))

    _add_col_if_missing(table, sa.Column("indicaciones_especiales", sa.Text(), nullable=True))
    _add_col_if_missing(table, sa.Column("estado", sa.String(length=30), nullable=True))
    _add_col_if_missing(table, sa.Column("programo", sa.String(length=160), nullable=True))
    _add_col_if_missing(table, sa.Column("orden_foto_path", sa.String(length=255), nullable=True))

    # Timestamps: usamos DateTime; en Postgres será timestamp, en SQLite text-ish.
    _add_col_if_missing(table, sa.Column("created_at", sa.DateTime(), nullable=True))
    _add_col_if_missing(table, sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade():
    # ⚠️ OJO: SQLite no siempre soporta DROP COLUMN según versión.
    # Lo dejamos "best effort": en Postgres funciona; en SQLite se intenta y si falla, no truena la migración.
    conn = op.get_bind()
    dialect = conn.dialect.name
    table = "cirugias"

    cols_to_drop = [
        "updated_at",
        "created_at",
        "orden_foto_path",
        "programo",
        "estado",
        "indicaciones_especiales",
        "instrumentista",
        "ayudantes",
        "anestesiologo",
        "cirujano",
        "procedimiento",
        "especialidad",
        "folio_expediente",
        "telefono",
        "sexo",
        "edad",
        "paciente",
    ]

    for col in cols_to_drop:
        if _col_exists(conn, table, col):
            try:
                op.drop_column(table, col)
            except Exception:
                # En SQLite viejo puede fallar; no rompemos downgrade.
                if dialect != "sqlite":
                    raise
