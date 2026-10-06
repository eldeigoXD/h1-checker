@echo off
TITLE Instalador de Dependencias - Asignador Smartsheet
echo ========================================================
echo   INSTALANDO LIBRERIAS NECESARIAS PARA PYTHON
echo ========================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se encontro Python en el PATH del sistema.
    echo Asegurate de tener Python instalado y marcar la casilla "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/3] Verificando Python y Pip...
python --version
python -m pip --version
echo.

echo [2/3] Instalando Selenium...
python -m pip install --upgrade pip
python -m pip install selenium
echo.

echo [3/3] Comprobando instalacion...
python -c "import selenium; print('   [OK] Selenium version:', selenium.__version__)"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   ¡TODO LISTO! Todas las dependencias estan instaladas.
    echo ========================================================
) else (
    echo.
    echo [ERROR] Ocurrio un error al instalar la libreria Selenium.
)

pause
