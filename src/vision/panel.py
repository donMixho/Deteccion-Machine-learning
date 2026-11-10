"""Panel de conteo en vivo (estilo panel_conteo_vivo_manzanas.png).

Dibuja sobre el frame: tarjeta de lote (arriba izquierda), panel de conteo
(arriba derecha) y la línea de conteo punteada. El texto usa PIL para
soportar tildes y la ñ; si no hay fuente TrueType cae a la fuente por defecto.
"""
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.utils.config import Config
from src.vision.clasificador import DETALLE, GOOD, NO_PASA

# Colores en RGB (PIL)
VERDE = (46, 204, 113)
NARANJA = (245, 158, 11)
ROJO = (231, 76, 60)
GRIS = (150, 150, 150)
BLANCO = (240, 240, 240)
FONDO = (13, 13, 13, 225)
FONDO_ENCABEZADO = (28, 28, 28, 235)
BARRA_FONDO = (45, 45, 45, 255)

FILAS = [("Buena", GOOD, VERDE), ("Con detalle", DETALLE, NARANJA), ("No pasa", NO_PASA, ROJO)]
AZUL_LINEA_BGR = (206, 130, 49)

_FUENTES: dict = {}


def _fuente(tam: float, negrita: bool = False) -> ImageFont.ImageFont:
    tam = max(int(round(tam)), 6)
    clave = (tam, negrita)
    if clave not in _FUENTES:
        nombres = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if negrita
                   else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
        for nombre in nombres:
            try:
                _FUENTES[clave] = ImageFont.truetype(nombre, tam)
                break
            except OSError:
                continue
        else:
            _FUENTES[clave] = ImageFont.load_default()
    return _FUENTES[clave]


