# scripts/instalar_modelo.py
"""Instala un modelo entrenado como models/best.pt.

    python scripts/instalar_modelo.py                 # lista los entrenamientos y pregunta cual instalar
    python scripts/instalar_modelo.py --nombre apple_2clases_mejorado

Hace tres cosas:
  1. Copia runs/detect/<nombre>/weights/best.pt a models/best.pt (el anterior queda en models/best_anterior.pt).
  2. Ajusta `imgsz` de config.yaml al tamano con que se entreno ese modelo (el detector infiere con ese valor;
     si no coincide, el conteo empeora).
  3. No toca nada si el entrenamiento no tiene best.pt.
"""
import argparse
import csv
import re
import shutil
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RUNS = RAIZ / "runs" / "detect"
MODELO = RAIZ / "models" / "best.pt"
CONFIG = RAIZ / "config.yaml"
ACTIVO_SEG = 180   # un results.csv tocado hace menos de esto indica que aun se esta entrenando


def _args(carpeta: Path) -> dict:
    """Lee args.yaml de Ultralytics (solo las claves simples que necesitamos)."""
    datos = {}
    ruta = carpeta / "args.yaml"
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^(imgsz|epochs|model):\s*(\S+)", linea)
            if m:
                datos[m.group(1)] = m.group(2)
    return datos


def _resultados(carpeta: Path):
    """(epocas hechas, mejor mAP50) desde results.csv, o (0, None)."""
    ruta = carpeta / "results.csv"
    if not ruta.exists():
        return 0, None
    with ruta.open(encoding="utf-8", newline="") as f:
        filas = [{k.strip(): v.strip() for k, v in fila.items()} for fila in csv.DictReader(f)]
    mejores = [float(f["metrics/mAP50(B)"]) for f in filas if f.get("metrics/mAP50(B)")]
    return len(filas), (max(mejores) if mejores else None)


def entrenamientos() -> list:
    """Carpetas de runs/detect con best.pt, de la mas reciente a la mas antigua."""
    if not RUNS.exists():
        return []
    carpetas = [c for c in RUNS.iterdir() if (c / "weights" / "best.pt").exists()]
    return sorted(carpetas, key=lambda c: (c / "weights" / "best.pt").stat().st_mtime, reverse=True)


def descripcion(carpeta: Path) -> str:
    a = _args(carpeta)
    hechas, mapa = _resultados(carpeta)
    activo = (carpeta / "results.csv").exists() and time.time() - (carpeta / "results.csv").stat().st_mtime < ACTIVO_SEG
    return (f"{carpeta.name:<28} imgsz {a.get('imgsz', '?'):>4} | epocas {hechas}/{a.get('epochs', '?')}"
            f" | mAP50 {'-' if mapa is None else f'{mapa:.3f}'}{'  (entrenando ahora)' if activo else ''}")


def fijar_imgsz(valor: str) -> None:
    texto = CONFIG.read_text(encoding="utf-8")
    nuevo, n = re.subn(r"^imgsz:.*$", f"imgsz: {valor}", texto, count=1, flags=re.MULTILINE)
    if n:
        CONFIG.write_text(nuevo, encoding="utf-8")


def instalar(carpeta: Path) -> None:
    origen = carpeta / "weights" / "best.pt"
    if MODELO.exists():
        shutil.copy2(MODELO, MODELO.with_name("best_anterior.pt"))
    MODELO.parent.mkdir(exist_ok=True)
    shutil.copy2(origen, MODELO)
    imgsz = _args(carpeta).get("imgsz")
    if imgsz:
        fijar_imgsz(imgsz)
    print(f"\n[OK] Instalado {carpeta.name} -> models\\best.pt" + (f" (imgsz {imgsz} en config.yaml)" if imgsz else ""))


def main() -> int:
    p = argparse.ArgumentParser(description="Instala un modelo entrenado como models/best.pt")
    p.add_argument("--nombre", help="Carpeta dentro de runs/detect")
    args = p.parse_args()

    disponibles = entrenamientos()
    if not disponibles:
        print("[AVISO] No hay entrenamientos con best.pt en runs\\detect.")
        print("        Reentrena el modelo desde modelo.bat o copia un best.pt a models\\ a mano.")
        return 1
    if args.nombre:
        elegido = next((c for c in disponibles if c.name == args.nombre), None)
        if elegido is None:
            print(f"[ERROR] No existe el entrenamiento '{args.nombre}'.")
            return 1
    else:
        print("Entrenamientos disponibles (el mas reciente primero):\n")
        for i, c in enumerate(disponibles, 1):
            print(f"  {i}) {descripcion(c)}")
        try:
            respuesta = input("\nNumero a instalar (Enter para cancelar): ").strip()
        except EOFError:
            respuesta = ""
        if not respuesta:
            print("Cancelado.")
            return 0
        if not respuesta.isdigit() or not 1 <= int(respuesta) <= len(disponibles):
            print("[ERROR] Opcion no valida.")
            return 1
        elegido = disponibles[int(respuesta) - 1]
    instalar(elegido)
    return 0


if __name__ == "__main__":
    sys.exit(main())
