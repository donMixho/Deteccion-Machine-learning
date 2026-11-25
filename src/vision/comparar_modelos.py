"""Compara dos modelos sobre las mismas fotos, lado a lado («antes» y «ahora»).

    python -m src.vision.comparar_modelos                     # reports/comparacion_modelos/
    python -m src.vision.comparar_modelos --salida docs/img   # regenera las imágenes del README
    python -m src.vision.comparar_modelos --fotos ruta/foto1.jpg ruta/foto2.jpg

Cada modelo se aplica como en la app (procesar_imagen), con la regla de pudrición que le
corresponda según `regla_pudricion`. Si la foto está en el dataset de 2 clases, el pie muestra
cuántas manzanas sanas y dañadas tiene etiquetadas. Por defecto compara models/best_1clase.pt
con models/best.pt en dos fotos de validación sin marcas de agua visibles.
"""
import argparse
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

from src.utils.config import RAIZ, cargar_config
from src.vision.clasificador import usar_regla_pudricion
from src.vision.detector import procesar_imagen
from src.vision.panel import _fuente

DATASET = RAIZ / "data" / "02_processed" / "dataset_2clases"
FOTOS_DEFECTO = {"sanas": "as_apple--337-", "danadas": "as_damaged_apple--183-"}   # split valid
LADO, CABECERA, PIE = 560, 88, 46
FONDO, TEXTO, SUAVE = (24, 24, 24), (240, 240, 240), (190, 190, 190)


def describir(modelo: Path, cfg) -> str:
    nombres = list(YOLO(str(modelo)).names.values())
    texto = f"{len(nombres)} clase{'s' if len(nombres) != 1 else ''}"
    return texto + (" + regla de color" if usar_regla_pudricion(cfg, nombres) else "")


def anotar(foto: Path, modelo: Path, cfg):
    """Foto anotada por el detector (cajas + panel) y su resultado."""
    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "anotada.jpg"
        r = procesar_imagen(str(foto), str(modelo), cfg, mostrar=False, lote="Comparación", guardar=str(destino))
        imagen = cv2.imdecode(np.fromfile(str(destino), np.uint8), cv2.IMREAD_COLOR)
    return Image.fromarray(cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)), r


def panel(imagen: Image.Image, titulo: str, r: dict) -> Image.Image:
    lienzo = Image.new("RGB", (LADO, LADO + CABECERA), FONDO)
    escala = min(LADO / imagen.width, LADO / imagen.height)   # agranda o achica hasta llenar el panel
    imagen = imagen.resize((round(imagen.width * escala), round(imagen.height * escala)), Image.LANCZOS)
    lienzo.paste(imagen, ((LADO - imagen.width) // 2, CABECERA + (LADO - imagen.height) // 2))
    d = ImageDraw.Draw(lienzo)
    d.text((16, 10), titulo, font=_fuente(25, True), fill=TEXTO)
    cat = r["categorias"]
    d.text((16, 50), f"Buena {cat.get('good', 0)} · Con detalle {cat.get('detalle', 0)} · No pasa {cat.get('no_pasa', 0)}",
           font=_fuente(19), fill=SUAVE)
    return lienzo


def etiquetas(foto: Path):
    """(sanas, dañadas) si la foto está en el dataset de 2 clases; si no, None."""
    etiqueta = foto.parent.parent / "labels" / (foto.stem + ".txt")
    if not etiqueta.exists():
        return None
    clases = [linea.split()[0] for linea in etiqueta.read_text(encoding="utf-8").splitlines() if linea.strip()]
    return clases.count("0"), clases.count("1")


def comparar(foto: Path, antes: Path, ahora: Path, destino: Path, cfg) -> dict:
    paneles, resultados = [], {}
    for rotulo, modelo in (("ANTES", antes), ("AHORA", ahora)):
        imagen, r = anotar(foto, modelo, cfg)
        paneles.append(panel(imagen, f"{rotulo}: {describir(modelo, cfg)}", r))
        resultados[rotulo] = r["categorias"]
    total = Image.new("RGB", (2 * LADO + 16, LADO + CABECERA + PIE), (40, 40, 40))
    total.paste(paneles[0], (0, 0))
    total.paste(paneles[1], (LADO + 16, 0))
    reales = etiquetas(foto)
    pie = (f"Etiquetado real: {reales[0]} sanas y {reales[1]} dañadas · " if reales else "") + \
        "rojo = No pasa · amarillo = Con detalle · verde = Buena"
    ImageDraw.Draw(total).text((16, LADO + CABECERA + 10), pie, font=_fuente(19), fill=TEXTO)
    destino.parent.mkdir(parents=True, exist_ok=True)
    total.save(destino, quality=88, optimize=True)
    return resultados


def main() -> None:
    p = argparse.ArgumentParser(description="Comparar dos modelos lado a lado sobre las mismas fotos")
    p.add_argument("--antes", type=Path, default=RAIZ / "models" / "best_1clase.pt")
    p.add_argument("--ahora", type=Path, default=RAIZ / "models" / "best.pt")
    p.add_argument("--fotos", nargs="+", type=Path, help="Fotos a comparar (por defecto, dos de validación)")
    p.add_argument("--salida", type=Path, default=RAIZ / "reports" / "comparacion_modelos")
    args = p.parse_args()

    if args.fotos:
        fotos = {foto.stem[:40]: foto for foto in args.fotos}
    else:
        carpeta = DATASET / "valid" / "images"
        if not carpeta.exists():
            p.error("Falta el dataset de 2 clases: python scripts/preparar_dataset_2clases.py")
        fotos = {nombre: next(carpeta.glob(f"{prefijo}*.jpg")) for nombre, prefijo in FOTOS_DEFECTO.items()}
    cfg = cargar_config()
    for nombre, foto in fotos.items():
        destino = args.salida / f"comparacion_{nombre}.jpg"
        r = comparar(foto, args.antes, args.ahora, destino, cfg)
        print(f"{destino}  antes={r['ANTES']}  ahora={r['AHORA']}")


if __name__ == "__main__":
    main()
