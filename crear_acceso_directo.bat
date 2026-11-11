@echo off
rem Crea un acceso directo "Radar Inversor" en el escritorio con su icono.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$escritorio = [Environment]::GetFolderPath('Desktop');" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $escritorio 'Radar Inversor.lnk'));" ^
  "$s.TargetPath = (Join-Path (Get-Location) 'iniciar.bat');" ^
  "$s.WorkingDirectory = (Get-Location).Path;" ^
  "$s.IconLocation = (Join-Path (Get-Location) 'radar.ico');" ^
  "$s.Description = 'Radar Inversor';" ^
  "$s.Save()"
if "%~1"=="silencioso" exit /b 0
echo.
echo Listo: tienes "Radar Inversor" en el escritorio. A partir de ahora abre el programa desde ahi.
pause
