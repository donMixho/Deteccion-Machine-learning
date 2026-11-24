"""Lotes y análisis: vistas compartidas por todos los roles, filtradas según quién mira."""
import csv
import io
import shutil
import uuid
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)

from src.web import graficos
from src.web.analisis import recalcular_estado_lote
from src.web.auth import login_requerido, rol_requerido, usuario_actual
from src.web.db import ejecutar, get_db, todos, uno, valor
from src.web.negocio import (ESTADOS_LOTE, LINEA_CONTEO_DEFECTO, NIVELES_SENSIBILIDAD, PLANES,
                             SENSIBILIDADES, VARIEDADES, ahora_iso, codigo_lote, nuevo_certificado,
                             porcentaje, puede_ver_lote, tipo_archivo)

bp = Blueprint("lotes", __name__)


# ------------------------------------------------------------------ utilidades
def filtro_lotes(usuario):
    """(condición SQL, parámetros) con los lotes que el usuario puede ver."""
    rol, empresa = usuario["rol"], usuario["empresa_id"]
    if rol == "admin":
        return "1 = 1", []
    if rol in ("jefe_planta", "operador"):
        return "packing_id = ?", [empresa]
    if rol == "productor":
        return "productor_id = ?", [empresa]
    return "exportadora_id = ? AND estado = 'aprobado'", [empresa]


def lote_visible(lote_id: int):
    lote = uno("SELECT * FROM v_lotes WHERE id = ?", (lote_id,))
    if lote is None or not puede_ver_lote(usuario_actual(), lote):
        abort(404)   # 404 y no 403: no revela que el lote existe
    return lote


def analisis_visible(analisis_id: int):
    a = uno("SELECT * FROM analisis WHERE id = ?", (analisis_id,))
    if a is None:
        abort(404)
    usuario = usuario_actual()
    if a["lote_id"]:
        lote_visible(a["lote_id"])
    elif usuario["rol"] != "admin" and a["empresa_id"] != usuario["empresa_id"]:
        abort(404)
    return a


def puede_editar_lote(usuario, lote) -> bool:
    return (usuario["rol"] in ("jefe_planta", "operador") and lote["packing_id"] == usuario["empresa_id"]
            and lote["estado"] != "aprobado")


def guardar_subida(archivo):
    """Guarda el archivo subido en web_data/analisis/<id>/ y devuelve (tipo, ruta relativa, nombre)."""
    nombre = (archivo.filename or "").strip()
    tipo = tipo_archivo(nombre)
    if tipo is None:
        raise ValueError("Formato no soportado. Fotos: jpg, png, bmp, webp. Videos: mp4, avi, mov, mkv, wmv, webm.")
    ext = "." + nombre.rsplit(".", 1)[-1].lower()
    carpeta_id = uuid.uuid4().hex
    carpeta = Path(current_app.config["DATOS"]) / "analisis" / carpeta_id
    carpeta.mkdir(parents=True)
    destino = carpeta / f"entrada{ext}"
    archivo.save(destino)
    if destino.stat().st_size == 0:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise ValueError("El archivo está vacío.")
    return tipo, f"analisis/{carpeta_id}/entrada{ext}", nombre[:120]


