@echo off
TITLE Abrir Helium con Sesion QA (Port 9222)
echo ========================================================
echo   ABRIENDO HELIUM / NAVEGADOR CON PUERTO DEPURACION (9222)
echo ========================================================
echo.
echo Cerrando instancias previas para liberar el perfil de sesion...
taskkill /F /IM helium.exe 2>nul
taskkill /F /IM chrome.exe 2>nul
timeout /t 2 /nobreak >nul

echo Iniciando navegador con puerto 9222 activo...

:: Intentar Helium primero, luego Chrome
where helium.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Iniciando Helium...
    start "" "helium.exe" --remote-debugging-port=9222
    goto ok
)

where chrome.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Iniciando Chrome...
    start "" "chrome.exe" --remote-debugging-port=9222
    goto ok
)

:: Rutas habituales si no estan en PATH
if exist "%LOCALAPPDATA%\Helium\Application\helium.exe" (
    start "" "%LOCALAPPDATA%\Helium\Application\helium.exe" --remote-debugging-port=9222
    goto ok
)

if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
    goto ok
)

if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
    goto ok
)

echo No se encontro la ruta automatica. Iniciando via comando predeterminado...
start "" "chrome.exe" --remote-debugging-port=9222

:ok
echo.
echo ========================================================
echo Listo! Navegador iniciado con puerto 9222 activo.
echo.
echo PASO SIGUIENTE:
echo   1. En el navegador que se abrio, abre tu reporte de
echo      Smartsheet: "Report to start QA V2"
echo   2. Luego ejecuta 'asignar_casos.bat' para tomar tus casos.
echo ========================================================
timeout /t 5
