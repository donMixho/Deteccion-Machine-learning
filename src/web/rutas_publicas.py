"""Páginas sin cuenta: portada (modelo de negocio y planes) y verificación de certificados."""
from flask import Blueprint, render_template, request

from src.web import graficos
from src.web.db import uno
from src.web.negocio import BENEFICIOS, PLANES, ROLES

bp = Blueprint("publico", __name__)

# Resultados reales del modelo (README.md, sección Resultados)
METRICAS_MODELO = [
    ("0,908", "mAP50 en validación"),
    ("0,881", "Recall"),
    ("758", "imágenes de entrenamiento"),
    ("2.223", "manzanas etiquetadas"),
]


@bp.route("/")
def inicio():
    planes = {clave: p for clave, p in PLANES.items() if p["publico"]}
    return render_template("publico/inicio.html", planes=planes, beneficios=BENEFICIOS, roles=ROLES,
                           metricas=METRICAS_MODELO)


@bp.route("/verificar")
def verificar():
    codigo = request.args.get("codigo", "").strip().upper()[:20]
    lote = revisor = None
    if codigo:
        lote = uno("SELECT * FROM v_lotes WHERE certificado = ? AND estado = 'aprobado'", (codigo,))
        if lote is not None and lote["revisado_por"]:
            revisor = uno("SELECT nombre FROM usuarios WHERE id = ?", (lote["revisado_por"],))
    return render_template("publico/verificar.html", codigo=codigo, lote=lote, revisor=revisor,
                           seg_lote=graficos.segmentos(lote) if lote else [])
