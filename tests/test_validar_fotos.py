"""Pruebas de la lectura de casos del validador de fotos."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.vision import validar_fotos


class LeerCasosTests(unittest.TestCase):
    def test_omite_fotos_sin_etiqueta_en_vez_de_contarlas_como_cero(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "images" / "test"
            (base / "images").mkdir(parents=True)
            (base / "labels").mkdir()
            (base / "images" / "con_etiqueta.jpg").write_bytes(b"x")
            (base / "labels" / "con_etiqueta.txt").write_text("0 .5 .5 .1 .1\n0 .2 .2 .1 .1\n", encoding="utf-8")
            (base / "images" / "sin_etiqueta.jpg").write_bytes(b"x")
            salida = io.StringIO()
            with mock.patch.object(validar_fotos, "RAIZ", Path(tmp)), contextlib.redirect_stdout(salida):
                casos = validar_fotos.leer_casos("test")
        self.assertEqual([(imagen.name, n) for imagen, n in casos], [("con_etiqueta.jpg", 2)])
        self.assertIn("se omiten 1 fotos", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
