"""Pruebas de coordenadas y fusion de cajas del analisis de fotos por zonas."""
import unittest
from types import SimpleNamespace

import numpy as np
import torch
from ultralytics.engine.results import Results

from src.vision.detector import predecir_foto


class ModeloSimulado:
    def __init__(self, salidas):
        self.salidas = iter(salidas)
        self.llamadas = 0

    def predict(self, frame, **kwargs):
        self.llamadas += 1
        cajas = torch.tensor(next(self.salidas), dtype=torch.float32).reshape(-1, 6)
        return [Results(frame, path="foto.jpg", names={0: "apple", 1: "otra"}, boxes=cajas)]


class FotoDetalleTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((100, 100, 3), dtype=np.uint8)
        self.cfg = SimpleNamespace(imgsz=416)

    def predecir(self, salidas, detalle=True):
        modelo = ModeloSimulado(salidas)
        res = predecir_foto(modelo, self.frame, self.cfg, detalle=detalle)
        return res.boxes.data, modelo.llamadas

    def test_misma_manzana_en_zonas_se_cuenta_una_vez(self):
        salidas = [[] for _ in range(10)]
        salidas[0] = [[30, 30, 40, 40, .7, 0]]
        salidas[1] = [[30, 30, 40, 40, .8, 0]]
        # Zona central: origen (27, 27). Recuperar coordenadas absolutas.
        salidas[5] = [[3, 3, 13, 13, .9, 0]]
        cajas, llamadas = self.predecir(salidas)
        self.assertEqual(llamadas, 10)
        self.assertEqual(len(cajas), 1)
        torch.testing.assert_close(cajas[0, :4], torch.tensor([30., 30., 40., 40.]))

    def test_manzanas_distintas_se_conservan(self):
        salidas = [[] for _ in range(10)]
        salidas[0] = [[30, 30, 40, 40, .8, 0]]
        salidas[9] = [[5, 5, 15, 15, .8, 0]]
        cajas, _ = self.predecir(salidas)
        self.assertEqual(len(cajas), 2)
        self.assertTrue(any(torch.equal(caja[:4], torch.tensor([60., 60., 70., 70.]))
                            for caja in cajas))

    def test_caja_cortada_en_borde_interno_se_descarta(self):
        salidas = [[] for _ in range(10)]
        salidas[5] = [[0, 3, 10, 13, .9, 0]]
        cajas, _ = self.predecir(salidas)
        self.assertEqual(len(cajas), 0)

    def test_borde_real_de_la_foto_se_conserva(self):
        salidas = [[] for _ in range(10)]
        salidas[1] = [[0, 5, 10, 15, .9, 0]]
        cajas, _ = self.predecir(salidas)
        self.assertEqual(len(cajas), 1)

    def test_sin_detecciones_no_falla(self):
        cajas, llamadas = self.predecir([[] for _ in range(10)])
        self.assertEqual(len(cajas), 0)
        self.assertEqual(llamadas, 10)

    def test_modo_normal_solo_analiza_la_foto_completa(self):
        cajas, llamadas = self.predecir([[[30, 30, 40, 40, .8, 0]]], detalle=False)
        self.assertEqual(len(cajas), 1)
        self.assertEqual(llamadas, 1)


if __name__ == "__main__":
    unittest.main()
