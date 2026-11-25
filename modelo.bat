@echo off
title AppleVision Chile - Modelo
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"

REM ---- Verificar entorno virtual ----
if not exist "%PY%" (
    echo.
    echo [ERROR] El entorno virtual no existe.
    echo         Ejecuta "instalar.bat" primero.
    echo.
    pause
    exit /b 1
)

REM ---- Aviso si falta el modelo ----
set "HAYMODELO=1"
if not exist "models\best.pt" set "HAYMODELO=0"

:menu
cls
echo.
echo  ==============================================
echo   AppleVision Chile - Modelo
echo  ==============================================
echo.
if "%HAYMODELO%"=="1" (
    echo   Modelo: models\best.pt  [OK]
) else (
    echo   Modelo: FALTA models\best.pt
    echo   Usa la opcion 5 si ya entrenaste, o la 3 para entrenar.
)
echo.
echo   1) Ejecutar la app de escritorio
echo   2) Ejecutar la plataforma web
echo   3) Reentrenar el modelo - receta base       (unos 40 min en CPU)
echo   4) Reentrenar el modelo - receta mejorada   (varias horas en CPU)
echo   5) Instalar un modelo ya entrenado como models\best.pt
echo   6) Salir
echo.
set "OPCION="
set /p "OPCION=Elige una opcion (1-6): "

if "%OPCION%"=="1" goto app
if "%OPCION%"=="2" goto web
if "%OPCION%"=="3" goto entrenar_base
if "%OPCION%"=="4" goto entrenar_mejorado
if "%OPCION%"=="5" goto instalar
if "%OPCION%"=="6" exit /b 0
goto menu

:app
if "%HAYMODELO%"=="0" goto sin_modelo
"%PY%" -m src.app
if errorlevel 1 pause
goto menu

:web
if "%HAYMODELO%"=="0" (
    echo.
    echo [AVISO] Sin models\best.pt la web abre, pero los analisis fallan.
    pause
)
"%PY%" -m src.web --abrir
if errorlevel 1 pause
goto menu

:entrenar_base
set "ARGS_ENTRENO="
goto entrenar

:entrenar_mejorado
set "ARGS_ENTRENO=--mejorado"
goto entrenar

:entrenar
echo.
if not exist "data\02_processed\dataset_2clases\data.yaml" (
    echo Preparando el dataset de 2 clases...
    "%PY%" scripts\preparar_dataset_2clases.py
    if errorlevel 1 (
        echo [ERROR] No se pudo preparar el dataset.
        pause
        goto menu
    )
)
echo Entrenando. Puedes dejar esta ventana abierta; el progreso se ve abajo.
echo Los pesos quedan en runs\detect\...\weights\best.pt
echo.
"%PY%" scripts\entrenar_2clases.py %ARGS_ENTRENO%
if errorlevel 1 (
    echo.
    echo [ERROR] El entrenamiento termino con un error.
    pause
    goto menu
)
echo.
echo Entrenamiento terminado. Ahora instala el modelo para usarlo:
goto instalar

:instalar
echo.
"%PY%" scripts\instalar_modelo.py
if exist "models\best.pt" set "HAYMODELO=1"
echo.
pause
goto menu

:sin_modelo
echo.
echo [AVISO] Falta models\best.pt: la app no puede analizar sin el modelo.
echo         Instala uno entrenado (opcion 5) o reentrena (opcion 3).
echo.
pause
goto menu
