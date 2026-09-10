@echo off
TITLE QA Web Tool - Backend Server
echo ==========================================
echo    INICIANDO QA WEB TOOL (PRO)
echo ==========================================
echo.

:: 0. Liberar puerto 5000 si hay procesos previos colgados
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    echo [INFO] Liberando puerto 5000 ocupado por proceso PID %%a...
    taskkill /f /pid %%a >nul 2>&1
)

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
echo 2. Abriendo QA Tool en el navegador (http://127.0.0.1:5000)...
start http://127.0.0.1:5000

echo.
echo 3. Iniciando servidor Flask en http://127.0.0.1:5000
echo    (Presione Ctrl+C para detener el servidor)
echo.
python app.py
pause


