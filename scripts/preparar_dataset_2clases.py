# scripts/preparar_dataset_2clases.py
"""Arma el dataset de 2 clases (apple / damaged_apple) para entrenar la detección de daño.

Al unificar los datasets en images/ la clase damaged_apple del dataset 2 pasó a apple.
Este script la recupera sin tocar images/:
  - fotos del dataset 2 (prefijo as_): etiqueta original de data/01_raw/apple_sorting_original
    (las cajas son idénticas a las de images/; solo cambia la clase)
  - frames de cinta (dataset 1): etiqueta de images/, todas apple
  - fotos sin etiqueta (p. ej. las de Pexels en images/test): se omiten

Salida: data/02_processed/dataset_2clases/ (ignorada por git) con su data.yaml.

    python scripts/preparar_dataset_2clases.py
    yolo detect train data=data/02_processed/dataset_2clases/data.yaml model=yolo26n.pt epochs=50 patience=15 imgsz=416 batch=16 device=cpu project=runs name=apple_2clases
"""
import shutil
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORIGEN = RAIZ / "images"
RAW_2CLASES = RAIZ / "data" / "01_raw" / "apple_sorting_original"
DESTINO = RAIZ / "data" / "02_processed" / "dataset_2clases"
SPLITS = ("train", "valid", "test")
NOMBRES = ["apple", "damaged_apple"]
EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def cajas_sin_clase(texto: str) -> list:
    return sorted(" ".join(linea.split()[1:]) for linea in texto.splitlines() if linea.strip())


def etiqueta_2clases(split: str, imagen: Path):
    """Texto de la etiqueta con 2 clases, o None si la foto no tiene etiqueta."""
    etiqueta = ORIGEN / split / "labels" / (imagen.stem + ".txt")
    if not etiqueta.exists():
        return None
    texto = etiqueta.read_text(encoding="utf-8")
    if not imagen.name.startswith("as_"):
        return texto                      # cinta: una sola clase (apple = 0)
    raw = RAW_2CLASES / split / "labels" / (imagen.stem[3:] + ".txt")
    texto_raw = raw.read_text(encoding="utf-8")
    if cajas_sin_clase(texto_raw) != cajas_sin_clase(texto):
        raise ValueError(f"Las cajas de {etiqueta.name} no coinciden con el dataset original; revisar antes de entrenar")
    return texto_raw


def main() -> None:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    resumen = {}
    for split in SPLITS:
        (DESTINO / split / "images").mkdir(parents=True)
        (DESTINO / split / "labels").mkdir(parents=True)
        clases, fotos, omitidas = Counter(), 0, 0
        for imagen in sorted((ORIGEN / split / "images").iterdir()):
            if imagen.suffix.lower() not in EXTENSIONES:
                continue
            texto = etiqueta_2clases(split, imagen)
            if texto is None:
                omitidas += 1
                continue
            shutil.copy2(imagen, DESTINO / split / "images" / imagen.name)
            (DESTINO / split / "labels" / (imagen.stem + ".txt")).write_text(texto, encoding="utf-8")
            clases.update(NOMBRES[int(linea.split()[0])] for linea in texto.splitlines() if linea.strip())
            fotos += 1
        resumen[split] = (fotos, clases, omitidas)

    (DESTINO / "data.yaml").write_text(
        "# Generado por scripts/preparar_dataset_2clases.py (no editar a mano)\n"
        "train: train/images\nval: valid/images\ntest: test/images\n\n"
        f"nc: {len(NOMBRES)}\nnames: {NOMBRES}\n", encoding="utf-8")

    for split, (fotos, clases, omitidas) in resumen.items():
        print(f"{split:5}: {fotos} fotos | apple={clases['apple']} damaged_apple={clases['damaged_apple']}"
              + (f" | {omitidas} sin etiqueta omitidas" if omitidas else ""))
    print(f"Dataset listo en {DESTINO}")


if __name__ == "__main__":
    main()
