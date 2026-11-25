"""Cola de análisis: corre el detector YOLO del proyecto en un hilo aparte.

La web no espera a que termine un video: guarda el análisis "en cola", el hilo lo
procesa con `src.vision.detector` (el mismo de la app de escritorio) y la página
consulta el estado por /api/analisis/<id>.
"""
import queue
import threading
import time
import traceback
from pathlib import Path

import cv2
import numpy as np

from src.utils.config import RAIZ, cargar_config
from src.utils.s3_helper import subir_resultados
from src.web.db import conectar
from src.web.negocio import ahora_iso

MODELO = RAIZ / "models" / "best.pt"
ANCHO_MINIATURA = 480


def _guardar_jpg(imagen: np.ndarray, ruta: Path, ancho_max: int = None) -> Path:
    h, w = imagen.shape[:2]
    if ancho_max and w > ancho_max:
        imagen = cv2.resize(imagen, (ancho_max, int(h * ancho_max / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", imagen, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError(f"No se pudo guardar {ruta.name}")
    buf.tofile(str(ruta))   # tofile: funciona con tildes y ñ en la ruta (Windows)
    return ruta


def _leer_imagen(ruta: Path):
    datos = np.fromfile(str(ruta), dtype=np.uint8)
    return cv2.imdecode(datos, cv2.IMREAD_COLOR) if datos.size else None


def analizar_con_yolo(tipo: str, entrada: Path, carpeta: Path, sensibilidad: int, linea: int,
                      etiqueta: str, al_progreso) -> dict:
    """Analizador real. Devuelve el dict del detector + rutas de resultado y miniatura."""
    from src.vision.detector import procesar, procesar_imagen   # diferido: torch se carga al analizar

    if not MODELO.exists():
        raise RuntimeError(f"Falta el modelo entrenado: {MODELO.relative_to(RAIZ)}")
    cfg = cargar_config()
    conf = min(max((100 - sensibilidad) / 100, 0.01), 0.99)   # sensibilidad = 100 - confianza

    if tipo == "foto":
        salida = carpeta / "resultado.jpg"
        r = procesar_imagen(str(entrada), str(MODELO), cfg, mostrar=False, lote=etiqueta,
                            guardar=str(salida), conf=conf)
        imagen = _leer_imagen(salida)
        miniatura = _guardar_jpg(imagen, carpeta / "miniatura.jpg", ANCHO_MINIATURA) if imagen is not None else None
        al_progreso(1.0)
        return {**r, "resultado": salida, "miniatura": miniatura}

    cap = cv2.VideoCapture(str(entrada))
    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir el video (formato no soportado o archivo dañado)")
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    ultimo = {}

    def al_frame(n_frame, frame):
        ultimo["frame"] = frame          # el último frame trae el panel con el conteo final
        if total_frames:
            al_progreso(min(n_frame / total_frames, 0.99))
        return False

    salida = carpeta / "resultado.webm"   # WebM: se reproduce directo en el navegador
    r = procesar(str(entrada), str(MODELO), cfg, mostrar=False, csv_salida=carpeta / "metricas.csv",
                 lote=etiqueta, linea=linea / 100, guardar=str(salida), conf=conf, al_frame=al_frame)
    miniatura = (_guardar_jpg(ultimo["frame"], carpeta / "miniatura.jpg", ANCHO_MINIATURA)
                 if "frame" in ultimo else None)
    return {**r, "resultado": salida, "miniatura": miniatura}


def mensaje_para_usuario(error: Exception, entrada: Path) -> str:
    """Texto del error sin rutas del servidor (el detalle completo queda en la consola)."""
    texto = (str(error) or error.__class__.__name__).replace(str(entrada), entrada.name)
    if texto.startswith("No se pudo leer la imagen"):
        return "El archivo no es una imagen válida o está dañado."
    if texto.startswith("No se pudo abrir"):
        return "No se pudo abrir el video: formato no soportado o archivo dañado."
    return texto[:400]


def recalcular_estado_lote(con, lote_id: int) -> None:
    """Estado del lote según sus análisis (no toca lotes aprobados ni rechazados)."""
    lote = con.execute("SELECT estado FROM lotes WHERE id = ?", (lote_id,)).fetchone()
    if lote is None or lote["estado"] in ("aprobado", "rechazado"):
        return
    estados = {r["estado"] for r in con.execute("SELECT estado FROM analisis WHERE lote_id = ?", (lote_id,))}
    if estados & {"en_cola", "procesando"}:
        nuevo = "en_analisis"
    elif "listo" in estados:
        nuevo = "por_aprobar"
    else:
        nuevo = "recepcionado"
    con.execute("UPDATE lotes SET estado = ? WHERE id = ?", (nuevo, lote_id))
    con.commit()


class ColaAnalisis:
    """Un hilo trabajador procesa los análisis en orden (la CPU no se reparte entre videos)."""

    def __init__(self, db_ruta: Path, datos: Path, analizador=analizar_con_yolo, sincrona: bool = False):
        self.db_ruta, self.datos = Path(db_ruta), Path(datos)
        self.analizador, self.sincrona = analizador, sincrona
        self.progreso = {}                       # analisis_id -> 0..1 (solo mientras procesa)
        self._cola = queue.Queue()
        self._hilo = None
        self._candado = threading.Lock()

    def encolar(self, analisis_id: int) -> None:
        if self.sincrona:                        # pruebas: sin hilos
            self.procesar(analisis_id)
            return
        with self._candado:
            if self._hilo is None or not self._hilo.is_alive():
                self._hilo = threading.Thread(target=self._bucle, name="cola-analisis", daemon=True)
                self._hilo.start()
        self._cola.put(analisis_id)

    def reanudar_pendientes(self) -> int:
        """Al iniciar el servidor, vuelve a encolar lo que quedó a medias."""
        con = conectar(self.db_ruta)
        try:
            con.execute("UPDATE analisis SET estado = 'en_cola' WHERE estado = 'procesando'")
            con.commit()
            ids = [r["id"] for r in con.execute("SELECT id FROM analisis WHERE estado = 'en_cola' ORDER BY id")]
        finally:
            con.close()
        for analisis_id in ids:
            self.encolar(analisis_id)
        return len(ids)

    def _bucle(self) -> None:
        while True:
            analisis_id = self._cola.get()
            try:
                self.procesar(analisis_id)
            except Exception:   # noqa: BLE001 - el hilo no debe morir por un análisis
                traceback.print_exc()
            finally:
                self._cola.task_done()

    def _relativa(self, ruta):
        return Path(ruta).relative_to(self.datos).as_posix() if ruta else None

    def procesar(self, analisis_id: int) -> None:
        con = conectar(self.db_ruta)
        try:
            fila = con.execute("""SELECT a.*, l.codigo AS lote_codigo FROM analisis a
                                  LEFT JOIN lotes l ON l.id = a.lote_id WHERE a.id = ?""",
                               (analisis_id,)).fetchone()
            if fila is None or fila["estado"] not in ("en_cola", "procesando"):
                return
            con.execute("UPDATE analisis SET estado = 'procesando' WHERE id = ?", (analisis_id,))
            con.commit()
            self.progreso[analisis_id] = 0.0
            entrada = self.datos / fila["archivo_entrada"]
            inicio = time.perf_counter()
            r = None
            try:
                r = self.analizador(fila["tipo"], entrada, entrada.parent, fila["sensibilidad"],
                                    fila["linea_conteo"] or 50, fila["lote_codigo"] or "Análisis rápido",
                                    lambda p: self.progreso.__setitem__(analisis_id, p))
                cat = r.get("categorias", {})
                con.execute(
                    """UPDATE analisis SET estado = 'listo', total = ?, buena = ?, detalle = ?, no_pasa = ?,
                       pudricion = ?, ids_vistos = ?, archivo_resultado = ?, miniatura = ?, duracion_s = ?,
                       terminado_en = ?, mensaje_error = NULL WHERE id = ?""",
                    (int(r["contadas"]), int(cat.get("good", 0)), int(cat.get("detalle", 0)),
                     int(cat.get("no_pasa", 0)), int(r.get("pudricion", 0)), int(r.get("ids_vistos", 0)),
                     self._relativa(r.get("resultado")), self._relativa(r.get("miniatura")),
                     round(time.perf_counter() - inicio, 2), ahora_iso(), analisis_id))
            except Exception as e:   # noqa: BLE001 - el error se muestra en la página del análisis
                traceback.print_exc()
                con.execute("UPDATE analisis SET estado = 'error', mensaje_error = ?, terminado_en = ? WHERE id = ?",
                            (mensaje_para_usuario(e, entrada), ahora_iso(), analisis_id))
            finally:
                self.progreso.pop(analisis_id, None)
            con.commit()
            if fila["lote_id"]:
                recalcular_estado_lote(con, fila["lote_id"])
            if r is not None and r.get("resultado"):   # respaldo en S3 (sin bucket o sin red: queda local)
                subir_resultados([r.get("resultado"), r.get("miniatura"), Path(r["resultado"]).parent / "metricas.csv"],
                                 f"analisis/{analisis_id}")
        finally:
            con.close()
