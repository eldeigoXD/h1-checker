@echo off
TITLE Abrir Google Chrome con Sesion QA (Port 9222)
echo ========================================================
echo   ABRIENDO GOOGLE CHROME CON PUERTO DEPURACION (9222)
echo ========================================================
echo.
echo Cerrando instancias previas de Chrome para habilitar depuracion...
taskkill /F /IM chrome.exe 2>nul
timeout /t 2 /nobreak >nul

set "DEBUG_DIR=%LOCALAPPDATA%\ChromeDebug"
if not exist "%DEBUG_DIR%" mkdir "%DEBUG_DIR%"

echo Iniciando Google Chrome con puerto 9222 activo...

:: 1. Intentar via PATH
where chrome.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Iniciando Chrome desde PATH...
    start "" "chrome.exe" --remote-debugging-port=9222 --user-data-dir="%DEBUG_DIR%"
    goto ok
)

:: 2. Rutas estandar de instalacion de Google Chrome
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    echo [OK] Iniciando Chrome desde Program Files...
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%DEBUG_DIR%"
    goto ok
)

if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    echo [OK] Iniciando Chrome desde Program Files (x86)...
    start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%DEBUG_DIR%"
    goto ok
)

if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    echo [OK] Iniciando Chrome desde LocalAppData...
    start "" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%DEBUG_DIR%"
    goto ok
)

echo [AVISO] No se encontro ruta automatica. Intentando comando directo...
start "" "chrome.exe" --remote-debugging-port=9222 --user-data-dir="%DEBUG_DIR%"

:ok
echo.
echo ========================================================
echo Listo! Google Chrome iniciado con puerto 9222 activo.
echo.
echo IMPORTANTE (Solo la primera vez si te pide login):
echo   Abre e inicia sesion en tus 2 pestanas:
echo   1. Smartsheet (Report to start QA V2)
echo   2. Dynamics 365 (Cola / Deliverables)
echo.
echo Luego ejecuta:
echo   - asignar_mis_casos.bat (para tomar casos en blanco)
echo   - start_batch_qa.bat    (para auditar tu lote)
echo ========================================================
timeout /t 6
