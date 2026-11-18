@echo off
title AppleVision Chile - Instalacion
cd /d "%~dp0"

echo.
echo  ==============================================
echo   AppleVision Chile - Instalacion
echo  ==============================================
echo.

REM ---- Verificar Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo   Descarga Python 3.9 o superior desde:
    echo   https://www.python.org/downloads/
    echo.
    echo   Al instalar, marca la opcion "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% encontrado.

REM ---- Crear entorno virtual ----
if exist ".venv\Scripts\python.exe" (
    echo [OK] Entorno virtual ya existe. Actualizando dependencias...
) else (
    echo.
    echo Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado.
)

REM ---- Actualizar pip ----
echo.
echo Actualizando pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

REM ---- Instalar dependencias ----
echo.
echo Instalando dependencias (puede tardar varios minutos)...
echo.
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    echo         Revisa que tengas conexion a internet.
    pause
    exit /b 1
)

REM ---- Crear .env si no existe ----
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo.
        echo [OK] Archivo .env creado desde .env.example
        echo      Si vas a usar Roboflow o AWS S3, abre .env y agrega tus claves.
    )
)

REM ---- Verificar modelo ----
echo.
if exist "models\best.pt" (
    echo [OK] Modelo entrenado encontrado en models\best.pt
) else (
    echo [AVISO] No se encontro el modelo en models\best.pt
    echo         El detector no funcionara sin el modelo.
    echo         Entrena el modelo con YOLO o coloca best.pt en la carpeta models\.
)

echo.
echo  ==============================================
echo   Instalacion completada.
echo   Ejecuta "ejecutar.bat" para iniciar la app.
echo  ==============================================
echo.
pause
