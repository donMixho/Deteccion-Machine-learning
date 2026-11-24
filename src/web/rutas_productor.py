"""Rol Productor: sus lotes con evidencia, análisis rápido de fotos (cuota por plan) y su plan."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.web import graficos
from src.web.auth import rol_requerido, usuario_actual
from src.web.db import ejecutar, todos, uno, valor
from src.web.negocio import (BENEFICIOS, NIVELES_SENSIBILIDAD, PLANES, ahora_iso, inicio_mes, planes_para,
                             porcentaje)
from src.web.rutas_lotes import crear_analisis

bp = Blueprint("productor", __name__, url_prefix="/productor")


def cuota(usuario) -> dict:
    """Análisis rápidos usados este mes contra el límite del plan (None = ilimitado).

    Un análisis que falló (archivo dañado) no consume cuota."""
    plan = PLANES[usuario["empresa_plan"]]
    usados = valor("""SELECT COUNT(*) FROM analisis WHERE empresa_id = ? AND lote_id IS NULL
                      AND estado != 'error' AND creado_en >= ?""", (usuario["empresa_id"], inicio_mes()))
    limite = plan["cuota_fotos"]
    return {"usados": usados, "limite": limite, "plan": plan,
            "pct": min(100.0, 100.0 * usados / limite) if limite else 0.0,
            "agotada": limite is not None and usados >= limite}


def solicitud_pendiente(empresa_id):
    return uno("SELECT * FROM solicitudes WHERE empresa_id = ? AND estado = 'pendiente'", (empresa_id,))


@bp.route("/")
@rol_requerido("productor")
def panel():
    usuario = usuario_actual()
    lotes = todos("SELECT * FROM v_lotes WHERE productor_id = ? ORDER BY creado_en DESC", (usuario["empresa_id"],))
    total = sum(l["total"] for l in lotes)
    buena = sum(l["buena"] for l in lotes)
    con_resultado = [l for l in lotes if l["total"] > 0][:10][::-1]   # 10 más recientes, en orden temporal
    serie = [(l["codigo"].split("-")[-1], porcentaje(l["buena"], l["total"]),
              f"{l['codigo']} · {l['variedad']}: {porcentaje(l['buena'], l['total']):.1f} % Buena".replace(".", ","))
             for l in con_resultado]
    return render_template(
        "productor/panel.html", lotes=lotes, total=total, pct_buena=porcentaje(buena, total),
        certificados=sum(1 for l in lotes if l["estado"] == "aprobado"),
        grafico=graficos.columnas(serie, porcentaje=True) if serie else None, serie=serie,
        cuota=cuota(usuario), solicitud=solicitud_pendiente(usuario["empresa_id"]))


@bp.route("/analisis", methods=["GET", "POST"])
@rol_requerido("productor")
def analisis():
    usuario = usuario_actual()
    estado_cuota = cuota(usuario)
    if request.method == "POST":
        if estado_cuota["agotada"]:
            flash(f"Usaste los {estado_cuota['limite']} análisis de tu plan este mes. "
                  "Cámbiate a Pro para seguir analizando.", "error")
            return redirect(url_for("productor.plan"))
        nivel = request.form.get("sensibilidad", "normal")
        try:
            analisis_id = crear_analisis(request.files.get("archivo"), usuario, None,
                                         nivel if nivel in NIVELES_SENSIBILIDAD else "normal",
                                         permitir_video=PLANES[usuario["empresa_plan"]]["video"])
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("productor.analisis"))
        return redirect(url_for("lotes.ver_analisis", analisis_id=analisis_id))
    previos = todos("""SELECT * FROM analisis WHERE empresa_id = ? AND lote_id IS NULL
                       ORDER BY creado_en DESC, id DESC LIMIT 24""", (usuario["empresa_id"],))
    return render_template("productor/analisis.html", previos=previos, cuota=estado_cuota,
                           niveles=NIVELES_SENSIBILIDAD)


@bp.route("/plan", methods=["GET", "POST"])
@rol_requerido("productor")
def plan():
    usuario = usuario_actual()
    pendiente = solicitud_pendiente(usuario["empresa_id"])
    planes = planes_para("productor")
    if request.method == "POST":
        solicitado = request.form.get("plan", "")
        if pendiente:
            flash("Ya tienes una solicitud pendiente.", "info")
        elif solicitado not in planes or solicitado == usuario["empresa_plan"]:
            flash("Elige un plan distinto al actual.", "error")
        else:
            ejecutar("""INSERT INTO solicitudes (empresa_id, usuario_id, plan_solicitado, creada_en)
                        VALUES (?, ?, ?, ?)""", (usuario["empresa_id"], usuario["id"], solicitado, ahora_iso()))
            flash(f"Solicitud enviada: {PLANES[solicitado]['nombre']}. El equipo AppleVision la activará.", "exito")
        return redirect(url_for("productor.plan"))
    return render_template("productor/plan.html", planes=planes, beneficios=BENEFICIOS, cuota=cuota(usuario),
                           pendiente=pendiente)
