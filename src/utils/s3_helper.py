"""Upload/download a S3 con respaldo local.

Si no hay bucket configurado o S3 falla (p. ej. credenciales del Learner Lab expiradas),
el archivo queda disponible localmente y la función devuelve False/None sin romper el flujo.
"""
import logging
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from src.utils.config import RAIZ, cargar_config

log = logging.getLogger(__name__)
load_dotenv(RAIZ / ".env")


def _cliente():
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )


def subir(ruta_local: str, clave: Optional[str] = None) -> bool:
    """Sube un archivo a S3. El original local siempre se conserva (respaldo)."""
    cfg = cargar_config()
    ruta = Path(ruta_local)
    if not ruta.exists():
        raise FileNotFoundError(ruta)
    if not cfg.s3_bucket:
        log.info("s3_bucket vacío: modo local, no se sube %s", ruta)
        return False
    clave = clave or f"{cfg.s3_prefix}{ruta.name}"
    try:
        _cliente().upload_file(str(ruta), cfg.s3_bucket, clave)
        log.info("Subido %s -> s3://%s/%s", ruta, cfg.s3_bucket, clave)
        return True
    except (BotoCoreError, ClientError) as e:
        log.warning("Falló la subida a S3 (%s). Se mantiene copia local en %s", e, ruta)
        return False


def descargar(clave: str, ruta_local: str) -> Optional[Path]:
    """Descarga desde S3; si falla y existe copia local, devuelve esa copia."""
    cfg = cargar_config()
    destino = Path(ruta_local)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if cfg.s3_bucket:
        try:
            _cliente().download_file(cfg.s3_bucket, clave, str(destino))
            return destino
        except (BotoCoreError, ClientError) as e:
            log.warning("Falló la descarga de S3 (%s)", e)
    if destino.exists():
        log.info("Usando respaldo local %s", destino)
        return destino
    return None
