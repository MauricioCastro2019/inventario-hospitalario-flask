from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

def clean_db_url(raw: str) -> str:
    # quita espacios y comillas comunes
    s = (raw or "").strip().strip('"').strip("'").strip()

    # normaliza esquema viejo
    if s.startswith("postgres://"):
        s = s.replace("postgres://", "postgresql://", 1)

    return s

raw_db = os.getenv("DATABASE_URL", "")

# 👇 DEBUG: esto saldrá en Deploy Logs para confirmar qué trae Railway
print("🔎 RAW DATABASE_URL repr:", repr(raw_db))

db_url = clean_db_url(raw_db)

# Si sigue sin pinta de URL válida, usa SQLite (para que al menos arranque)
# OJO: esto es SOLO fallback; lo correcto es arreglar la variable en Railway
if db_url.startswith("postgresql://") or db_url.startswith("sqlite:///"):
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    print("⚠️ DATABASE_URL inválida, usando SQLite fallback. Valor limpio:", repr(db_url))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"

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
    tipo = db.Column(db.String(10), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    nota = db.Column(db.String(255))

# crea tablas
with app.app_context():
    db.create_all()

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
        producto = Producto(
            nombre=request.form["nombre"],
            codigo=request.form["codigo"],
            descripcion=request.form.get("descripcion", ""),
            proveedor=request.form.get("proveedor", ""),
            lote=request.form.get("lote", ""),
            categoria=request.form.get("categoria", ""),
            unidad=request.form["unidad"],
            cantidad=int(request.form.get("cantidad", 0) or 0),
            stock_minimo=int(request.form.get("stock_minimo", 0) or 0),
            costo=float(request.form.get("costo", 0) or 0),
            precio=float(request.form.get("precio", 0) or 0),
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
        producto.cantidad = int(request.form.get("cantidad", 0) or 0)
        producto.stock_minimo = int(request.form.get("stock_minimo", 0) or 0)
        producto.costo = float(request.form.get("costo", 0) or 0)
        producto.precio = float(request.form.get("precio", 0) or 0)
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
        movs = Movimiento.query.filter_by(producto_id=producto_id).order_by(Movimiento.fecha.desc()).all()
        return render_template("movimientos.html", producto=producto, movimientos=movs)

    movs = Movimiento.query.order_by(Movimiento.fecha.desc()).limit(200).all()
    return render_template("movimientos.html", producto=None, movimientos=movs)


@app.route("/movimiento/nuevo/<int:producto_id>", methods=["GET", "POST"])
def nuevo_movimiento(producto_id):
    producto = Producto.query.get_or_404(producto_id)

    if request.method == "POST":
        tipo = request.form.get("tipo")
        cantidad = int(request.form.get("cantidad", 0) or 0)
        nota = (request.form.get("nota") or "").strip() or None

        if tipo not in ("entrada", "salida"):
            return "Tipo inválido", 400
        if cantidad <= 0:
            return "Cantidad inválida", 400

        if producto.cantidad is None:
            producto.cantidad = 0

        if tipo == "salida" and producto.cantidad < cantidad:
            return f"Stock insuficiente. Stock actual: {producto.cantidad}", 400

        producto.cantidad += cantidad if tipo == "entrada" else -cantidad

        mov = Movimiento(producto_id=producto.id, tipo=tipo, cantidad=cantidad, nota=nota)
        producto.ultima_modificacion = datetime.utcnow()

        db.session.add(mov)
        db.session.commit()
        return redirect(url_for("movimientos", producto_id=producto.id))

    return render_template("nuevo_movimiento.html", producto=producto)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
