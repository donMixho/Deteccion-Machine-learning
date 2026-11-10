"""Entrenamiento (Random Forest, XGBoost, K-Means).

Validación por grupos (leave-one-id-out): las filas de una misma manzana (`id`) nunca están
a la vez en train y test, porque son observaciones del mismo objeto en distintos frames.
El registro en MLflow está en evaluate.registrar.
"""
import joblib
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.utils.config import RAIZ

MODELOS_DIR = RAIZ / "models"
SEMILLA = 42


def crear_modelos(y) -> dict:
    n_neg, n_pos = int((y == 0).sum()), int((y == 1).sum())
    return {
        "random_forest": RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=2,
                                                class_weight="balanced", random_state=SEMILLA),
        "xgboost": XGBClassifier(n_estimators=100, max_depth=2, learning_rate=0.1,
                                 scale_pos_weight=n_neg / max(n_pos, 1), eval_metric="logloss",
                                 random_state=SEMILLA),
    }


def predecir_por_grupos(modelo, X, y, grupos):
    """Predicciones out-of-fold con leave-one-group-out."""
    return cross_val_predict(modelo, X, y, groups=grupos, cv=LeaveOneGroupOut())


def entrenar_kmeans(X, k: int = 3):
    pipe = make_pipeline(StandardScaler(), KMeans(n_clusters=k, n_init=10, random_state=SEMILLA))
    pipe.fit(X)
    return pipe


def guardar_modelo(modelo, nombre: str):
    MODELOS_DIR.mkdir(exist_ok=True)
    ruta = MODELOS_DIR / f"{nombre}.joblib"
    joblib.dump(modelo, ruta)
    return ruta
