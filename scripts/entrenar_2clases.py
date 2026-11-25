# scripts/entrenar_2clases.py
"""Entrena el detector de 2 clases (apple / damaged_apple).

    python scripts/preparar_dataset_2clases.py     # arma data/02_processed/dataset_2clases
    python scripts/entrenar_2clases.py             # receta base: yolo26n a 416 px, ~40 min en CPU
    python scripts/entrenar_2clases.py --mejorado  # receta para contar mejor (ver RECETA_MEJORADA)

Los pesos quedan en runs/detect/<nombre>/weights/best.pt; para usarlos, copiarlos a models/best.pt.
Si cambias --imgsz, usa el mismo valor en `imgsz` de config.yaml: el detector infiere con ese tamaño.
Usa rutas absolutas (la configuración global de Ultralytics puede apuntar a otra carpeta) y registra
el entrenamiento en mlflow.db, igual que el modelo anterior.
"""
import argparse
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Receta base: la del modelo entregado en el README.
RECETA_BASE = dict(modelo="yolo26n.pt", epocas=50, patience=15, imgsz=416, batch=16)
# Receta para mejorar el conteo: más resolución (manzanas chicas y tapadas en los montones), más épocas
# con cierre gradual del mosaico, decaimiento coseno del aprendizaje y mixup suave.
RECETA_MEJORADA = dict(modelo="yolo26n.pt", epocas=80, patience=25, imgsz=640, batch=16,
                       cos_lr=True, close_mosaic=15, mixup=0.1, degrees=5.0, fliplr=0.5, flipud=0.5)


def main() -> None:
    p = argparse.ArgumentParser(description="Entrenar YOLO con 2 clases")
    p.add_argument("--mejorado", action="store_true", help="Usa RECETA_MEJORADA en vez de la receta base")
    p.add_argument("--modelo", default=None, help="Pesos de partida (yolo26n.pt, yolo26s.pt...)")
    p.add_argument("--epocas", type=int, default=None)
    p.add_argument("--imgsz", type=int, default=None)
    p.add_argument("--fraccion", type=float, default=1.0, help="Usa solo esta fracción del train (pruebas de tiempo)")
    p.add_argument("--nombre", default=None)
    p.add_argument("--proyecto", type=Path, default=RAIZ / "runs" / "detect")
    args = p.parse_args()

    receta = dict(RECETA_MEJORADA if args.mejorado else RECETA_BASE)
    for clave, valor in (("modelo", args.modelo), ("epocas", args.epocas), ("imgsz", args.imgsz)):
        if valor is not None:
            receta[clave] = valor
    nombre = args.nombre or ("apple_2clases_mejorado" if args.mejorado else "apple_2clases")

    datos = RAIZ / "data" / "02_processed" / "dataset_2clases" / "data.yaml"
    if not datos.exists():
        raise SystemExit("Falta el dataset: python scripts/preparar_dataset_2clases.py")
    os.environ.setdefault("MLFLOW_TRACKING_URI", f"sqlite:///{(RAIZ / 'mlflow.db').as_posix()}")

    from ultralytics import YOLO   # después de fijar MLflow
    modelo = receta.pop("modelo")
    epocas = receta.pop("epocas")
    ruta_modelo = RAIZ / modelo
    YOLO(str(ruta_modelo) if ruta_modelo.exists() else modelo).train(
        data=str(datos), epochs=epocas, device="cpu", fraction=args.fraccion,
        project=str(args.proyecto.resolve()), name=nombre, seed=0, deterministic=True, workers=4, **receta)


if __name__ == "__main__":   # obligatorio en Windows: los workers del DataLoader vuelven a importar este archivo
    main()
