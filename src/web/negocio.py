"""Reglas del modelo de negocio: roles, planes, cuotas, ingresos y códigos.

Todo lo que define "cómo gana dinero AppleVision" está aquí, separado de las rutas,
para poder cambiar precios o permisos en un solo lugar (ver MODELO_NEGOCIO.md).
"""
import secrets
import string
from datetime import datetime

# ---------------------------------------------------------------- roles
# tipo_empresa: a qué clase de empresa pertenece un usuario con ese rol
ROLES = {
    "admin": {"nombre": "Administrador", "tipo_empresa": "plataforma",
              "descripcion": "Equipo AppleVision: empresas, usuarios, planes y métricas del negocio."},
    "jefe_planta": {"nombre": "Jefe de planta", "tipo_empresa": "packing",
                    "descripcion": "Valida el conteo, aprueba lotes, emite certificados y gestiona operadores."},
    "operador": {"nombre": "Operador de línea", "tipo_empresa": "packing",
                 "descripcion": "Recibe lotes y sube la foto o el video de la línea para analizarlos."},
    "productor": {"nombre": "Productor", "tipo_empresa": "productor",
                  "descripcion": "Ve sus lotes con evidencia y hace análisis rápidos de fotos."},
    "exportador": {"nombre": "Exportadora", "tipo_empresa": "exportadora",
                   "descripcion": "Ve los lotes certificados de sus proveedores y verifica certificados."},
}

TIPOS_EMPRESA = {
    "plataforma": "Plataforma",
    "packing": "Packing",
    "productor": "Productor",
    "exportadora": "Exportadora",
}

# ---------------------------------------------------------------- planes
# precio en CLP + IVA (supuestos del modelo de negocio). cuota_fotos=None -> ilimitado.
PLANES = {
    "interno": {"nombre": "Interno", "tipo_empresa": "plataforma", "precio": 0, "unidad": "",
                "cuota_fotos": None, "video": True, "csv": True, "publico": False},
    "productor_basico": {"nombre": "Productor Básico", "tipo_empresa": "productor", "precio": 0,
                         "unidad": "/ mes", "cuota_fotos": 10, "video": False, "csv": False, "publico": True},
    "productor_pro": {"nombre": "Productor Pro", "tipo_empresa": "productor", "precio": 9990,
                      "unidad": "/ mes", "cuota_fotos": 300, "video": False, "csv": True, "publico": True},
    "packing": {"nombre": "Packing", "tipo_empresa": "packing", "precio": 290000,
                "unidad": "/ mes por línea", "cuota_fotos": None, "video": True, "csv": True,
                "instalacion": 1500000, "publico": True},
    "exportadora": {"nombre": "Exportadora", "tipo_empresa": "exportadora", "precio": 190000,
                    "unidad": "/ mes", "cuota_fotos": None, "video": False, "csv": True, "publico": True},
}

BENEFICIOS = {
    "productor_basico": ["Reportes de todos sus lotes", "10 análisis rápidos de foto al mes",
                         "Verificación de certificados"],
    "productor_pro": ["Todo lo del plan Básico", "300 análisis de foto al mes", "Descarga de reportes CSV"],
    "packing": ["Análisis de video y foto ilimitado", "Panel de planta y validación de conteo",
                "Certificados verificables por lote", "Usuarios ilimitados (jefes y operadores)"],
    "exportadora": ["Lotes certificados de sus proveedores", "Consolidado por variedad y packing",
                    "Verificación y descarga CSV"],
}

IVA = 0.19
DIAS_PLAN = 30          # vigencia de un plan pagado con Webpay


def con_iva(neto: int) -> dict:
    """Desglose en pesos enteros (Webpay cobra CLP sin decimales)."""
    iva = round(neto * IVA)
    return {"neto": neto, "iva": iva, "total": neto + iva}


VARIEDADES = ["Gala", "Fuji", "Cripps Pink", "Granny Smith", "Red Delicious", "Braeburn"]

# ---------------------------------------------------------------- estados
ESTADOS_LOTE = {
    "recepcionado": "Recepcionado",
    "en_analisis": "En análisis",
    "por_aprobar": "Por aprobar",
    "aprobado": "Aprobado",
    "rechazado": "Rechazado",
}
ESTADOS_ANALISIS = {"en_cola": "En cola", "procesando": "Procesando", "listo": "Listo", "error": "Error"}

CATEGORIAS = [  # (clave en la BD, nombre visible, clase css)
    ("buena", "Buena", "buena"),
    ("detalle", "Con detalle", "detalle"),
    ("no_pasa", "No pasa", "nopasa"),
]

# Sensibilidad = 100 - confianza mínima del detector. "normal" replica los valores por
# defecto de src/vision/detector.py (CONF_FOTO_DEFAULT = 0.35, CONF_DEFAULT = 0.18).
SENSIBILIDADES = {
    "foto": {"baja": 50, "normal": 65, "alta": 75},
    "video": {"baja": 70, "normal": 82, "alta": 88},
}
NIVELES_SENSIBILIDAD = {
    "normal": "Normal (recomendada)",
    "alta": "Alta: detecta más, puede contar de más",
    "baja": "Baja: solo detecciones muy seguras",
}
LINEA_CONTEO_DEFECTO = 50   # % del ancho del video donde se cuenta el cruce

EXT_FOTO = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
EXT_VIDEO = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm"}


def tipo_archivo(nombre: str):
    """'foto', 'video' o None según la extensión."""
    ext = ("." + nombre.rsplit(".", 1)[-1].lower()) if "." in nombre else ""
    if ext in EXT_FOTO:
        return "foto"
    if ext in EXT_VIDEO:
        return "video"
    return None


def planes_para(tipo_empresa: str) -> dict:
    return {k: v for k, v in PLANES.items() if v["tipo_empresa"] == tipo_empresa}


def ingreso_mensual(plan: str, lineas: int = 1) -> int:
    """Ingreso recurrente mensual (MRR) de una empresa según su plan."""
    datos = PLANES.get(plan)
    if not datos:
        return 0
    return datos["precio"] * (max(int(lineas or 1), 1) if plan == "packing" else 1)


def porcentaje(parte, total) -> float:
    return round(100.0 * (parte or 0) / total, 1) if total else 0.0


def inicio_mes(ahora: datetime = None) -> str:
    ahora = ahora or datetime.now()
    return ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def ahora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


_ALFABETO = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL")


def nuevo_certificado(anio: int = None) -> str:
    """Código de certificado legible y difícil de adivinar: AV-2026-7KQ3XD."""
    anio = anio or datetime.now().year
    return f"AV-{anio}-" + "".join(secrets.choice(_ALFABETO) for _ in range(6))


def codigo_lote(lote_id: int, anio: int = None) -> str:
    return f"L-{anio or datetime.now().year}-{lote_id:04d}"


def puede_ver_lote(usuario, lote) -> bool:
    """Regla de acceso a un lote según el rol (el admin ve todo, como soporte)."""
    if usuario is None or lote is None:
        return False
    rol, empresa = usuario["rol"], usuario["empresa_id"]
    if rol == "admin":
        return True
    if rol in ("jefe_planta", "operador"):
        return lote["packing_id"] == empresa
    if rol == "productor":
        return lote["productor_id"] == empresa
    if rol == "exportador":
        return lote["exportadora_id"] == empresa and lote["estado"] == "aprobado"
    return False