def crear_analisis(archivo, usuario, lote_id=None, nivel="normal", linea_conteo=LINEA_CONTEO_DEFECTO,
                   permitir_video=True) -> int:
    """Registra un análisis y lo deja en la cola. Lanza ValueError con un mensaje para el usuario."""
    if not archivo or not archivo.filename:
        raise ValueError("Elige una foto o un video.")
    if not permitir_video and tipo_archivo(archivo.filename) == "video":
        raise ValueError("Tu plan permite analizar fotos. El análisis de video es parte del plan Packing.")
    tipo, ruta, nombre = guardar_subida(archivo)
    sensibilidad = SENSIBILIDADES[tipo].get(nivel, SENSIBILIDADES[tipo]["normal"])
    analisis_id = ejecutar(
        """INSERT INTO analisis (lote_id, empresa_id, usuario_id, tipo, nombre_archivo, archivo_entrada,
                                 sensibilidad, linea_conteo, creado_en)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (lote_id, usuario["empresa_id"], usuario["id"], tipo, nombre, ruta, sensibilidad,
         int(linea_conteo) if tipo == "video" else None, ahora_iso()))
    if lote_id:
        ejecutar("UPDATE lotes SET estado = 'en_analisis' WHERE id = ? AND estado != 'aprobado'", (lote_id,))
    current_app.extensions["cola"].encolar(analisis_id)
    return analisis_id


def _entero(texto, minimo=None, maximo=None):
    try:
        n = int(str(texto).strip())
    except (TypeError, ValueError):
        return None
    if (minimo is not None and n < minimo) or (maximo is not None and n > maximo):
        return None
    return n


def _parametros_analisis():
    nivel = request.form.get("sensibilidad", "normal")
    nivel = nivel if nivel in NIVELES_SENSIBILIDAD else "normal"
    linea = _entero(request.form.get("linea_conteo"), 10, 90) or LINEA_CONTEO_DEFECTO
    return nivel, linea


# ------------------------------------------------------------------ lista y CSV
def _consulta_lista(usuario):
    condicion, params = filtro_lotes(usuario)
    estado = request.args.get("estado", "")
    buscar = request.args.get("q", "").strip()
    if estado in ESTADOS_LOTE:
        condicion += " AND estado = ?"
        params.append(estado)
    if buscar:
        condicion += " AND (codigo LIKE ? OR productor_nombre LIKE ? OR variedad LIKE ? OR certificado LIKE ?)"
        params += [f"%{buscar}%"] * 4
    return todos(f"SELECT * FROM v_lotes WHERE {condicion} ORDER BY creado_en DESC LIMIT 300", params), estado, buscar


@bp.route("/lotes")
@login_requerido
def lista():
    usuario = usuario_actual()
    lotes, estado, buscar = _consulta_lista(usuario)
    return render_template("lotes/lista.html", lotes=lotes, estado=estado, buscar=buscar,
                           permite_csv=PLANES[usuario["empresa_plan"]]["csv"])


@bp.route("/lotes.csv")
@login_requerido
def exportar_csv():
    usuario = usuario_actual()
    if not PLANES[usuario["empresa_plan"]]["csv"]:
        flash("La descarga CSV es parte del plan Pro.", "info")
        return redirect(url_for("productor.plan"))
    lotes, _, _ = _consulta_lista(usuario)
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")   # ';' para Excel en español
    escritor.writerow(["codigo", "fecha", "packing", "productor", "exportadora", "variedad", "bins", "linea",
                       "estado", "total", "buena", "con_detalle", "no_pasa", "pct_buena", "conteo_manual",
                       "certificado"])
    for l in lotes:
        escritor.writerow([l["codigo"], l["creado_en"][:16].replace("T", " "), l["packing_nombre"],
                           l["productor_nombre"], l["exportadora_nombre"] or "", l["variedad"], l["bins"] or "",
                           l["linea"], ESTADOS_LOTE[l["estado"]], l["total"], l["buena"], l["detalle"],
                           l["no_pasa"], str(porcentaje(l["buena"], l["total"])).replace(".", ","),
                           "" if l["conteo_manual"] is None else l["conteo_manual"], l["certificado"] or ""])
    return Response("﻿" + salida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=lotes_applevision.csv"})


# ------------------------------------------------------------------ recepción
@bp.route("/lotes/nuevo", methods=["GET", "POST"])
@rol_requerido("jefe_planta", "operador")
def nuevo():
    usuario = usuario_actual()
    productores = todos("SELECT id, nombre FROM empresas WHERE tipo = 'productor' AND activa = 1 ORDER BY nombre")
    exportadoras = todos("SELECT id, nombre FROM empresas WHERE tipo = 'exportadora' AND activa = 1 ORDER BY nombre")
    lineas = max(int(usuario["empresa_lineas"] or 1), 1)
    form = request.form if request.method == "POST" else {}

    if request.method == "POST":
        productor_id = _entero(form.get("productor_id"))
        exportadora_id = _entero(form.get("exportadora_id"))
        variedad = form.get("variedad", "")
        linea = _entero(form.get("linea"), 1, lineas) or 1
        bins = _entero(form.get("bins"), 0, 10000) if form.get("bins") else None
        errores = []
        if productor_id not in {p["id"] for p in productores}:
            errores.append("Elige el productor que entrega la fruta.")
        if exportadora_id is not None and exportadora_id not in {e["id"] for e in exportadoras}:
            errores.append("La exportadora elegida no es válida.")
        if variedad not in VARIEDADES:
            errores.append("Elige la variedad.")
        archivo = request.files.get("archivo")
        if archivo and archivo.filename and tipo_archivo(archivo.filename) is None:
            errores.append("El archivo debe ser una foto (jpg, png, bmp, webp) o un video (mp4, avi, mov, mkv, wmv, webm).")
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("lotes/nuevo.html", productores=productores, exportadoras=exportadoras,
                                   lineas=lineas, form=form, niveles=NIVELES_SENSIBILIDAD,
                                   variedades=VARIEDADES, linea_defecto=LINEA_CONTEO_DEFECTO), 400

        con = get_db()
        cur = con.execute(
            """INSERT INTO lotes (codigo, packing_id, productor_id, exportadora_id, variedad, bins, linea,
                                  creado_por, creado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, usuario["empresa_id"], productor_id, exportadora_id, variedad, bins, linea,
             usuario["id"], ahora_iso()))
        lote_id = cur.lastrowid
        con.execute("UPDATE lotes SET codigo = ? WHERE id = ?", (codigo_lote(lote_id), lote_id))
        con.commit()
        if archivo and archivo.filename:
            nivel, linea_conteo = _parametros_analisis()
            try:
                crear_analisis(archivo, usuario, lote_id, nivel, linea_conteo,
                               permitir_video=PLANES[usuario["empresa_plan"]]["video"])
                flash("Lote recibido. El modelo está analizando el archivo.", "exito")
            except ValueError as e:
                flash(f"Lote creado, pero el archivo no se pudo analizar: {e}", "error")
        else:
            flash("Lote recibido. Sube una foto o un video para analizarlo.", "exito")
        return redirect(url_for("lotes.detalle", lote_id=lote_id))

    return render_template("lotes/nuevo.html", productores=productores, exportadoras=exportadoras, lineas=lineas,
                           form=form, niveles=NIVELES_SENSIBILIDAD, variedades=VARIEDADES,
                           linea_defecto=LINEA_CONTEO_DEFECTO)


