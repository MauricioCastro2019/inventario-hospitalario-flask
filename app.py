from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from sqlalchemy import text, CheckConstraint
from flask_migrate import Migrate

from datetime import datetime, timezone
import os

app = Flask(__name__)

# ---------------------------
# DB URL (Railway / local)
# ---------------------------

def clean_db_url(raw: str) -> str:
    """
    Limpia y normaliza DATABASE_URL.
    - Quita comillas/espacios
    - Convierte postgres:// a postgresql:// (SQLAlchemy)
    - Si detecta placeholders tipo ${PGPORT} (no expandidos), regresa "" para forzar fallback
    """
    s = (raw or "").strip()
    s = s.strip('"').strip("'").strip()

    # Si Railway/otra config te dejó placeholders sin expandir, NO intentes parsearlo.
    if "${" in s:
        return ""

    if s.startswith("postgres://"):
        s = s.replace("postgres://", "postgresql://", 1)

    return s


raw_db = os.getenv("DATABASE_URL", "")
print("🔎 RAW DATABASE_URL repr:", repr(raw_db))

db_url = clean_db_url(raw_db)

# Decide DB final
if db_url.startswith("postgresql://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
elif db_url.startswith("sqlite:///"):
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    print("⚠️ DATABASE_URL inválida/vacía (o placeholders sin expandir). Usando SQLite fallback.")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Uploads
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["PHARMA_UPLOAD_FOLDER"] = "static/uploads/farmacia_pendientes"
app.config["CIRUGIA_UPLOAD_FOLDER"] = "static/uploads/cirugias"  # ✅ nuevo

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB por request

# Evita conexiones zombie en Postgres (cuando aplique)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# ---------------------------
# CONFIG DE PRECIOS
# ---------------------------
DEFAULT_MARGEN = 0.35
IVA_RATE = 0.16

def calcular_precio_sugerido(costo: float, margen: float = DEFAULT_MARGEN, aplica_iva: bool = False) -> float:
    """
    Precio sugerido = costo * (1 + margen)
    Si aplica IVA: * (1 + IVA_RATE)
    """
    costo = float(costo or 0)
    margen = float(margen if margen is not None else DEFAULT_MARGEN)

    precio = costo * (1.0 + margen)
    if aplica_iva:
        precio *= (1.0 + IVA_RATE)

    return round(precio, 2)


# ---------------------------
# HELPERS GENERALES
# ---------------------------
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def utcnow():
    """UTC timezone-aware ahora."""
    return datetime.now(timezone.utc)

def build_photo_filename(original_name: str, fecha, folio=None) -> str:
    """
    Nombre consistente para fotos (Farmacia).
    fecha: datetime.date
    """
    ext = original_name.rsplit(".", 1)[1].lower()
    safe_folio = (folio or "sinfolio").replace(" ", "_")
    timestamp = utcnow().strftime("%H%M%S%f")
    return f"{fecha.strftime('%Y%m%d')}_{safe_folio}_{timestamp}.{ext}"

def build_cirugia_photo_filename(original_name: str, fecha, folio_expediente: str) -> str:
    """
    Nombre consistente para fotos (Cirugías).
    fecha: datetime.date
    """
    ext = original_name.rsplit(".", 1)[1].lower()
    safe_folio = (folio_expediente or "sinfolio").replace(" ", "_").replace("/", "_")
    timestamp = utcnow().strftime("%H%M%S%f")
    return f"cirugia_{fecha.strftime('%Y%m%d')}_{safe_folio}_{timestamp}.{ext}"


def ensure_upload_folder():
    try:
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        os.makedirs(app.config["PHARMA_UPLOAD_FOLDER"], exist_ok=True)
        os.makedirs(app.config["CIRUGIA_UPLOAD_FOLDER"], exist_ok=True)
    except Exception as e:
        print("⚠️ No se pudo crear UPLOAD_FOLDER:", e)


# ---------------------------
# MODELOS
# ---------------------------

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    nombre = db.Column(db.String(100))
    codigo = db.Column(db.String(50))
    descripcion = db.Column(db.Text)

    proveedor = db.Column(db.String(100))     # label en HTML: Marca/Proveedor
    lote = db.Column(db.String(50))
    categoria = db.Column(db.String(50))

    unidad = db.Column(db.String(20))

    # legacy (compat)
    cantidad = db.Column(db.Integer)

    # inventario en piezas
    unidad_compra = db.Column(db.String(20))          # ej. "caja"
    piezas_por_unidad = db.Column(db.Integer)         # ej. 50
    cantidad_piezas = db.Column(db.Integer, default=0)

    stock_minimo = db.Column(db.Integer, default=0)

    costo = db.Column(db.Float)
    margen = db.Column(db.Float, default=DEFAULT_MARGEN)
    aplica_iva = db.Column(db.Boolean, default=False)
    precio = db.Column(db.Float)

    fecha_ingreso = db.Column(db.Date)
    caducidad = db.Column(db.Date)

    imagen = db.Column(db.String(200))
    ultima_modificacion = db.Column(db.DateTime, default=lambda: utcnow())

    movimientos = db.relationship(
        "Movimiento",
        backref="producto",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("producto.id"), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # "entrada" | "salida"
    cantidad = db.Column(db.Integer, nullable=False) # SIEMPRE en piezas
    fecha = db.Column(db.DateTime, default=lambda: utcnow())
    nota = db.Column(db.String(255))


class FarmaciaPendienteRegistro(db.Model):
    __tablename__ = "farmacia_pendiente_registro"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    folio = db.Column(db.String(50), nullable=True, index=True)
    notas = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: utcnow(), nullable=False)

    fotos = db.relationship(
        "FarmaciaPendienteFoto",
        backref="registro",
        lazy=True,
        cascade="all, delete-orphan"
    )


class FarmaciaPendienteFoto(db.Model):
    __tablename__ = "farmacia_pendiente_foto"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("farmacia_pendiente_registro.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: utcnow(), nullable=False)


class Cirugia(db.Model):
    """
    Cirugía v2 (orden digital complementaria al papel).
    """
    __tablename__ = "cirugias"

    id = db.Column(db.Integer, primary_key=True)

    # Programación (obligatorias según tu lista)
    fecha = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.Time, nullable=False)
    duracion_min = db.Column(db.Integer, nullable=True)  # opcional
    quirofano = db.Column(db.String(50), nullable=False, index=True)

    # Paciente (obligatorias)
    paciente = db.Column(db.String(160), nullable=False)
    edad = db.Column(db.Integer, nullable=False)
    sexo = db.Column(db.String(10), nullable=False)  # "M", "F", "Otro"
    telefono = db.Column(db.String(30), nullable=True)  # luego

    # Admin/Clínico
    folio_expediente = db.Column(db.String(80), nullable=False, index=True)
    especialidad = db.Column(db.String(120), nullable=True, index=True)  # opcional luego
    procedimiento = db.Column(db.String(200), nullable=False)

    # Equipo (obligatorios como dijiste)
    cirujano = db.Column(db.String(160), nullable=False, index=True)
    anestesiologo = db.Column(db.String(160), nullable=False, index=True)
    ayudantes = db.Column(db.Text, nullable=False)
    instrumentista = db.Column(db.String(160), nullable=False)

    # Observaciones
    indicaciones_especiales = db.Column(db.Text, nullable=True)

    # Estado
    estado = db.Column(db.String(30), nullable=False, default="PROGRAMADA", index=True)

    # Control
    programo = db.Column(db.String(160), nullable=False)

    # Foto orden física (obligatoria)
    orden_foto_path = db.Column(db.String(255), nullable=False)

    # Auditoría
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: utcnow())
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: utcnow(), onupdate=lambda: utcnow())

    __table_args__ = (
        CheckConstraint(
            "duracion_min IS NULL OR (duracion_min >= 10 AND duracion_min <= 1440)",
            name="ck_cirugia_duracion"
        ),
    )


