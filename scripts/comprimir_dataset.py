# scripts/comprimir_dataset.py
from PIL import Image
from pathlib import Path

RAIZ    = Path(__file__).resolve().parents[1]
RAW     = RAIZ / "data" / "01_raw"
SPLITS  = ["train", "valid", "test"]
IMGSZ   = 416  # resolución máxima
CALIDAD = 75   # compresión JPEG

total = 0
for split in SPLITS:
    carpeta = RAW / split / "images"
    if not carpeta.exists():
        continue
    for img_path in carpeta.glob("*.*"):
        if img_path.suffix.lower() not in [".jpg", ".jpeg", ".png"]:
            continue
        img = Image.open(img_path).convert("RGB")
        img.thumbnail((IMGSZ, IMGSZ))  # mantiene proporción
        img.save(img_path.with_suffix(".jpg"), "JPEG", quality=CALIDAD, optimize=True)
        total += 1
        if total % 200 == 0:
            print(f"{total} imagenes procesadas...")

print(f"Listo. {total} imagenes comprimidas.")
