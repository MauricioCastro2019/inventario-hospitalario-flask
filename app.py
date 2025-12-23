from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import sys

# ---------------------------
# APP
# ---------------------------

app = Flask(__name__)

# ---------------------------
# DATABASE CONFIG (Railway / Local)
# ---------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Railway usa postgres:// pero SQLAlchemy necesita postgresql://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    # Local fallback
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
    tipo = db.Column(db.String(10), nullable=False)  # entrada / salida
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    nota = db.Column(db.String(255))


# ---------------------------
# AUTO CREATE TABLES (Railway Safe)
# ---------------------------

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
        productos = Producto.query.order_by(Producto.ingreso.desc()).all()

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
            cantidad=int(request.form["cantidad"]),
            stock_minimo=int(request.form.get("stock_minimo", 0)),
            costo=float(request.form["costo"]),
            precio=float(request.form["precio"]),
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
        producto.cantidad = int(request.form["cantidad"])
        producto.stock_minimo = int(request.form.get("stock_minimo", 0))
        producto.costo = float(request.form["costo"])
        producto.precio = float(request.form["precio"])
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
        tipo = request.form["tipo"]
        cantidad = int(request.form["cantidad"])
        nota = request.form.get("nota") or None

        if tipo == "salida" and producto.cantidad < cantidad:
            return "Stock insuficiente", 400

        producto.cantidad += cantidad if tipo == "entrada" else -cantidad

        mov = Movimiento(
            producto_id=producto.id,
            tipo=tipo,
            cantidad=cantidad,
            nota=nota
        )

        producto.ultima_modificacion = datetime.utcnow()

        db.session.add(mov)
        db.session.commit()
        return redirect(url_for("movimientos", producto_id=producto.id))

    return render_template("nuevo_movimiento.html", producto=producto)


# ---------------------------
# ENTRYPOINT
# ---------------------------

if __name__ == "__main__":
    app.run()
