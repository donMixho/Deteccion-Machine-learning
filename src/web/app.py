"""Plataforma web de AppleVision Chile (Flask + SQLite).

    python -m src.web                 # http://127.0.0.1:5000
"""
import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, render_template, request, session
from werkzeug.exceptions import HTTPException

from src.utils.config import RAIZ
from src.web import db
from src.web.analisis import ColaAnalisis, analizar_con_yolo
from src.web.auth import usuario_actual
from src.web.graficos import MESES, num, segmentos
from src.web.iconos import icono
from src.web.negocio import (CATEGORIAS, ESTADOS_ANALISIS, ESTADOS_LOTE, PLANES, ROLES, TIPOS_EMPRESA,
                             porcentaje)

# Menú lateral de cada rol: (endpoint, texto, ícono)
NAVEGACION = {
    "admin": [("admin.panel", "Panel del negocio", "panel"), ("admin.empresas", "Empresas y planes", "empresa"),
              ("admin.usuarios", "Usuarios", "usuarios"), ("lotes.lista", "Todos los lotes", "lotes")],
    "jefe_planta": [("planta.panel", "Panel de planta", "panel"), ("lotes.lista", "Lotes", "lotes"),
                    ("lotes.nuevo", "Recibir lote", "nuevo"), ("planta.equipo", "Equipo", "usuarios")],
    "operador": [("planta.turno", "Mi turno", "panel"), ("lotes.nuevo", "Recibir lote", "nuevo"),
                 ("lotes.lista", "Lotes de la planta", "lotes")],
    "productor": [("productor.panel", "Mis lotes", "panel"), ("productor.analisis", "Análisis rápido", "camara"),
                  ("productor.plan", "Mi plan", "plan")],
    "exportador": [("exportador.panel", "Panel", "panel"), ("lotes.lista", "Lotes certificados", "certificado"),
                   ("publico.verificar", "Verificar certificado", "verificar")],
}

MENSAJES_ERROR = {
    400: "La solicitud no es válida. Recarga la página e inténtalo otra vez.",
    403: "Tu rol no tiene acceso a esta sección.",
    404: "No encontramos lo que buscas, o no tienes permiso para verlo.",
    413: "El archivo es demasiado grande (máximo 500 MB).",
}


def _clave_secreta(datos: Path) -> str:
    if os.environ.get("APPLEVISION_SECRET"):
        return os.environ["APPLEVISION_SECRET"]
    ruta = datos / ".clave_secreta"
    if not ruta.exists():
        datos.mkdir(parents=True, exist_ok=True)
        ruta.write_text(secrets.token_hex(32), encoding="utf-8")
    return ruta.read_text(encoding="utf-8").strip()


def _fecha(valor, formato="completa"):
    if not valor:
        return "—"
    f = datetime.fromisoformat(valor) if isinstance(valor, str) else valor
    if formato == "dia":
        return f"{f.day} {MESES[f.month - 1]}"
    if formato == "corta":
        return f.strftime("%d-%m-%Y")
    return f.strftime("%d-%m-%Y %H:%M")


def _pct(valor, decimales=1):
    return f"{(valor or 0):.{decimales}f}".replace(".", ",") + " %"


def _duracion(segundos):
    if segundos is None:
        return "—"
    if segundos < 60:
        return f"{segundos:.1f} s".replace(".", ",")
    return f"{int(segundos // 60)} min {int(segundos % 60):02d} s"


def _csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def create_app(config: dict = None) -> Flask:
    app = Flask(__name__)
    datos = Path((config or {}).get("DATOS") or os.environ.get("APPLEVISION_DATOS") or RAIZ / "web_data")
    app.config.update(
        DATOS=datos,
        DB_RUTA=datos / "applevision.db",
        MAX_CONTENT_LENGTH=500 * 1024 * 1024,
        DEMO=os.environ.get("APPLEVISION_DEMO", "1") != "0",
        COLA_SINCRONA=False,
        ANALIZADOR=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)
    app.secret_key = _clave_secreta(datos)
    (datos / "analisis").mkdir(parents=True, exist_ok=True)

    db.inicializar(app.config["DB_RUTA"])
    app.teardown_appcontext(db.cerrar_db)
    app.extensions["cola"] = ColaAnalisis(app.config["DB_RUTA"], datos,
                                          analizador=app.config["ANALIZADOR"] or analizar_con_yolo,
                                          sincrona=app.config["COLA_SINCRONA"])

    from src.web import (auth, rutas_admin, rutas_exportador, rutas_lotes, rutas_pagos, rutas_planta,
                         rutas_productor, rutas_publicas)
    for modulo in (auth, rutas_publicas, rutas_admin, rutas_planta, rutas_lotes, rutas_productor,
                   rutas_exportador, rutas_pagos):
        app.register_blueprint(modulo.bp)

    app.add_template_filter(_fecha, "fecha")
    app.add_template_filter(num, "num")
    app.add_template_filter(lambda v: "$" + num(v), "clp")
    app.add_template_filter(_pct, "pct")
    app.add_template_filter(_duracion, "duracion")
    app.add_template_global(icono, "icono")
    app.add_template_global(porcentaje, "porcentaje")
    app.add_template_global(segmentos, "segmentos")

    @app.context_processor
    def _contexto():
        usuario = usuario_actual()
        return {
            "usuario": usuario,
            "navegacion": NAVEGACION.get(usuario["rol"], []) if usuario else [],
            "endpoint": request.endpoint or "",
            "ROLES": ROLES, "PLANES": PLANES, "TIPOS_EMPRESA": TIPOS_EMPRESA,
            "ESTADOS_PAGO": rutas_pagos.ESTADOS_PAGO, "ESTADOS_LOTE": ESTADOS_LOTE, "ESTADOS_ANALISIS": ESTADOS_ANALISIS, "CATEGORIAS": CATEGORIAS,
            "csrf_token": _csrf_token, "DEMO": app.config["DEMO"],
        }

    @app.before_request
    def _vencimientos():
        if session.get("uid"):
            rutas_pagos.vencer_planes()

    @app.before_request
    def _verificar_csrf():
        if request.endpoint == "pagos.retorno":   # Webpay vuelve desde otro sitio; se valida con Transbank
            return
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            esperado = session.get("csrf")
            enviado = request.form.get("csrf") or request.headers.get("X-CSRF-Token") or ""
            if not esperado or not secrets.compare_digest(esperado, enviado):
                abort(400, "Token de seguridad vencido. Recarga la página e inténtalo otra vez.")

    @app.errorhandler(HTTPException)
    def _error(e):
        mensaje = e.description if e.code == 400 and e.description and "Token" in e.description \
            else MENSAJES_ERROR.get(e.code, e.description)
        return render_template("error.html", codigo=e.code, mensaje=mensaje), e.code

    return app
