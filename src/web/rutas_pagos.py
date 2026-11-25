"""Pago de planes con Webpay Plus (Transbank): crear la transacción, volver del banco y activar el plan."""
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from src.web.auth import rol_requerido, usuario_actual
from src.web.db import get_db, todos, uno
from src.web.negocio import DIAS_PLAN, PLANES, ahora_iso, con_iva, planes_para
from src.web.webpay import ClienteWebpay, ErrorWebpay

bp = Blueprint("pagos", __name__, url_prefix="/pagos")

ESTADOS_PAGO = {"pendiente": "Pendiente", "autorizado": "Pagado", "rechazado": "Rechazado",
                "anulado": "Anulado", "error": "Con error"}


def cliente() -> ClienteWebpay:
    """Cliente Webpay de la app (en pruebas se reemplaza por uno simulado con app.config['WEBPAY'])."""
    if current_app.config.get("WEBPAY") is None:
        current_app.config["WEBPAY"] = ClienteWebpay()
    return current_app.config["WEBPAY"]


def webpay_listo():
    """(disponible, es_prueba): falso si faltan las credenciales de producción."""
    try:
        return True, cliente().es_prueba
    except ValueError:
        return False, False


def vencer_planes() -> None:
    """Un plan pagado que llegó a su fecha de vencimiento vuelve al plan gratuito de su tipo."""
    con = get_db()
    vencidas = con.execute("SELECT id, tipo FROM empresas WHERE plan_vence IS NOT NULL AND plan_vence < ?",
                           (ahora_iso(),)).fetchall()
    for e in vencidas:
        gratis = next((k for k, p in planes_para(e["tipo"]).items() if p["precio"] == 0), None)
        if gratis:
            con.execute("UPDATE empresas SET plan = ?, plan_vence = NULL WHERE id = ?", (gratis, e["id"]))
    if vencidas:
        con.commit()


def _cerrar_pago(pago_id: int, estado: str, **campos) -> bool:
    """Cierra un pago pendiente una sola vez. False si otra petición ya lo había cerrado."""
    columnas = ", ".join(f"{k} = ?" for k in campos)
    con = get_db()
    cur = con.execute(f"UPDATE pagos SET estado = ?, resuelto_en = ?{', ' + columnas if columnas else ''} "
                      "WHERE id = ? AND estado = 'pendiente'",
                      (estado, ahora_iso(), *campos.values(), pago_id))
    con.commit()
    return cur.rowcount == 1


def _activar_plan(pago) -> None:
    con = get_db()
    empresa = con.execute("SELECT plan, plan_vence FROM empresas WHERE id = ?", (pago["empresa_id"],)).fetchone()
    ahora = datetime.now()
    inicio = ahora
    if empresa["plan"] == pago["plan"] and empresa["plan_vence"]:        # renovación: suma desde el vencimiento
        inicio = max(ahora, datetime.fromisoformat(empresa["plan_vence"]))
    vence = (inicio + timedelta(days=DIAS_PLAN)).isoformat(timespec="seconds")
    con.execute("UPDATE empresas SET plan = ?, plan_vence = ? WHERE id = ?", (pago["plan"], vence, pago["empresa_id"]))
    con.execute("""UPDATE solicitudes SET estado = 'aprobada', resuelta_en = ?
                   WHERE empresa_id = ? AND estado = 'pendiente' AND plan_solicitado = ?""",
                (ahora_iso(), pago["empresa_id"], pago["plan"]))
    con.commit()


