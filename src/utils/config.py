"""Carga de parámetros desde config.yaml."""
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CONFIG_PATH = RAIZ / "config.yaml"


@dataclass(frozen=True)
class Config:
    calibre_min_mm: float
    calibre_max_mm: float
    hue_min: int
    hue_max: int
    saturacion_min: int
    fuente_video: Union[int, str]
    px_por_mm: float
    imgsz: int
    s3_bucket: str
    s3_prefix: str


def cargar_config(ruta: Path = CONFIG_PATH) -> Config:
    with open(ruta, "r", encoding="utf-8") as f:
        datos = yaml.safe_load(f)
    return Config(
        calibre_min_mm=float(datos["calibre_min_mm"]),
        calibre_max_mm=float(datos["calibre_max_mm"]),
        hue_min=int(datos["hue_min"]),
        hue_max=int(datos["hue_max"]),
        saturacion_min=int(datos["saturacion_min"]),
        fuente_video=datos["fuente_video"],
        px_por_mm=float(datos["px_por_mm"]),
        imgsz=int(datos.get("imgsz", 640)),
        s3_bucket=str(datos.get("s3_bucket") or ""),
        s3_prefix=str(datos.get("s3_prefix") or ""),
    )
