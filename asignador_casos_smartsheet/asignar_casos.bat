@echo off
TITLE Asignador Automatico de Casos QA - Smartsheet
echo ========================================================
echo     ASIGNADOR AUTOMATICO DE CASOS - SMARTSHEET
echo ========================================================
echo.
echo Este script busca casos en blanco de la fecha completada que elijas
echo y los asigna con la fecha de HOY, tu nombre y estado 'In progress'.
echo.

if exist ".\venv\Scripts\activate.bat" (
    echo [INFO] Activando entorno virtual local...
    call .\venv\Scripts\activate.bat
    python assign_cases_runner.py %*
    goto done
)

where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Ejecutando con Python del sistema...
    python assign_cases_runner.py %*
    goto done
)

echo [ERROR] No se encontro Python instalado en el sistema.
echo Por favor ejecuta 'instalar_dependencias.bat' o instala Python 3.
pause
exit /b

:done
echo.
echo ========================================================
echo   Ejecucion finalizada.
echo ========================================================
pause