@bp.route("/iniciar", methods=["POST"])
@rol_requerido("productor")
def iniciar():
    usuario = usuario_actual()
    clave = request.form.get("plan", "")
    plan = planes_para("productor").get(clave)
    if plan is None or not plan["precio"]:
        flash("Elige un plan de pago.", "error")
        return redirect(url_for("productor.plan"))
    empresa = uno("SELECT plan_vence FROM empresas WHERE id = ?", (usuario["empresa_id"],))
    if clave == usuario["empresa_plan"] and not empresa["plan_vence"]:
        flash("Tu empresa ya tiene este plan sin vencimiento.", "info")
        return redirect(url_for("productor.plan"))

    montos = con_iva(plan["precio"])
    con = get_db()
    buy_order = f"AV{secrets.token_hex(6).upper()}"                      # máx. 26 caracteres en Webpay
    pago_id = con.execute("""INSERT INTO pagos (empresa_id, usuario_id, plan, buy_order, neto, monto, creado_en)
                             VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          (usuario["empresa_id"], usuario["id"], clave, buy_order, montos["neto"], montos["total"],
                           ahora_iso())).lastrowid
    con.commit()
    try:
        tx = cliente().crear(buy_order, f"e{usuario['empresa_id']}-u{usuario['id']}", montos["total"],
                             url_for("pagos.retorno", _external=True))
        con.execute("UPDATE pagos SET token = ? WHERE id = ?", (tx["token"], pago_id))
        con.commit()
    except (ErrorWebpay, KeyError) as e:
        current_app.logger.warning("Webpay: no se pudo crear la transacción: %s", e)
        _cerrar_pago(pago_id, "error")
        flash("No pudimos conectar con Webpay. Inténtalo de nuevo en unos minutos.", "error")
        return redirect(url_for("productor.plan"))
    return render_template("pagos/redirigir.html", url=tx["url"], token=tx["token"])


@bp.route("/retorno", methods=["GET", "POST"])
def retorno():
    """Vuelta desde Webpay. No exige sesión ni CSRF: el banco redirige desde otro sitio y la
    transacción se valida con Transbank usando un token que solo conocemos nosotros."""
    datos = {**request.args, **request.form}
    token = datos.get("token_ws")
    if datos.get("TBK_TOKEN") or not token:                              # el usuario canceló o venció el tiempo
        pago = uno("SELECT * FROM pagos WHERE token = ? OR buy_order = ?",
                   (datos.get("TBK_TOKEN") or "-", datos.get("TBK_ORDEN_COMPRA") or "-"))
        if pago is None:
            abort(404)
        _cerrar_pago(pago["id"], "anulado")
        flash("El pago fue cancelado. No se realizó ningún cargo.", "info")
        return redirect(url_for("pagos.resultado", pago_id=pago["id"]))

    pago = uno("SELECT * FROM pagos WHERE token = ?", (token,))
    if pago is None:
        abort(404)
    if pago["estado"] == "pendiente":
        try:
            r = cliente().confirmar(token)
        except ErrorWebpay as e:
            current_app.logger.warning("Webpay: no se pudo confirmar %s: %s", pago["buy_order"], e)
            _cerrar_pago(pago["id"], "error")
        else:
            autorizado = (r.get("status") == "AUTHORIZED" and r.get("response_code") == 0
                          and r.get("amount") == pago["monto"] and r.get("buy_order") == pago["buy_order"])
            detalle = {"autorizacion": r.get("authorization_code"),
                       "tarjeta": (r.get("card_detail") or {}).get("card_number"),
                       "tipo_pago": r.get("payment_type_code"), "cuotas": r.get("installments_number")}
            if autorizado:
                if _cerrar_pago(pago["id"], "autorizado", **detalle):
                    _activar_plan(pago)
            else:
                _cerrar_pago(pago["id"], "rechazado", **detalle)
    return redirect(url_for("pagos.resultado", pago_id=pago["id"]))


@bp.route("/<int:pago_id>")
@rol_requerido("productor")
def resultado(pago_id):
    usuario = usuario_actual()
    pago = uno("SELECT * FROM pagos WHERE id = ? AND empresa_id = ?", (pago_id, usuario["empresa_id"]))
    if pago is None:
        abort(404)
    return render_template("pagos/resultado.html", pago=pago, plan=PLANES[pago["plan"]],
                           ESTADOS_PAGO=ESTADOS_PAGO, iva=pago["monto"] - pago["neto"],
                           vence=uno("SELECT plan_vence FROM empresas WHERE id = ?", (usuario["empresa_id"],))["plan_vence"])


def historial(empresa_id: int, limite: int = 5):
    return todos("SELECT * FROM pagos WHERE empresa_id = ? AND estado != 'pendiente' ORDER BY id DESC LIMIT ?",
                 (empresa_id, limite))
