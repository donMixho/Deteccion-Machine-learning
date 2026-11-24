"""Datos de demostración: empresas, una cuenta por rol y lotes analizados con el modelo REAL.

Las fotos salen de images/test (dataset del proyecto) y el "conteo manual" de los lotes
aprobados es el número de manzanas etiquetadas en esas fotos: así el error de conteo
que muestra la plataforma es un error real del modelo, no un número inventado.
"""
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import cv2

from src.utils.config import RAIZ
from src.web.analisis import ColaAnalisis, recalcular_estado_lote
from src.web.db import conectar
from src.web.negocio import SENSIBILIDADES, codigo_lote, nuevo_certificado
from werkzeug.security import generate_password_hash

CLAVE_DEMO = "demo1234"
TEST = RAIZ / "images" / "test"

# Una cuenta por rol (las muestra la pantalla de ingreso en modo demo)
CUENTAS_DEMO = {
    "admin": {"email": "admin@applevision.demo", "nombre": "Camila Rojas", "empresa": "AppleVision Chile"},
    "jefe_planta": {"email": "jefe@losrobles.demo", "nombre": "Jorge Muñoz", "empresa": "Packing Los Robles"},
    "operador": {"email": "operador@losrobles.demo", "nombre": "Daniela Soto", "empresa": "Packing Los Robles"},
    "productor": {"email": "productor@elmanzano.demo", "nombre": "Pedro Fuentes", "empresa": "Agrícola El Manzano"},
    "exportador": {"email": "comercial@andesfruit.demo", "nombre": "Valentina Díaz",
                   "empresa": "Exportadora Andes Fruit"},
}
OTRAS_CUENTAS = [  # para mostrar que cada empresa ve solo lo suyo y el flujo de cambio de plan
    {"rol": "productor", "email": "productor@santarosa.demo", "nombre": "Rosa Pérez", "empresa": "Agrícola Santa Rosa"},
]

EMPRESAS = [  # (nombre, tipo, plan, líneas, región)
    ("AppleVision Chile", "plataforma", "interno", 1, "Metropolitana"),
    ("Packing Los Robles", "packing", "packing", 2, "Maule"),
    ("Packing Valle Verde", "packing", "packing", 3, "O'Higgins"),
    ("Agrícola El Manzano", "productor", "productor_pro", 1, "Maule"),
    ("Agrícola Santa Rosa", "productor", "productor_basico", 1, "Maule"),
    ("Agrícola Los Aromos", "productor", "productor_pro", 1, "O'Higgins"),
    ("Exportadora Andes Fruit", "exportadora", "exportadora", 1, "Metropolitana"),
    ("Exportadora Pacífico Sur", "exportadora", "exportadora", 1, "Valparaíso"),
]

# Lotes de Packing Los Robles: (días atrás, productor, exportadora, variedad, línea, bins, archivos, estado final)
# "VIDEO" = video armado con los 61 frames consecutivos de cinta del dataset 1 (dominio público).
LOTES = [
    (12, "Agrícola El Manzano", "Exportadora Andes Fruit", "Gala", 1, 18, ["as_apple--149-", "as_apple--120-"], "aprobado"),
    (11, "Agrícola Santa Rosa", "Exportadora Andes Fruit", "Fuji", 2, 12, ["as_apple--137-", "mp4-0007_"], "aprobado"),
    (9, "Agrícola El Manzano", "Exportadora Andes Fruit", "Cripps Pink", 1, 20, ["as_apple--174-", "as_apple--1-"], "aprobado"),
    (8, "Agrícola Los Aromos", "Exportadora Pacífico Sur", "Braeburn", 2, 15, ["as_apple--179-", "as_apple--17-"], "aprobado"),
    (6, "Agrícola El Manzano", "Exportadora Andes Fruit", "Fuji", 1, 22, ["VIDEO"], "aprobado"),
    (4, "Agrícola Santa Rosa", "Exportadora Andes Fruit", "Gala", 2, 10, ["as_apple--148-"], "rechazado"),
    (2, "Agrícola El Manzano", "Exportadora Andes Fruit", "Red Delicious", 1, 16, ["as_apple--156-", "as_apple--129-"], "por_aprobar"),
    (1, "Agrícola Los Aromos", "Exportadora Andes Fruit", "Gala", 2, 14, ["mp4-0018_", "as_apple--13-"], "por_aprobar"),
    (0, "Agrícola El Manzano", "Exportadora Andes Fruit", "Fuji", 1, 8, [], "recepcionado"),
]
ANALISIS_RAPIDOS = [  # (empresa, días atrás, foto)
    ("Agrícola El Manzano", 5, "as_apple--159-"),
    ("Agrícola El Manzano", 1, "as_apple--113-"),
    ("Agrícola Santa Rosa", 7, "as_apple--178-"),
    ("Agrícola Santa Rosa", 3, "as_apple--176-"),
    ("Agrícola Santa Rosa", 2, "as_apple--173-"),
]


