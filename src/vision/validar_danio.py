"""Evalúa si se detectan bien las manzanas dañadas: regla de color vs. modelo de 2 clases.

Usa el dataset de 2 clases (scripts/preparar_dataset_2clases.py). En cada foto empareja las
detecciones con las manzanas etiquetadas (IoU >= 0.5, de mayor a menor confianza) y compara
"dañada" (verdad: clase damaged_apple) con lo que dice cada método:
  - regla:        % de píxeles oscuros o marrones > max_pct_defecto (lo que usa hoy la app)
  - modelo:       la detección es de clase damaged_apple (solo modelos de 2 clases)
  - modelo+regla: cualquiera de los dos (lo que hace clasificar() con un modelo de 2 clases)
  - semáforo:     la categoría final es «No pasa» (incluye además la forma)

    python -m src.vision.validar_danio --split valid
    python -m src.vision.validar_danio --split valid --modelos models/best.pt runs/detect/apple_2clases/weights/best.pt

Escribe una fila por manzana emparejada en reports/validacion_danio.csv.
"""
import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from src.utils.config import RAIZ, cargar_config
from src.vision.calibrador import estimar_diametro_mm
from src.vision.clasificador import CLASES_DEFECTO, NO_PASA, clasificar, tiene_pudricion, usar_regla_pudricion
from src.vision.detector import CONF_FOTO_DEFAULT, IOU_FOTO_DEFAULT, caracteristicas_roi, predecir_foto

DATASET = RAIZ / "data" / "02_processed" / "dataset_2clases"
IOU_MIN = 0.5
EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def leer_verdad(etiqueta: Path, ancho: int, alto: int) -> list:
    """Cajas etiquetadas en píxeles: [(x1, y1, x2, y2, dañada)]. Acepta cajas y polígonos YOLO."""
    verdad = []
    for linea in etiqueta.read_text(encoding="utf-8").splitlines():
        partes = linea.split()
        if not partes:
            continue
        clase, coords = int(partes[0]), [float(v) for v in partes[1:]]
        if len(coords) == 4:
            xc, yc, w, h = coords
            x1, y1, x2, y2 = (xc - w / 2) * ancho, (yc - h / 2) * alto, (xc + w / 2) * ancho, (yc + h / 2) * alto
        else:   # polígono: caja que lo contiene
            xs, ys = coords[0::2], coords[1::2]
            x1, y1, x2, y2 = min(xs) * ancho, min(ys) * alto, max(xs) * ancho, max(ys) * alto
        verdad.append((x1, y1, x2, y2, clase == 1))
    return verdad


def iou(a, b) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(ix2 - ix1, 0) * max(iy2 - iy1, 0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def emparejar(detecciones: list, verdad: list) -> list:
    """Pares (índice detección, índice verdad), uno a uno, de mayor a menor confianza."""
    libres, pares = set(range(len(verdad))), []
    for i in sorted(range(len(detecciones)), key=lambda k: -detecciones[k]["conf"]):
        mejor, mejor_iou = None, IOU_MIN
        for j in libres:
            valor = iou(detecciones[i]["caja"], verdad[j])
            if valor >= mejor_iou:
                mejor, mejor_iou = j, valor
        if mejor is not None:
            libres.discard(mejor)
            pares.append((i, mejor))
    return pares


def detectar(yolo, frame, cfg, conf, iou_nms, regla_app: bool = True) -> list:
    """Detecciones como las ve la app: caja, clase, % de defecto y categoría del semáforo."""
    res = predecir_foto(yolo, frame, cfg, conf=conf, iou=iou_nms)
    salida = []
    for caja, cls, confianza in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.cls.int().cpu().tolist(),
                                    res.boxes.conf.cpu().tolist()):
        x1, y1, x2, y2 = [int(v) for v in caja]
        x1, y1 = max(x1, 0), max(y1, 0)
        if x2 <= x1 or y2 <= y1:
            continue
        carac = caracteristicas_roi(frame, x1, y1, x2, y2)
        if carac is None:
            continue
        area_px, hue, sat, _, _, pct = carac
        nombre = yolo.names[cls]
        aspecto = min(x2 - x1, y2 - y1) / max(x2 - x1, y2 - y1)
        categoria = clasificar(estimar_diametro_mm(area_px, cfg.px_por_mm), hue, sat, aspecto, nombre, cfg,
                               usar_calibre=False, pct_defecto=pct, regla_color=regla_app)
        salida.append({"caja": (x1, y1, x2, y2), "conf": confianza, "clase": nombre, "pct": pct,
                       "categoria": categoria})
    return salida


