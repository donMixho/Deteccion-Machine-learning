"""Pruebas de la plataforma web: roles, permisos, flujo de un lote y reglas del negocio.

Usan un analizador simulado (no cargan YOLO) y una carpeta de datos temporal.
    python -m unittest tests.test_web -v
"""
import io
import re
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.web import demo
from src.web.app import create_app
from src.web.db import conectar
from src.web.negocio import SENSIBILIDADES, ingreso_mensual, inicio_mes, nuevo_certificado


def analizador_falso(tipo, entrada, carpeta, sensibilidad, linea, etiqueta, al_progreso):
    resultado = carpeta / ("resultado.webm" if tipo == "video" else "resultado.jpg")
    resultado.write_bytes(b"resultado")
    miniatura = carpeta / "miniatura.jpg"
    miniatura.write_bytes(b"miniatura")
    al_progreso(1.0)
    return {"contadas": 10, "ids_vistos": 12, "categorias": {"good": 6, "detalle": 3, "no_pasa": 1},
            "pudricion": 1, "resultado": resultado, "miniatura": miniatura}


class WebpayFalso:
    """Reemplaza a Transbank: guarda lo que se le pide y responde lo que cada prueba configure."""
    es_prueba = True

    def __init__(self):
        self.creadas, self.confirmadas = [], []
        self.respuesta = {}          # campos que reemplazan a la respuesta de un pago autorizado

    def crear(self, buy_order, session_id, monto, url_retorno):
        self.creadas.append({"buy_order": buy_order, "monto": monto, "url_retorno": url_retorno})
        return {"token": f"tok{len(self.creadas)}", "url": "https://webpay.test/pagar"}

    def confirmar(self, token):
        self.confirmadas.append(token)
        orden = self.creadas[int(token[3:]) - 1]
        base = {"status": "AUTHORIZED", "response_code": 0, "amount": orden["monto"], "buy_order": orden["buy_order"],
                "authorization_code": "1213", "card_detail": {"card_number": "6623"}, "payment_type_code": "VN",
                "installments_number": 0}
        return {**base, **self.respuesta}


def config(datos):
    return {"DATOS": datos, "TESTING": True, "COLA_SINCRONA": True, "ANALIZADOR": analizador_falso, "DEMO": True,
            "WEBPAY": WebpayFalso()}


class PruebaWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plantilla = Path(tempfile.mkdtemp()) / "datos"
        app = create_app(config(cls.plantilla))
        demo.sembrar(app.config["DB_RUTA"], cls.plantilla, analizador=analizador_falso, avisar=lambda *_: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.plantilla.parent, ignore_errors=True)

    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())
        self.datos = self.raiz / "datos"
        shutil.copytree(self.plantilla, self.datos)
        self.app = create_app(config(self.datos))
        self.c = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    # ------------------------------------------------------------ ayudas
    def db(self):
        return conectar(self.app.config["DB_RUTA"])

    def uno(self, sql, params=()):
        con = self.db()
        try:
            return con.execute(sql, params).fetchone()
        finally:
            con.close()

    def entrar(self, rol):
        r = self.c.get(f"/demo/{rol}")
        self.assertEqual(r.status_code, 302, rol)
        return r

    def entrar_con(self, email, clave="demo1234"):
        self.c.get("/ingresar")
        return self.c.post("/ingresar", data={"email": email, "clave": clave, "csrf": self.token()})

    def token(self):
        with self.c.session_transaction() as s:
            if "csrf" not in s:
                s["csrf"] = "token-de-prueba"
            return s["csrf"]

    def lote(self, condicion, params=()):
        return self.uno(f"SELECT * FROM v_lotes WHERE {condicion} ORDER BY id LIMIT 1", params)

    # ------------------------------------------------------------ público e ingreso
    def test_portada_muestra_modelo_de_negocio_y_planes(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        for texto in ("Un servicio, tres clientes", "Productor Pro", "$290.000", "Jefe de planta", "0,914"):
            self.assertIn(texto, html)

    def test_ingreso_con_clave_incorrecta_y_correcta(self):
        r = self.entrar_con("jefe@losrobles.demo", "mala-clave")
        self.assertEqual(r.status_code, 401)
        r = self.entrar_con("jefe@losrobles.demo")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/planta/"))

    def test_no_redirige_a_sitios_externos(self):
        self.c.get("/ingresar")
        r = self.c.post("/ingresar?next=//sitio-malo.com", data={"email": "jefe@losrobles.demo", "clave": "demo1234",
                                                                  "csrf": self.token()})
        self.assertNotIn("sitio-malo", r.headers["Location"])

    def test_cada_rol_llega_a_su_panel(self):
        esperado = {"admin": "/admin/", "jefe_planta": "/planta/", "operador": "/planta/turno",
                    "productor": "/productor/", "exportador": "/exportador/"}
        for rol, ruta in esperado.items():
            with self.subTest(rol=rol):
                r = self.entrar(rol)
                self.assertTrue(r.headers["Location"].endswith(ruta))
                self.assertEqual(self.c.get(ruta).status_code, 200)
                self.assertEqual(self.c.get("/lotes" if rol != "productor" else "/productor/analisis").status_code, 200)

    # ------------------------------------------------------------ permisos
    def test_sin_sesion_pide_ingresar(self):
        r = self.c.get("/admin/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/ingresar", r.headers["Location"])

    def test_cada_rol_solo_entra_a_lo_suyo(self):
        prohibido = {"operador": ["/admin/", "/planta/", "/planta/equipo", "/productor/"],
                     "productor": ["/admin/", "/planta/", "/lotes/nuevo", "/exportador/"],
                     "exportador": ["/admin/usuarios", "/lotes/nuevo", "/productor/plan"],
                     "jefe_planta": ["/admin/empresas", "/productor/", "/exportador/"]}
        for rol, rutas in prohibido.items():
            self.entrar(rol)
            for ruta in rutas:
                with self.subTest(rol=rol, ruta=ruta):
                    self.assertEqual(self.c.get(ruta).status_code, 403)

    def test_productor_no_ve_lotes_de_otro_productor(self):
        ajeno = self.lote("productor_nombre = 'Agrícola Santa Rosa'")
        propio = self.lote("productor_nombre = 'Agrícola El Manzano'")
        self.entrar("productor")
        self.assertEqual(self.c.get(f"/lotes/{ajeno['id']}").status_code, 404)
        self.assertEqual(self.c.get(f"/lotes/{propio['id']}").status_code, 200)

    def test_exportadora_solo_ve_lotes_aprobados_a_su_nombre(self):
        aprobado = self.lote("estado = 'aprobado' AND exportadora_nombre = 'Exportadora Andes Fruit'")
        pendiente = self.lote("estado = 'por_aprobar' AND exportadora_nombre = 'Exportadora Andes Fruit'")
        de_otra = self.lote("exportadora_nombre = 'Exportadora Pacífico Sur'")
        self.entrar("exportador")
        self.assertEqual(self.c.get(f"/lotes/{aprobado['id']}").status_code, 200)
        self.assertEqual(self.c.get(f"/lotes/{pendiente['id']}").status_code, 404)
        self.assertEqual(self.c.get(f"/lotes/{de_otra['id']}").status_code, 404)
        html = self.c.get("/exportador/").get_data(as_text=True)
        self.assertIn(aprobado["certificado"], html)
        self.assertNotIn(pendiente["codigo"], html)

    def test_archivos_protegidos_por_rol(self):
        ajeno = self.lote("productor_nombre = 'Agrícola Santa Rosa' AND ultimo_analisis_id IS NOT NULL")
        ruta = f"/archivos/{ajeno['ultimo_analisis_id']}/miniatura"
        self.assertEqual(self.c.get(ruta).status_code, 302)          # sin sesión
        self.entrar("productor")
        self.assertEqual(self.c.get(ruta).status_code, 404)          # otro productor
        self.entrar("jefe_planta")
        r = self.c.get(ruta)
        self.assertEqual(r.status_code, 200)                         # su planta
        r.close()

    def test_post_sin_token_csrf_es_rechazado(self):
        lote = self.lote("estado = 'por_aprobar'")
        self.entrar("jefe_planta")
        r = self.c.post(f"/lotes/{lote['id']}/revisar", data={"accion": "aprobar"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.lote("id = ?", (lote["id"],))["estado"], "por_aprobar")

    # ------------------------------------------------------------ flujo del negocio
    def test_flujo_completo_recepcion_aprobacion_y_certificado(self):
        productor = self.uno("SELECT id FROM empresas WHERE nombre = 'Agrícola El Manzano'")["id"]
        exportadora = self.uno("SELECT id FROM empresas WHERE nombre = 'Exportadora Andes Fruit'")["id"]
        self.entrar("operador")
        r = self.c.post("/lotes/nuevo", content_type="multipart/form-data", data={
            "csrf": self.token(), "productor_id": productor, "exportadora_id": exportadora, "variedad": "Gala",
            "bins": "12", "linea": "1", "sensibilidad": "normal",
            "archivo": (io.BytesIO(b"\xff\xd8 foto"), "bin.jpg")})
        self.assertEqual(r.status_code, 302)
        lote_id = int(r.headers["Location"].rsplit("/", 1)[-1])
        lote = self.lote("id = ?", (lote_id,))
        self.assertEqual((lote["estado"], lote["total"], lote["buena"]), ("por_aprobar", 10, 6))
        self.assertRegex(lote["codigo"], r"^L-\d{4}-\d{4}$")

        self.entrar("jefe_planta")
        r = self.c.post(f"/lotes/{lote_id}/revisar", data={"csrf": self.token(), "accion": "aprobar",
                                                            "conteo_manual": "9"})
        self.assertEqual(r.status_code, 302)
        lote = self.lote("id = ?", (lote_id,))
        self.assertEqual(lote["estado"], "aprobado")
        self.assertEqual(lote["conteo_manual"], 9)
        self.assertRegex(lote["certificado"], r"^AV-\d{4}-[A-Z2-9]{6}$")

        self.c.post("/salir", data={"csrf": self.token()})
        html = self.c.get(f"/verificar?codigo={lote['certificado'].lower()}").get_data(as_text=True)
        self.assertIn("Certificado válido", html)
        self.assertIn("No reemplaza la inspección", html)
        self.assertIn("No hay un certificado válido", self.c.get("/verificar?codigo=AV-0000-XXXXXX").get_data(as_text=True))

        self.entrar("operador")   # un lote aprobado ya no acepta análisis
        r = self.c.post(f"/lotes/{lote_id}/analisis", content_type="multipart/form-data",
                        data={"csrf": self.token(), "archivo": (io.BytesIO(b"x"), "otra.jpg")})
        self.assertEqual(r.status_code, 403)

    def test_rechazo_exige_motivo_y_reanalisis_vuelve_a_revision(self):
        lote = self.lote("estado = 'por_aprobar'")
        self.entrar("jefe_planta")
        self.c.post(f"/lotes/{lote['id']}/revisar", data={"csrf": self.token(), "accion": "rechazar"})
        self.assertEqual(self.lote("id = ?", (lote["id"],))["estado"], "por_aprobar")
        self.c.post(f"/lotes/{lote['id']}/revisar", data={"csrf": self.token(), "accion": "rechazar",
                                                           "observacion": "Repetir con más luz"})
        self.assertEqual(self.lote("id = ?", (lote["id"],))["estado"], "rechazado")
        self.entrar("operador")
        self.c.post(f"/lotes/{lote['id']}/analisis", content_type="multipart/form-data",
                    data={"csrf": self.token(), "archivo": (io.BytesIO(b"x"), "nueva.png")})
        self.assertEqual(self.lote("id = ?", (lote["id"],))["estado"], "por_aprobar")

    def test_formato_no_soportado(self):
        lote = self.lote("estado = 'por_aprobar'")
        self.entrar("operador")
        r = self.c.post(f"/lotes/{lote['id']}/analisis", content_type="multipart/form-data",
                        data={"csrf": self.token(), "archivo": (io.BytesIO(b"x"), "planilla.xlsx")}, follow_redirects=True)
        self.assertIn("Formato no soportado", r.get_data(as_text=True))

    def test_cuota_del_plan_basico(self):
        empresa = self.uno("SELECT id FROM empresas WHERE nombre = 'Agrícola Santa Rosa'")["id"]
        usuario = self.uno("SELECT id FROM usuarios WHERE email = 'productor@santarosa.demo'")["id"]
        con = self.db()
        usados = con.execute("SELECT COUNT(*) FROM analisis WHERE empresa_id = ? AND lote_id IS NULL AND creado_en >= ?",
                             (empresa, inicio_mes())).fetchone()[0]
        for _ in range(10 - usados):   # llenar la cuota de 10 del plan Básico
            con.execute("""INSERT INTO analisis (empresa_id, usuario_id, tipo, nombre_archivo, archivo_entrada,
                           sensibilidad, estado, creado_en) VALUES (?, ?, 'foto', 'x.jpg', 'x', 65, 'listo', ?)""",
                        (empresa, usuario, datetime.now().isoformat(timespec="seconds")))
        con.commit()
        con.close()
        self.entrar_con("productor@santarosa.demo")
        r = self.c.post("/productor/analisis", content_type="multipart/form-data",
                        data={"csrf": self.token(), "archivo": (io.BytesIO(b"x"), "bin.jpg")})
        self.assertTrue(r.headers["Location"].endswith("/productor/plan"))
        self.assertEqual(self.uno("""SELECT COUNT(*) AS n FROM analisis WHERE empresa_id = ? AND lote_id IS NULL
                                     AND creado_en >= ?""", (empresa, inicio_mes()))["n"], 10)
        self.assertEqual(self.c.get("/lotes.csv").status_code, 302)   # CSV es del plan Pro

    def test_error_de_analisis_no_expone_rutas_ni_consume_cuota(self):
        from src.web.rutas_productor import cuota

        def falla(tipo, entrada, *args):
            raise RuntimeError(f"No se pudo leer la imagen: {entrada}")
        self.app.extensions["cola"].analizador = falla
        usuario = self.uno("""SELECT u.*, e.plan AS empresa_plan FROM usuarios u JOIN empresas e ON e.id = u.empresa_id
                              WHERE u.email = 'productor@elmanzano.demo'""")
        with self.app.app_context():
            antes = cuota(usuario)["usados"]
        self.entrar("productor")
        r = self.c.post("/productor/analisis", content_type="multipart/form-data",
                        data={"csrf": self.token(), "archivo": (io.BytesIO(b"no es una imagen"), "bin.jpg")})
        a = self.uno("SELECT * FROM analisis WHERE id = ?", (int(r.headers["Location"].rsplit("/", 1)[-1]),))
        self.assertEqual(a["estado"], "error")
        self.assertEqual(a["mensaje_error"], "El archivo no es una imagen válida o está dañado.")
        with self.app.app_context():
            self.assertEqual(cuota(usuario)["usados"], antes)

    def test_productor_no_puede_subir_video(self):
        self.entrar("productor")
        r = self.c.post("/productor/analisis", content_type="multipart/form-data", follow_redirects=True,
                        data={"csrf": self.token(), "archivo": (io.BytesIO(b"x"), "cinta.mp4")})
        self.assertIn("plan Packing", r.get_data(as_text=True))

    def test_admin_aprueba_cambio_de_plan(self):
        solicitud = self.uno("SELECT * FROM solicitudes WHERE estado = 'pendiente'")
        self.entrar("admin")
        self.assertIn("Solicitudes de cambio de plan", self.c.get("/admin/").get_data(as_text=True))
        self.c.post(f"/admin/solicitudes/{solicitud['id']}", data={"csrf": self.token(), "accion": "aprobar"})
        plan = self.uno("SELECT plan FROM empresas WHERE id = ?", (solicitud["empresa_id"],))["plan"]
        self.assertEqual(plan, "productor_pro")

    def test_admin_valida_rol_contra_tipo_de_empresa(self):
        exportadora = self.uno("SELECT id FROM empresas WHERE tipo = 'exportadora'")["id"]
        self.entrar("admin")
        r = self.c.post("/admin/usuarios", follow_redirects=True, data={
            "csrf": self.token(), "nombre": "X", "email": "x@demo.cl", "clave": "12345678", "rol": "operador",
            "empresa_id": exportadora})
        self.assertIn("debe pertenecer", r.get_data(as_text=True))
        self.assertIsNone(self.uno("SELECT 1 FROM usuarios WHERE email = 'x@demo.cl'"))

    def test_jefe_descarga_csv_de_su_planta(self):
        self.entrar("jefe_planta")
        r = self.c.get("/lotes.csv")
        self.assertEqual(r.status_code, 200)
        texto = r.get_data(as_text=True)
        self.assertTrue(texto.startswith("﻿codigo;fecha;packing"))
        self.assertNotIn("Valle Verde", texto)

    # ------------------------------------------------------------ reglas del negocio
    def test_reglas_de_negocio(self):
        self.assertEqual(ingreso_mensual("packing", 3), 870000)
        self.assertEqual(ingreso_mensual("productor_basico"), 0)
        self.assertRegex(nuevo_certificado(2026), r"^AV-2026-[A-Z2-9]{6}$")

    def test_sensibilidad_normal_igual_al_detector(self):
        from src.vision.detector import CONF_DEFAULT, CONF_FOTO_DEFAULT
        self.assertEqual(SENSIBILIDADES["foto"]["normal"], 100 - round(CONF_FOTO_DEFAULT * 100))
        self.assertEqual(SENSIBILIDADES["video"]["normal"], 100 - round(CONF_DEFAULT * 100))

    def test_demo_crea_una_cuenta_por_rol_y_lotes_en_todos_los_estados(self):
        roles = {r["rol"] for r in self.db().execute("SELECT rol FROM usuarios")}
        self.assertEqual(roles, {"admin", "jefe_planta", "operador", "productor", "exportador"})
        estados = {r["estado"] for r in self.db().execute("SELECT estado FROM lotes")}
        self.assertEqual(estados, {"recepcionado", "por_aprobar", "aprobado", "rechazado"})

    # ------------------------------------------------------------ pagos con Webpay
    def iniciar_pago(self):
        """Productor Básico (Santa Rosa) empieza a pagar el plan Pro. Devuelve (respuesta, pago)."""
        self.entrar_con("productor@santarosa.demo")
        r = self.c.post("/pagos/iniciar", data={"csrf": self.token(), "plan": "productor_pro"})
        return r, self.uno("SELECT * FROM pagos ORDER BY id DESC LIMIT 1")

    def volver_del_banco(self, **datos):
        """El banco redirige desde otro sitio: sin cookie de sesión ni token CSRF."""
        return self.app.test_client().post("/pagos/retorno", data=datos)

    def plan_de(self, email):
        return self.uno("""SELECT e.plan, e.plan_vence FROM empresas e JOIN usuarios u ON u.empresa_id = e.id
                           WHERE u.email = ?""", (email,))

    def test_webpay_cobra_el_plan_con_iva_y_redirige_al_banco(self):
        r, pago = self.iniciar_pago()
        html = r.get_data(as_text=True)
        self.assertIn("https://webpay.test/pagar", html)
        self.assertIn('name="token_ws" value="tok1"', html)
        self.assertEqual((pago["neto"], pago["monto"], pago["estado"]), (9990, 11888, "pendiente"))   # 9.990 + 19 %
        self.assertEqual(self.app.config["WEBPAY"].creadas[0]["monto"], 11888)
        self.assertLessEqual(len(pago["buy_order"]), 26)

    def test_pago_autorizado_activa_el_plan_por_30_dias(self):
        _, pago = self.iniciar_pago()
        r = self.volver_del_banco(token_ws="tok1")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith(f"/pagos/{pago['id']}"))
        plan = self.plan_de("productor@santarosa.demo")
        self.assertEqual(plan["plan"], "productor_pro")
        dias = (datetime.fromisoformat(plan["plan_vence"]) - datetime.now()).days
        self.assertIn(dias, (29, 30))
        cerrado = self.uno("SELECT * FROM pagos WHERE id = ?", (pago["id"],))
        self.assertEqual((cerrado["estado"], cerrado["tarjeta"], cerrado["autorizacion"]), ("autorizado", "6623", "1213"))
        self.assertIsNone(self.uno("SELECT 1 FROM solicitudes WHERE estado = 'pendiente' AND plan_solicitado = 'productor_pro'"))
        html = self.c.get(f"/pagos/{pago['id']}").get_data(as_text=True)
        self.assertIn("Plan Productor Pro activo", html)
        self.assertIn("$11.888", html)

    def test_pago_rechazado_no_cambia_el_plan(self):
        self.iniciar_pago()
        self.app.config["WEBPAY"].respuesta = {"status": "FAILED", "response_code": -1}
        self.volver_del_banco(token_ws="tok1")
        self.assertEqual(self.plan_de("productor@santarosa.demo")["plan"], "productor_basico")
        self.assertEqual(self.uno("SELECT estado FROM pagos")["estado"], "rechazado")

    def test_pago_con_monto_distinto_no_se_acepta(self):
        self.iniciar_pago()
        self.app.config["WEBPAY"].respuesta = {"amount": 100}
        self.volver_del_banco(token_ws="tok1")
        self.assertEqual(self.plan_de("productor@santarosa.demo")["plan"], "productor_basico")
        self.assertEqual(self.uno("SELECT estado FROM pagos")["estado"], "rechazado")

    def test_pago_cancelado_en_el_banco_no_cobra(self):
        _, pago = self.iniciar_pago()
        r = self.app.test_client().get("/pagos/retorno", query_string={
            "TBK_TOKEN": "tok1", "TBK_ORDEN_COMPRA": pago["buy_order"], "TBK_ID_SESION": "s"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.uno("SELECT estado FROM pagos")["estado"], "anulado")
        self.assertEqual(self.plan_de("productor@santarosa.demo")["plan"], "productor_basico")
        self.assertEqual(self.app.config["WEBPAY"].confirmadas, [])

    def test_volver_dos_veces_del_banco_confirma_una_sola_vez(self):
        self.iniciar_pago()
        self.volver_del_banco(token_ws="tok1")
        self.volver_del_banco(token_ws="tok1")
        self.assertEqual(self.app.config["WEBPAY"].confirmadas, ["tok1"])

    def test_retorno_con_token_desconocido_es_404(self):
        self.assertEqual(self.volver_del_banco(token_ws="inventado").status_code, 404)

    def test_solo_el_productor_inicia_pagos_y_solo_ve_los_suyos(self):
        for rol in ("operador", "exportador", "admin"):
            self.entrar(rol)
            r = self.c.post("/pagos/iniciar", data={"csrf": self.token(), "plan": "productor_pro"})
            self.assertEqual(r.status_code, 403, rol)
        _, pago = self.iniciar_pago()
        self.entrar("productor")                                    # otra empresa (El Manzano)
        self.assertEqual(self.c.get(f"/pagos/{pago['id']}").status_code, 404)

    def test_plan_gratis_o_inexistente_no_se_paga(self):
        self.entrar_con("productor@santarosa.demo")
        for plan in ("productor_basico", "packing", "inventado"):
            self.c.post("/pagos/iniciar", data={"csrf": self.token(), "plan": plan})
        self.assertIsNone(self.uno("SELECT 1 FROM pagos"))

    def test_plan_vencido_vuelve_al_gratuito(self):
        con = self.db()
        con.execute("""UPDATE empresas SET plan_vence = '2020-01-01T00:00:00'
                       WHERE id = (SELECT empresa_id FROM usuarios WHERE email = 'productor@elmanzano.demo')""")
        con.commit()
        con.close()
        self.entrar_con("productor@elmanzano.demo")
        self.c.get("/productor/plan")
        self.assertEqual(self.plan_de("productor@elmanzano.demo")["plan"], "productor_basico")

    def test_falla_de_transbank_no_deja_pago_pendiente(self):
        from src.web.webpay import ErrorWebpay

        def falla(*_):
            raise ErrorWebpay("sin conexión")
        self.app.config["WEBPAY"].crear = falla
        self.entrar_con("productor@santarosa.demo")
        r = self.c.post("/pagos/iniciar", data={"csrf": self.token(), "plan": "productor_pro"}, follow_redirects=True)
        self.assertIn("No pudimos conectar con Webpay", r.get_data(as_text=True))
        self.assertEqual(self.uno("SELECT estado FROM pagos")["estado"], "error")

    def test_url_publica_define_la_url_de_retorno_del_banco(self):
        self.app.config["URL_PUBLICA"] = "https://app.ejemplo.cl"
        self.iniciar_pago()
        self.assertEqual(self.app.config["WEBPAY"].creadas[0]["url_retorno"], "https://app.ejemplo.cl/pagos/retorno")

    def test_produccion_exige_https_para_cobrar(self):
        self.app.config["WEBPAY"].es_prueba = False
        self.app.config["URL_PUBLICA"] = "http://app.ejemplo.cl"
        _, pago = self.iniciar_pago()
        self.assertIsNone(pago)                                     # no se creó ningún cobro
        self.assertEqual(self.app.config["WEBPAY"].creadas, [])
        self.app.config["URL_PUBLICA"] = "https://app.ejemplo.cl"
        _, pago = self.iniciar_pago()
        self.assertEqual(pago["estado"], "pendiente")

    def test_pago_que_nunca_volvio_del_banco_se_anula(self):
        _, pago = self.iniciar_pago()
        con = self.db()
        con.execute("UPDATE pagos SET creado_en = '2020-01-01T00:00:00' WHERE id = ?", (pago["id"],))
        con.commit()
        con.close()
        self.c.get("/productor/plan")
        self.assertEqual(self.uno("SELECT estado FROM pagos WHERE id = ?", (pago["id"],))["estado"], "anulado")

    def test_comprobante_muestra_medio_de_pago_y_cuotas(self):
        _, pago = self.iniciar_pago()
        self.app.config["WEBPAY"].respuesta = {"payment_type_code": "VC", "installments_number": 3}
        self.volver_del_banco(token_ws="tok1")
        html = self.c.get(f"/pagos/{pago['id']}").get_data(as_text=True)
        self.assertIn("Crédito en cuotas", html)
        self.assertIn("Cuotas", html)

    def test_cliente_webpay_usa_integracion_por_defecto_y_exige_llaves_en_produccion(self):
        from src.web.webpay import ClienteWebpay
        c = ClienteWebpay(ambiente="integracion")
        self.assertTrue(c.es_prueba)
        self.assertIn("webpay3gint", c._url())
        with self.assertRaises(ValueError):
            ClienteWebpay(ambiente="produccion", comercio="", llave="")


if __name__ == "__main__":
    unittest.main()
