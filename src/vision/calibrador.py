"""Conversión px -> mm usando un objeto de referencia de tamaño conocido."""
import math


def calibrar_escala(ancho_px: float, diametro_real_mm: float) -> float:
    """Recalcula `px_por_mm` a partir de un objeto/patrón de diámetro real conocido.

    Medir el objeto (ancho en píxeles) con la cámara fija y copiar el resultado a
    `px_por_mm` en config.yaml, o usarlo directamente para recalibrar en caliente.
    """
    if diametro_real_mm <= 0:
        raise ValueError("El diámetro real en mm debe ser > 0")
    if ancho_px <= 0:
        raise ValueError("El ancho en píxeles debe ser > 0")
    return ancho_px / diametro_real_mm


# Nombre anterior, se mantiene por compatibilidad
calcular_px_por_mm = calibrar_escala


def px_a_mm(valor_px: float, px_por_mm: float) -> float:
    return valor_px / px_por_mm


def estimar_diametro_mm(area_px: float, px_por_mm: float) -> float:
    """Diámetro equivalente (círculo/elipse) del área segmentada.

    d_mm = 2 * sqrt(area_px / pi) / px_por_mm
    """
    if px_por_mm <= 0:
        raise ValueError("px_por_mm debe ser > 0")
    if area_px <= 0:
        return 0.0
    return (2.0 * math.sqrt(area_px / math.pi)) / px_por_mm
