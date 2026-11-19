@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo [English Lens] No se encontro .venv. Ejecuta primero: py -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "src\main.py"
