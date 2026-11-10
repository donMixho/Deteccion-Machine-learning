"""Construcción de features y etiqueta desde data/02_processed/metricas.csv.

ADVERTENCIA de fuga de datos: el semáforo (`clasificador.clasificar`) se calcula con
hue, saturacion y aspecto. Si esas columnas fueran features, el modelo solo reaprendería la
regla. Por eso la etiqueta `apto` (1 = 'good', 0 = 'detalle'/'no_pasa') se deriva del
semáforo SIN calibre (la escala px/mm aún no está calibrada) y los modelos supervisados se
entrenan solo con las columnas que el semáforo NO usa (FEATURES_SUPERVISADO).
Esto es una etiqueta de negocio simulada, no una verdad de campo (Roboflow).
"""
import pandas as pd

from src.utils.config import RAIZ, Config, cargar_config
from src.vision.clasificador import clasificar

CSV_METRICAS = RAIZ / "data" / "02_processed" / "metricas.csv"
FEATURES_TODAS = ["area_px", "diametro_mm_est", "hue", "saturacion", "valor", "aspecto"]
FEATURES_REGLA = ["hue", "saturacion", "aspecto"]            # entradas del semáforo
FEATURES_SUPERVISADO = [c for c in FEATURES_TODAS if c not in FEATURES_REGLA]
FEATURES_KMEANS = ["diametro_mm_est", "hue", "saturacion", "valor", "aspecto"]  # sin area_px (≡ diámetro)


def cargar_metricas(ruta=CSV_METRICAS) -> pd.DataFrame:
    return pd.read_csv(ruta)


def agregar_etiqueta(df: pd.DataFrame, cfg: Config = None) -> pd.DataFrame:
    """Añade `semaforo` (good/detalle/no_pasa) y `apto` (1 si good) sin usar calibre."""
    cfg = cfg or cargar_config()
    df = df.copy()
    df["semaforo"] = [clasificar(r.diametro_mm_est, r.hue, r.saturacion, r.aspecto,
                                 r.clase_yolo, cfg, usar_calibre=False)
                      for r in df.itertuples()]
    df["apto"] = (df["semaforo"] == "good").astype(int)
    return df


def preparar(ruta=CSV_METRICAS):
    """Devuelve (df con etiqueta, X supervisado, y, grupos por id)."""
    df = agregar_etiqueta(cargar_metricas(ruta))
    return df, df[FEATURES_SUPERVISADO], df["apto"], df["id"]
