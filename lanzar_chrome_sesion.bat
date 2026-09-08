@echo off
TITLE Abrir Chrome con Sesion QA (Port 9222)
echo ========================================================
echo   ABRIENDO CHROME CON PUERTO DE DEPURACION (9222)
echo ========================================================
echo.
echo Cerrando instancias previas de Chrome para liberar el perfil...
taskkill /F /IM chrome.exe 2>nul
timeout /t 2 /nobreak >nul

echo Iniciando Chrome con tu perfil y puerto 9222 activo...
start "" "chrome.exe" --remote-debugging-port=9222

echo.
echo Listo! Ahora el script de QA se conectara directamente
echo a este Chrome abierto sin pedir credenciales ni abrir ventanas secundarias.
echo.
timeout /t 5