def metricas(pares: list, clave: str) -> dict:
    tp = sum(p["danada"] and p[clave] for p in pares)
    fp = sum(not p["danada"] and p[clave] for p in pares)
    fn = sum(p["danada"] and not p[clave] for p in pares)
    tn = sum(not p["danada"] and not p[clave] for p in pares)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1,
            "falsas_alarmas": fp / (fp + tn) if fp + tn else 0.0}


def evaluar(ruta_modelo: Path, split: str, conf: float, iou_nms: float):
    cfg = cargar_config()
    yolo = YOLO(str(ruta_modelo))
    dos_clases = any(n in CLASES_DEFECTO for n in yolo.names.values())
    regla_app = usar_regla_pudricion(cfg, yolo.names.values())   # lo mismo que hace la app
    filas, total_verdad, total_danadas, omitidas, de_mas, fotos = [], 0, 0, 0, 0, 0
    for imagen in sorted((DATASET / split / "images").iterdir()):
        if imagen.suffix.lower() not in EXTENSIONES:
            continue
        datos = np.fromfile(str(imagen), dtype=np.uint8)
        frame = cv2.imdecode(datos, cv2.IMREAD_COLOR)
        alto, ancho = frame.shape[:2]
        verdad = leer_verdad(DATASET / split / "labels" / (imagen.stem + ".txt"), ancho, alto)
        detecciones = detectar(yolo, frame, cfg, conf, iou_nms, regla_app)
        pares = emparejar(detecciones, verdad)
        fotos += 1
        total_verdad += len(verdad)
        total_danadas += sum(v[4] for v in verdad)
        omitidas += len(verdad) - len(pares)
        de_mas += len(detecciones) - len(pares)
        for i, j in pares:
            d = detecciones[i]
            filas.append({"modelo": ruta_modelo.as_posix(), "imagen": imagen.name, "danada": verdad[j][4],
                          "clase_modelo": d["clase"], "pct_defecto": round(d["pct"], 2),
                          "regla": tiene_pudricion(d["pct"], cfg),
                          "modelo_dice": d["clase"] in CLASES_DEFECTO,
                          "modelo_o_regla": d["clase"] in CLASES_DEFECTO or tiene_pudricion(d["pct"], cfg),
                          "semaforo_no_pasa": d["categoria"] == NO_PASA})
    resumen = {"fotos": fotos, "verdad": total_verdad, "danadas": total_danadas, "emparejadas": len(filas),
               "omitidas": omitidas, "de_mas": de_mas, "dos_clases": dos_clases, "regla_app": regla_app}
    return filas, resumen


def main() -> None:
    p = argparse.ArgumentParser(description="Detección de manzanas dañadas: regla vs. modelo de 2 clases")
    p.add_argument("--split", choices=["train", "valid", "test"], default="valid")
    p.add_argument("--modelos", nargs="+", type=Path, default=[RAIZ / "models" / "best.pt"])
    p.add_argument("--conf", type=float, default=CONF_FOTO_DEFAULT)
    p.add_argument("--iou", type=float, default=IOU_FOTO_DEFAULT)
    p.add_argument("--salida", type=Path, default=RAIZ / "reports" / "validacion_danio.csv")
    args = p.parse_args()
    if not (DATASET / args.split / "images").exists():
        p.error("Falta el dataset de 2 clases: python scripts/preparar_dataset_2clases.py")

    todas = []
    for ruta in args.modelos:
        filas, r = evaluar(ruta, args.split, args.conf, args.iou)
        todas += filas
        print(f"\n{ruta.as_posix()} ({'2 clases' if r['dos_clases'] else '1 clase'}) · {args.split}: {r['fotos']} fotos, "
              f"{r['verdad']} manzanas etiquetadas ({r['danadas']} dañadas)")
        print(f"  Detección: {r['emparejadas']} emparejadas, {r['omitidas']} omitidas, {r['de_mas']} detecciones de más")
        metodos = [("regla", "regla de color")]
        if r["dos_clases"]:
            metodos += [("modelo_dice", "modelo"), ("modelo_o_regla", "modelo + regla")]
        metodos.append(("semaforo_no_pasa", "semáforo «No pasa»"))
        print(f"  (el semáforo usa la regla de color: {'sí' if r['regla_app'] else 'no'}; "
              f"regla_pudricion={cargar_config().regla_pudricion})")
        print(f"  {'Método':<20}{'Precisión':>10}{'Recall':>8}{'F1':>7}{'Sanas marcadas dañadas':>25}")
        for clave, nombre in metodos:
            m = metricas(filas, clave)
            print(f"  {nombre:<20}{m['precision']:>10.2f}{m['recall']:>8.2f}{m['f1']:>7.2f}"
                  f"{m['falsas_alarmas']:>19.0%} ({m['fp']})")

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(todas[0]))
        escritor.writeheader()
        escritor.writerows(todas)
    print(f"\nInforme por manzana: {args.salida}")


if __name__ == "__main__":
    main()
