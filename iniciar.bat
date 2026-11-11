@echo off
setlocal
cd /d "%~dp0"
title Radar Inversor
echo.
echo  ==============================================
echo    RADAR INVERSOR
echo  ==============================================
echo.

set "PY="

rem --- 1) Si ya existe el entorno del programa, se usa directamente
if exist ".venv\Scripts\python.exe" goto arrancar

rem --- 2) Buscar un Python 3.10+ ya instalado
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "PY="%%D\python.exe""
  )
)

rem --- 3) Si no hay Python, instalarlo con winget (gestor oficial de Windows)
if not defined PY (
  echo No tienes Python instalado. Lo instalo ahora; tarda 1-3 minutos.
  echo Si Windows te pide permiso, acepta.
  echo.
  winget --version >nul 2>&1
  if errorlevel 1 goto sin_winget
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
)
if not defined PY goto sin_python

rem --- 4) Crear el entorno del programa e instalar librerias (solo la primera vez)
echo Preparando el programa (solo la primera vez, unos 2-3 minutos)...
%PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto sin_python
set "PRIMERA_VEZ=1"

:arrancar
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo No pude instalar las librerias. Revisa tu conexion a internet y vuelve a abrir este archivo.
  pause
  exit /b 1
)
rem Mantiene al dia la libreria de Yahoo Finance (Yahoo cambia su web a menudo)
".venv\Scripts\python.exe" -m pip install -q -U --disable-pip-version-check yfinance >nul 2>&1
rem Crea el icono del escritorio la primera vez (o si lo borraste)
if not exist ".acceso_creado" (
  call crear_acceso_directo.bat silencioso
  echo creado> ".acceso_creado"
  echo Te he dejado un icono "Radar Inversor" en el escritorio para las proximas veces.
)
echo.
echo Abriendo Radar Inversor en tu navegador... (para cerrarlo, cierra esta ventana)
".venv\Scripts\python.exe" lanzar.py
pause
exit /b 0

:sin_winget
echo No encuentro el instalador de Windows (winget).
:sin_python
echo.
echo Instala Python a mano:
echo   1. Entra en https://www.python.org/downloads/ y pulsa "Download Python 3.12"
echo   2. Al instalar, MARCA la casilla "Add python.exe to PATH"
echo   3. Vuelve a hacer doble clic en iniciar.bat
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1