# ------------------------------------------------------------------ detalle
@bp.route("/lotes/<int:lote_id>")
@login_requerido
def detalle(lote_id):
    usuario = usuario_actual()
    lote = lote_visible(lote_id)
    analisis = todos("""SELECT a.*, u.nombre AS usuario_nombre FROM analisis a
                        JOIN usuarios u ON u.id = a.usuario_id WHERE a.lote_id = ?
                        ORDER BY a.creado_en DESC, a.id DESC""", (lote_id,))
    revisor = uno("SELECT nombre FROM usuarios WHERE id = ?", (lote["revisado_por"],)) if lote["revisado_por"] else None
    pendientes = any(a["estado"] in ("en_cola", "procesando") for a in analisis)
    error_conteo = None
    if lote["conteo_manual"]:
        diferencia = lote["total"] - lote["conteo_manual"]
        error_conteo = {"diferencia": diferencia, "pct": porcentaje(abs(diferencia), lote["conteo_manual"])}
    return render_template(
        "lotes/detalle.html", lote=lote, analisis=analisis, revisor=revisor, seg_lote=graficos.segmentos(lote),
        editable=puede_editar_lote(usuario, lote), pendientes=pendientes, error_conteo=error_conteo,
        puede_revisar=(usuario["rol"] == "jefe_planta" and lote["packing_id"] == usuario["empresa_id"]
                       and lote["estado"] in ("por_aprobar", "rechazado") and not pendientes and lote["total"] > 0),
        niveles=NIVELES_SENSIBILIDAD, linea_defecto=LINEA_CONTEO_DEFECTO,
        permite_video=PLANES[usuario["empresa_plan"]]["video"])


@bp.route("/lotes/<int:lote_id>/analisis", methods=["POST"])
@rol_requerido("jefe_planta", "operador")
def agregar_analisis(lote_id):
    usuario = usuario_actual()
    lote = lote_visible(lote_id)
    if not puede_editar_lote(usuario, lote):
        abort(403)
    nivel, linea = _parametros_analisis()
    try:
        crear_analisis(request.files.get("archivo"), usuario, lote_id, nivel, linea,
                       permitir_video=PLANES[usuario["empresa_plan"]]["video"])
        if lote["estado"] == "rechazado":
            flash("Nuevo análisis en curso. El lote vuelve a revisión.", "exito")
        else:
            flash("Archivo recibido. El modelo lo está analizando.", "exito")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("lotes.detalle", lote_id=lote_id))


