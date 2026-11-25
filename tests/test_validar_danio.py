"""Pruebas del evaluador de manzanas dañadas (sin cargar YOLO)."""
import tempfile
import unittest
from pathlib import Path

from src.vision.validar_danio import emparejar, iou, leer_verdad, metricas


class ValidarDanioTests(unittest.TestCase):
    def test_lee_cajas_y_poligonos_en_pixeles(self):
        with tempfile.TemporaryDirectory() as tmp:
            etiqueta = Path(tmp) / "foto.txt"
            etiqueta.write_text("1 0.5 0.5 0.2 0.4\n0 0.1 0.1 0.3 0.1 0.3 0.3\n", encoding="utf-8")
            verdad = leer_verdad(etiqueta, ancho=100, alto=200)
        self.assertEqual(len(verdad), 2)
        for obtenido, esperado in zip(verdad[0][:4], (40, 60, 60, 140)):
            self.assertAlmostEqual(obtenido, esperado)
        self.assertTrue(verdad[0][4])                       # clase 1 = dañada
        for obtenido, esperado in zip(verdad[1][:4], (10, 20, 30, 60)):
            self.assertAlmostEqual(obtenido, esperado)      # polígono -> caja que lo contiene
        self.assertFalse(verdad[1][4])

    def test_iou(self):
        self.assertAlmostEqual(iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)
        self.assertAlmostEqual(iou((0, 0, 10, 10), (5, 0, 15, 10)), 50 / 150)
        self.assertEqual(iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)

    def test_emparejar_uno_a_uno_por_confianza(self):
        verdad = [(0, 0, 10, 10, False), (20, 0, 30, 10, True)]
        detecciones = [{"caja": (0, 0, 10, 10), "conf": 0.5},
                       {"caja": (1, 0, 11, 10), "conf": 0.9},      # misma manzana, más confianza
                       {"caja": (21, 0, 31, 10), "conf": 0.8},
                       {"caja": (50, 50, 60, 60), "conf": 0.7}]    # no corresponde a ninguna
        pares = emparejar(detecciones, verdad)
        self.assertEqual(sorted(pares), [(1, 0), (2, 1)])

    def test_metricas(self):
        pares = [{"danada": True, "m": True}, {"danada": True, "m": False},
                 {"danada": False, "m": True}, {"danada": False, "m": False}, {"danada": False, "m": False}]
        m = metricas(pares, "m")
        self.assertEqual((m["tp"], m["fp"], m["fn"], m["tn"]), (1, 1, 1, 2))
        self.assertAlmostEqual(m["precision"], 0.5)
        self.assertAlmostEqual(m["recall"], 0.5)
        self.assertAlmostEqual(m["falsas_alarmas"], 1 / 3)


if __name__ == "__main__":
    unittest.main()
