import os
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text, CheckConstraint

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# =========================
# Flask-Login (PRO, limpio)
# =========================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = None

class User(UserMixin):
    def __init__(self, user_id: str, role: str = "general", username: str = ""):
        self.id = str(user_id)
        self.role = role
        self.username = username

# Usuarios demo (temporal)
USERS = {
    "admin":       {"id": "1", "password": "admin123",       "role": "admin"},
    "farmacia":    {"id": "2", "password": "farmacia123",    "role": "farmacia"},
    "almacen":     {"id": "3", "password": "almacen123",     "role": "almacen"},
    "recepcion":   {"id": "4", "password": "recepcion123",   "role": "recepcion"},
    "quirofano":   {"id": "5", "password": "quirofano123",   "role": "quirofano"},
    "intendencia": {"id": "6", "password": "intendencia123", "role": "intendencia"},
}

# A dónde cae cada rol después de login
ROLE_HOME = {
    "admin": "dashboard",                # ✅ tu dashboard principal
    "farmacia": "dashboard_farmacia",
    "almacen": "dashboard_almacen",
    "recepcion": "dashboard_recepcion",
    "quirofano": "dashboard_quirofano",
    "intendencia": "dashboard_intendencia",
}

@login_manager.user_loader
def load_user(user_id: str):
    for username, data in USERS.items():
        if str(data["id"]) == str(user_id):
            return User(user_id=data["id"], role=data.get("role", "general"), username=username)
    return None

# -------------------------
# Seguridad: next seguro
# -------------------------
def is_safe_url(target: str) -> bool:
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (test_url.scheme in ("http", "https")) and (ref_url.netloc == test_url.netloc)

# -------------------------
# Roles guard (PRO)
# -------------------------
def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if getattr(current_user, "role", None) not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# =========================
# Login (operativo + next)
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = (request.form.get("password") or "")

        data = USERS.get(username)

        # Validación de credenciales
        if not data or data.get("password") != password:
            flash("Credenciales inválidas.", "danger")
            return redirect(url_for("login", next=request.form.get("next") or ""))

        # Login
        user = User(
            user_id=data["id"],
            role=data.get("role", "general"),
            username=username
        )
        login_user(user)
        flash("Bienvenido ✅", "success")

        # 1) Respeta next si venía de una ruta protegida (si es seguro)
        next_url = (request.form.get("next") or request.args.get("next") or "").strip()
        if next_url and is_safe_url(next_url):
            return redirect(next_url)

        # 2) Si no hay next, manda al router por rol
        return redirect(url_for("ingresar"))

    # GET: conserva next en el form
    next_url = (request.args.get("next") or "").strip()
    return render_template("login.html", next=next_url)


# =========================
# Router general (1 punto)
# =========================
@app.route("/ingresar")
@login_required
def ingresar():
    role = getattr(current_user, "role", "general")
    endpoint = ROLE_HOME.get(role, "dashboard")

    # Si endpoint no existe por typo, cae al dashboard principal
    try:
        return redirect(url_for(endpoint))
    except Exception:
        return redirect(url_for("dashboard"))


# =========================
# Dashboards por rol (dummy)
# =========================
@app.route("/dash/farmacia")
@login_required
@roles_required("admin", "farmacia")
def dashboard_farmacia():
    return "<h1>Dashboard Farmacia</h1>"

@app.route("/dash/almacen")
@login_required
@roles_required("admin", "almacen")
def dashboard_almacen():
    return "<h1>Dashboard Almacén</h1>"

@app.route("/dash/recepcion")
@login_required
@roles_required("admin", "recepcion")
def dashboard_recepcion():
    return "<h1>Dashboard Recepción</h1>"

@app.route("/dash/quirofano")
@login_required
@roles_required("admin", "quirofano")
def dashboard_quirofano():
    return "<h1>Dashboard Quirófano</h1>"

@app.route("/dash/intendencia")
@login_required
@roles_required("admin", "intendencia")
def dashboard_intendencia():
    return "<h1>Dashboard Intendencia</h1>"


# =========================
# Logout (pro)
# =========================
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("web_publica"))


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
app.config["CIRUGIA_UPLOAD_FOLDER"] = "static/uploads/cirugias"

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# ---------------------------
# CONFIG DE PRECIOS
# ---------------------------
DEFAULT_MARGEN = 0.35
IVA_RATE = 0.16

