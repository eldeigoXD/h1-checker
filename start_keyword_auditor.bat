@echo off
TITLE DDC Keyword & Metadata Auditor - Port 5050
echo ====================================================
echo    INICIANDO DDC KEYWORD & METADATA AUDITOR
echo ====================================================
echo.

:: Liberar puerto 5050 si esta ocupado
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5050 ^| findstr LISTENING') do (
    echo [INFO] Liberando puerto 5050 ocupado por PID %%a...
    taskkill /f /pid %%a >nul 2>&1
)

echo 1. Activando entorno virtual...
if exist ".\venv\Scripts\activate.bat" (
    call .\venv\Scripts\activate.bat
) else (
    echo [ADVERTENCIA] No se encontro venv local, usando Python global...
)

echo.
echo 2. Abriendo Keyword Auditor en el navegador (http://127.0.0.1:5050)...
timeout /t 2 /nobreak >nul
start http://127.0.0.1:5050

echo.
echo 3. Iniciando servidor en http://127.0.0.1:5050
echo    (Presione Ctrl+C para detener el servidor)
echo.
python ddc_keyword_auditor\app.py
pause