def _foto_test(prefijo: str) -> Path:
    candidatas = sorted((TEST / "images").glob(f"*{prefijo}*.jpg"))
    if not candidatas:
        raise FileNotFoundError(f"No se encontró la imagen de prueba {prefijo} en {TEST / 'images'}")
    return candidatas[0]


def etiquetas_en(foto: Path) -> int:
    """Manzanas etiquetadas en la foto (verdad de terreno del dataset)."""
    etiqueta = TEST / "labels" / (foto.stem + ".txt")
    if not etiqueta.exists():
        return 0
    return sum(1 for linea in etiqueta.read_text(encoding="utf-8").splitlines() if linea.strip())


def video_cinta_demo(destino: Path, fps: int = 8):
    """Arma un video con los frames consecutivos de cinta (images/*/images/apple-conveyor_horz_mp4-*)."""
    rutas = sorted(RAIZ.glob("images/*/images/apple-conveyor_horz_mp4-*_jpg*.jpg"),
                   key=lambda p: int(re.search(r"mp4-(\d+)_jpg", p.name).group(1)))
    if not rutas:
        return None
    primero = cv2.imread(str(rutas[0]))
    alto, ancho = primero.shape[:2]
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritor = cv2.VideoWriter(str(destino), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ancho, alto))
    for ruta in rutas:
        frame = cv2.imread(str(ruta))
        if frame is not None and frame.shape[:2] == (alto, ancho):
            escritor.write(frame)
    escritor.release()
    return destino


def reiniciar(datos: Path) -> None:
    """Borra la base y los archivos de la plataforma (solo dentro de la carpeta de datos)."""
    for nombre in ("applevision.db", "applevision.db-wal", "applevision.db-shm"):
        (datos / nombre).unlink(missing_ok=True)
    shutil.rmtree(datos / "analisis", ignore_errors=True)


