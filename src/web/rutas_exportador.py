"""Rol Exportadora: lotes certificados de sus proveedores, consolidado por variedad y packing."""
from flask import Blueprint, render_template

from src.web import graficos
from src.web.auth import rol_requerido, usuario_actual
from src.web.db import todos, valor
from src.web.negocio import porcentaje

bp = Blueprint("exportador", __name__, url_prefix="/exportador")


def _agrupar(lotes, campo):
    grupos = {}
    for l in lotes:
        g = grupos.setdefault(l[campo], {"nombre": l[campo], "lotes": 0, "total": 0, "buena": 0, "detalle": 0,
                                         "no_pasa": 0})
        g["lotes"] += 1
        for clave in ("total", "buena", "detalle", "no_pasa"):
            g[clave] += l[clave]
    filas = sorted(grupos.values(), key=lambda g: -g["total"])
    for g in filas:
        g["pct_buena"] = porcentaje(g["buena"], g["total"])
        g["segmentos"] = graficos.segmentos(g)
    return filas


@bp.route("/")
@rol_requerido("exportador")
def panel():
    usuario = usuario_actual()
    lotes = todos("""SELECT * FROM v_lotes WHERE exportadora_id = ? AND estado = 'aprobado'
                     ORDER BY revisado_en DESC""", (usuario["empresa_id"],))
    total = sum(l["total"] for l in lotes)
    return render_template(
        "exportador/panel.html", lotes=lotes, total=total,
        pct_buena=porcentaje(sum(l["buena"] for l in lotes), total),
        proveedores=len({l["packing_id"] for l in lotes}), productores=len({l["productor_id"] for l in lotes}),
        en_proceso=valor("SELECT COUNT(*) FROM lotes WHERE exportadora_id = ? AND estado != 'aprobado'",
                         (usuario["empresa_id"],)),
        por_variedad=_agrupar(lotes, "variedad"), por_packing=_agrupar(lotes, "packing_nombre"))
