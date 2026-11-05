@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Instale Python 3.10 ou superior com o Python Launcher antes de continuar.
  exit /b 1
)
py -3 -c "import sys; assert sys.version_info >= (3,10), 'Use Python 3.10 ou superior'"
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 exit /b 1
echo Instalacao concluida. Execute iniciar.cmd. Dados permanecem nesta pasta.
