"""Ingreso, salida, acceso rápido de demostración y control de acceso por rol."""
import secrets
from functools import wraps

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

from src.web.db import ejecutar, uno
from src.web.negocio import ahora_iso

bp = Blueprint("auth", __name__)

INICIO_POR_ROL = {
    "admin": "admin.panel",
    "jefe_planta": "planta.panel",
    "operador": "planta.turno",
    "productor": "productor.panel",
    "exportador": "exportador.panel",
}


def usuario_actual():
    if "usuario" not in g:
        uid = session.get("uid")
        g.usuario = uno(
            """SELECT u.*, e.nombre AS empresa_nombre, e.tipo AS empresa_tipo, e.plan AS empresa_plan,
                      e.lineas AS empresa_lineas
               FROM usuarios u JOIN empresas e ON e.id = u.empresa_id
               WHERE u.id = ? AND u.activo = 1 AND e.activa = 1""", (uid,)) if uid else None
    return g.usuario


def url_inicio(usuario) -> str:
    return url_for(INICIO_POR_ROL[usuario["rol"]])


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if usuario_actual() is None:
            return redirect(url_for("auth.ingresar", next=request.full_path.rstrip("?")))
        return vista(*args, **kwargs)
    return envoltura


def rol_requerido(*roles):
    """Restringe una vista a ciertos roles. Sin sesión -> login; rol distinto -> 403."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                return redirect(url_for("auth.ingresar", next=request.full_path.rstrip("?")))
            if usuario["rol"] not in roles:
                abort(403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador


def _destino_seguro(destino: str):
    """Solo rutas internas: evita redirecciones abiertas a otros sitios."""
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return None


def iniciar_sesion(usuario) -> None:
    session.clear()
    session["uid"] = usuario["id"]
    session["csrf"] = secrets.token_urlsafe(32)
    ejecutar("UPDATE usuarios SET ultimo_acceso = ? WHERE id = ?", (ahora_iso(), usuario["id"]))
    g.pop("usuario", None)


@bp.route("/ingresar", methods=["GET", "POST"])
def ingresar():
    if usuario_actual() is not None and request.method == "GET":
        return redirect(url_inicio(usuario_actual()))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        clave = request.form.get("clave", "")
        usuario = uno("""SELECT u.* FROM usuarios u JOIN empresas e ON e.id = u.empresa_id
                         WHERE u.email = ? AND u.activo = 1 AND e.activa = 1""", (email,))
        if usuario is None or not check_password_hash(usuario["clave_hash"], clave):
            flash("Correo o contraseña incorrectos.", "error")
            return render_template("publico/ingresar.html", email=email), 401
        iniciar_sesion(usuario)
        return redirect(_destino_seguro(request.args.get("next")) or url_inicio(usuario_actual()))
    return render_template("publico/ingresar.html", email="")


@bp.route("/salir", methods=["POST"])
def salir():
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("publico.inicio"))


@bp.route("/demo/<rol>")
def demo(rol):
    """Acceso con un clic a las cuentas de demostración (solo con APPLEVISION_DEMO activo)."""
    from src.web.demo import CUENTAS_DEMO
    if not current_app.config["DEMO"] or rol not in CUENTAS_DEMO:
        abort(404)
    usuario = uno("SELECT * FROM usuarios WHERE email = ? AND activo = 1", (CUENTAS_DEMO[rol]["email"],))
    if usuario is None:
        flash("La cuenta de demostración no existe. Reinicia los datos con: python -m src.web --reiniciar-demo",
              "error")
        return redirect(url_for("auth.ingresar"))
    iniciar_sesion(usuario)
    return redirect(_destino_seguro(request.args.get("next")) or url_inicio(usuario_actual()))
