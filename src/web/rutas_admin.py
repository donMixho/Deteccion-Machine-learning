"""Rol Administrador (equipo AppleVision): empresas, planes, usuarios y métricas del negocio."""
import re
from collections import Counter

from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from src.web import graficos
from src.web.auth import rol_requerido, usuario_actual
from src.web.db import ejecutar, todos, uno, valor
from src.web.negocio import (PLANES, ROLES, TIPOS_EMPRESA, ahora_iso, ingreso_mensual, inicio_mes,
                             planes_para)

bp = Blueprint("admin", __name__, url_prefix="/admin")

EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.route("/")
@rol_requerido("admin")
def panel():
    empresas = todos("SELECT * FROM empresas WHERE activa = 1")
    por_plan = {}
    for e in empresas:
        fila = por_plan.setdefault(e["plan"], {"clientes": 0, "unidades": 0, "mrr": 0})
        fila["clientes"] += 1
        fila["unidades"] += e["lineas"] if e["plan"] == "packing" else 1
        fila["mrr"] += ingreso_mensual(e["plan"], e["lineas"])
    por_plan = dict(sorted(((p, f) for p, f in por_plan.items() if p != "interno"),
                           key=lambda x: -x[1]["mrr"]))
    desde = inicio_mes()

    dias = graficos.dias_recientes(14)
    conteo = {r["d"]: r["n"] for r in todos(
        "SELECT substr(creado_en, 1, 10) AS d, COUNT(*) AS n FROM analisis WHERE creado_en >= ? GROUP BY d",
        (dias[0].isoformat(),))}
    serie = []
    for d in dias:
        n = conteo.get(d.isoformat(), 0)
        serie.append((graficos.etiqueta_dia(d), n, f"{graficos.etiqueta_dia(d)}: {n} análisis"))

    return render_template(
        "admin/panel.html",
        mrr=sum(f["mrr"] for f in por_plan.values()), por_plan=por_plan,
        tipos=Counter(e["tipo"] for e in empresas if e["tipo"] != "plataforma"),
        usuarios_activos=valor("SELECT COUNT(*) FROM usuarios WHERE activo = 1"),
        analisis_mes=valor("SELECT COUNT(*) FROM analisis WHERE creado_en >= ?", (desde,)),
        manzanas_mes=valor("SELECT SUM(total) FROM analisis WHERE estado = 'listo' AND creado_en >= ?", (desde,)),
        certificados_mes=valor("SELECT COUNT(*) FROM lotes WHERE estado = 'aprobado' AND revisado_en >= ?", (desde,)),
        grafico=graficos.columnas(serie, cada=2), serie=serie,
        solicitudes=todos("""SELECT s.*, e.nombre AS empresa_nombre, e.plan AS plan_actual, u.nombre AS usuario_nombre
                             FROM solicitudes s JOIN empresas e ON e.id = s.empresa_id
                             JOIN usuarios u ON u.id = s.usuario_id
                             WHERE s.estado = 'pendiente' ORDER BY s.creada_en"""),
        recientes=todos("""SELECT a.*, e.nombre AS empresa_nombre, u.nombre AS usuario_nombre, l.codigo AS lote_codigo
                           FROM analisis a JOIN empresas e ON e.id = a.empresa_id
                           JOIN usuarios u ON u.id = a.usuario_id LEFT JOIN lotes l ON l.id = a.lote_id
                           ORDER BY a.creado_en DESC, a.id DESC LIMIT 8"""))


@bp.route("/solicitudes/<int:solicitud_id>", methods=["POST"])
@rol_requerido("admin")
def resolver_solicitud(solicitud_id):
    s = uno("SELECT * FROM solicitudes WHERE id = ? AND estado = 'pendiente'", (solicitud_id,))
    if s is None:
        flash("La solicitud ya fue resuelta.", "info")
        return redirect(url_for("admin.panel"))
    if request.form.get("accion") == "aprobar":
        ejecutar("UPDATE empresas SET plan = ? WHERE id = ?", (s["plan_solicitado"], s["empresa_id"]))
        ejecutar("UPDATE solicitudes SET estado = 'aprobada', resuelta_en = ? WHERE id = ?", (ahora_iso(), solicitud_id))
        flash(f"Plan actualizado a {PLANES[s['plan_solicitado']]['nombre']}.", "exito")
    else:
        ejecutar("UPDATE solicitudes SET estado = 'rechazada', resuelta_en = ? WHERE id = ?", (ahora_iso(), solicitud_id))
        flash("Solicitud rechazada.", "info")
    return redirect(url_for("admin.panel"))


