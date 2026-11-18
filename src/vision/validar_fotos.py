"""Compara conteos de fotos con etiquetas YOLO o un CSV imagen,conteo_manual.

    python -m src.vision.validar_fotos --split test
    python -m src.vision.validar_fotos --manifiesto reports/pruebas_fotos/manual.csv

El CSV externo usa rutas relativas a su carpeta. Las fotos de valid se usan
para elegir parametros; test y fotos externas para evaluar. El exceso de conteo
no demuestra duplicacion: puede haber objetos reales sin etiquetar.
"""
import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from src.utils.config import RAIZ, cargar_config
from src.vision.detector import (
    CONF_DEFAULT, CONF_FOTO_DEFAULT, IOU_NMS, IOU_FOTO_DEFAULT, caracteristicas_roi, predecir_foto,
)

EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def leer_casos(split=None, manifiesto=None):
    if manifiesto is not None:
        ruta = Path(manifiesto).resolve()
        casos = []
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            for fila in csv.DictReader(archivo):
                imagen = Path(fila["imagen"])
                if not imagen.is_absolute():
                    imagen = ruta.parent / imagen
                numero = int(fila["conteo_manual"])
                if numero < 0:
                    raise ValueError("El conteo manual no puede ser negativo")
                casos.append((imagen, numero))
    else:
        carpeta = RAIZ / "images" / split
        casos = []
        for imagen in sorted((carpeta / "images").iterdir()):
            if imagen.suffix.lower() not in EXTENSIONES:
                continue
            etiqueta = carpeta / "labels" / (imagen.stem + ".txt")
            # No asumir cero si falta la etiqueta.
            lineas = etiqueta.read_text(encoding="utf-8").splitlines()
            casos.append((imagen, sum(bool(linea.strip()) for linea in lineas)))
    if not casos:
        raise ValueError("No hay fotos para evaluar")
    return casos


def contar_cajas(resultado, frame):
    """Mismo descarte de recortes vacios que en procesar_imagen."""
    total = 0
    for caja in resultado.boxes.xyxy.cpu().numpy():
        x1, y1, x2, y2 = [int(v) for v in caja]
        x1, y1 = max(x1, 0), max(y1, 0)
        if x2 > x1 and y2 > y1 and caracteristicas_roi(frame, x1, y1, x2, y2) is not None:
            total += 1
    return total


def comparar(casos, modelo, conf, iou, detalle=False):
    yolo = YOLO(str(modelo))
    cfg = cargar_config()
    filas = []
    perfiles = [
        ("anterior", CONF_DEFAULT, IOU_NMS),
        ("ajustado", conf, iou),
    ]
    if detalle:
        perfiles.append(("detalle", conf, iou))
    for imagen, manual in casos:
        datos = np.fromfile(imagen, dtype=np.uint8)
        frame = cv2.imdecode(datos, cv2.IMREAD_COLOR) if datos.size else None
        if frame is None:
            raise ValueError(f"No se puede leer: {imagen}")
        for nombre, confianza, solapamiento in perfiles:
            res = predecir_foto(yolo, frame, cfg, conf=confianza,
                                iou=solapamiento, detalle=(nombre == "detalle"))
            auto = contar_cajas(res, frame)
            filas.append({
                "imagen": str(imagen), "perfil": nombre,
                "conf": confianza, "iou": solapamiento, "imgsz": cfg.imgsz,
                "detalle": nombre == "detalle",
                "conteo_manual": manual, "conteo_auto": auto,
                "error": auto - manual, "error_abs": abs(auto - manual),
            })
    return filas


def main():
    parser = argparse.ArgumentParser(description="Validar conteo de manzanas en fotos")
    fuente = parser.add_mutually_exclusive_group()
    fuente.add_argument("--split", choices=["valid", "test"], default=None)
    fuente.add_argument("--manifiesto", type=Path)
    parser.add_argument("--modelo", type=Path, default=RAIZ / "models" / "best.pt")
    parser.add_argument("--conf", type=float, default=CONF_FOTO_DEFAULT)
    parser.add_argument("--iou", type=float, default=IOU_FOTO_DEFAULT)
    parser.add_argument("--salida", type=Path, default=RAIZ / "reports" / "validacion_fotos.csv")
    parser.add_argument("--detalle-foto", action="store_true",
                        help="Comparar tambien el analisis por zonas")
    args = parser.parse_args()
    if not 0 <= args.conf <= 1 or not 0 <= args.iou <= 1:
        parser.error("--conf e --iou deben estar entre 0 y 1")
    try:
        casos = leer_casos(args.split or "test", args.manifiesto)
        filas = comparar(casos, args.modelo, args.conf, args.iou, detalle=args.detalle_foto)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)
    for perfil in dict.fromkeys(fila["perfil"] for fila in filas):
        sub = [fila for fila in filas if fila["perfil"] == perfil]
        mae = sum(fila["error_abs"] for fila in sub) / len(sub)
        exceso = sum(max(fila["error"], 0) for fila in sub)
        faltantes = sum(max(-fila["error"], 0) for fila in sub)
        exactas = sum(fila["error"] == 0 for fila in sub)
        print(f"{perfil}: {len(sub)} fotos | MAE={mae:.3f} | "
              f"exceso={exceso} | faltantes={faltantes} | exactas={exactas}")
    print(f"Informe: {args.salida}")
    print("MAE: error absoluto medio del conteo. No mide por si solo los duplicados.")


if __name__ == "__main__":
    main()
