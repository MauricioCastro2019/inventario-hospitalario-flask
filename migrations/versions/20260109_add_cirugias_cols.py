from alembic import op
import sqlalchemy as sa

revision = "20260109_add_cirugias_cols"
down_revision = None
branch_labels = None
depends_on = None



def upgrade():
    # Agrega columnas si no existen (Postgres soporta IF NOT EXISTS)
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS paciente VARCHAR(160);")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS edad INTEGER;")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS sexo VARCHAR(10);")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS telefono VARCHAR(30);")

    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS folio_expediente VARCHAR(80);")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS especialidad VARCHAR(120);")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS procedimiento VARCHAR(200);")

    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS cirujano VARCHAR(160);")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS anestesiologo VARCHAR(160);")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS ayudantes TEXT;")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS instrumentista VARCHAR(160);")

    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS indicaciones_especiales TEXT;")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS estado VARCHAR(30);")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS programo VARCHAR(160);")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS orden_foto_path VARCHAR(255);")

    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;")
    op.execute("ALTER TABLE cirugias ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;")


def downgrade():
    # (Opcional) reversa
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS updated_at;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS created_at;")

    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS orden_foto_path;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS programo;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS estado;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS indicaciones_especiales;")

    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS instrumentista;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS ayudantes;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS anestesiologo;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS cirujano;")

    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS procedimiento;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS especialidad;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS folio_expediente;")

    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS telefono;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS sexo;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS edad;")
    op.execute("ALTER TABLE cirugias DROP COLUMN IF EXISTS paciente;")
