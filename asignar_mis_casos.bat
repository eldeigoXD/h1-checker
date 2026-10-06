@echo off
TITLE Auto Claim Cases - Diego Torrez
echo ========================================================
echo     AUTO-CLAIM CASOS DE SMARTSHEET - DIEGO TORREZ
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

echo [ERROR] No se encontro Python instalado.
pause
exit /b

:done
echo.
echo ========================================================
echo   Ejecucion finalizada.
echo ========================================================
pause
