from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
from sqlalchemy import text
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
app.config["UPLOAD_FOLDER"] = "static/uploads"

# Evita conexiones zombie en Postgres (cuando aplique)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True
}

db = SQLAlchemy(app)

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
    ultima_modificacion = db.Column(db.DateTime, default=datetime.utcnow)

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
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    nota = db.Column(db.String(255))

# ---------------------------
# AUTOPARCHE DE ESQUEMA (SQLite friendly)
# ---------------------------

def ensure_product_columns():
    """
    Asegura que la tabla 'producto' tenga columnas que el modelo/plantillas esperan.
    Evita errores tipo: sqlite3.OperationalError: no such column: producto.unidad_compra
    NO borra datos. Funciona excelente en SQLite.
    En Postgres, esto normalmente se haría con migraciones (Flask-Migrate).
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
        # Solo aplica ALTER TABLE directo en SQLite.
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        is_sqlite = uri.startswith("sqlite")

        if not is_sqlite:
            # En Postgres, mejor confiar en create_all para tablas nuevas.
            # Si falta columna en producción, lo correcto es migración.
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

def ensure_upload_folder():
    try:
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    except Exception as e:
        print("⚠️ No se pudo crear UPLOAD_FOLDER:", e)

# ---------------------------
# INIT DB (prototipo)
# ---------------------------
with app.app_context():
    db.create_all()
    ensure_product_columns()
    ensure_upload_folder()

# ---------------------------
# RUTAS
# ---------------------------

@app.route("/")
def index():
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
            ultima_modificacion=datetime.utcnow()
        )

        imagen = request.files.get("imagen")
        if imagen and imagen.filename:
            filename = secure_filename(imagen.filename)
            imagen.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            producto.imagen = filename

        db.session.add(producto)
        db.session.commit()
        return redirect(url_for("index"))

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

        producto.ultima_modificacion = datetime.utcnow()

        imagen = request.files.get("imagen")
        if imagen and imagen.filename:
            filename = secure_filename(imagen.filename)
            imagen.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            producto.imagen = filename

        db.session.commit()
        return redirect(url_for("index"))

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
        producto.ultima_modificacion = datetime.utcnow()

        db.session.add(mov)
        db.session.commit()
        return redirect(url_for("movimientos", producto_id=producto.id))

    return render_template("nuevo_movimiento.html", producto=producto)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
