"""Métricas, gráficos y registro en MLflow (tracking local en ./mlruns)."""
import mlflow
import numpy as np
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                             recall_score, silhouette_score)

from src.utils.config import RAIZ

mlflow.set_tracking_uri(f"sqlite:///{(RAIZ / 'mlflow.db').as_posix()}")  # MLflow 3 ya no admite el file store
mlflow.set_experiment("applevision-calidad")


def metricas_clasificacion(y_true, y_pred) -> dict:
    kw = dict(zero_division=0)
    return {"accuracy": accuracy_score(y_true, y_pred),
            "precision": precision_score(y_true, y_pred, **kw),
            "recall": recall_score(y_true, y_pred, **kw),
            "f1": f1_score(y_true, y_pred, **kw)}


def matriz_confusion(y_true, y_pred) -> np.ndarray:
    return confusion_matrix(y_true, y_pred, labels=[0, 1])


def silhouette(X_escalado, etiquetas) -> float:
    return float(silhouette_score(X_escalado, etiquetas))


def registrar(nombre: str, params: dict, metricas: dict, artefactos: dict = None, modelo_path=None):
    """Un run de MLflow con parámetros, métricas y archivos (modelo, figuras)."""
    with mlflow.start_run(run_name=nombre):
        mlflow.log_params(params)
        mlflow.log_metrics({k: float(v) for k, v in metricas.items()})
        if modelo_path is not None:
            mlflow.log_artifact(str(modelo_path), artifact_path="modelo")
        for ruta in (artefactos or {}).values():
            mlflow.log_artifact(str(ruta), artifact_path="figuras")
