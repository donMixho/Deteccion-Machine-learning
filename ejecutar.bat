@echo off
title AppleVision Chile
cd /d "%~dp0"

REM ---- Verificar entorno virtual ----
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] El entorno virtual no existe.
    echo         Ejecuta "instalar.bat" primero para instalar las dependencias.
    echo.
    pause
    exit /b 1
)

REM ---- Verificar modelo ----
if not exist "models\best.pt" (
    echo.
    echo [AVISO] No se encontro el modelo entrenado en models\best.pt
    echo         El detector no podra analizar video ni fotos sin el modelo.
    echo.
    pause
)

REM ---- Iniciar aplicacion ----
echo Iniciando AppleVision Chile...
".venv\Scripts\python.exe" -m src.app

if errorlevel 1 (
    echo.
    echo [ERROR] La aplicacion cerro con un error.
    echo         Si es la primera vez, prueba correr "instalar.bat" de nuevo.
    pause
)