def sembrar(db_ruta: Path, datos: Path, analizador=None, avisar=print) -> bool:
    """Crea los datos de demostración si la base no tiene usuarios. `analizador=None` omite los análisis."""
    con = conectar(db_ruta)
    try:
        if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
            return False
        ahora = datetime.now().replace(second=0, microsecond=0)
        iso = lambda f: f.isoformat(timespec="seconds")   # noqa: E731

        empresas = {}
        for nombre, tipo, plan, lineas, region in EMPRESAS:
            cur = con.execute("""INSERT INTO empresas (nombre, tipo, plan, lineas, region, creada_en)
                                 VALUES (?, ?, ?, ?, ?, ?)""",
                              (nombre, tipo, plan, lineas, region, iso(ahora - timedelta(days=60))))
            empresas[nombre] = cur.lastrowid

        clave = generate_password_hash(CLAVE_DEMO)
        usuarios = {}
        cuentas = [{"rol": rol, **datos_cuenta} for rol, datos_cuenta in CUENTAS_DEMO.items()] + OTRAS_CUENTAS
        for c in cuentas:
            cur = con.execute("""INSERT INTO usuarios (nombre, email, clave_hash, rol, empresa_id, creado_en)
                                 VALUES (?, ?, ?, ?, ?, ?)""",
                              (c["nombre"], c["email"], clave, c["rol"], empresas[c["empresa"]],
                               iso(ahora - timedelta(days=45))))
            usuarios[c["email"]] = cur.lastrowid
        con.commit()

        cola = ColaAnalisis(db_ruta, datos, analizador=analizador, sincrona=True) if analizador else None
        operador, jefe = usuarios[CUENTAS_DEMO["operador"]["email"]], usuarios[CUENTAS_DEMO["jefe_planta"]["email"]]
        packing = empresas["Packing Los Robles"]

        def analizar(archivo: Path, lote_id, empresa_id, usuario_id, momento: datetime, nombre: str):
            tipo = "video" if archivo.suffix == ".mp4" else "foto"
            carpeta_id = uuid.uuid4().hex
            carpeta = datos / "analisis" / carpeta_id
            carpeta.mkdir(parents=True)
            if archivo.parent != carpeta:
                shutil.copyfile(archivo, carpeta / f"entrada{archivo.suffix}")
            cur = con.execute(
                """INSERT INTO analisis (lote_id, empresa_id, usuario_id, tipo, nombre_archivo, archivo_entrada,
                                         sensibilidad, linea_conteo, creado_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (lote_id, empresa_id, usuario_id, tipo, nombre,
                 f"analisis/{carpeta_id}/entrada{archivo.suffix}", SENSIBILIDADES[tipo]["normal"],
                 50 if tipo == "video" else None, iso(momento)))
            con.commit()
            cola.procesar(cur.lastrowid)
            con.execute("UPDATE analisis SET creado_en = ?, terminado_en = ? WHERE id = ?",
                        (iso(momento), iso(momento + timedelta(minutes=1)), cur.lastrowid))
            con.commit()

        for i, (dias, productor, exportadora, variedad, linea, bins, archivos, estado) in enumerate(LOTES, start=1):
            momento = (ahora - timedelta(days=dias)).replace(hour=8 + i % 9, minute=(i * 13) % 60)
            cur = con.execute(
                """INSERT INTO lotes (codigo, packing_id, productor_id, exportadora_id, variedad, bins, linea,
                                      creado_por, creado_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uuid.uuid4().hex, packing, empresas[productor], empresas[exportadora], variedad, bins, linea,
                 operador, iso(momento)))
            lote_id = cur.lastrowid
            con.execute("UPDATE lotes SET codigo = ? WHERE id = ?",
                        (codigo_lote(lote_id, momento.year), lote_id))
            con.commit()
            avisar(f"  Lote {i}/{len(LOTES)} ({variedad}, {len(archivos)} archivo(s))...")

            manual = 0
            if cola:
                for k, nombre in enumerate(archivos):
                    if nombre == "VIDEO":
                        carpeta = datos / "analisis" / "_video_demo"
                        carpeta.mkdir(parents=True, exist_ok=True)
                        video = video_cinta_demo(carpeta / "cinta_demo.mp4")
                        if video is None:
                            continue
                        analizar(video, lote_id, packing, operador, momento + timedelta(minutes=5 + k),
                                 f"cinta_linea{linea}.mp4")
                        shutil.rmtree(carpeta, ignore_errors=True)
                        manual = None   # sin conteo manual de referencia para el video
                    else:
                        foto = _foto_test(nombre)
                        analizar(foto, lote_id, packing, operador, momento + timedelta(minutes=5 + k),
                                 f"linea{linea}_bin{k + 1}.jpg")
                        if manual is not None:
                            manual += etiquetas_en(foto)
                recalcular_estado_lote(con, lote_id)

            revisado = iso(momento + timedelta(hours=2))
            if estado == "aprobado" and cola:
                con.execute("""UPDATE lotes SET estado = 'aprobado', certificado = ?, conteo_manual = ?,
                               observacion = ?, revisado_por = ?, revisado_en = ? WHERE id = ?""",
                            (nuevo_certificado(momento.year), manual or None,
                             "Conteo manual = manzanas etiquetadas en las fotos del lote." if manual else None,
                             jefe, revisado, lote_id))
            elif estado == "rechazado" and cola:
                con.execute("""UPDATE lotes SET estado = 'rechazado', observacion = ?, revisado_por = ?,
                               revisado_en = ? WHERE id = ?""",
                            ("Foto tomada con poca luz y fruta apilada: repetir con el lote en la cinta.",
                             jefe, revisado, lote_id))
            con.commit()

        if cola:
            for n, (empresa, dias, nombre) in enumerate(ANALISIS_RAPIDOS, start=1):
                usuario = next(usuarios[c["email"]] for c in cuentas if c["empresa"] == empresa)
                avisar(f"  Análisis rápido de {empresa}...")
                analizar(_foto_test(nombre), None, empresas[empresa], usuario,
                         (ahora - timedelta(days=dias)).replace(hour=17, minute=30), f"foto_bin_{n}.jpg")

        con.execute("""INSERT INTO solicitudes (empresa_id, usuario_id, plan_solicitado, creada_en)
                       VALUES (?, ?, 'productor_pro', ?)""",
                    (empresas["Agrícola Santa Rosa"], usuarios["productor@santarosa.demo"],
                     iso(ahora - timedelta(hours=20))))
        con.commit()
        return True
    finally:
        con.close()


if __name__ == "__main__":
    # python -m src.web.demo [destino.mp4]  ->  video de prueba de la cinta (por defecto reports/cinta_demo.mp4)
    import sys
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "reports" / "cinta_demo.mp4"
    video = video_cinta_demo(destino)
    print(f"Video de prueba: {video}" if video else "No se encontraron los frames de cinta en images/*/images/")
