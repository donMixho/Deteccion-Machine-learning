@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m src.web --abrir
if errorlevel 1 pause
