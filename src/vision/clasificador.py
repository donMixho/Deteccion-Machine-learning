"""Lógica de semáforo: good / detalle / no_pasa.

Reglas basadas en calibre, color HSV, forma y clase YOLO, con umbrales de config.yaml.
OJO (fuga de datos): este semáforo es una regla de negocio para la pantalla en vivo.
La etiqueta `calidad` para entrenar ML debe venir de Roboflow, NO de esta función,
porque está derivada de las mismas features que usarían los modelos.
"""
from src.utils.config import Config

GOOD = "good"
DETALLE = "detalle"
NO_PASA = "no_pasa"

# Clases YOLO que indican defecto directo (ajustar según las clases del modelo entrenado)
CLASES_DEFECTO = {"rotten", "defect", "damaged"}

# Margen (mm) fuera de calibre tolerado como "detalle" antes de pasar a "no_pasa"
MARGEN_CALIBRE_MM = 3.0
# Relación de aspecto (lado menor / lado mayor) mínima aceptable
ASPECTO_MIN_GOOD = 0.85
ASPECTO_MIN_DETALLE = 0.70

COLORES_BGR = {GOOD: (0, 200, 0), DETALLE: (0, 215, 255), NO_PASA: (0, 0, 255)}


def color_ok(hue: float, saturacion: float, cfg: Config) -> bool:
    """Rojo en OpenCV (H 0-179) envuelve en 0: se acepta hue<=hue_max o su espejo cercano a 179."""
    ancho = cfg.hue_max - cfg.hue_min
    en_rango = cfg.hue_min <= hue <= cfg.hue_max or hue >= 180 - ancho
    return en_rango and saturacion >= cfg.saturacion_min


def clasificar(diametro_mm: float, hue: float, saturacion: float,
               aspecto: float, clase_yolo: str, cfg: Config, usar_calibre: bool = True) -> str:
    """Devuelve 'good', 'detalle' o 'no_pasa'.

    `usar_calibre=False` ignora el diámetro: en una foto cualquiera no se conoce la escala px/mm.
    """
    if str(clase_yolo).lower() in CLASES_DEFECTO:
        return NO_PASA

    # Calibre
    fuera = (max(cfg.calibre_min_mm - diametro_mm, diametro_mm - cfg.calibre_max_mm, 0.0)
             if usar_calibre else 0.0)
    if fuera > MARGEN_CALIBRE_MM:
        return NO_PASA

    # Forma
    if aspecto < ASPECTO_MIN_DETALLE:
        return NO_PASA

    problemas = 0
    if fuera > 0:
        problemas += 1
    if aspecto < ASPECTO_MIN_GOOD:
        problemas += 1
    if not color_ok(hue, saturacion, cfg):
        problemas += 1

    return GOOD if problemas == 0 else DETALLE