@bp.route("/empresas", methods=["GET", "POST"])
@rol_requerido("admin")
def empresas():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()[:120]
        tipo = request.form.get("tipo", "")
        plan = request.form.get("plan", "")
        lineas = request.form.get("lineas", "1")
        lineas = int(lineas) if lineas.isdigit() and 1 <= int(lineas) <= 50 else 1
        if not nombre or tipo not in TIPOS_EMPRESA or tipo == "plataforma":
            flash("Completa el nombre y el tipo de empresa.", "error")
        elif plan not in planes_para(tipo):
            flash(f"El plan elegido no corresponde a una empresa de tipo {TIPOS_EMPRESA[tipo]}.", "error")
        else:
            ejecutar("""INSERT INTO empresas (nombre, tipo, rut, region, plan, lineas, creada_en)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (nombre, tipo, request.form.get("rut", "").strip()[:20] or None,
                      request.form.get("region", "").strip()[:60] or None, plan,
                      lineas if tipo == "packing" else 1, ahora_iso()))
            flash(f"Empresa «{nombre}» creada. Ahora crea sus usuarios.", "exito")
            return redirect(url_for("admin.empresas"))
    filas = todos("""SELECT e.*, (SELECT COUNT(*) FROM usuarios u WHERE u.empresa_id = e.id) AS n_usuarios
                     FROM empresas e WHERE e.tipo != 'plataforma' ORDER BY e.tipo, e.nombre""")
    return render_template("admin/empresas.html", empresas=filas, ingreso_mensual=ingreso_mensual,
                           planes_por_tipo={t: planes_para(t) for t in TIPOS_EMPRESA})


@bp.route("/empresas/<int:empresa_id>", methods=["POST"])
@rol_requerido("admin")
def editar_empresa(empresa_id):
    e = uno("SELECT * FROM empresas WHERE id = ? AND tipo != 'plataforma'", (empresa_id,))
    if e is None:
        flash("Empresa no encontrada.", "error")
        return redirect(url_for("admin.empresas"))
    if request.form.get("accion") == "estado":
        ejecutar("UPDATE empresas SET activa = ? WHERE id = ?", (0 if e["activa"] else 1, empresa_id))
        flash(f"«{e['nombre']}» {'desactivada' if e['activa'] else 'activada'}.", "info")
    else:
        plan = request.form.get("plan", e["plan"])
        lineas = request.form.get("lineas", str(e["lineas"]))
        lineas = int(lineas) if lineas.isdigit() and 1 <= int(lineas) <= 50 else e["lineas"]
        if plan not in planes_para(e["tipo"]):
            flash("Plan no válido para este tipo de empresa.", "error")
        else:
            ejecutar("UPDATE empresas SET plan = ?, lineas = ? WHERE id = ?",
                     (plan, lineas if e["tipo"] == "packing" else 1, empresa_id))
            flash(f"«{e['nombre']}» actualizada.", "exito")
    return redirect(url_for("admin.empresas"))


@bp.route("/usuarios", methods=["GET", "POST"])
@rol_requerido("admin")
def usuarios():
    empresas_activas = todos("SELECT id, nombre, tipo FROM empresas WHERE activa = 1 ORDER BY tipo, nombre")
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()[:80]
        email = request.form.get("email", "").strip().lower()[:120]
        clave = request.form.get("clave", "")
        rol = request.form.get("rol", "")
        empresa = uno("SELECT * FROM empresas WHERE id = ?", (request.form.get("empresa_id", type=int),))
        if not nombre or not EMAIL_VALIDO.match(email) or rol not in ROLES or empresa is None:
            flash("Completa nombre, correo válido, rol y empresa.", "error")
        elif ROLES[rol]["tipo_empresa"] != empresa["tipo"]:
            flash(f"El rol {ROLES[rol]['nombre']} debe pertenecer a una empresa de tipo "
                  f"{TIPOS_EMPRESA[ROLES[rol]['tipo_empresa']]}.", "error")
        elif len(clave) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "error")
        elif uno("SELECT 1 FROM usuarios WHERE email = ?", (email,)):
            flash("Ya existe un usuario con ese correo.", "error")
        else:
            ejecutar("""INSERT INTO usuarios (nombre, email, clave_hash, rol, empresa_id, creado_en)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                     (nombre, email, generate_password_hash(clave), rol, empresa["id"], ahora_iso()))
            flash(f"Usuario {email} creado con rol {ROLES[rol]['nombre']}.", "exito")
            return redirect(url_for("admin.usuarios"))
    filas = todos("""SELECT u.*, e.nombre AS empresa_nombre FROM usuarios u
                     JOIN empresas e ON e.id = u.empresa_id ORDER BY u.rol, u.nombre""")
    return render_template("admin/usuarios.html", usuarios=filas, empresas=empresas_activas)


@bp.route("/usuarios/<int:usuario_id>/estado", methods=["POST"])
@rol_requerido("admin")
def cambiar_estado_usuario(usuario_id):
    if usuario_id == usuario_actual()["id"]:
        flash("No puedes desactivar tu propia cuenta.", "error")
        return redirect(url_for("admin.usuarios"))
    u = uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    if u is not None:
        ejecutar("UPDATE usuarios SET activo = ? WHERE id = ?", (0 if u["activo"] else 1, usuario_id))
        flash(f"{u['email']} {'desactivado' if u['activo'] else 'activado'}.", "info")
    return redirect(url_for("admin.usuarios"))