def dibujar_panel(frame: np.ndarray, conteo: dict, cfg: Config, lote: str,
                  fps: float, vivo: bool = True, en_pantalla: int = None) -> None:
    """Dibuja tarjeta de lote y panel de conteo sobre `frame` (BGR, in-place).

    `en_pantalla`: manzanas detectadas a la vez en el frame actual (métrica instantánea).
    `conteo`: acumulado por categoría de las que ya cruzaron la línea (métrica histórica).
    Con `en_pantalla=None` (foto fija) se omite el bloque instantáneo y el acumulado se
    muestra como «Total detectadas».
    """
    alto, ancho = frame.shape[:2]
    s = max(ancho / 1000, 0.4)  # el diseño base está pensado para 1000 px de ancho
    m = 12 * s

    base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    capa = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)

    # --- Tarjeta de lote (arriba izquierda) ---
    lw, lh = 232 * s, 86 * s
    d.rounded_rectangle([m, m, m + lw, m + lh], radius=8 * s, fill=FONDO)
    d.text((m + 14 * s, m + 8 * s), "Lote activo", font=_fuente(12 * s), fill=GRIS)
    d.text((m + 14 * s, m + 26 * s), lote, font=_fuente(17 * s, True), fill=BLANCO)
    d.text((m + 14 * s, m + 54 * s), datetime.now().strftime("%Y-%m-%d %H:%M"),
           font=_fuente(13 * s), fill=GRIS)

    # --- Panel de conteo (arriba derecha) ---
    mostrar_vivo = en_pantalla is not None
    pw = min(ancho * 0.35, 265 * s)  # nunca más del 35 % del ancho en imágenes angostas
    ph = (374 if mostrar_vivo else 342) * s
    margen_der = 3 * s  # pegado al borde derecho para no tapar las manzanas
    px = ancho - pw - margen_der
    py = m
    c_sep = (60, 60, 60, 255)
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=10 * s, fill=FONDO,
                        outline=(70, 70, 70, 255), width=max(int(s), 1))
    d.rounded_rectangle([px, py, px + pw, py + 40 * s], radius=10 * s, fill=FONDO_ENCABEZADO)
    d.ellipse([px + 14 * s, py + 12 * s, px + 30 * s, py + 28 * s], fill=ROJO)
    d.text((px + 40 * s, py + 9 * s), "AppleVision Chile", font=_fuente(16 * s, True), fill=(200, 200, 200))

    y = 48.0
    if mostrar_vivo:
        # Bloque 1: manzanas en el frame actual, destacado
        d.text((px + 14 * s, py + (y + 14) * s), "En pantalla", font=_fuente(16 * s), fill=GRIS)
        f_vivo = _fuente(38 * s, True)
        txt = str(en_pantalla)
        d.text((px + pw - 14 * s - d.textlength(txt, font=f_vivo), py + y * s), txt,
               font=f_vivo, fill=BLANCO)
        y += 56
        d.line([px + 14 * s, py + y * s, px + pw - 14 * s, py + y * s], fill=c_sep, width=1)
        y += 8

    # Bloque 2: acumulado al cruzar la línea
    total = sum(conteo.get(clave, 0) for _, clave, _ in FILAS)
    d.text((px + 14 * s, py + (y + 3) * s), "Cruzaron línea" if mostrar_vivo else "Total detectadas",
           font=_fuente(14 * s), fill=GRIS)
    f_total = _fuente(20 * s, True)
    txt = str(total)
    d.text((px + pw - 14 * s - d.textlength(txt, font=f_total), py + y * s), txt,
           font=f_total, fill=BLANCO)
    y += 32
    d.line([px + 14 * s, py + y * s, px + pw - 14 * s, py + y * s], fill=c_sep, width=1)
    y += 8

    f_fila, f_num = _fuente(15 * s), _fuente(18 * s, True)
    ancho_barra = pw - 28 * s
    for etiqueta, clave, color in FILAS:
        y0 = py + y * s
        n = conteo.get(clave, 0)
        d.rounded_rectangle([px + 14 * s, y0 + 4 * s, px + 28 * s, y0 + 18 * s], radius=3 * s, fill=color)
        d.text((px + 38 * s, y0 + 1 * s), etiqueta, font=f_fila, fill=(215, 215, 215))
        d.text((px + pw - 14 * s - d.textlength(str(n), font=f_num), y0 - 2 * s), str(n),
               font=f_num, fill=color)
        yb = y0 + 26 * s
        d.rounded_rectangle([px + 14 * s, yb, px + 14 * s + ancho_barra, yb + 6 * s],
                            radius=3 * s, fill=BARRA_FONDO)
        if total > 0 and n > 0:
            d.rounded_rectangle([px + 14 * s, yb, px + 14 * s + ancho_barra * n / total, yb + 6 * s],
                                radius=3 * s, fill=color)
        y += 40

    # Pie: calibre configurado y estado
    y += 2
    d.line([px + 14 * s, py + y * s, px + pw - 14 * s, py + y * s], fill=c_sep, width=1)
    d.text((px + 14 * s, py + (y + 9) * s), "Calibre configurado", font=_fuente(13 * s), fill=GRIS)
    d.text((px + 14 * s, py + (y + 28) * s), f"{cfg.calibre_min_mm:.0f} mm — {cfg.calibre_max_mm:.0f} mm",
           font=_fuente(16 * s), fill=(215, 215, 215))
    d.text((px + 14 * s, py + (y + 60) * s), "Estado", font=_fuente(13 * s), fill=GRIS)
    color_estado = VERDE if vivo else GRIS
    d.ellipse([px + 14 * s, py + (y + 83) * s, px + 26 * s, py + (y + 95) * s], fill=color_estado)
    estado = f"En vivo · {fps:.0f} fps" if vivo else "Detenido"
    d.text((px + 34 * s, py + (y + 78) * s), estado, font=_fuente(14 * s), fill=color_estado)

    salida = Image.alpha_composite(base, capa).convert("RGB")
    frame[:] = cv2.cvtColor(np.asarray(salida), cv2.COLOR_RGB2BGR)


def dibujar_linea_conteo(frame: np.ndarray, x: int) -> None:
    """Línea vertical punteada azul con la etiqueta «conteo»."""
    alto = frame.shape[0]
    grosor = max(int(round(frame.shape[1] / 600)), 2)
    for y in range(0, alto, 24):
        cv2.line(frame, (x, y), (x, min(y + 14, alto)), AZUL_LINEA_BGR, grosor)
    cv2.putText(frame, "conteo", (x + 8, alto - 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.5 * max(frame.shape[1] / 1000, 0.8), AZUL_LINEA_BGR, 1, cv2.LINE_AA)


def dibujar_caja(frame: np.ndarray, caja, tid: int, color_bgr) -> None:
    """Caja de la manzana con etiqueta «ID:n» y punto de color."""
    x1, y1, x2, y2 = caja
    escala = max(frame.shape[1] / 1000, 0.8)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color_bgr, 2)
    y_txt = max(y1 - 8, int(14 * escala))
    cv2.putText(frame, f"ID:{tid}", (x1, y_txt), cv2.FONT_HERSHEY_SIMPLEX,
                0.55 * escala, color_bgr, 2, cv2.LINE_AA)
    cv2.circle(frame, (x1 + int(62 * escala), y_txt - int(5 * escala)), int(5 * escala), color_bgr, -1)
