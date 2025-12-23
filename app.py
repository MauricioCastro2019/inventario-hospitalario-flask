from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
import os

# ---------------------------
# APP
# ---------------------------

app = Flask(__name__)

# ---------------------------
# DATABASE CONFIG (Railway / Local)
# ---------------------------

def get_database_uri() -> str:
    """
    Railway normalmente expone DATABASE_URL (postgres://...)
    SQLAlchemy necesita postgresql://...
    Si no hay env, usamos SQLite local.
    """
    db_url = os.getenv("DATABASE_URL")

    # Si Railway está mal configurado y nos llega vacío o raro, caemos a SQLite.
    if not db_url or db_url.strip() == "":
        return "sqlite:///db.sqlite3"

    db_url = db_url.strip()

    # Normalización segura: solo si empieza con postgres:// y solo 1 vez
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    return db_url


app.config["SQLALCHEMY_DATABASE_URI"] = get_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "static/uploads"

db = SQLAlchemy(app)

# ---------------------------
# MODELOS
# ---------------------------

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    codigo = db.Column(db.String(50))
    descripcion = db.Column(db.Text)
    proveedor = db.Column(db.String(100))
    lote = db.Column(db.String(50))
    categoria = db.Column(db.String(50))
    unidad = db.Column(db.String(20))
    cantidad = db.Column(db.Integer)
    stock_minimo = db.Column(db.Integer, default=0)
    costo = db.Column(db.Float)
    precio = db.Column(db.Float)
    ingreso = db.Column(db.Date)
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
    tipo = db.Column(db.String(10), nullable=False)  # entrada / salida
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    nota = db.Column(db.String(255))


# ---------------------------
# AUTO CREATE TABLES (SAFE)
# ---------------------------

def ensure_tables():
    """
    Crea tablas si no existen.
    En Railway esto evita: "no such table: producto"
    Si la DB todavía no está lista por un instante, no tumba el deploy.
    """
    try:
        with app.app_context():
            db.create_all()
    except Exception as e:
        # Log simple para Railway. No detenemos el arranque por esto.
        print("⚠️ ensure_tables() error:", repr(e))


ensure_tables()

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
        # Si ingreso es NULL en algunos registros, esto puede fallar dependiendo DB.
        # Por seguridad, ordenamos por última modificación:
        productos = Producto.query.order_by(Producto.ultima_modificacion.desc()).all()

    return render_template("index.html", productos=productos)


@app.route("/agregar", methods=["GET", "POST"])
def agregar():
    if request.method == "POST":
        producto = Producto(
            nombre=request.form["nombre"],
            codigo=request.form["codigo"],
            descripcion=request.form.get("descripcion", ""),
            proveedor=request.form.get("proveedor", ""),
            lote=request.form.get("lote", ""),
            categoria=request.form.get("categoria", ""),
            unidad=request.form["unidad"],
            cantidad=int(request.form["cantidad"]) if request.form.get("cantidad") else 0,
            stock_minimo=int(request.form.get("stock_minimo", 0) or 0),
            costo=float(request.form["costo"]) if request.form.get("costo") else 0.0,
            precio=float(request.form["precio"]) if request.form.get("precio") else 0.0,
            ingreso=datetime.strptime(
                request.form["fecha_ingreso"], "%Y-%m-%d"
            ).date() if request.form.get("fecha_ingreso") else None,
            caducidad=datetime.strptime(
                request.form["fecha_caducidad"], "%Y-%m-%d"
            ).date() if request.form.get("fecha_caducidad") else None,
            ultima_modificacion=datetime.utcnow()
        )

        imagen = request.files.get("imagen")
        if imagen and imagen.filename:
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
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
        producto.cantidad = int(request.form["cantidad"]) if request.form.get("cantidad") else 0
        producto.stock_minimo = int(request.form.get("stock_minimo", 0) or 0)
        producto.costo = float(request.form["costo"]) if request.form.get("costo") else 0.0
        producto.precio = float(request.form["precio"]) if request.form.get("precio") else 0.0
        producto.ingreso = datetime.strptime(
            request.form["fecha_ingreso"], "%Y-%m-%d"
        ).date() if request.form.get("fecha_ingreso") else None
        producto.caducidad = datetime.strptime(
            request.form["fecha_caducidad"], "%Y-%m-%d"
        ).date() if request.form.get("fecha_caducidad") else None
        producto.ultima_modificacion = datetime.utcnow()

        imagen = request.files.get("imagen")
        if imagen and imagen.filename:
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
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
        movs = Movimiento.query.filter_by(
            producto_id=producto_id
        ).order_by(Movimiento.fecha.desc()).all()
        return render_template("movimientos.html", producto=producto, movimientos=movs)

    movs = Movimiento.query.order_by(Movimiento.fecha.desc()).limit(200).all()
    return render_template("movimientos.html", producto=None, movimientos=movs)


@app.route("/movimiento/nuevo/<int:producto_id>", methods=["GET", "POST"])
def nuevo_movimiento(producto_id):
    producto = Producto.query.get_or_404(producto_id)

    if request.method == "POST":
        tipo = request.form.get("tipo")  # entrada / salida
        cantidad = int(request.form.get("cantidad", 0) or 0)
        nota = (request.form.get("nota") or "").strip() or None

        if tipo not in ("entrada", "salida"):
            return "Tipo inválido", 400
        if cantidad <= 0:
            return "Cantidad inválida", 400

        # Normaliza cantidad si viene None
        if producto.cantidad is None:
            producto.cantidad = 0

        # Validación de stock
        if tipo == "salida" and producto.cantidad < cantidad:
            return f"Stock insuficiente. Stock actual: {producto.cantidad}", 400

        # Ajuste stock
        if tipo == "entrada":
            producto.cantidad += cantidad
        else:
            producto.cantidad -= cantidad

        mov = Movimiento(
            producto_id=producto.id,
            tipo=tipo,
            cantidad=cantidad,
            nota=nota,
            fecha=datetime.utcnow()
        )

        producto.ultima_modificacion = datetime.utcnow()

        db.session.add(mov)
        db.session.commit()
        return redirect(url_for("movimientos", producto_id=producto.id))

    return render_template("nuevo_movimiento.html", producto=producto)


# ---------------------------
# ENTRYPOINT (Local only)
# Railway usa gunicorn con wsgi.py
# ---------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
