"""Detección + tracking YOLO de manzanas, conteo por línea y CSV de métricas.

Cada manzana recibe un ID (tracker ByteTrack) y se cuenta UNA sola vez, cuando su
centro cruza la línea de conteo. El panel en vivo muestra el total y la categoría.

    python -m src.vision.detector --modelo models/best.pt --video ruta.mp4
    python -m src.vision.detector --modelo models/best.pt --video ruta.mp4 --guardar salida.mp4 --sin-ventana

Sin --modelo se usa el nombre por defecto (YOLO26 nano, preentrenado COCO).
"""
import argparse
import csv
import os
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from src.utils.config import RAIZ, Config, cargar_config
from src.vision.calibrador import estimar_diametro_mm
from src.vision.clasificador import COLORES_BGR, NO_PASA, clasificar, tiene_pudricion
from src.vision.panel import dibujar_caja, dibujar_linea_conteo, dibujar_panel

MODELO_DEFAULT = "yolo26n.pt"
CONF_DEFAULT = 0.18   # confianza mínima: más baja capta manzanas inclinadas o parcialmente giradas
CONF_FOTO_DEFAULT = 0.35  # Seleccionado con images/valid; ajustable desde el panel.
IOU_FOTO_DEFAULT = 0.35
IOU_NMS = 0.45        # NMS más estricto: una sola caja por manzana aunque estén juntas en el centro
TRACKER_CFG = RAIZ / "config" / "bytetrack_apple.yaml"   # ByteTrack con track_buffer=60
CSV_SALIDA = RAIZ / "data" / "02_processed" / "metricas.csv"
# Códec según la extensión del video guardado. WebM (VP8) se reproduce en el navegador
# (lo usa la plataforma web); mp4v solo en reproductores de escritorio.
FOURCC_POR_EXTENSION = {".webm": "VP80"}
COLUMNAS = ["id", "frame", "area_px", "diametro_mm_est", "hue", "saturacion",
            "valor", "aspecto", "clase_yolo", "pct_defecto"]


KERNEL_3 = np.ones((3, 3), np.uint8)
FRACCION_MIN_MASCARA = 0.05   # si la máscara cubre menos que esto del bbox, se considera fallida


