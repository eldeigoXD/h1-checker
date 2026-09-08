@echo off
TITLE QA Web Tool - Home PC Remote Worker
echo ==========================================
echo    INICIANDO WORKER REMOTO (HOME PC)
echo ==========================================
echo.

if not exist ".\venv\Scripts\activate.bat" (
    echo [INFO] No se encontro el entorno virtual 'venv'. Creando uno nuevo...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual Python.
        pause
        exit /b
    )
    echo [INFO] Instalando dependencias...
    call .\venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
) else (
    echo 1. Activando entorno virtual...
    call .\venv\Scripts\activate.bat
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo activar el entorno virtual.
        pause
        exit /b
    )
)

echo.
echo 2. Conectando con Vercel para escuchar peticiones remotas...
python local_worker.py
pause
