"""Roles del packing: Jefe de planta (panel, equipo) y Operador de línea (turno)."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from src.web import graficos
from src.web.auth import rol_requerido, usuario_actual
from src.web.db import ejecutar, todos, uno, valor
from src.web.negocio import ahora_iso, inicio_mes, porcentaje
from src.web.rutas_admin import EMAIL_VALIDO

bp = Blueprint("planta", __name__, url_prefix="/planta")


@bp.route("/")
@rol_requerido("jefe_planta")
def panel():
    usuario = usuario_actual()
    pid, desde = usuario["empresa_id"], inicio_mes()
    mes = uno("""SELECT COUNT(*) AS n, SUM(a.total) AS total, SUM(a.buena) AS buena, SUM(a.detalle) AS detalle,
                        SUM(a.no_pasa) AS no_pasa, SUM(a.pudricion) AS pudricion
                 FROM analisis a JOIN lotes l ON l.id = a.lote_id
                 WHERE l.packing_id = ? AND a.estado = 'listo' AND a.creado_en >= ?""", (pid, desde))
    validados = todos("SELECT total, conteo_manual FROM v_lotes WHERE packing_id = ? AND conteo_manual > 0", (pid,))
    error_medio = (sum(abs(v["total"] - v["conteo_manual"]) / v["conteo_manual"] for v in validados)
                   * 100 / len(validados)) if validados else None

    dias = graficos.dias_recientes(14)
    filas = {r["d"]: dict(r) for r in todos(
        """SELECT substr(a.creado_en, 1, 10) AS d, SUM(a.buena) AS buena, SUM(a.detalle) AS detalle,
                  SUM(a.no_pasa) AS no_pasa
           FROM analisis a JOIN lotes l ON l.id = a.lote_id
           WHERE l.packing_id = ? AND a.estado = 'listo' AND a.creado_en >= ? GROUP BY d""",
        (pid, dias[0].isoformat()))}
    datos_grafico = [(graficos.etiqueta_dia(d), filas.get(d.isoformat(), {})) for d in dias]

    return render_template(
        "planta/panel.html", mes=mes, pct_buena=porcentaje(mes["buena"], mes["total"]),
        pct_no_pasa=porcentaje(mes["no_pasa"], mes["total"]), segmentos_mes=graficos.segmentos(mes),
        por_aprobar=valor("SELECT COUNT(*) FROM lotes WHERE packing_id = ? AND estado = 'por_aprobar'", (pid,)),
        en_analisis=valor("SELECT COUNT(*) FROM lotes WHERE packing_id = ? AND estado = 'en_analisis'", (pid,)),
        certificados_mes=valor("""SELECT COUNT(*) FROM lotes WHERE packing_id = ? AND estado = 'aprobado'
                                  AND revisado_en >= ?""", (pid, desde)),
        error_medio=error_medio, n_validados=len(validados),
        grafico=graficos.apiladas(datos_grafico, cada=2), datos_grafico=datos_grafico,
        por_revisar=todos("""SELECT * FROM v_lotes WHERE packing_id = ? AND estado IN ('por_aprobar', 'en_analisis')
                             ORDER BY creado_en""", (pid,)),
        por_linea=todos("""SELECT l.linea, COUNT(DISTINCT l.id) AS lotes, COALESCE(SUM(a.total), 0) AS total,
                                  COALESCE(SUM(a.buena), 0) AS buena
                           FROM lotes l LEFT JOIN analisis a ON a.lote_id = l.id AND a.estado = 'listo'
                           WHERE l.packing_id = ? AND l.creado_en >= ? GROUP BY l.linea ORDER BY l.linea""",
                        (pid, desde)))


@bp.route("/turno")
@rol_requerido("operador")
def turno():
    usuario = usuario_actual()
    hoy = date.today().isoformat()
    return render_template(
        "planta/turno.html",
        hoy=uno("""SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS total FROM analisis
                   WHERE usuario_id = ? AND estado = 'listo' AND creado_en >= ?""", (usuario["id"], hoy)),
        mis_analisis=todos("""SELECT a.*, l.codigo AS lote_codigo FROM analisis a LEFT JOIN lotes l ON l.id = a.lote_id
                              WHERE a.usuario_id = ? ORDER BY a.creado_en DESC, a.id DESC LIMIT 10""",
                           (usuario["id"],)),
        activos=todos("""SELECT * FROM v_lotes WHERE packing_id = ?
                         AND estado IN ('recepcionado', 'en_analisis', 'por_aprobar', 'rechazado')
                         ORDER BY CASE estado WHEN 'rechazado' THEN 0 WHEN 'recepcionado' THEN 1 ELSE 2 END,
                                  creado_en DESC LIMIT 12""", (usuario["empresa_id"],)))


@bp.route("/equipo", methods=["GET", "POST"])
@rol_requerido("jefe_planta")
def equipo():
    usuario = usuario_actual()
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()[:80]
        email = request.form.get("email", "").strip().lower()[:120]
        clave = request.form.get("clave", "")
        rol = request.form.get("rol", "operador")
        if rol not in ("operador", "jefe_planta") or not nombre or not EMAIL_VALIDO.match(email):
            flash("Completa nombre, correo válido y rol.", "error")
        elif len(clave) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "error")
        elif uno("SELECT 1 FROM usuarios WHERE email = ?", (email,)):
            flash("Ya existe un usuario con ese correo.", "error")
        else:
            ejecutar("""INSERT INTO usuarios (nombre, email, clave_hash, rol, empresa_id, creado_en)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                     (nombre, email, generate_password_hash(clave), rol, usuario["empresa_id"], ahora_iso()))
            flash(f"{nombre} ya puede ingresar con {email}.", "exito")
            return redirect(url_for("planta.equipo"))
    miembros = todos("""SELECT u.*, (SELECT COUNT(*) FROM analisis a WHERE a.usuario_id = u.id) AS n_analisis
                        FROM usuarios u WHERE u.empresa_id = ? ORDER BY u.rol, u.nombre""", (usuario["empresa_id"],))
    return render_template("planta/equipo.html", miembros=miembros)


@bp.route("/equipo/<int:usuario_id>/estado", methods=["POST"])
@rol_requerido("jefe_planta")
def cambiar_estado(usuario_id):
    usuario = usuario_actual()
    miembro = uno("SELECT * FROM usuarios WHERE id = ? AND empresa_id = ?", (usuario_id, usuario["empresa_id"]))
    if miembro is None or miembro["id"] == usuario["id"]:
        flash("No puedes cambiar el estado de esa cuenta.", "error")
    else:
        ejecutar("UPDATE usuarios SET activo = ? WHERE id = ?", (0 if miembro["activo"] else 1, usuario_id))
        flash(f"{miembro['nombre']} {'desactivado' if miembro['activo'] else 'activado'}.", "info")
    return redirect(url_for("planta.equipo"))