class CirugiaEvento(db.Model):
    __tablename__ = "cirugia_eventos"

    id = db.Column(db.Integer, primary_key=True)

    cirugia_id = db.Column(
        db.Integer,
        db.ForeignKey("cirugias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Tipos recomendados: "CREADA", "CAMBIO_ESTADO", "EDITADA", "NOTA", etc.
    tipo = db.Column(db.String(30), nullable=False, index=True)

    # Detalles del evento (qué cambió, nota, razón, etc.)
    detalle = db.Column(db.Text, nullable=True)

    # Por ahora texto (nombre/usuario). En el futuro: user_id (FK a tabla usuarios).
    actor = db.Column(db.String(80), nullable=True)

    # Timestamp UTC (timezone-aware) para auditoría
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: utcnow(),
        index=True
    )

    # Relación hacia Cirugia
    cirugia = db.relationship(
        "Cirugia",
        backref=db.backref(
            "eventos",
            lazy=True,
            cascade="all, delete-orphan",
            passive_deletes=True
        )
    )


# ---------------------------
# AUTOPARCHE DE ESQUEMA (SQLite friendly)
# ---------------------------

def ensure_product_columns():
    """
    Asegura que la tabla 'producto' tenga columnas que el modelo/plantillas esperan.
    Evita errores tipo: sqlite3.OperationalError: no such column: producto.unidad_compra
    NO borra datos. Funciona excelente en SQLite.

    En Postgres, lo correcto es migraciones (Flask-Migrate), aquí solo se usa para SQLite fallback.
    """
    required = {
        "nombre": "TEXT",
        "codigo": "TEXT",
        "descripcion": "TEXT",
        "proveedor": "TEXT",
        "lote": "TEXT",
        "categoria": "TEXT",
        "unidad": "TEXT",
        "cantidad": "INTEGER",

        "unidad_compra": "TEXT",
        "piezas_por_unidad": "INTEGER",
        "cantidad_piezas": "INTEGER",

        "stock_minimo": "INTEGER",
        "costo": "REAL",
        "margen": "REAL",
        "aplica_iva": "INTEGER",     # SQLite: 0/1
        "precio": "REAL",

        "fecha_ingreso": "DATE",
        "caducidad": "DATE",

        "imagen": "TEXT",
        "ultima_modificacion": "DATETIME"
    }

    try:
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        is_sqlite = uri.startswith("sqlite")

        if not is_sqlite:
            print("ℹ️ ensure_product_columns: DB no es SQLite. Saltando autoparche.")
            return

        cols = db.session.execute(text("PRAGMA table_info(producto)")).fetchall()
        existing = {c[1] for c in cols}

        added = False
        for col, coltype in required.items():
            if col not in existing:
                db.session.execute(text(f"ALTER TABLE producto ADD COLUMN {col} {coltype}"))
                print(f"✅ Columna agregada: {col} ({coltype})")
                added = True

        if added:
            db.session.commit()
            print("✅ Tabla 'producto' actualizada sin perder datos.")
        else:
            print("✅ Tabla 'producto' ya estaba actualizada.")

    except Exception as e:
        print("⚠️ Error en ensure_product_columns():", e)


# ---------------------------
# INIT DB (prototipo + seguridad)
# ---------------------------
with app.app_context():
    # ✅ Lo dejamos por seguridad como pediste.
    # En cuanto confirmemos que migraciones están 100% estables, lo retiramos.
    db.create_all()
    ensure_product_columns()
    ensure_upload_folder()


# ---------------------------
# RUTAS
# ---------------------------

@app.route("/")
def home():
    return redirect(url_for("dashboard"))


@app.route("/productos")
def productos():
    q = request.args.get("q")
    if q:
        productos = Producto.query.filter(
            (Producto.nombre.ilike(f"%{q}%")) |
            (Producto.codigo.ilike(f"%{q}%")) |
            (Producto.categoria.ilike(f"%{q}%"))
        ).all()
    else:
        productos = Producto.query.order_by(Producto.ultima_modificacion.desc()).all()

    return render_template("index.html", productos=productos)


@app.route("/index")
def index_redirect():
    return redirect(url_for("productos"))


@app.route("/agregar", methods=["GET", "POST"])
def agregar():
    if request.method == "POST":
        nombre = request.form["nombre"]
        codigo = request.form["codigo"]
        descripcion = request.form.get("descripcion", "")
        proveedor = request.form.get("proveedor", "")
        lote = request.form.get("lote", "")
        categoria = request.form.get("categoria", "")
        unidad = request.form["unidad"]

        stock_minimo = int(request.form.get("stock_minimo", 0) or 0)

        unidad_compra = (request.form.get("unidad_compra") or "").strip() or None
        piezas_por_unidad = int(request.form.get("piezas_por_unidad", 0) or 0)

        cantidad_legacy = int(request.form.get("cantidad", 0) or 0)

        if piezas_por_unidad > 0:
            cantidad_piezas = cantidad_legacy * piezas_por_unidad
        else:
            cantidad_piezas = cantidad_legacy

        costo = float(request.form.get("costo", 0) or 0)
        aplica_iva = ("aplica_iva" in request.form)

        precio_sugerido = calcular_precio_sugerido(costo, DEFAULT_MARGEN, aplica_iva)

        precio_form = request.form.get("precio")
        precio_final = float(precio_form) if (precio_form and precio_form.strip() != "") else precio_sugerido

        fecha_ingreso = datetime.strptime(
            request.form["fecha_ingreso"], "%Y-%m-%d"
        ).date() if request.form.get("fecha_ingreso") else None

        fecha_caducidad = datetime.strptime(
            request.form["fecha_caducidad"], "%Y-%m-%d"
        ).date() if request.form.get("fecha_caducidad") else None

        producto = Producto(
            nombre=nombre,
            codigo=codigo,
            descripcion=descripcion,
            proveedor=proveedor,
            lote=lote,
            categoria=categoria,
            unidad=unidad,

            cantidad=cantidad_legacy,
            unidad_compra=unidad_compra,
            piezas_por_unidad=(piezas_por_unidad if piezas_por_unidad > 0 else None),
            cantidad_piezas=cantidad_piezas,

            stock_minimo=stock_minimo,

            costo=costo,
            margen=DEFAULT_MARGEN,
            aplica_iva=aplica_iva,
            precio=precio_final,

            fecha_ingreso=fecha_ingreso,
            caducidad=fecha_caducidad,
            ultima_modificacion=utcnow()
        )

        imagen = request.files.get("imagen")
        if imagen and imagen.filename:
            filename = secure_filename(imagen.filename)
            imagen.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            producto.imagen = filename

        db.session.add(producto)
        db.session.commit()
        return redirect(url_for("productos"))

    return render_template("agregar.html")


@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    producto = Producto.query.get_or_404(id)

    if request.method == "POST":
        producto.nombre = request.form["nombre"]
        producto.codigo = request.form["codigo"]
        producto.descripcion = request.form.get("descripcion", "")
        producto.proveedor = request.form.get("proveedor", "")
        producto.lote = request.form.get("lote", "")
        producto.categoria = request.form.get("categoria", "")
        producto.unidad = request.form["unidad"]

        producto.stock_minimo = int(request.form.get("stock_minimo", 0) or 0)

        producto.unidad_compra = (request.form.get("unidad_compra") or "").strip() or None
        piezas_por_unidad = int(request.form.get("piezas_por_unidad", 0) or 0)
        producto.piezas_por_unidad = piezas_por_unidad if piezas_por_unidad > 0 else None

        cantidad_legacy = int(request.form.get("cantidad", 0) or 0)
        producto.cantidad = cantidad_legacy

        if producto.piezas_por_unidad and producto.piezas_por_unidad > 0:
            producto.cantidad_piezas = cantidad_legacy * producto.piezas_por_unidad
        else:
            producto.cantidad_piezas = cantidad_legacy

        producto.costo = float(request.form.get("costo", 0) or 0)
        producto.aplica_iva = ("aplica_iva" in request.form)

        precio_form = request.form.get("precio")
        if precio_form and precio_form.strip() != "":
            producto.precio = float(precio_form)
        else:
            producto.precio = calcular_precio_sugerido(
                producto.costo,
                producto.margen or DEFAULT_MARGEN,
                producto.aplica_iva
            )

        producto.fecha_ingreso = datetime.strptime(
            request.form["fecha_ingreso"], "%Y-%m-%d"
        ).date() if request.form.get("fecha_ingreso") else None

        producto.caducidad = datetime.strptime(
            request.form["fecha_caducidad"], "%Y-%m-%d"
        ).date() if request.form.get("fecha_caducidad") else None

        producto.ultima_modificacion = utcnow()

        imagen = request.files.get("imagen")
        if imagen and imagen.filename:
            filename = secure_filename(imagen.filename)
            imagen.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            producto.imagen = filename

        db.session.commit()
        return redirect(url_for("productos"))

    return render_template("editar.html", producto=producto)


@app.route("/movimientos")
def movimientos():
    producto_id = request.args.get("producto_id", type=int)
    if producto_id:
        producto = Producto.query.get_or_404(producto_id)
        movs = Movimiento.query.filter_by(producto_id=producto_id).order_by(Movimiento.fecha.desc()).all()
        return render_template("movimientos.html", producto=producto, movimientos=movs)

    movs = Movimiento.query.order_by(Movimiento.fecha.desc()).limit(200).all()
    return render_template("movimientos.html", producto=None, movimientos=movs)


@app.route("/movimiento/nuevo/<int:producto_id>", methods=["GET", "POST"])
def nuevo_movimiento(producto_id):
    producto = Producto.query.get_or_404(producto_id)

    if request.method == "POST":
        tipo = request.form.get("tipo")
        cantidad = int(request.form.get("cantidad", 0) or 0)  # EN PIEZAS
        nota = (request.form.get("nota") or "").strip() or None

        if tipo not in ("entrada", "salida"):
            return "Tipo inválido", 400
        if cantidad <= 0:
            return "Cantidad inválida", 400

        if producto.cantidad_piezas is None:
            producto.cantidad_piezas = 0

        if tipo == "salida" and producto.cantidad_piezas < cantidad:
            return f"Stock insuficiente. Stock actual (pzas): {producto.cantidad_piezas}", 400

        producto.cantidad_piezas += cantidad if tipo == "entrada" else -cantidad

        # compatibilidad con legacy
        if producto.piezas_por_unidad and producto.piezas_por_unidad > 0:
            producto.cantidad = int(producto.cantidad_piezas // producto.piezas_por_unidad)
        else:
            producto.cantidad = producto.cantidad_piezas

        mov = Movimiento(producto_id=producto.id, tipo=tipo, cantidad=cantidad, nota=nota)
        producto.ultima_modificacion = utcnow()

        db.session.add(mov)
        db.session.commit()
        return redirect(url_for("movimientos", producto_id=producto.id))

    return render_template("nuevo_movimiento.html", producto=producto)


@app.route("/farmacia/pendientes", methods=["GET"])
def farmacia_pendientes():
    fecha_str = request.args.get("fecha")  # YYYY-MM-DD
    q = FarmaciaPendienteRegistro.query

    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            q = q.filter(FarmaciaPendienteRegistro.fecha == fecha)
        except ValueError:
            fecha_str = None

    registros = q.order_by(
        FarmaciaPendienteRegistro.fecha.desc(),
        FarmaciaPendienteRegistro.id.desc()
    ).all()

    return render_template("farmacia_pendientes.html", registros=registros, fecha_str=fecha_str)


@app.route("/farmacia/pendientes/nuevo", methods=["GET", "POST"])
def farmacia_pendientes_nuevo():
    if request.method == "POST":
        fecha_str = request.form.get("fecha")
        folio = (request.form.get("folio") or "").strip() or None
        notas = (request.form.get("notas") or "").strip() or None

        if not fecha_str:
            return "Fecha obligatoria", 400

        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            return "Fecha inválida", 400

        files = request.files.getlist("fotos")
        valid_files = [f for f in files if f and f.filename and allowed_file(f.filename)]

        if not valid_files:
            return "Sube al menos una foto válida (jpg/png/webp).", 400

        registro = FarmaciaPendienteRegistro(fecha=fecha, folio=folio, notas=notas)
        db.session.add(registro)
        db.session.flush()

        for f in valid_files:
            original = secure_filename(f.filename)
            new_name = build_photo_filename(original, fecha, folio)
            save_path = os.path.join(app.config["PHARMA_UPLOAD_FOLDER"], new_name)
            f.save(save_path)

            rel_path = f"uploads/farmacia_pendientes/{new_name}"
            db.session.add(FarmaciaPendienteFoto(registro_id=registro.id, filename=rel_path))

        db.session.commit()
        return redirect(url_for("farmacia_pendiente_detalle", registro_id=registro.id))

    return render_template("farmacia_pendientes_nuevo.html")


@app.route("/farmacia/pendientes/<int:registro_id>", methods=["GET", "POST"])
def farmacia_pendiente_detalle(registro_id):
    registro = FarmaciaPendienteRegistro.query.get_or_404(registro_id)

    if request.method == "POST":
        files = request.files.getlist("fotos")
        valid_files = [f for f in files if f and f.filename and allowed_file(f.filename)]

        if valid_files:
            for f in valid_files:
                original = secure_filename(f.filename)
                new_name = build_photo_filename(original, registro.fecha, registro.folio)
                save_path = os.path.join(app.config["PHARMA_UPLOAD_FOLDER"], new_name)
                f.save(save_path)

                rel_path = f"uploads/farmacia_pendientes/{new_name}"
                db.session.add(FarmaciaPendienteFoto(registro_id=registro.id, filename=rel_path))

            db.session.commit()

        return redirect(url_for("farmacia_pendiente_detalle", registro_id=registro.id))

    return render_template("farmacia_pendiente_detalle.html", registro=registro)


@app.route("/dashboard")
def dashboard():
    productos_count = Producto.query.count()
    movimientos_count = Movimiento.query.count()
    pendientes_count = FarmaciaPendienteRegistro.query.count()

    hoy = datetime.utcnow().date()
    ahora = datetime.utcnow().time()

    pendientes_hoy = FarmaciaPendienteRegistro.query.filter_by(fecha=hoy).count()

    cirugias_hoy = Cirugia.query.filter_by(fecha=hoy).count()

    proxima_cirugia = (
        Cirugia.query
        .filter(Cirugia.fecha == hoy, Cirugia.hora_inicio >= ahora)
        .order_by(Cirugia.hora_inicio.asc())
        .first()
    )

    if not proxima_cirugia:
        proxima_cirugia = (
            Cirugia.query
            .filter(Cirugia.fecha == hoy)
            .order_by(Cirugia.hora_inicio.asc())
            .first()
        )

    return render_template(
        "dashboard.html",
        productos_count=productos_count,
        movimientos_count=movimientos_count,
        pendientes_count=pendientes_count,
        pendientes_hoy=pendientes_hoy,
        cirugias_hoy=cirugias_hoy,
        proxima_cirugia=proxima_cirugia,
    )


@app.route("/cirugias")
def cirugias():
    fecha_str = request.args.get("fecha")
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else datetime.utcnow().date()
    except ValueError:
        fecha = datetime.utcnow().date()

    cirugias = Cirugia.query.filter_by(fecha=fecha).order_by(Cirugia.hora_inicio.asc()).all()

    return render_template("cirugias/lista.html", cirugias=cirugias, fecha=fecha)


ESTADOS_CIRUGIA = [
    "PROGRAMADA",
    "CONFIRMADA",
    "EN_PREP",
    "EN_CURSO",
    "FINALIZADA",
    "CANCELADA",
    "REPROGRAMADA",
]

SEXOS = ["M", "F", "Otro"]


@app.route("/cirugias/nueva", methods=["GET", "POST"])
def nueva_cirugia():
    if request.method == "POST":
        # --- Fecha/Hora obligatorias
        fecha_str = (request.form.get("fecha") or "").strip()
        hora_str = (request.form.get("hora_inicio") or "").strip()

        if not fecha_str or not hora_str:
            return "Fecha y hora son obligatorias", 400

        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            hora_inicio = datetime.strptime(hora_str, "%H:%M").time()
        except ValueError:
            return "Fecha u hora inválidas", 400

        # Duración opcional
        dur_str = (request.form.get("duracion_min") or "").strip()
        duracion_min = int(dur_str) if dur_str else None

        # Estado
        estado = request.form.get("estado", "PROGRAMADA")
        if estado not in ESTADOS_CIRUGIA:
            estado = "PROGRAMADA"
        

        # Campos obligatorios v2
        quirofano = (request.form.get("quirofano") or "").strip()
        paciente = (request.form.get("paciente") or "").strip()
        folio_expediente = (request.form.get("folio_expediente") or "").strip()
        procedimiento = (request.form.get("procedimiento") or "").strip()

        cirujano = (request.form.get("cirujano") or "").strip()
        anestesiologo = (request.form.get("anestesiologo") or "").strip()
        ayudantes = (request.form.get("ayudantes") or "").strip()
        instrumentista = (request.form.get("instrumentista") or "").strip()

        programo = (request.form.get("programo") or "").strip()

        sexo = (request.form.get("sexo") or "").strip()
        if sexo not in SEXOS:
            return "Sexo inválido", 400

        # Edad obligatoria y razonable
        try:
            edad = int((request.form.get("edad") or "").strip())
            if edad < 0 or edad > 120:
                return "Edad inválida", 400
        except:
            return "Edad inválida", 400

        # Indicaciones (opcional)
        indicaciones = (request.form.get("indicaciones_especiales") or "").strip() or None

        # Validación mínima pro
        obligatorios = [
            ("quirófano", quirofano),
            ("paciente", paciente),
            ("edad", str(edad) if edad is not None else ""),
            ("sexo", sexo),
            ("folio/expediente", folio_expediente),
            ("procedimiento", procedimiento),
            ("cirujano", cirujano),
            ("anestesiólogo", anestesiologo),
            ("ayudantes", ayudantes),
            ("instrumentista", instrumentista),
            ("programó", programo),
        ]
        faltan = [name for name, val in obligatorios if not (val and str(val).strip())]
        if faltan:
            return f"Faltan campos obligatorios: {', '.join(faltan)}", 400

        # --- Foto obligatoria (orden física)
        file = request.files.get("orden_foto")
        if not file or not file.filename:
            return "La foto de la orden física es obligatoria.", 400
        if not allowed_file(file.filename):
            return "Formato inválido. Usa JPG, PNG o WEBP.", 400

        original = secure_filename(file.filename)
        new_name = build_cirugia_photo_filename(original, fecha, folio_expediente)
        save_path = os.path.join(app.config["CIRUGIA_UPLOAD_FOLDER"], new_name)
        file.save(save_path)

        # Guardamos path relativo (como en farmacia)
        rel_path = f"uploads/cirugias/{new_name}"

        c = Cirugia(
            fecha=fecha,
            hora_inicio=hora_inicio,
            duracion_min=duracion_min,
            quirofano=quirofano,

            paciente=paciente,
            edad=edad,
            sexo=sexo,

            folio_expediente=folio_expediente,
            especialidad=(request.form.get("especialidad") or "").strip() or None,
            procedimiento=procedimiento,

            cirujano=cirujano,
            anestesiologo=anestesiologo,
            ayudantes=ayudantes,
            instrumentista=instrumentista,

            indicaciones_especiales=indicaciones,
            estado=estado,
            programo=programo,

            orden_foto_path=rel_path,
        )

        db.session.add(c)
        db.session.flush()

        db.session.add(CirugiaEvento(
            cirugia_id=c.id,
            tipo="CREADA",
            detalle=f"Creada en estado {c.estado}",
            actor=programo or None
        ))

        db.session.commit()

        return redirect(url_for("cirugias", fecha=fecha.strftime("%Y-%m-%d")))

    return render_template("cirugias/nueva.html", estados=ESTADOS_CIRUGIA, sexos=SEXOS)


@app.route("/cirugias/<int:cirugia_id>/estado", methods=["POST"])
def cirugia_cambiar_estado(cirugia_id):
    nuevo = request.form.get("estado")
    if nuevo not in ESTADOS_CIRUGIA:
        return "Estado inválido", 400

    c = Cirugia.query.get_or_404(cirugia_id)
    anterior = c.estado

    if nuevo != anterior:
        c.estado = nuevo
        db.session.add(CirugiaEvento(
            cirugia_id=c.id,
            tipo="CAMBIO_ESTADO",
            detalle=f"{anterior} → {nuevo}",
            actor=None
        ))
        db.session.commit()

    return redirect(url_for("cirugias", fecha=c.fecha.strftime("%Y-%m-%d")))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
