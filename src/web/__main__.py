"""Inicia la plataforma web.

    python -m src.web                     # http://127.0.0.1:5000 (crea datos de demo la primera vez)
    python -m src.web --reiniciar-demo    # borra la base y vuelve a crear los datos de demo
    python -m src.web --host 0.0.0.0      # accesible desde otros equipos de la red (p. ej. un celular)
"""
import argparse
import os
import threading
import webbrowser

from src.web.analisis import MODELO, analizar_con_yolo
from src.web.app import create_app
from src.web.demo import CLAVE_DEMO, CUENTAS_DEMO, reiniciar, sembrar


def main() -> None:
    p = argparse.ArgumentParser(description="Plataforma web AppleVision Chile")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--reiniciar-demo", action="store_true", help="Borra los datos y crea la demo de nuevo")
    p.add_argument("--sin-demo", action="store_true", help="No crear datos ni accesos de demostración")
    p.add_argument("--abrir", action="store_true", help="Abrir el navegador cuando el servidor esté listo")
    args = p.parse_args()
    if args.sin_demo:
        os.environ["APPLEVISION_DEMO"] = "0"

    if args.reiniciar_demo:
        app = create_app()
        reiniciar(app.config["DATOS"])
    app = create_app()

    if app.config["DEMO"]:
        print("Preparando datos de demostración (solo la primera vez; analiza fotos reales con el modelo)...")
        if not MODELO.exists():
            print(f"  Aviso: falta {MODELO}; los lotes de demo se crean sin análisis.")
        creados = sembrar(app.config["DB_RUTA"], app.config["DATOS"],
                          analizador=analizar_con_yolo if MODELO.exists() else None)
        print("  Datos de demo creados." if creados else "  Ya existían datos; se mantienen.")

    pendientes = app.extensions["cola"].reanudar_pendientes()
    if pendientes:
        print(f"Reanudando {pendientes} análisis pendientes...")

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}"
    print("\n  AppleVision Chile - plataforma web")
    print(f"  Abre {url} en el navegador (Ctrl+C para detener)")
    if app.config["DEMO"]:
        print(f"  Cuentas de demo (contraseña: {CLAVE_DEMO}):")
        for rol, c in CUENTAS_DEMO.items():
            print(f"    {rol:<12} {c['email']}")
    print()
    if args.abrir:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