@bp.route("/lotes/<int:lote_id>/revisar", methods=["POST"])
@rol_requerido("jefe_planta")
def revisar(lote_id):
    usuario = usuario_actual()
    lote = lote_visible(lote_id)
    en_curso = valor("SELECT COUNT(*) FROM analisis WHERE lote_id = ? AND estado IN ('en_cola','procesando')",
                     (lote_id,))
    if lote["estado"] not in ("por_aprobar", "rechazado") or en_curso or lote["total"] <= 0:
        flash("Este lote no se puede revisar ahora: necesita al menos un análisis terminado y ninguno en curso.",
              "error")
        return redirect(url_for("lotes.detalle", lote_id=lote_id))

    accion = request.form.get("accion")
    observacion = request.form.get("observacion", "").strip()[:500] or None
    texto_manual = request.form.get("conteo_manual", "").strip()
    manual = _entero(texto_manual, 0, 10_000_000) if texto_manual else None
    if texto_manual and manual is None:
        flash("El conteo manual debe ser un número entero mayor o igual a 0.", "error")
        return redirect(url_for("lotes.detalle", lote_id=lote_id))

    con = get_db()
    if accion == "aprobar":
        for _ in range(5):   # el código es aleatorio: reintentar si (muy raro) ya existe
            certificado = nuevo_certificado()
            if not con.execute("SELECT 1 FROM lotes WHERE certificado = ?", (certificado,)).fetchone():
                break
        con.execute("""UPDATE lotes SET estado = 'aprobado', certificado = ?, conteo_manual = ?, observacion = ?,
                       revisado_por = ?, revisado_en = ? WHERE id = ?""",
                    (certificado, manual, observacion, usuario["id"], ahora_iso(), lote_id))
        con.commit()
        flash(f"Lote aprobado. Certificado emitido: {certificado}", "exito")
    elif accion == "rechazar":
        if not observacion:
            flash("Para rechazar, escribe el motivo en «Observación».", "error")
            return redirect(url_for("lotes.detalle", lote_id=lote_id))
        con.execute("""UPDATE lotes SET estado = 'rechazado', conteo_manual = ?, observacion = ?, revisado_por = ?,
                       revisado_en = ? WHERE id = ?""", (manual, observacion, usuario["id"], ahora_iso(), lote_id))
        con.commit()
        flash("Lote rechazado. El operador puede subir un nuevo análisis.", "info")
    else:
        abort(400)
    return redirect(url_for("lotes.detalle", lote_id=lote_id))


# ------------------------------------------------------------------ análisis
@bp.route("/analisis/<int:analisis_id>")
@login_requerido
def ver_analisis(analisis_id):
    a = analisis_visible(analisis_id)
    if a["lote_id"]:
        return redirect(url_for("lotes.detalle", lote_id=a["lote_id"]) + f"#analisis-{analisis_id}")
    a = uno("""SELECT a.*, u.nombre AS usuario_nombre FROM analisis a JOIN usuarios u ON u.id = a.usuario_id
               WHERE a.id = ?""", (analisis_id,))
    return render_template("lotes/analisis.html", a=a)


@bp.route("/analisis/<int:analisis_id>/eliminar", methods=["POST"])
@login_requerido
def eliminar_analisis(analisis_id):
    usuario = usuario_actual()
    a = analisis_visible(analisis_id)
    if a["estado"] in ("en_cola", "procesando"):
        flash("Espera a que termine el análisis para eliminarlo.", "error")
        return redirect(request.referrer or url_for("lotes.lista"))
    if a["lote_id"]:
        if not puede_editar_lote(usuario, lote_visible(a["lote_id"])):
            abort(403)
        destino = url_for("lotes.detalle", lote_id=a["lote_id"])
    else:
        destino = url_for("productor.analisis")
    ejecutar("DELETE FROM analisis WHERE id = ?", (analisis_id,))
    carpeta = (Path(current_app.config["DATOS"]) / a["archivo_entrada"]).parent
    if carpeta.parent == Path(current_app.config["DATOS"]) / "analisis":   # solo su propia carpeta
        shutil.rmtree(carpeta, ignore_errors=True)
    if a["lote_id"]:
        recalcular_estado_lote(get_db(), a["lote_id"])
    flash("Análisis eliminado.", "info")
    return redirect(destino)


@bp.route("/api/analisis/<int:analisis_id>")
@login_requerido
def estado_analisis(analisis_id):
    a = analisis_visible(analisis_id)
    cola = current_app.extensions["cola"]
    posicion = None
    if a["estado"] == "en_cola":
        posicion = valor("SELECT COUNT(*) FROM analisis WHERE estado IN ('en_cola','procesando') AND id < ?",
                         (analisis_id,)) + 1
    return jsonify({"id": a["id"], "estado": a["estado"], "progreso": round(100 * cola.progreso.get(a["id"], 0)),
                    "posicion": posicion, "total": a["total"]})


@bp.route("/archivos/<int:analisis_id>/<cual>")
@login_requerido
def archivo(analisis_id, cual):
    a = analisis_visible(analisis_id)
    columna = {"entrada": "archivo_entrada", "resultado": "archivo_resultado", "miniatura": "miniatura"}.get(cual)
    if columna is None or not a[columna]:
        abort(404)
    datos = Path(current_app.config["DATOS"]).resolve()
    ruta = (datos / a[columna]).resolve()
    if datos not in ruta.parents or not ruta.is_file():
        abort(404)
    tipo = "video/webm" if ruta.suffix == ".webm" else None
    return send_file(ruta, mimetype=tipo, conditional=True, max_age=3600)
