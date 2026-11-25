"""Pruebas de la regla de pudrición según el modelo (1 clase vs. 2 clases)."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from src.utils.config import CONFIG_PATH, _modo_regla, cargar_config
from src.vision.clasificador import DETALLE, GOOD, NO_PASA, clasificar, es_danada, usar_regla_pudricion

UN_MODELO = ["apple"]
DOS_CLASES = ["apple", "damaged_apple"]


class ReglaPudricionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cargar_config()

    def test_auto_usa_la_regla_solo_si_el_modelo_no_detecta_danio(self):
        cfg = replace(self.cfg, regla_pudricion="auto")
        self.assertTrue(usar_regla_pudricion(cfg, UN_MODELO))
        self.assertFalse(usar_regla_pudricion(cfg, DOS_CLASES))

    def test_si_y_no_fuerzan_la_regla(self):
        self.assertTrue(usar_regla_pudricion(replace(self.cfg, regla_pudricion="si"), DOS_CLASES))
        self.assertFalse(usar_regla_pudricion(replace(self.cfg, regla_pudricion="no"), UN_MODELO))

    def test_clasificar_respeta_la_regla_y_la_clase(self):
        args = dict(diametro_mm=70, hue=5, saturacion=200, aspecto=0.95, cfg=self.cfg, usar_calibre=False)
        manchada = self.cfg.max_pct_defecto + 10
        self.assertEqual(clasificar(clase_yolo="apple", pct_defecto=manchada, **args), NO_PASA)
        self.assertEqual(clasificar(clase_yolo="apple", pct_defecto=manchada, regla_color=False, **args), GOOD)
        self.assertEqual(clasificar(clase_yolo="damaged_apple", regla_color=False, **args), NO_PASA)
        self.assertIn(clasificar(clase_yolo="apple", **args), (GOOD, DETALLE))

    def test_es_danada_por_clase_mayoritaria_o_por_regla(self):
        alto = self.cfg.max_pct_defecto + 10
        self.assertTrue(es_danada(["damaged_apple", "damaged_apple", "apple"], [0, 0, 0], self.cfg, False))
        self.assertFalse(es_danada(["apple", "apple", "damaged_apple"], [0, 0, 0], self.cfg, False))
        self.assertTrue(es_danada(["apple"], [alto], self.cfg, True))
        self.assertFalse(es_danada(["apple"], [alto], self.cfg, False))
        self.assertFalse(es_danada([], [], self.cfg, True))

    def test_lee_regla_pudricion_de_config(self):
        self.assertEqual(_modo_regla(True), "si")
        self.assertEqual(_modo_regla(False), "no")      # YAML lee "false" y "no" como booleano
        self.assertEqual(_modo_regla("AUTO"), "auto")
        self.assertEqual(_modo_regla("cualquier cosa"), "auto")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "config.yaml"
            ruta.write_text(CONFIG_PATH.read_text(encoding="utf-8").replace("regla_pudricion: auto",
                                                                              "regla_pudricion: false"),
                            encoding="utf-8")
            self.assertEqual(cargar_config(ruta).regla_pudricion, "no")


if __name__ == "__main__":
    unittest.main()
