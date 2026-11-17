"""Pantalla de inicio (dashboard) de AppleVision Chile.

Tres bloques: 1) fuente de entrada (cámara, video o foto), 2) parámetros y calibración
de la escala de la cámara, 3) ejecución y último resultado.

    python -m src.app
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np

from src.utils.config import RAIZ, cargar_config, guardar_px_por_mm
from src.vision.calibrador import calibrar_escala
from src.vision.detector import CONF_DEFAULT, medir_referencia, procesar, procesar_imagen

MODELO = RAIZ / "models" / "best.pt"
CARPETA_REPORTES = RAIZ / "reports"
DIAMETRO_REFERENCIA_MM = 72.0   # manzana estándar de exportación, si no se mide otra

# Paleta (coincide con el panel en vivo)
FONDO, TARJETA, BORDE = "#141414", "#1e1e1e", "#333333"
TEXTO, TEXTO_SUAVE = "#eaeaea", "#9a9a9a"
VERDE, NARANJA, ROJO, AZUL = "#2ecc71", "#f59e0b", "#e74c3c", "#3182ce"


class Tooltip:
    """Texto de ayuda que aparece al pasar el mouse sobre un control."""

    def __init__(self, widget, texto: str) -> None:
        self.widget, self.texto, self.ventana = widget, texto, None
        widget.bind("<Enter>", self._mostrar, add="+")
        widget.bind("<Leave>", self._ocultar, add="+")

    def _mostrar(self, _evento=None) -> None:
        if self.ventana:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.ventana = tk.Toplevel(self.widget)
        self.ventana.wm_overrideredirect(True)
        self.ventana.wm_geometry(f"+{x}+{y}")
        tk.Label(self.ventana, text=self.texto, bg="#2b2b2b", fg=TEXTO, font=("Segoe UI", 9),
                 justify="left", wraplength=320, padx=8, pady=5, relief="solid", bd=1).pack()

    def _ocultar(self, _evento=None) -> None:
        if self.ventana:
            self.ventana.destroy()
            self.ventana = None


class App:
    def __init__(self) -> None:
        self.cfg = cargar_config()
        self.root = tk.Tk()
        self.root.title("AppleVision Chile")
        self.root.configure(bg=FONDO)
        self.root.geometry("740x920")
        self.root.minsize(680, 860)

        self.fuente = tk.StringVar(value="camara")
        self.indice_cam = tk.IntVar(value=0)
        self.ruta_video = tk.StringVar(value="")
        self.ruta_foto = tk.StringVar(value="")
        self.lote = tk.StringVar(value="Lote 1")
        self.linea = tk.IntVar(value=80)
        # Sensibilidad = 100 - confianza mínima: más alto detecta más (incluye manzanas inclinadas)
        self.sensibilidad = tk.IntVar(value=100 - round(CONF_DEFAULT * 100))
        self.guardar = tk.BooleanVar(value=False)
        self.estado = tk.StringVar(value="Listo para iniciar")
        self.aviso_fuente = tk.StringVar(value="")
        self.texto_escala = tk.StringVar(value="")
        self.resultado = {k: tk.StringVar(value="—")
                          for k in ("total", "good", "detalle", "no_pasa", "pudricion", "ids")}

        self._estilos()
        self._construir()
        for var in (self.fuente, self.ruta_video, self.ruta_foto, self.indice_cam):
            var.trace_add("write", lambda *_: self._actualizar_aviso())
        self._actualizar_aviso()
        self._actualizar_escala()

    # ---------- estilos y piezas ----------
    def _estilos(self) -> None:
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("TFrame", background=FONDO)
        st.configure("Card.TFrame", background=TARJETA)
        st.configure("TLabel", background=TARJETA, foreground=TEXTO, font=("Segoe UI", 10))
        st.configure("Suave.TLabel", background=TARJETA, foreground=TEXTO_SUAVE, font=("Segoe UI", 9))
        st.configure("TRadiobutton", background=TARJETA, foreground=TEXTO, font=("Segoe UI", 11, "bold"),
                     focuscolor=TARJETA)
        st.map("TRadiobutton", background=[("active", TARJETA)])
        st.configure("TCheckbutton", background=TARJETA, foreground=TEXTO, font=("Segoe UI", 10))
        st.map("TCheckbutton", background=[("active", TARJETA)])
        st.configure("TButton", font=("Segoe UI", 10), padding=6, background="#2a2a2a", foreground=TEXTO,
                     bordercolor=BORDE)
        st.map("TButton", background=[("active", "#3a3a3a")])
        st.configure("Calibrar.TButton", font=("Segoe UI", 10, "bold"), padding=6, background=AZUL,
                     foreground="white")
        st.map("Calibrar.TButton", background=[("active", "#2b6cb0")])
        st.configure("Inicio.TButton", font=("Segoe UI", 13, "bold"), padding=12, background=VERDE,
                     foreground="#0b2e1a")
        st.map("Inicio.TButton", background=[("active", "#27ae60")])
        st.configure("TEntry", fieldbackground="#2a2a2a", foreground=TEXTO, bordercolor=BORDE, insertcolor=TEXTO)
        st.configure("TSpinbox", fieldbackground="#2a2a2a", foreground=TEXTO, arrowcolor=TEXTO)
        st.configure("Horizontal.TScale", background=TARJETA, troughcolor="#2a2a2a")

    def _tarjeta(self, padre, titulo: str, subtitulo: str = "") -> ttk.Frame:
        marco = tk.Frame(padre, bg=TARJETA, highlightbackground=BORDE, highlightthickness=1)
        marco.pack(fill="x", pady=7)
        cab = tk.Frame(marco, bg=TARJETA)
        cab.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(cab, text=titulo, bg=TARJETA, fg=TEXTO, font=("Segoe UI", 11, "bold")).pack(side="left")
        if subtitulo:
            tk.Label(cab, text=subtitulo, bg=TARJETA, fg=TEXTO_SUAVE, font=("Segoe UI", 9)
                     ).pack(side="left", padx=10)
        interior = ttk.Frame(marco, style="Card.TFrame")
        interior.pack(fill="x", padx=16, pady=(0, 14))
        return interior

    def _construir(self) -> None:
        cont = ttk.Frame(self.root)
        cont.pack(fill="both", expand=True, padx=26, pady=16)

        tk.Label(cont, text="AppleVision Chile", bg=FONDO, fg=TEXTO, font=("Segoe UI", 22, "bold")
                 ).pack(anchor="w")
        tk.Label(cont, text="Conteo y clasificación de manzanas en la línea de embalaje", bg=FONDO,
                 fg=TEXTO_SUAVE, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 6))

        self._bloque_fuente(cont)
        self._bloque_parametros(cont)
        self._bloque_ejecucion(cont)

    def _bloque_fuente(self, cont) -> None:
        t1 = self._tarjeta(cont, "1 · Fuente de entrada", "¿De dónde vienen las imágenes?")
        fila_cam = ttk.Frame(t1, style="Card.TFrame")
        fila_cam.pack(fill="x", pady=(0, 8))
        ttk.Radiobutton(fila_cam, text="Cámara conectada", value="camara", variable=self.fuente
                        ).pack(side="left")
        b = ttk.Button(fila_cam, text="Probar cámara", command=self._probar_camara)
        b.pack(side="right")
        Tooltip(b, "Abre la cámara un instante para comprobar que funciona.")
        sp = ttk.Spinbox(fila_cam, from_=0, to=9, width=4, textvariable=self.indice_cam)
        sp.pack(side="right", padx=8)
        Tooltip(sp, "0 = cámara integrada. Si tienes una cámara USB, prueba con 1 o 2.")
        ttk.Label(fila_cam, text="N.º de cámara", style="Suave.TLabel").pack(side="right")

        fila_vid = ttk.Frame(t1, style="Card.TFrame")
        fila_vid.pack(fill="x")
        ttk.Radiobutton(fila_vid, text="Video del equipo", value="video", variable=self.fuente
                        ).pack(side="left")
        ttk.Button(fila_vid, text="Elegir video…", command=self._elegir_video).pack(side="right")
        ttk.Entry(t1, textvariable=self.ruta_video, state="readonly").pack(fill="x", pady=(6, 0))

        fila_foto = ttk.Frame(t1, style="Card.TFrame")
        fila_foto.pack(fill="x", pady=(10, 0))
        ttk.Radiobutton(fila_foto, text="Foto del equipo", value="foto", variable=self.fuente
                        ).pack(side="left")
        ttk.Button(fila_foto, text="Elegir foto…", command=self._elegir_foto).pack(side="right")
        ttk.Entry(t1, textvariable=self.ruta_foto, state="readonly").pack(fill="x", pady=(6, 0))

        self.lbl_aviso = tk.Label(t1, textvariable=self.aviso_fuente, bg=TARJETA, fg=NARANJA,
                                  font=("Segoe UI", 10, "bold"), anchor="w")
        self.lbl_aviso.pack(fill="x", pady=(10, 0))

    def _bloque_parametros(self, cont) -> None:
        t2 = self._tarjeta(cont, "2 · Parámetros y calibración")
        fila = ttk.Frame(t2, style="Card.TFrame")
        fila.pack(fill="x", pady=(0, 8))
        ttk.Label(fila, text="Nombre del lote", width=30).pack(side="left")
        ttk.Entry(fila, textvariable=self.lote).pack(side="left", fill="x", expand=True)

        self._slider(t2, "Posición línea de conteo (% del ancho)", self.linea, 10, 95,
                     "Dónde se dibuja la línea vertical que cuenta las manzanas al cruzarla.\n"
                     "0 % = borde izquierdo, 100 % = borde derecho. Recomendado: 50–80 %.")
        self._slider(t2, "Sensibilidad de detección (%)", self.sensibilidad, 10, 95,
                     "Más alto = detecta más manzanas (también inclinadas o semiocultas), "
                     "pero puede marcar objetos que no son fruta.\nMás bajo = solo detecciones muy seguras. "
                     f"Recomendado: {100 - round(CONF_DEFAULT * 100)} %.")

        fila_cal = ttk.Frame(t2, style="Card.TFrame")
        fila_cal.pack(fill="x", pady=(10, 4))
        ttk.Label(fila_cal, text="Escala de la cámara", width=30).pack(side="left")
        tk.Label(fila_cal, textvariable=self.texto_escala, bg=TARJETA, fg=AZUL,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        b = ttk.Button(fila_cal, text="📏  Calibrar cámara / escala…", style="Calibrar.TButton",
                       command=self._dialogo_calibrar)
        b.pack(side="right")
        Tooltip(b, "Convierte píxeles a milímetros para medir el calibre (65–80 mm).\n"
                   "Pon una manzana de diámetro conocido frente a la cámara y mídela.\n"
                   "Repetir si se mueve la cámara o cambia su altura.")

        ttk.Checkbutton(t2, text="Guardar el video/foto con el panel en la carpeta reports/",
                        variable=self.guardar).pack(anchor="w", pady=(8, 0))

    def _bloque_ejecucion(self, cont) -> None:
        t3 = self._tarjeta(cont, "3 · Ejecución")
        if not MODELO.exists():
            tk.Label(t3, text=f"⚠ Falta el modelo entrenado: {MODELO.relative_to(RAIZ)}", bg=TARJETA, fg=ROJO,
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 8))
        ttk.Button(t3, text="▶  Iniciar análisis", style="Inicio.TButton", command=self._iniciar
                   ).pack(fill="x", pady=(0, 6))
        pie = ttk.Frame(t3, style="Card.TFrame")
        pie.pack(fill="x", pady=(0, 10))
        tk.Label(pie, textvariable=self.estado, bg=TARJETA, fg=TEXTO_SUAVE, font=("Segoe UI", 9)).pack(side="left")
        tk.Label(pie, text="En la ventana de video, presiona Q para terminar", bg=TARJETA, fg=TEXTO_SUAVE,
                 font=("Segoe UI", 9)).pack(side="right")

        tk.Label(t3, text="ÚLTIMO RESULTADO", bg=TARJETA, fg=TEXTO_SUAVE, font=("Segoe UI", 9, "bold")
                 ).pack(anchor="w", pady=(4, 2))
        grilla = ttk.Frame(t3, style="Card.TFrame")
        grilla.pack(fill="x")
        columnas = [("total", "Contadas", TEXTO), ("good", "Buena", VERDE), ("detalle", "Con detalle", NARANJA),
                    ("no_pasa", "No pasa", ROJO), ("pudricion", "…por pudrición", ROJO),
                    ("ids", "IDs vistos", TEXTO_SUAVE)]
        for i, (clave, nombre, color) in enumerate(columnas):
            col = ttk.Frame(grilla, style="Card.TFrame")
            col.grid(row=0, column=i, padx=8, sticky="w")
            tk.Label(col, textvariable=self.resultado[clave], bg=TARJETA, fg=color,
                     font=("Segoe UI", 20, "bold")).pack(anchor="w")
            tk.Label(col, text=nombre, bg=TARJETA, fg=TEXTO_SUAVE, font=("Segoe UI", 9)).pack(anchor="w")
            grilla.columnconfigure(i, weight=1)

    def _slider(self, padre, texto: str, variable: tk.IntVar, minimo: int, maximo: int, ayuda: str) -> None:
        fila = ttk.Frame(padre, style="Card.TFrame")
        fila.pack(fill="x", pady=4)
        etiqueta = ttk.Label(fila, text=texto + "  ⓘ", width=36)
        etiqueta.pack(side="left")
        Tooltip(etiqueta, ayuda)
        valor = tk.Label(fila, text=f"{variable.get()} %", bg=TARJETA, fg=AZUL, width=5,
                         font=("Segoe UI", 10, "bold"))
        valor.pack(side="right")
        escala = ttk.Scale(fila, from_=minimo, to=maximo, variable=variable, orient="horizontal",
                           command=lambda v: (variable.set(int(float(v))), valor.config(text=f"{int(float(v))} %")))
        escala.pack(side="left", fill="x", expand=True, padx=8)
        Tooltip(escala, ayuda)

    # ---------- estado visual ----------
    def _actualizar_aviso(self) -> None:
        fuente = self.fuente.get()
        ruta = {"video": self.ruta_video.get(), "foto": self.ruta_foto.get()}.get(fuente)
        if fuente == "camara":
            try:
                n = self.indice_cam.get()
            except tk.TclError:   # spinbox vacío mientras se escribe
                n = "?"
            texto, color = f"✓ Se usará la cámara n.º {n}", VERDE
        elif not ruta:
            texto, color = f"⚠ Falta elegir un archivo de {fuente}", NARANJA
        elif not Path(ruta).exists():
            texto, color = f"⚠ El archivo de {fuente} ya no existe", ROJO
        else:
            texto, color = f"✓ {fuente.capitalize()} listo: {Path(ruta).name}", VERDE
        self.aviso_fuente.set(texto)
        self.lbl_aviso.config(fg=color)

    def _actualizar_escala(self) -> None:
        self.texto_escala.set(f"{self.cfg.px_por_mm:.2f} px/mm")

    def _conf(self) -> float:
        return (100 - self.sensibilidad.get()) / 100

    # ---------- acciones ----------
    def _elegir_video(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Elegir video", filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv *.wmv"), ("Todos", "*.*")])
        if ruta:
            self.ruta_video.set(ruta)
            self.fuente.set("video")

    def _elegir_foto(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Elegir foto", filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp"), ("Todos", "*.*")])
        if ruta:
            self.ruta_foto.set(ruta)
            self.fuente.set("foto")

    def _abrir_camara(self, indice: int):
        # En Windows DirectShow abre más rápido y evita errores con algunas cámaras
        cap = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(indice)
        return cap

    def _probar_camara(self) -> None:
        self.fuente.set("camara")
        cap = self._abrir_camara(self.indice_cam.get())
        ok = cap.isOpened() and cap.read()[0]
        cap.release()
        if ok:
            messagebox.showinfo("Cámara", f"La cámara {self.indice_cam.get()} funciona correctamente.")
        else:
            messagebox.showwarning("Cámara", f"No se pudo abrir la cámara {self.indice_cam.get()}.\n"
                                   "Revisa que esté conectada y que otra aplicación no la esté usando.")

    def _validar_fuente(self):
        """Devuelve la fuente lista para usar o None (y avisa al usuario qué falta)."""
        fuente = self.fuente.get()
        if fuente == "camara":
            return self.indice_cam.get()
        ruta = self.ruta_video.get() if fuente == "video" else self.ruta_foto.get()
        if not ruta or not Path(ruta).exists():
            messagebox.showwarning("Falta el archivo",
                                   f"Elige un archivo de {fuente} en «1 · Fuente de entrada» antes de continuar.")
            return None
        return ruta

    def _leer_frame(self):
        """Un frame de la fuente actual (foto, primer frame del video o captura de la cámara)."""
        fuente = self._validar_fuente()
        if fuente is None:
            return None
        if self.fuente.get() == "foto":
            datos = np.fromfile(fuente, dtype=np.uint8)
            return cv2.imdecode(datos, cv2.IMREAD_COLOR) if datos.size else None
        cap = self._abrir_camara(fuente) if self.fuente.get() == "camara" else cv2.VideoCapture(fuente)
        frame = None
        for _ in range(5 if self.fuente.get() == "camara" else 1):   # la cámara tarda en exponer bien
            ok, f = cap.read()
            if ok:
                frame = f
        cap.release()
        return frame

    def _dialogo_calibrar(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Calibrar cámara / escala")
        dlg.configure(bg=TARJETA)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        diam_mm = tk.StringVar(value=f"{DIAMETRO_REFERENCIA_MM:g}")
        diam_px = tk.StringVar(value="")
        resultado = tk.StringVar(value="Ingresa ambos valores para calcular la escala")

        marco = ttk.Frame(dlg, style="Card.TFrame")
        marco.pack(fill="both", padx=20, pady=16)
        tk.Label(marco, text="Calibración de escala (píxeles → milímetros)", bg=TARJETA, fg=TEXTO,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(marco, justify="left", bg=TARJETA, fg=TEXTO_SUAVE, font=("Segoe UI", 9), wraplength=440,
                 text="1. Mide con pie de metro una manzana de muestra y escribe su diámetro.\n"
                      "2. Ponla sola frente a la cámara, a la misma distancia que la cinta.\n"
                      "3. Pulsa «Medir en la fuente actual» (usa la fuente elegida en el bloque 1) "
                      "o escribe el diámetro en píxeles a mano.\n4. Guarda."
                 ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 12))

        ttk.Label(marco, text="Diámetro real de la manzana (mm)").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(marco, textvariable=diam_mm, width=10).grid(row=2, column=1, sticky="w", padx=8)
        ttk.Label(marco, text="Diámetro en la imagen (px)").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(marco, textvariable=diam_px, width=10).grid(row=3, column=1, sticky="w", padx=8)

        def medir() -> None:
            if not MODELO.exists():
                messagebox.showerror("Falta el modelo", f"No se encontró el modelo entrenado:\n{MODELO}", parent=dlg)
                return
            frame = self._leer_frame()
            if frame is None:
                messagebox.showwarning("Sin imagen", "No se pudo leer una imagen de la fuente elegida.", parent=dlg)
                return
            dlg.config(cursor="watch")
            dlg.update_idletasks()
            try:
                ref = medir_referencia(frame, str(MODELO), self.cfg, conf=self._conf())
            finally:
                dlg.config(cursor="")
            if ref is None:
                messagebox.showwarning("Sin manzana", "No se detectó ninguna manzana en la imagen.\n"
                                       "Prueba subiendo la sensibilidad o mejorando la luz.", parent=dlg)
                return
            diam_px.set(f"{ref['diametro_px']:.1f}")
            x1, y1, x2, y2 = ref["caja"]
            vista = frame.copy()
            cv2.rectangle(vista, (x1, y1), (x2, y2), (255, 160, 50), 3)
            cv2.putText(vista, f"{ref['diametro_px']:.0f} px", (x1, max(y1 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 160, 50), 2)
            h, w = vista.shape[:2]
            k = min(1.0, 1000 / w, 650 / h)
            if k < 1:
                vista = cv2.resize(vista, (int(w * k), int(h * k)))
            cv2.imshow("Manzana medida (cualquier tecla para cerrar)", vista)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        ttk.Button(marco, text="Medir en la fuente actual", command=medir).grid(row=3, column=2, sticky="w")

        def calcular(*_):
            try:
                valor = calibrar_escala(float(diam_px.get().replace(",", ".")),
                                        float(diam_mm.get().replace(",", ".")))
            except ValueError:
                resultado.set("Ingresa ambos valores (números mayores que 0)")
                return None
            resultado.set(f"Nueva escala: {valor:.3f} px/mm   (actual: {self.cfg.px_por_mm:.3f})")
            return valor

        diam_mm.trace_add("write", calcular)
        diam_px.trace_add("write", calcular)
        tk.Label(marco, textvariable=resultado, bg=TARJETA, fg=AZUL, font=("Segoe UI", 10, "bold")
                 ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 8))

        def guardar() -> None:
            valor = calcular()
            if valor is None:
                messagebox.showwarning("Datos incompletos", "Faltan el diámetro real o el diámetro en píxeles.",
                                       parent=dlg)
                return
            guardar_px_por_mm(valor)
            self.cfg = cargar_config()
            self._actualizar_escala()
            dlg.destroy()
            messagebox.showinfo("Calibración guardada", f"px_por_mm = {valor:.4f} guardado en config.yaml.")

        botones = ttk.Frame(marco, style="Card.TFrame")
        botones.grid(row=5, column=0, columnspan=3, sticky="e")
        ttk.Button(botones, text="Cancelar", command=dlg.destroy).pack(side="right")
        ttk.Button(botones, text="Guardar en config.yaml", style="Calibrar.TButton", command=guardar
                   ).pack(side="right", padx=8)

    def _iniciar(self) -> None:
        if not MODELO.exists():
            messagebox.showerror("Falta el modelo", f"No se encontró el modelo entrenado:\n{MODELO}")
            return
        fuente = self._validar_fuente()
        if fuente is None:
            return
        if self.fuente.get() == "foto":
            self._contar_foto(fuente)
            return

        guardar = None
        if self.guardar.get():
            CARPETA_REPORTES.mkdir(exist_ok=True)
            guardar = str(CARPETA_REPORTES / "conteo_con_panel.mp4")

        self.estado.set("Procesando… (ventana de video abierta)")
        self.root.withdraw()
        try:
            r = procesar(fuente, str(MODELO), self.cfg, mostrar=True, lote=self.lote.get() or "Lote 1",
                         linea=self.linea.get() / 100, guardar=guardar, conf=self._conf())
        except Exception as e:  # noqa: BLE001 - se muestra al usuario
            self.root.deiconify()
            self.estado.set("Error al procesar")
            messagebox.showerror("Error", str(e))
            return
        self.root.deiconify()
        self._mostrar_resultado(r)
        self.estado.set("Terminado. Puedes iniciar otro análisis.")

    def _contar_foto(self, ruta: str) -> None:
        guardar = None
        if self.guardar.get():
            CARPETA_REPORTES.mkdir(exist_ok=True)
            guardar = str(CARPETA_REPORTES / "foto_contada.jpg")
        self.estado.set("Analizando foto…")
        self.root.update_idletasks()
        try:
            r = procesar_imagen(ruta, str(MODELO), self.cfg, mostrar=True, lote=self.lote.get() or "Foto",
                                guardar=guardar, conf=self._conf())
        except Exception as e:  # noqa: BLE001 - se muestra al usuario
            self.estado.set("Error al procesar")
            messagebox.showerror("Error", str(e))
            return
        self._mostrar_resultado(r)
        self.estado.set(f"Foto analizada: {r['contadas']} manzanas.")

    def _mostrar_resultado(self, r: dict) -> None:
        cat = r["categorias"]
        self.resultado["total"].set(str(r["contadas"]))
        self.resultado["good"].set(str(cat.get("good", 0)))
        self.resultado["detalle"].set(str(cat.get("detalle", 0)))
        self.resultado["no_pasa"].set(str(cat.get("no_pasa", 0)))
        self.resultado["pudricion"].set(str(r.get("pudricion", 0)))
        self.resultado["ids"].set(str(r["ids_vistos"]))

    def ejecutar(self) -> None:
        self.root.mainloop()


def main() -> None:
    App().ejecutar()


if __name__ == "__main__":
    main()
