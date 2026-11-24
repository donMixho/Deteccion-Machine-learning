"""Geometría de los gráficos del panel. Se dibujan con HTML/CSS (macros en _graficos.html),
así el texto se mantiene nítido en cualquier ancho y funcionan sin internet."""
import math
from datetime import date, timedelta

from src.web.negocio import CATEGORIAS

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def num(n) -> str:
    """1234567 -> '1.234.567' (formato chileno)."""
    n = n or 0
    if isinstance(n, float) and not n.is_integer():
        return f"{n:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{int(round(n)):,}".replace(",", ".")


def escala(maximo, n: int = 4):
    """Tope y marcas 'limpias' del eje Y para conteos enteros (pasos 1, 2, 5 × 10^k)."""
    maximo = float(maximo or 0)
    if maximo <= 0:
        return 4, [0, 1, 2, 3, 4]
    bruto = maximo / n
    magnitud = 10 ** math.floor(math.log10(bruto))
    paso = next(m * magnitud for m in (1, 2, 5, 10) if m * magnitud >= bruto)
    paso = max(1, int(math.ceil(paso)))
    tope = paso * math.ceil(maximo / paso)
    return tope, list(range(0, tope + 1, paso))


def dias_recientes(n: int = 14, hoy: date = None) -> list:
    hoy = hoy or date.today()
    return [hoy - timedelta(days=i) for i in range(n - 1, -1, -1)]


def etiqueta_dia(d: date) -> str:
    return f"{d.day} {MESES[d.month - 1]}"


def _mostrar_etiqueta(i: int, n: int, cada: int) -> bool:
    """Etiqueta del eje X cada `cada` columnas contando desde la última (siempre se ve la más reciente)."""
    return (n - 1 - i) % max(cada, 1) == 0


def columnas(datos, cada: int = 1, porcentaje: bool = False) -> dict:
    """datos: [(etiqueta, valor, tip)] -> columnas de una sola serie.

    `porcentaje=True` fija el eje en 0-100 % (marcas cada 25)."""
    if porcentaje:
        tope, marcas = 100, [0, 25, 50, 75, 100]
    else:
        tope, marcas = escala(max((v for _, v, _ in datos), default=0))
    sufijo = " %" if porcentaje else ""
    barras = [{"etiqueta": e, "valor": v, "pct": min(100.0 * v / tope, 100.0), "tip": tip,
               "mostrar": _mostrar_etiqueta(i, len(datos), cada)}
              for i, (e, v, tip) in enumerate(datos)]
    return {"barras": barras, "marcas": [{"pct": 100.0 * m / tope, "texto": num(m) + sufijo} for m in marcas]}


def apiladas(datos, cada: int = 1) -> dict:
    """datos: [(etiqueta, {'buena': n, 'detalle': n, 'no_pasa': n})] -> columnas apiladas por categoría."""
    totales = [sum(int(v.get(c, 0) or 0) for c, _, _ in CATEGORIAS) for _, v in datos]
    tope, marcas = escala(max(totales, default=0))
    cols = []
    for i, ((etiqueta, valores), total) in enumerate(zip(datos, totales)):
        segs = [{"clase": clase, "nombre": nombre, "valor": int(valores.get(clave, 0) or 0)}
                for clave, nombre, clase in CATEGORIAS if int(valores.get(clave, 0) or 0) > 0]
        detalle = " · ".join(f"{s['nombre']}: {num(s['valor'])}" for s in segs) or "sin análisis"
        cols.append({"etiqueta": etiqueta, "total": total, "pct": 100.0 * total / tope, "segmentos": segs,
                     "tip": f"{etiqueta} — {num(total)} manzanas ({detalle})",
                     "mostrar": _mostrar_etiqueta(i, len(datos), cada)})
    return {"columnas": cols, "marcas": [{"pct": 100.0 * m / tope, "texto": num(m)} for m in marcas]}


def segmentos(fila) -> list:
    """Partes de la barra segmentada Buena / Con detalle / No pasa (una parte en cero no se dibuja)."""
    valores = {clave: int((fila[clave] if fila else 0) or 0) for clave, _, _ in CATEGORIAS}
    total = sum(valores.values())
    partes = []
    for clave, nombre, clase in CATEGORIAS:
        v = valores[clave]
        if v <= 0:
            continue
        pct = 100.0 * v / total
        partes.append({"clave": clave, "nombre": nombre, "clase": clase, "valor": v, "pct": pct,
                       "texto": f"{pct:.0f} %" if pct >= 12 else "",   # solo si cabe dentro del bloque
                       "tip": f"{nombre}: {num(v)} ({pct:.1f} %)".replace(".", ",", 1)})
    return partes