def _elipse_inscrita(h: int, w: int) -> np.ndarray:
    mascara = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(mascara, (w // 2, h // 2), (max(w // 2, 1), max(h // 2, 1)), 0, 0, 360, 255, -1)
    return mascara


def segmentar_fruta(hsv: np.ndarray):
    """Máscara binaria (0/255) de la fruta dentro del ROI HSV del bbox.

    La cinta (gris/oscura) tiene saturación baja: se umbraliza con Otsu sobre S
    y se descartan además los píxeles muy oscuros (canal V). Luego OPEN para
    quitar ruido y CLOSE para cerrar huecos (kernel 3x3).
    Si la segmentación falla (ROI uniforme, máscara casi vacía) se usa la elipse
    inscrita en el bbox como respaldo. Devuelve (mascara, fallida).
    """
    h, w = hsv.shape[:2]
    sat, val = hsv[..., 1], hsv[..., 2]
    _, m_sat = cv2.threshold(sat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, m_val = cv2.threshold(val, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Fondo oscuro: exige V sobre el umbral de Otsu solo si éste es razonablemente bajo
    umbral_v = cv2.threshold(val, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[0]
    mascara = m_sat if umbral_v > 100 else cv2.bitwise_and(m_sat, m_val)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, KERNEL_3)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, KERNEL_3)
    if np.count_nonzero(mascara) < FRACCION_MIN_MASCARA * h * w:
        return _elipse_inscrita(h, w), True
    return mascara, False


# Pudrición / daño: píxeles necróticos (muy oscuros) o marrones apagados dentro de la fruta
V_MAX_OSCURO = 75
H_MARRON_MIN, H_MARRON_MAX = 10, 25
S_MAX_MARRON = 110


def porcentaje_defecto(hsv: np.ndarray, mascara: np.ndarray) -> float:
    """% de la fruta con manchas oscuras (V < 75) o marrón apagado (10 <= H <= 25 y S < 110).

    La máscara de `segmentar_fruta` excluye justamente las manchas oscuras/poco saturadas,
    así que se rellena su contorno exterior (la mancha queda dentro) y se erosiona un poco
    para no contar la sombra del borde de la fruta.
    """
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return 0.0
    fruta = np.zeros_like(mascara)
    cv2.drawContours(fruta, contornos, -1, 255, -1)
    lado = max(3, (min(mascara.shape[:2]) // 20) | 1)   # ~5 % del lado, impar
    erosionada = cv2.erode(fruta, np.ones((lado, lado), np.uint8))
    if np.count_nonzero(erosionada) > 0.3 * np.count_nonzero(fruta):
        fruta = erosionada
    dentro = fruta > 0
    total = int(np.count_nonzero(dentro))
    if total == 0:
        return 0.0
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    oscuro = v < V_MAX_OSCURO
    marron = (h >= H_MARRON_MIN) & (h <= H_MARRON_MAX) & (s < S_MAX_MARRON)
    return 100.0 * np.count_nonzero((oscuro | marron) & dentro) / total


def toca_borde(x1: int, y1: int, x2: int, y2: int, ancho: int, alto: int) -> bool:
    """True si el bbox toca alguno de los 4 bordes del encuadre (objeto cortado)."""
    return x1 <= 0 or y1 <= 0 or x2 >= ancho or y2 >= alto


AREA_MIN_PX = 3000
ASPECTO_MIN = 0.50   # 0.60 descartaba manzanas inclinadas o vistas en perspectiva
HUE_MAX_ROJO = 25.0
HUE_MIN_ROJO = 165.0


def es_deteccion_valida(area_px: float, aspecto: float, hue: float) -> bool:
    """Calidad geométrica y de color mínima para escribir la fila en metricas.csv."""
    return (area_px >= AREA_MIN_PX and aspecto >= ASPECTO_MIN
            and (hue <= HUE_MAX_ROJO or hue >= HUE_MIN_ROJO))


def caracteristicas_roi(frame: np.ndarray, x1: int, y1: int, x2: int, y2: int):
    """(area_px, hue, sat, val, mascara_fallida, pct_defecto) de la fruta, sobre los píxeles de la máscara."""
    recorte = frame[y1:y2, x1:x2]
    if recorte.size == 0:
        return None
    hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
    mascara, fallida = segmentar_fruta(hsv)
    area_px = int(np.count_nonzero(mascara))
    if area_px == 0:
        return None
    # El matiz es circular (rojo ~0/179): media circular para no sesgar
    ang = hsv[..., 0][mascara > 0].astype(np.float64) * 2 * np.pi / 180
    hue = (np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) * 180 / (2 * np.pi)) % 180
    sat, val = cv2.mean(hsv, mask=mascara)[1:3]
    return area_px, float(hue), float(sat), float(val), fallida, porcentaje_defecto(hsv, mascara)


def hsv_promedio(frame: np.ndarray, x1: int, y1: int, x2: int, y2: int):
    """HSV medio de la fruta binarizada (compatibilidad)."""
    r = caracteristicas_roi(frame, x1, y1, x2, y2)
    return None if r is None else r[1:4]


def medir_referencia(frame: np.ndarray, modelo: str, cfg: Config, conf: float = CONF_DEFAULT):
    """Mide la manzana más grande del frame para calibrar la escala.

    Devuelve {"diametro_px", "caja"} o None si no hay detección. El diámetro es el
    equivalente al área segmentada (2*sqrt(area/pi)), la misma medida que usa
    `estimar_diametro_mm`, así px_por_mm = diametro_px / diametro_real_mm es coherente.
    """
    res = YOLO(modelo).predict(frame, imgsz=cfg.imgsz, conf=conf, iou=IOU_NMS, verbose=False)[0]
    mejor = None
    for caja in res.boxes.xyxy.cpu().numpy():
        x1, y1, x2, y2 = [int(v) for v in caja]
        x1, y1 = max(x1, 0), max(y1, 0)
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            continue
        carac = caracteristicas_roi(frame, x1, y1, x2, y2)
        if carac is None:
            continue
        diametro_px = 2.0 * np.sqrt(carac[0] / np.pi)
        if mejor is None or diametro_px > mejor["diametro_px"]:
            mejor = {"diametro_px": float(diametro_px), "caja": (x1, y1, x2, y2)}
    return mejor


def procesar(fuente, modelo: str, cfg: Config, mostrar: bool = True,
             csv_salida: Path = CSV_SALIDA, lote: str = "Lote 1",
             linea: float = 0.8, guardar: str = None, conf: float = CONF_DEFAULT,
             al_frame=None) -> dict:
    """Cuenta las manzanas de un video o cámara.

    `al_frame(n_frame, frame_anotado)`: opcional, se llama con cada frame ya dibujado
    (la plataforma web lo usa para mostrar el progreso). Si devuelve True, se detiene.
    """
    yolo = YOLO(modelo)
    # Cámara (índice entero): en Windows DirectShow abre más rápido; si falla, backend por defecto
    cap = cv2.VideoCapture(fuente, cv2.CAP_DSHOW) if isinstance(fuente, int) else cv2.VideoCapture(fuente)
    if isinstance(fuente, int) and not cap.isOpened():
        cap = cv2.VideoCapture(fuente)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir la fuente de video: {fuente}")

    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_video = cap.get(cv2.CAP_PROP_FPS) or 24.0
    x_linea = int(ancho * linea)

    escritor_video = None
    if guardar:
        os.makedirs(os.path.dirname(os.path.abspath(guardar)), exist_ok=True)
        fourcc = FOURCC_POR_EXTENSION.get(Path(guardar).suffix.lower(), "mp4v")
        escritor_video = cv2.VideoWriter(guardar, cv2.VideoWriter_fourcc(*fourcc),
                                         fps_video, (ancho, alto))

    os.makedirs(csv_salida.parent, exist_ok=True)
    historial = defaultdict(list)   # id -> categorías vistas (se usa la más frecuente)
    lado_previo = {}                # id -> signo de (centro_x - x_linea) en el frame anterior
    contadas = {}                   # id -> categoría con la que se contó al cruzar
    defecto_hist = defaultdict(list)  # id -> % de defecto por frame (pudrición)
    por_pudricion = set()           # ids contados como no_pasa por pudrición / daño
    n_frame, fps_suave, t_prev = 0, 0.0, time.perf_counter()
    descartadas = 0                 # detecciones incompletas no escritas al CSV

    with open(csv_salida, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(COLUMNAS)

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            n_frame += 1

            res = yolo.track(frame, persist=True, imgsz=cfg.imgsz, conf=conf, iou=IOU_NMS,
                             tracker=str(TRACKER_CFG), verbose=False)[0]
            dibujos = []
            if res.boxes is not None and res.boxes.id is not None:
                for caja, tid, cls in zip(res.boxes.xyxy.cpu().numpy(),
                                          res.boxes.id.int().cpu().tolist(),
                                          res.boxes.cls.int().cpu().tolist()):
                    x1, y1, x2, y2 = [int(v) for v in caja]
                    x1, y1 = max(x1, 0), max(y1, 0)
                    w_caja, h_caja = x2 - x1, y2 - y1
                    if w_caja <= 0 or h_caja <= 0:
                        continue
                    carac = caracteristicas_roi(frame, x1, y1, x2, y2)
                    if carac is None:
                        continue
                    area_px, hue, sat, val, mascara_fallida, pct_defecto = carac

                    diametro_mm = estimar_diametro_mm(area_px, cfg.px_por_mm)
                    aspecto = min(w_caja, h_caja) / max(w_caja, h_caja)
                    nombre = yolo.names[cls]

                    incompleta = (mascara_fallida or toca_borde(x1, y1, x2, y2, ancho, alto)
                                  or not es_deteccion_valida(area_px, aspecto, hue))
                    if incompleta:
                        descartadas += 1   # cortada por el encuadre o máscara fallida: sin métricas
                        # Sin historial: categoría provisional (no entra al historial) para
                        # no perder el cruce de línea ni el dibujo de un ID que ya existe
                        categoria_prov = clasificar(diametro_mm, hue, sat, aspecto, nombre, cfg,
                                                    pct_defecto=pct_defecto)
                    else:
                        escritor.writerow([tid, n_frame, area_px, round(diametro_mm, 2),
                                           round(hue, 2), round(sat, 2), round(val, 2),
                                           round(aspecto, 4), nombre, round(pct_defecto, 2)])
                        categoria = clasificar(diametro_mm, hue, sat, aspecto, nombre, cfg,
                                               pct_defecto=pct_defecto)
                        historial[tid].append(categoria)
                        defecto_hist[tid].append(pct_defecto)
                    categoria_estable = (Counter(historial[tid]).most_common(1)[0][0]
                                         if historial[tid] else categoria_prov)

                    # Conteo: se cuenta una vez, cuando el centro cambia de lado de la línea
                    lado = 1 if (x1 + x2) / 2 >= x_linea else -1
                    if tid in lado_previo and lado != lado_previo[tid] and tid not in contadas:
                        contadas[tid] = categoria_estable
                        if (categoria_estable == NO_PASA and defecto_hist[tid]
                                and tiene_pudricion(float(np.median(defecto_hist[tid])), cfg)):
                            por_pudricion.add(tid)
                    lado_previo[tid] = lado

                    dibujos.append(((x1, y1, x2, y2), tid, COLORES_BGR[categoria_estable]))

            ahora = time.perf_counter()
            inst = 1.0 / max(ahora - t_prev, 1e-6)
            fps_suave = inst if fps_suave == 0 else 0.9 * fps_suave + 0.1 * inst
            t_prev = ahora

            dibujar_linea_conteo(frame, x_linea)
            for caja, tid, color in dibujos:
                dibujar_caja(frame, caja, tid, color)
            conteo = Counter(contadas.values())
            en_pantalla = len(dibujos)          # detecciones del frame actual (instantáneo)
            dibujar_panel(frame, conteo, cfg, lote, fps_suave, en_pantalla=en_pantalla)

            if escritor_video is not None:
                escritor_video.write(frame)
            if al_frame is not None and al_frame(n_frame, frame):
                break
            if mostrar:
                cv2.imshow("AppleVision Chile (q para salir)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    cap.release()
    if escritor_video is not None:
        escritor_video.release()
    cv2.destroyAllWindows()
    resumen = dict(Counter(contadas.values()))
    print(f"CSV guardado en {csv_salida} | filas descartadas: {descartadas}")
    print(f"IDs vistos: {len(historial)} | contadas al cruzar la línea: {len(contadas)} | por categoría: {resumen}"
          f" | no pasa por pudrición/daño: {len(por_pudricion)}")
    return {"ids_vistos": len(historial), "contadas": len(contadas), "categorias": resumen,
            "pudricion": len(por_pudricion)}


def predecir_foto(yolo, frame, cfg, conf=CONF_FOTO_DEFAULT,
                  iou=IOU_FOTO_DEFAULT, detalle=False):
    """Inferencia global y, opcionalmente, nueve zonas con solapamiento.

    Las cajas se llevan a coordenadas de la foto y se fusionan con NMS
    por clase. No se suman los conteos de las zonas.
    """
    resultado = yolo.predict(frame, imgsz=cfg.imgsz, conf=conf, iou=iou,
                             verbose=False)[0]
    if not detalle or min(frame.shape[:2]) < 16:
        return resultado

    import torch
    from torchvision.ops import batched_nms

    alto, ancho = frame.shape[:2]
    ancho_zona, alto_zona = round(ancho * 0.45), round(alto * 0.45)
    xs = sorted({0, (ancho - ancho_zona) // 2, ancho - ancho_zona})
    ys = sorted({0, (alto - alto_zona) // 2, alto - alto_zona})
    candidatas = [resultado.boxes.data]
    for y in ys:
        for x in xs:
            zona = frame[y:y + alto_zona, x:x + ancho_zona]
            res = yolo.predict(zona, imgsz=cfg.imgsz, conf=conf, iou=iou,
                               verbose=False)[0]
            cajas = res.boxes.data.clone()
            # Una caja cortada por un borde interno puede duplicar un objeto.
            validas = torch.ones(len(cajas), dtype=torch.bool, device=cajas.device)
            if x > 0:
                validas &= cajas[:, 0] > 2
            if y > 0:
                validas &= cajas[:, 1] > 2
            if x + ancho_zona < ancho:
                validas &= cajas[:, 2] < ancho_zona - 2
            if y + alto_zona < alto:
                validas &= cajas[:, 3] < alto_zona - 2
            cajas = cajas[validas]
            cajas[:, [0, 2]] += x
            cajas[:, [1, 3]] += y
            candidatas.append(cajas)

    cajas = torch.cat(candidatas, dim=0)
    if len(cajas):
        indices = batched_nms(cajas[:, :4], cajas[:, 4], cajas[:, 5].long(), iou)
        cajas = cajas[indices]
    resultado.update(boxes=cajas)
    return resultado


def procesar_imagen(ruta: str, modelo: str, cfg: Config, mostrar: bool = True,
                    lote: str = "Foto", guardar: str = None, conf: float = CONF_FOTO_DEFAULT,
                    iou: float = IOU_FOTO_DEFAULT, detalle: bool = False) -> dict:
    """Cuenta las manzanas de UNA foto. Sin tracking: cada detección es una manzana."""
    # imdecode + fromfile: cv2.imread falla con rutas con tildes o ñ en Windows
    datos = np.fromfile(ruta, dtype=np.uint8)
    frame = cv2.imdecode(datos, cv2.IMREAD_COLOR) if datos.size else None
    if frame is None:
        raise RuntimeError(f"No se pudo leer la imagen: {ruta}")

    yolo = YOLO(modelo)
    res = predecir_foto(yolo, frame, cfg, conf=conf, iou=iou, detalle=detalle)
    conteo, dibujos, pudricion = Counter(), [], 0
    for n, (caja, cls) in enumerate(zip(res.boxes.xyxy.cpu().numpy(),
                                        res.boxes.cls.int().cpu().tolist()), start=1):
        x1, y1, x2, y2 = [int(v) for v in caja]
        x1, y1 = max(x1, 0), max(y1, 0)
        w_caja, h_caja = x2 - x1, y2 - y1
        carac = caracteristicas_roi(frame, x1, y1, x2, y2) if w_caja > 0 and h_caja > 0 else None
        if carac is None:
            continue
        area_px, hue, sat, _, _, pct_defecto = carac
        diametro_mm = estimar_diametro_mm(area_px, cfg.px_por_mm)
        aspecto = min(w_caja, h_caja) / max(w_caja, h_caja)
        categoria = clasificar(diametro_mm, hue, sat, aspecto, yolo.names[cls], cfg,
                               usar_calibre=False,  # foto: no se conoce px/mm
                               pct_defecto=pct_defecto)
        conteo[categoria] += 1
        pudricion += tiene_pudricion(pct_defecto, cfg)
        dibujos.append(((x1, y1, x2, y2), n, COLORES_BGR[categoria]))

    for caja, n, color in dibujos:
        dibujar_caja(frame, caja, n, color)
    dibujar_panel(frame, conteo, cfg, lote, 0.0)

    if guardar:
        os.makedirs(os.path.dirname(os.path.abspath(guardar)), exist_ok=True)
        ok, buf = cv2.imencode(Path(guardar).suffix or ".jpg", frame)
        if ok:
            buf.tofile(guardar)
    if mostrar:
        h, w = frame.shape[:2]
        k = min(1.0, 1100 / w, 700 / h)   # que quepa en pantalla
        vista = cv2.resize(frame, (int(w * k), int(h * k))) if k < 1 else frame
        cv2.imshow("Foto contada (cualquier tecla para cerrar)", vista)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    total = len(dibujos)
    print(f"Manzanas detectadas en la foto: {total} | por categoría: {dict(conteo)}"
          f" | no pasa por pudrición/daño: {pudricion}")
    return {"ids_vistos": total, "contadas": total, "categorias": dict(conteo), "pudricion": pudricion}


def main() -> None:
    parser = argparse.ArgumentParser(description="Detección y conteo de manzanas con YOLO")
    parser.add_argument("--modelo", default=MODELO_DEFAULT)
    parser.add_argument("--foto", default=None, help="Cuenta las manzanas de una foto y termina")
    parser.add_argument("--video", default=None, help="Ruta de video; por defecto config.yaml")
    parser.add_argument("--sin-ventana", action="store_true")
    parser.add_argument("--lote", default="Lote 1", help="Texto de la tarjeta «Lote activo»")
    parser.add_argument("--linea", type=float, default=0.8,
                        help="Posición de la línea de conteo, como fracción del ancho (0-1)")
    parser.add_argument("--guardar", default=None, help="Guardar el video con el panel (.mp4)")
    parser.add_argument("--conf", type=float, default=None,
                        help="Confianza minima (foto: 0.35; video: 0.18)")
    parser.add_argument("--iou", type=float, default=None,
                        help="Umbral de solapamiento para fotos (por defecto 0.35)")
    parser.add_argument("--detalle-foto", action="store_true",
                        help="Buscar manzanas pequenas en zonas solapadas (solo fotos)")
    args = parser.parse_args()

    cfg = cargar_config()
    if args.foto:
        procesar_imagen(args.foto, args.modelo, cfg, mostrar=not args.sin_ventana, lote=args.lote,
                        guardar=args.guardar,
                        conf=CONF_FOTO_DEFAULT if args.conf is None else args.conf,
                        iou=IOU_FOTO_DEFAULT if args.iou is None else args.iou,
                        detalle=args.detalle_foto)
        return
    fuente = args.video if args.video is not None else cfg.fuente_video
    procesar(fuente, args.modelo, cfg, mostrar=not args.sin_ventana, lote=args.lote,
             linea=args.linea, guardar=args.guardar,
             conf=CONF_DEFAULT if args.conf is None else args.conf)


if __name__ == "__main__":
    main()
