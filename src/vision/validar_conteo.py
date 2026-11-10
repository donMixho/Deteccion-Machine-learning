"""Valida el conteo automático contra un conteo manual.

Un solo video:
    python -m src.vision.validar_conteo --video cinta.mp4 --manual 25

Varios videos, con un CSV de verdad terreno (columnas: video,conteo_manual):
    python -m src.vision.validar_conteo --manifiesto reports/verdad_terreno.csv

Probar varias posiciones de la línea de conteo (fracción del ancho):
    python -m src.vision.validar_conteo --video cinta.mp4 --manual 25 --lineas 0.3,0.5,0.8

Escribe reports/validacion_conteo.csv. No toca data/02_processed/metricas.csv.
Usa videos continuos: una carpeta de frames sueltos no sirve para validar el tracking.
"""
import argparse
import csv
from pathlib import Path

from src.utils.config import RAIZ, cargar_config
from src.vision.detector import procesar

MODELO_DEFAULT = str(RAIZ / "models" / "best.pt")
CSV_TMP = RAIZ / "data" / "02_processed" / "validacion_tmp.csv"
CSV_INFORME = RAIZ / "reports" / "validacion_conteo.csv"
COLUMNAS = ["video", "linea", "conteo_manual", "conteo_auto", "ids_vistos",
            "error", "error_abs", "error_pct"]


def leer_manifiesto(ruta: Path) -> list:
    """Lee un CSV video,conteo_manual. Las rutas relativas cuentan desde el CSV."""
    pares = []
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            video = Path(fila["video"])
            if not video.is_absolute():
                video = ruta.parent / video
            pares.append((str(video), int(fila["conteo_manual"])))
    return pares


def validar(video: str, manual: int, modelo: str, linea: float, conf: float) -> dict:
    res = procesar(video, modelo, cargar_config(), mostrar=False, csv_salida=CSV_TMP,
                   linea=linea, conf=conf)
    auto = res["contadas"]
    error = auto - manual
    return {
        "video": Path(video).name,
        "linea": linea,
        "conteo_manual": manual,
        "conteo_auto": auto,
        "ids_vistos": res["ids_vistos"],
        "error": error,
        "error_abs": abs(error),
        "error_pct": round(100 * abs(error) / manual, 1) if manual else "",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Valida el conteo automático contra el manual")
    p.add_argument("--video", help="Video a validar")
    p.add_argument("--manual", type=int, help="Conteo manual de ese video")
    p.add_argument("--manifiesto", help="CSV con columnas video,conteo_manual")
    p.add_argument("--modelo", default=MODELO_DEFAULT)
    p.add_argument("--lineas", default="0.8",
                   help="Posiciones de la línea separadas por coma (fracción del ancho)")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--salida", default=str(CSV_INFORME))
    a = p.parse_args()

    if a.manifiesto:
        pares = leer_manifiesto(Path(a.manifiesto))
    elif a.video and a.manual is not None:
        pares = [(a.video, a.manual)]
    else:
        p.error("usa --video con --manual, o --manifiesto")
    lineas = [float(x) for x in a.lineas.split(",")]

    filas = [validar(v, m, a.modelo, ln, a.conf) for v, m in pares for ln in lineas]

    Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)

    print(f"\n{'video':<28}{'línea':>6}{'manual':>8}{'auto':>6}{'error':>7}{'%':>7}")
    for r in filas:
        print(f"{r['video'][:27]:<28}{r['linea']:>6}{r['conteo_manual']:>8}"
              f"{r['conteo_auto']:>6}{r['error']:>+7}{r['error_pct']:>7}")
    for ln in lineas:
        sub = [r for r in filas if r["linea"] == ln]
        mae = sum(r["error_abs"] for r in sub) / len(sub)
        total_m = sum(r["conteo_manual"] for r in sub)
        total_a = sum(r["conteo_auto"] for r in sub)
        pct = f"{100 * abs(total_a - total_m) / total_m:.1f}%" if total_m else "n/a"
        print(f"línea {ln}: error absoluto medio {mae:.2f} | total manual {total_m}, "
              f"auto {total_a} (desvío global {pct})")
    print(f"Informe: {a.salida}")


if __name__ == "__main__":
    main()
