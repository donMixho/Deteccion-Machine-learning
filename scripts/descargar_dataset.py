# scripts/descargar_dataset.py
"""Descarga el dataset de Roboflow hacia data/01_raw.

Requiere el paquete `roboflow` (pip install roboflow).
"""
from pathlib import Path

from roboflow import Roboflow

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_DESTINO = RAIZ / "data" / "01_raw"

# ==========================================================================
# PEGAR AQUÍ TU API KEY DE ROBOFLOW ANTES DE EJECUTAR (no subir con la clave puesta)
API_KEY = "O7O8l771rvehPAYaFpgj"
# ==========================================================================

# Dataset: https://universe.roboflow.com/apple-detection-ostsn/apple-detection-on-split-images/dataset/5
WORKSPACE = "apple-detection-ostsn"
PROYECTO = "apple-detection-on-split-images"
VERSION = 5
FORMATO = "yolov11"

if not API_KEY:
    raise ValueError("Completa API_KEY con tu clave de Roboflow antes de ejecutar este script.")

rf = Roboflow(api_key=API_KEY)
proyecto = rf.workspace(WORKSPACE).project(PROYECTO)
version = proyecto.version(VERSION)

CARPETA_DESTINO.mkdir(parents=True, exist_ok=True)
dataset = version.download(FORMATO, location=str(CARPETA_DESTINO), overwrite=True)

print(f"Dataset descargado en {dataset.location}")