def calcular_precio_sugerido(costo: float, margen: float = DEFAULT_MARGEN, aplica_iva: bool = False) -> float:
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
    return datetime.now(timezone.utc)

def build_photo_filename(original_name: str, fecha, folio=None) -> str:
    ext = original_name.rsplit(".", 1)[1].lower()
    safe_folio = (folio or "sinfolio").replace(" ", "_")
    timestamp = utcnow().strftime("%H%M%S%f")
    return f"{fecha.strftime('%Y%m%d')}_{safe_folio}_{timestamp}.{ext}"

def build_cirugia_photo_filename(original_name: str, fecha, folio_expediente: str) -> str:
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

    proveedor = db.Column(db.String(100))
    lote = db.Column(db.String(50))
    categoria = db.Column(db.String(50))

    unidad = db.Column(db.String(20))
    cantidad = db.Column(db.Integer)

    unidad_compra = db.Column(db.String(20))
    piezas_por_unidad = db.Column(db.Integer)
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
    tipo = db.Column(db.String(10), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
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
    __tablename__ = "cirugias"

    id = db.Column(db.Integer, primary_key=True)

    fecha = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.Time, nullable=False)
    duracion_min = db.Column(db.Integer, nullable=True)
    quirofano = db.Column(db.String(50), nullable=False, index=True)

    paciente = db.Column(db.String(160), nullable=False)
    paciente_nombre = db.Column(db.String(160), nullable=True)  # legacy
    edad = db.Column(db.Integer, nullable=False)
    sexo = db.Column(db.String(10), nullable=False)
    telefono = db.Column(db.String(30), nullable=True)

    folio_expediente = db.Column(db.String(80), nullable=False, index=True)
    especialidad = db.Column(db.String(120), nullable=True, index=True)
    procedimiento = db.Column(db.String(200), nullable=False)

    cirujano = db.Column(db.String(160), nullable=False, index=True)
    anestesiologo = db.Column(db.String(160), nullable=False, index=True)
    ayudantes = db.Column(db.Text, nullable=False)
    instrumentista = db.Column(db.String(160), nullable=False)

    indicaciones_especiales = db.Column(db.Text, nullable=True)

    estado = db.Column(db.String(30), nullable=False, default="PROGRAMADA", index=True)
    programo = db.Column(db.String(160), nullable=False)

    orden_foto_path = db.Column(db.String(255), nullable=False)

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
    tipo = db.Column(db.String(30), nullable=False, index=True)
    detalle = db.Column(db.Text, nullable=True)
    actor = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: utcnow(), index=True)

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
# INIT
# ---------------------------
with app.app_context():
    ensure_upload_folder()


# ---------------------------
# RUTAS PUBLICAS
# ---------------------------
@app.route("/")
def home():
    return redirect(url_for("web_publica"))

@app.route("/web")
def web_publica():
    return render_template("public_home.html")


# ---------------------------
# INVENTARIO (admin + almacen)
# ---------------------------
@app.route("/productos")
@login_required
@roles_required("admin", "almacen")
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
@login_required
@roles_required("admin", "almacen")
def index_redirect():
    return redirect(url_for("productos"))

@app.route("/agregar", methods=["GET", "POST"])
@login_required
@roles_required("admin", "almacen")
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
@login_required
@roles_required("admin", "almacen")
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
@login_required
@roles_required("admin", "almacen")
def movimientos():
    producto_id = request.args.get("producto_id", type=int)
    if producto_id:
        producto = Producto.query.get_or_404(producto_id)
        movs = Movimiento.query.filter_by(producto_id=producto_id).order_by(Movimiento.fecha.desc()).all()
        return render_template("movimientos.html", producto=producto, movimientos=movs)

    movs = Movimiento.query.order_by(Movimiento.fecha.desc()).limit(200).all()
    return render_template("movimientos.html", producto=None, movimientos=movs)

@app.route("/movimiento/nuevo/<int:producto_id>", methods=["GET", "POST"])
@login_required
@roles_required("admin", "almacen")
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


# ---------------------------
# FARMACIA (admin + farmacia)
# ---------------------------
@app.route("/farmacia/pendientes", methods=["GET"])
@login_required
@roles_required("admin", "farmacia")
def farmacia_pendientes():
    fecha_str = request.args.get("fecha")
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
@login_required
@roles_required("admin", "farmacia")
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
@login_required
@roles_required("admin", "farmacia")
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


