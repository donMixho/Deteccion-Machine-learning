"""Pantalla de inicio (dashboard) de AppleVision Chile.

Permite elegir la fuente (cámara o video del equipo), ajustar lote, línea de conteo
y confianza, e iniciar el conteo en vivo. Al terminar muestra el último resultado.

    python -m src.app
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2

from src.utils.config import RAIZ, cargar_config
from src.vision.detector import procesar, procesar_imagen

MODELO = RAIZ / "models" / "best.pt"
CARPETA_REPORTES = RAIZ / "reports"

# Paleta (coincide con el panel en vivo)
FONDO, TARJETA, BORDE = "#141414", "#1e1e1e", "#333333"
TEXTO, TEXTO_SUAVE = "#eaeaea", "#9a9a9a"
VERDE, NARANJA, ROJO, AZUL = "#2ecc71", "#f59e0b", "#e74c3c", "#3182ce"


class App:
    def __init__(self) -> None:
        self.cfg = cargar_config()
        self.root = tk.Tk()
        self.root.title("AppleVision Chile")
        self.root.configure(bg=FONDO)
        self.root.geometry("720x860")
        self.root.minsize(660, 800)

        self.fuente = tk.StringVar(value="camara")
        self.indice_cam = tk.IntVar(value=0)
        self.ruta_video = tk.StringVar(value="")
        self.ruta_foto = tk.StringVar(value="")
        self.lote = tk.StringVar(value="Lote 1")
        self.linea = tk.IntVar(value=80)
        self.conf = tk.IntVar(value=25)
        self.guardar = tk.BooleanVar(value=False)
        self.estado = tk.StringVar(value="Listo para iniciar")
        self.resultado = {k: tk.StringVar(value="—") for k in ("total", "good", "detalle", "no_pasa", "ids")}

        self._estilos()
        self._construir()

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
        st.configure("Inicio.TButton", font=("Segoe UI", 13, "bold"), padding=12, background=VERDE,
                     foreground="#0b2e1a")
        st.map("Inicio.TButton", background=[("active", "#27ae60")])
        st.configure("TEntry", fieldbackground="#2a2a2a", foreground=TEXTO, bordercolor=BORDE, insertcolor=TEXTO)
        st.configure("TSpinbox", fieldbackground="#2a2a2a", foreground=TEXTO, arrowcolor=TEXTO)
        st.configure("Horizontal.TScale", background=TARJETA, troughcolor="#2a2a2a")

    def _tarjeta(self, padre, titulo: str) -> ttk.Frame:
        marco = tk.Frame(padre, bg=TARJETA, highlightbackground=BORDE, highlightthickness=1)
        marco.pack(fill="x", pady=7)
        tk.Label(marco, text=titulo, bg=TARJETA, fg=TEXTO_SUAVE, font=("Segoe UI", 9, "bold")
                 ).pack(anchor="w", padx=16, pady=(12, 4))
        interior = ttk.Frame(marco, style="Card.TFrame")
        interior.pack(fill="x", padx=16, pady=(0, 14))
        return interior

    def _construir(self) -> None:
        cont = ttk.Frame(self.root)
        cont.pack(fill="both", expand=True, padx=26, pady=18)

        tk.Label(cont, text="AppleVision Chile", bg=FONDO, fg=TEXTO, font=("Segoe UI", 22, "bold")
                 ).pack(anchor="w")
        tk.Label(cont, text="Conteo y clasificación de manzanas en la línea de embalaje", bg=FONDO,
                 fg=TEXTO_SUAVE, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))

        # --- 1. Fuente ---
        t1 = self._tarjeta(cont, "1 · FUENTE DE VIDEO")
        fila_cam = ttk.Frame(t1, style="Card.TFrame")
        fila_cam.pack(fill="x", pady=(0, 8))
        ttk.Radiobutton(fila_cam, text="Cámara conectada", value="camara", variable=self.fuente
                        ).pack(side="left")
        ttk.Button(fila_cam, text="Probar cámara", command=self._probar_camara).pack(side="right")
        ttk.Spinbox(fila_cam, from_=0, to=9, width=4, textvariable=self.indice_cam).pack(side="right", padx=8)
        ttk.Label(fila_cam, text="N.º de cámara", style="Suave.TLabel").pack(side="right")

        fila_vid = ttk.Frame(t1, style="Card.TFrame")
        fila_vid.pack(fill="x")
        ttk.Radiobutton(fila_vid, text="Video del equipo", value="video", variable=self.fuente
                        ).pack(side="left")
        ttk.Button(fila_vid, text="Elegir archivo…", command=self._elegir_video).pack(side="right")
        ttk.Entry(t1, textvariable=self.ruta_video, state="readonly").pack(fill="x", pady=(6, 0))

        fila_foto = ttk.Frame(t1, style="Card.TFrame")
        fila_foto.pack(fill="x", pady=(10, 0))
        ttk.Radiobutton(fila_foto, text="Foto del equipo", value="foto", variable=self.fuente
                        ).pack(side="left")
        ttk.Button(fila_foto, text="Elegir foto…", command=self._elegir_foto).pack(side="right")
        ttk.Entry(t1, textvariable=self.ruta_foto, state="readonly").pack(fill="x", pady=(6, 0))

        # --- 2. Ajustes ---
        t2 = self._tarjeta(cont, "2 · AJUSTES")
        fila = ttk.Frame(t2, style="Card.TFrame")
        fila.pack(fill="x", pady=(0, 8))
        ttk.Label(fila, text="Nombre del lote", width=20).pack(side="left")
        ttk.Entry(fila, textvariable=self.lote).pack(side="left", fill="x", expand=True)

        self._slider(t2, "Línea de conteo (% del ancho)", self.linea, 10, 95)
        self._slider(t2, "Confianza mínima (%)", self.conf, 10, 90)
        ttk.Checkbutton(t2, text="Guardar el video con el panel en la carpeta reports/",
                        variable=self.guardar).pack(anchor="w", pady=(6, 0))

        # --- Resultado ---
        t3 = self._tarjeta(cont, "ÚLTIMO RESULTADO")
        grilla = ttk.Frame(t3, style="Card.TFrame")
        grilla.pack(fill="x")
        for i, (clave, nombre, color) in enumerate([
                ("total", "Contadas", TEXTO), ("good", "Buena", VERDE), ("detalle", "Con detalle", NARANJA),
                ("no_pasa", "No pasa", ROJO), ("ids", "IDs vistos", TEXTO_SUAVE)]):
            col = ttk.Frame(grilla, style="Card.TFrame")
            col.grid(row=0, column=i, padx=10, sticky="w")
            tk.Label(col, textvariable=self.resultado[clave], bg=TARJETA, fg=color,
                     font=("Segoe UI", 20, "bold")).pack(anchor="w")
            tk.Label(col, text=nombre, bg=TARJETA, fg=TEXTO_SUAVE, font=("Segoe UI", 9)).pack(anchor="w")
            grilla.columnconfigure(i, weight=1)

        # --- Acciones ---
        ttk.Button(cont, text="▶  Iniciar conteo", style="Inicio.TButton", command=self._iniciar
                   ).pack(fill="x", pady=(14, 6))
        pie = ttk.Frame(cont)
        pie.pack(fill="x")
        tk.Label(pie, textvariable=self.estado, bg=FONDO, fg=TEXTO_SUAVE, font=("Segoe UI", 9)).pack(side="left")
        tk.Label(pie, text="En la ventana de video, presiona Q para terminar", bg=FONDO, fg=TEXTO_SUAVE,
                 font=("Segoe UI", 9)).pack(side="right")

    def _slider(self, padre, texto: str, variable: tk.IntVar, minimo: int, maximo: int) -> None:
        fila = ttk.Frame(padre, style="Card.TFrame")
        fila.pack(fill="x", pady=4)
        ttk.Label(fila, text=texto, width=28).pack(side="left")
        valor = tk.Label(fila, text=str(variable.get()), bg=TARJETA, fg=AZUL, width=4, font=("Segoe UI", 10, "bold"))
        valor.pack(side="right")
        ttk.Scale(fila, from_=minimo, to=maximo, variable=variable, orient="horizontal",
                  command=lambda v: (variable.set(int(float(v))), valor.config(text=str(int(float(v)))))
                  ).pack(side="left", fill="x", expand=True, padx=8)

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
        cap = self._abrir_camara(self.indice_cam.get())
        ok = cap.isOpened() and cap.read()[0]
        cap.release()
        if ok:
            messagebox.showinfo("Cámara", f"La cámara {self.indice_cam.get()} funciona correctamente.")
        else:
            messagebox.showwarning("Cámara", f"No se pudo abrir la cámara {self.indice_cam.get()}.\n"
                                   "Revisa que esté conectada y que otra aplicación no la esté usando.")

    def _iniciar(self) -> None:
        if not MODELO.exists():
            messagebox.showerror("Falta el modelo", f"No se encontró el modelo entrenado:\n{MODELO}")
            return
        if self.fuente.get() == "foto":
            ruta = self.ruta_foto.get()
            if not ruta or not Path(ruta).exists():
                messagebox.showwarning("Foto", "Elige una foto antes de iniciar.")
                return
            self._contar_foto(ruta)
            return
        if self.fuente.get() == "video":
            ruta = self.ruta_video.get()
            if not ruta or not Path(ruta).exists():
                messagebox.showwarning("Video", "Elige un archivo de video antes de iniciar.")
                return
            fuente = ruta
        else:
            fuente = self.indice_cam.get()

        guardar = None
        if self.guardar.get():
            CARPETA_REPORTES.mkdir(exist_ok=True)
            guardar = str(CARPETA_REPORTES / "conteo_con_panel.mp4")

        self.estado.set("Procesando… (ventana de video abierta)")
        self.root.withdraw()
        try:
            r = procesar(fuente, str(MODELO), self.cfg, mostrar=True, lote=self.lote.get() or "Lote 1",
                         linea=self.linea.get() / 100, guardar=guardar, conf=self.conf.get() / 100)
        except Exception as e:  # noqa: BLE001 - se muestra al usuario
            self.root.deiconify()
            self.estado.set("Error al procesar")
            messagebox.showerror("Error", str(e))
            return
        self.root.deiconify()
        cat = r["categorias"]
        self.resultado["total"].set(str(r["contadas"]))
        self.resultado["good"].set(str(cat.get("good", 0)))
        self.resultado["detalle"].set(str(cat.get("detalle", 0)))
        self.resultado["no_pasa"].set(str(cat.get("no_pasa", 0)))
        self.resultado["ids"].set(str(r["ids_vistos"]))
        self.estado.set("Terminado. Puedes iniciar otro conteo.")

    def _contar_foto(self, ruta: str) -> None:
        guardar = None
        if self.guardar.get():
            CARPETA_REPORTES.mkdir(exist_ok=True)
            guardar = str(CARPETA_REPORTES / "foto_contada.jpg")
        self.estado.set("Analizando foto…")
        self.root.update_idletasks()
        try:
            r = procesar_imagen(ruta, str(MODELO), self.cfg, mostrar=True, lote=self.lote.get() or "Foto",
                                guardar=guardar, conf=self.conf.get() / 100)
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
        self.resultado["ids"].set(str(r["ids_vistos"]))

    def ejecutar(self) -> None:
        self.root.mainloop()


def main() -> None:
    App().ejecutar()


if __name__ == "__main__":
    main()
