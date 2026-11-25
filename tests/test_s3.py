"""Respaldo en S3 con fallback local: sin bucket o con S3 caído, el flujo sigue y los archivos quedan en disco.

    python -m unittest tests.test_s3 -v
"""
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from botocore.exceptions import ClientError

from src.utils import s3_helper
from tests.test_web import analizador_falso, config
from src.web import demo
from src.web.app import create_app
from src.web.db import conectar


def cfg(bucket):
    return SimpleNamespace(s3_bucket=bucket, s3_prefix="apple-vision/")


class PruebaS3(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.archivo = self.dir / "resultado.jpg"
        self.archivo.write_bytes(b"x")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_sin_bucket_no_sube_y_conserva_el_archivo(self):
        with mock.patch.object(s3_helper, "cargar_config", return_value=cfg("")), \
                mock.patch.object(s3_helper, "_cliente") as cliente:
            self.assertEqual(s3_helper.subir_resultados([self.archivo], "analisis/1"), [])
            cliente.assert_not_called()
        self.assertTrue(self.archivo.exists())

    def test_con_bucket_sube_con_prefijo_y_carpeta(self):
        with mock.patch.object(s3_helper, "cargar_config", return_value=cfg("mi-bucket")), \
                mock.patch.object(s3_helper, "_cliente") as cliente:
            claves = s3_helper.subir_resultados([self.archivo, None, self.dir / "no_existe.csv"], "analisis/7")
            self.assertEqual(claves, ["apple-vision/analisis/7/resultado.jpg"])
            cliente.return_value.upload_file.assert_called_once_with(
                str(self.archivo), "mi-bucket", "apple-vision/analisis/7/resultado.jpg")

    def test_s3_caido_no_lanza_y_devuelve_vacio(self):
        error = ClientError({"Error": {"Code": "ExpiredToken", "Message": "expirado"}}, "PutObject")
        with mock.patch.object(s3_helper, "cargar_config", return_value=cfg("mi-bucket")), \
                mock.patch.object(s3_helper, "_cliente") as cliente:
            cliente.return_value.upload_file.side_effect = error
            self.assertEqual(s3_helper.subir_resultados([self.archivo], "analisis/1"), [])
        self.assertTrue(self.archivo.exists())

    def test_error_inesperado_tampoco_rompe(self):
        with mock.patch.object(s3_helper, "cargar_config", side_effect=RuntimeError("config rota")):
            self.assertEqual(s3_helper.subir_resultados([self.archivo], "x"), [])


class PruebaColaConS3(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())
        self.datos = self.raiz / "datos"
        self.app = create_app(config(self.datos))
        demo.sembrar(self.app.config["DB_RUTA"], self.datos, analizador=analizador_falso, avisar=lambda *_: None)

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    def _encolar_un_analisis(self, subir):
        con = conectar(self.app.config["DB_RUTA"])
        try:
            fila = con.execute("SELECT id FROM analisis WHERE estado = 'listo' LIMIT 1").fetchone()
            con.execute("UPDATE analisis SET estado = 'en_cola' WHERE id = ?", (fila["id"],))
            con.commit()
        finally:
            con.close()
        with mock.patch("src.web.analisis.subir_resultados", subir):
            self.app.extensions["cola"].procesar(fila["id"])
        con = conectar(self.app.config["DB_RUTA"])
        try:
            return fila["id"], con.execute("SELECT estado FROM analisis WHERE id = ?", (fila["id"],)).fetchone()["estado"]
        finally:
            con.close()

    def test_al_terminar_un_analisis_se_respaldan_resultado_y_miniatura(self):
        subir = mock.Mock(return_value=[])
        analisis_id, estado = self._encolar_un_analisis(subir)
        self.assertEqual(estado, "listo")
        rutas, carpeta = subir.call_args.args
        self.assertEqual(carpeta, f"analisis/{analisis_id}")
        self.assertEqual([Path(r).name for r in rutas], ["resultado.jpg", "miniatura.jpg", "metricas.csv"]
                         if Path(rutas[0]).suffix == ".jpg" else ["resultado.webm", "miniatura.jpg", "metricas.csv"])

    def test_si_el_respaldo_falla_el_analisis_queda_listo_igual(self):
        # subir_resultados real con S3 caído: no debe afectar el estado del análisis
        error = ClientError({"Error": {"Code": "ExpiredToken", "Message": "expirado"}}, "PutObject")
        with mock.patch.object(s3_helper, "cargar_config", return_value=cfg("mi-bucket")), \
                mock.patch.object(s3_helper, "_cliente") as cliente:
            cliente.return_value.upload_file.side_effect = error
            _, estado = self._encolar_un_analisis(s3_helper.subir_resultados)
        self.assertEqual(estado, "listo")


if __name__ == "__main__":
    unittest.main()
