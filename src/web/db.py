"""Base de datos SQLite de la plataforma (sin dependencias extra).

Una conexión por petición (flask.g). El hilo de análisis abre la suya con `conectar`.
"""
import sqlite3
from pathlib import Path

from flask import current_app, g

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('plataforma','packing','productor','exportadora')),
    rut         TEXT,
    region      TEXT,
    plan        TEXT NOT NULL,
    lineas      INTEGER NOT NULL DEFAULT 1,
    activa      INTEGER NOT NULL DEFAULT 1,
    creada_en   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre        TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    clave_hash    TEXT NOT NULL,
    rol           TEXT NOT NULL CHECK (rol IN ('admin','jefe_planta','operador','productor','exportador')),
    empresa_id    INTEGER NOT NULL REFERENCES empresas(id),
    activo        INTEGER NOT NULL DEFAULT 1,
    creado_en     TEXT NOT NULL,
    ultimo_acceso TEXT
);
CREATE TABLE IF NOT EXISTS lotes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo         TEXT NOT NULL UNIQUE,
    packing_id     INTEGER NOT NULL REFERENCES empresas(id),
    productor_id   INTEGER NOT NULL REFERENCES empresas(id),
    exportadora_id INTEGER REFERENCES empresas(id),
    variedad       TEXT NOT NULL,
    bins           INTEGER,
    linea          INTEGER NOT NULL DEFAULT 1,
    estado         TEXT NOT NULL DEFAULT 'recepcionado'
                   CHECK (estado IN ('recepcionado','en_analisis','por_aprobar','aprobado','rechazado')),
    conteo_manual  INTEGER,
    observacion    TEXT,
    certificado    TEXT UNIQUE,
    creado_por     INTEGER NOT NULL REFERENCES usuarios(id),
    revisado_por   INTEGER REFERENCES usuarios(id),
    creado_en      TEXT NOT NULL,
    revisado_en    TEXT
);
CREATE TABLE IF NOT EXISTS analisis (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id           INTEGER REFERENCES lotes(id),
    empresa_id        INTEGER NOT NULL REFERENCES empresas(id),
    usuario_id        INTEGER NOT NULL REFERENCES usuarios(id),
    tipo              TEXT NOT NULL CHECK (tipo IN ('foto','video')),
    nombre_archivo    TEXT NOT NULL,
    archivo_entrada   TEXT NOT NULL,
    archivo_resultado TEXT,
    miniatura         TEXT,
    estado            TEXT NOT NULL DEFAULT 'en_cola' CHECK (estado IN ('en_cola','procesando','listo','error')),
    mensaje_error     TEXT,
    sensibilidad      INTEGER NOT NULL,
    linea_conteo      INTEGER,
    total INTEGER, buena INTEGER, detalle INTEGER, no_pasa INTEGER, pudricion INTEGER, ids_vistos INTEGER,
    duracion_s        REAL,
    creado_en         TEXT NOT NULL,
    terminado_en      TEXT
);
CREATE TABLE IF NOT EXISTS solicitudes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id      INTEGER NOT NULL REFERENCES empresas(id),
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    plan_solicitado TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','aprobada','rechazada')),
    creada_en       TEXT NOT NULL,
    resuelta_en     TEXT
);
CREATE INDEX IF NOT EXISTS ix_lotes_packing ON lotes(packing_id, creado_en);
CREATE INDEX IF NOT EXISTS ix_lotes_productor ON lotes(productor_id);
CREATE INDEX IF NOT EXISTS ix_lotes_exportadora ON lotes(exportadora_id, estado);
CREATE INDEX IF NOT EXISTS ix_analisis_lote ON analisis(lote_id);
CREATE INDEX IF NOT EXISTS ix_analisis_empresa ON analisis(empresa_id, creado_en);

-- Lote + nombres de las empresas + suma de sus análisis terminados
CREATE VIEW IF NOT EXISTS v_lotes AS
SELECT l.*,
       k.nombre AS packing_nombre,
       p.nombre AS productor_nombre,
       x.nombre AS exportadora_nombre,
       COUNT(a.id)                 AS n_analisis,
       COALESCE(SUM(a.total), 0)   AS total,
       COALESCE(SUM(a.buena), 0)   AS buena,
       COALESCE(SUM(a.detalle), 0) AS detalle,
       COALESCE(SUM(a.no_pasa), 0) AS no_pasa,
       COALESCE(SUM(a.pudricion), 0) AS pudricion,
       (SELECT a2.id FROM analisis a2 WHERE a2.lote_id = l.id AND a2.miniatura IS NOT NULL
        ORDER BY a2.id DESC LIMIT 1) AS ultimo_analisis_id
FROM lotes l
JOIN empresas k ON k.id = l.packing_id
JOIN empresas p ON p.id = l.productor_id
LEFT JOIN empresas x ON x.id = l.exportadora_id
LEFT JOIN analisis a ON a.lote_id = l.id AND a.estado = 'listo'
GROUP BY l.id;
"""


def conectar(ruta: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(ruta), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def inicializar(ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = conectar(ruta)
    try:
        con.execute("PRAGMA journal_mode = WAL")   # lecturas mientras el hilo de análisis escribe
        con.executescript(ESQUEMA)
        con.commit()
    finally:
        con.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = conectar(current_app.config["DB_RUTA"])
    return g.db


def cerrar_db(_exc=None) -> None:
    con = g.pop("db", None)
    if con is not None:
        con.close()


def uno(sql: str, params=()):
    return get_db().execute(sql, params).fetchone()


def todos(sql: str, params=()):
    return get_db().execute(sql, params).fetchall()


def valor(sql: str, params=(), defecto=0):
    fila = get_db().execute(sql, params).fetchone()
    return defecto if fila is None or fila[0] is None else fila[0]


def ejecutar(sql: str, params=()) -> int:
    con = get_db()
    cur = con.execute(sql, params)
    con.commit()
    return cur.lastrowid