# ---------------------------
# DASHBOARD PRINCIPAL (admin)
# ---------------------------
@app.route("/dashboard")
@login_required
@roles_required("admin")
def dashboard():
    productos_count = Producto.query.count()
    movimientos_count = Movimiento.query.count()
    pendientes_count = FarmaciaPendienteRegistro.query.count()

    hoy = datetime.now().date()
    ahora = datetime.now().time()

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


# ---------------------------
# CIRUGIAS (admin + quirofano)
# ---------------------------
@app.route("/cirugias")
@login_required
@roles_required("admin", "quirofano")
def cirugias():
    fecha_str = request.args.get("fecha")
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else datetime.now().date()
    except ValueError:
        fecha = datetime.now().date()

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
@login_required
@roles_required("admin", "quirofano")
def nueva_cirugia():
    if request.method == "POST":
        fecha_str = (request.form.get("fecha") or "").strip()
        hora_str  = (request.form.get("hora_inicio") or "").strip()

        if not fecha_str or not hora_str:
            return "Fecha y hora son obligatorias", 400

        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            hora_inicio = datetime.strptime(hora_str, "%H:%M").time()
        except ValueError:
            return "Fecha u hora inválidas", 400

        dur_str = (request.form.get("duracion_min") or "").strip()
        try:
            duracion_min = int(dur_str) if dur_str else 60
        except ValueError:
            duracion_min = 60

        estado = (request.form.get("estado") or "PROGRAMADA").strip()
        if estado not in ESTADOS_CIRUGIA:
            estado = "PROGRAMADA"

        quirofano = (request.form.get("quirofano") or "").strip()
        paciente  = (request.form.get("paciente") or "").strip()
        telefono = (request.form.get("telefono") or "").strip() or None

        folio_expediente = (request.form.get("folio_expediente") or "").strip()
        especialidad = (request.form.get("especialidad") or "").strip() or None
        procedimiento = (request.form.get("procedimiento") or "").strip()

        cirujano = (request.form.get("cirujano") or "").strip()
        anestesiologo = (request.form.get("anestesiologo") or "").strip()
        ayudantes = (request.form.get("ayudantes") or "").strip()
        instrumentista = (request.form.get("instrumentista") or "").strip()
        programo = (request.form.get("programo") or "").strip()

        sexo = (request.form.get("sexo") or "").strip()
        if sexo not in SEXOS:
            return "Sexo inválido", 400

        try:
            edad = int((request.form.get("edad") or "").strip())
            if edad < 0 or edad > 120:
                return "Edad inválida", 400
        except:
            return "Edad inválida", 400

        indicaciones = (request.form.get("indicaciones_especiales") or "").strip() or None

        obligatorios = [
            ("quirófano", quirofano),
            ("paciente", paciente),
            ("folio/expediente", folio_expediente),
            ("procedimiento", procedimiento),
            ("cirujano", cirujano),
            ("anestesiólogo", anestesiologo),
            ("ayudantes", ayudantes),
            ("instrumentista", instrumentista),
            ("programó", programo),
        ]
        faltan = [name for name, val in obligatorios if not val]
        if faltan:
            return f"Faltan campos obligatorios: {', '.join(faltan)}", 400

        file = request.files.get("orden_foto")
        if not file or not file.filename:
            return "La foto de la orden física es obligatoria.", 400
        if not allowed_file(file.filename):
            return "Formato inválido. Usa JPG, PNG o WEBP.", 400

        original = secure_filename(file.filename)
        new_name = build_cirugia_photo_filename(original, fecha, folio_expediente)

        save_path = os.path.join(app.config["CIRUGIA_UPLOAD_FOLDER"], new_name)
        file.save(save_path)

        rel_path = f"uploads/cirugias/{new_name}"

        c = Cirugia(
            fecha=fecha,
            hora_inicio=hora_inicio,
            duracion_min=duracion_min,
            quirofano=quirofano,

            paciente=paciente,
            paciente_nombre=paciente,  # legacy

            edad=edad,
            sexo=sexo,
            telefono=telefono,

            folio_expediente=folio_expediente,
            especialidad=especialidad,
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
@login_required
@roles_required("admin", "quirofano")
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


# ---------------------------
# ERRORES BONITOS
# ---------------------------
@app.errorhandler(403)
def forbidden(_):
    return "<h1>403 - No autorizado</h1><p>No tienes permisos para acceder aquí.</p>", 403


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
