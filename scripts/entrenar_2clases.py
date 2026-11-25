# scripts/entrenar_2clases.py
"""Entrena el detector de 2 clases (apple / damaged_apple) con la misma receta del modelo de 1 clase.

    python scripts/preparar_dataset_2clases.py     # arma data/02_processed/dataset_2clases
    python scripts/entrenar_2clases.py             # unos 40 min en CPU

Los pesos quedan en runs/detect/apple_2clases*/weights/best.pt; para usarlos, copiarlos a models/best.pt.
Usa rutas absolutas (la configuración global de Ultralytics puede apuntar a otra carpeta) y registra
el entrenamiento en mlflow.db, igual que el modelo anterior.
"""
import argparse
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser(description="Entrenar YOLO con 2 clases")
    p.add_argument("--epocas", type=int, default=50)
    p.add_argument("--nombre", default="apple_2clases")
    p.add_argument("--proyecto", type=Path, default=RAIZ / "runs" / "detect")
    args = p.parse_args()

    datos = RAIZ / "data" / "02_processed" / "dataset_2clases" / "data.yaml"
    if not datos.exists():
        raise SystemExit("Falta el dataset: python scripts/preparar_dataset_2clases.py")
    os.environ.setdefault("MLFLOW_TRACKING_URI", f"sqlite:///{(RAIZ / 'mlflow.db').as_posix()}")

    from ultralytics import YOLO   # después de fijar MLflow
    YOLO(str(RAIZ / "yolo26n.pt")).train(
        data=str(datos), epochs=args.epocas, patience=15, imgsz=416, batch=16, device="cpu",
        project=str(args.proyecto.resolve()), name=args.nombre, seed=0, deterministic=True, workers=4)


if __name__ == "__main__":   # obligatorio en Windows: los workers del DataLoader vuelven a importar este archivo
    main()
