"""Optimización de hiperparámetros (Optuna) y ensamble para el modelo tabular.

La validación es leave-one-id-out (equivale a GroupKFold con un ID por pliegue): las filas de
una misma manzana nunca están a la vez en train y test. El objetivo es el F1 de las
predicciones out-of-fold agrupadas.

OJO: el F1 del mejor trial está sesgado al alza (se eligió mirando esos mismos pliegues).
No debe leerse como rendimiento esperado en datos nuevos.
"""
import mlflow
import optuna
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
from xgboost import XGBClassifier

from src.ml.train import SEMILLA

optuna.logging.set_verbosity(optuna.logging.WARNING)


def _rf(params: dict, y=None) -> RandomForestClassifier:
    return RandomForestClassifier(class_weight="balanced", random_state=SEMILLA, **params)


def _xgb(params: dict, y) -> XGBClassifier:
    n_pos = max(int((y == 1).sum()), 1)
    return XGBClassifier(scale_pos_weight=int((y == 0).sum()) / n_pos, eval_metric="logloss",
                         random_state=SEMILLA, **params)


def _espacio_rf(trial) -> dict:
    return {"n_estimators": trial.suggest_int("n_estimators", 50, 400, step=50),
            "max_depth": trial.suggest_int("max_depth", 2, 10),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 10)}


def _espacio_xgb(trial) -> dict:
    return {"max_depth": trial.suggest_int("max_depth", 2, 6),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 400, step=50)}


CONSTRUCTORES = {"random_forest": (_rf, _espacio_rf), "xgboost": (_xgb, _espacio_xgb)}


def f1_cv(modelo, X, y, grupos) -> float:
    pred = cross_val_predict(modelo, X, y, groups=grupos, cv=LeaveOneGroupOut())
    return f1_score(y, pred, zero_division=0)


def optimizar(nombre: str, X, y, grupos, n_trials: int = 25, registrar_mlflow: bool = True):
    """Estudio Optuna (maximiza F1 CV por ID). Cada trial queda como run anidado en MLflow."""
    crear, espacio = CONSTRUCTORES[nombre]

    def objetivo(trial):
        params = espacio(trial)
        valor = f1_cv(crear(params, y), X, y, grupos)
        if registrar_mlflow:
            with mlflow.start_run(run_name=f"{nombre}_trial_{trial.number}", nested=True):
                mlflow.log_params(params)
                mlflow.log_metric("cv_f1", valor)
        return valor

    estudio = optuna.create_study(direction="maximize", study_name=nombre,
                                  sampler=optuna.samplers.TPESampler(seed=SEMILLA))
    if registrar_mlflow:
        with mlflow.start_run(run_name=f"optuna_{nombre}"):
            mlflow.log_param("n_trials", n_trials)
            estudio.optimize(objetivo, n_trials=n_trials)
            mlflow.log_params({f"mejor_{k}": v for k, v in estudio.best_params.items()})
            mlflow.log_metric("mejor_cv_f1", estudio.best_value)
    else:
        estudio.optimize(objetivo, n_trials=n_trials)
    return estudio


def construir(nombre: str, params: dict, y):
    return CONSTRUCTORES[nombre][0](params, y)


def crear_ensamble(params_rf: dict, params_xgb: dict, y, voting: str = "soft") -> VotingClassifier:
    return VotingClassifier([("rf", construir("random_forest", params_rf, y)),
                             ("xgb", construir("xgboost", params_xgb, y))], voting=voting)
